"""转写后处理：平滑误判的说话人、把碎片合并成完整的句子。

FunASR 按标点切分句子，远场录音（讲座、会议室）里经常切成一两秒的碎片，
说话人模型在这么短的片段上很不稳定，会在一句话中间来回切换。
"""
from __future__ import annotations

import logging
import re
from dataclasses import replace
from typing import Callable, Optional

from .base import Segment

log = logging.getLogger(__name__)

SENTENCE_END = "。？！?!…"
_PUNCT = re.compile(r"[，。？！、；：,.?!;:…]")
_WS = re.compile(r"\s+")
_SENTENCE = re.compile(r".+?(?:[。？！?!…]+|$)")

# 说话人平滑：被同一个人前后包夹、且发生在对方话没说完时的短片段，视为误判。
# 阈值故意取得保守：漏掉一些误判，好过把真人的一句话（比如「你帮我订一下机票」）归错人。
# 单人录音（讲座）请在上传时把说话人数设为 1，比靠规则平滑可靠得多。
SMOOTH_MAX_MS = 2000
# 碎片合并：同一人、间隔很短、上一段没说完（或太短）时接上
MERGE_MAX_GAP_MS = 1000
MERGE_MIN_MS = 1500
MERGE_MAX_MS = 25000
MERGE_MAX_CHARS = 100


def _ends_sentence(text: str) -> bool:
    return bool(text) and text.rstrip()[-1] in SENTENCE_END


def smooth_speakers(segments: list[Segment]) -> list[Segment]:
    """A A [B] A → A A A，仅当 [B] 很短、并且插在 A 一句话的中间。

    「插在中间」是区分误判和真实插话的关键：真实的短回应（「好的」「你没转吧？」）
    通常出现在对方说完一句之后，而误判常常把一句话从逗号处劈开。
    """
    segs = list(segments)
    changed = True
    while changed:
        changed = False
        # 按说话人分成连续的段落
        runs: list[tuple[int, int]] = []
        start = 0
        for i in range(1, len(segs) + 1):
            if i == len(segs) or segs[i].speaker != segs[start].speaker:
                runs.append((start, i))
                start = i
        for k in range(1, len(runs) - 1):
            (ps, pe), (rs, re_), (ns, _) = runs[k - 1], runs[k], runs[k + 1]
            outer = segs[ps].speaker
            if segs[ns].speaker != outer:
                continue
            duration = segs[re_ - 1].end_ms - segs[rs].start_ms
            if duration < SMOOTH_MAX_MS and not _ends_sentence(segs[pe - 1].text):
                for i in range(rs, re_):
                    segs[i] = replace(segs[i], speaker=outer)
                changed = True
                break  # 段落划分变了，重新来过
    return segs


def merge_fragments(segments: list[Segment]) -> list[Segment]:
    merged: list[Segment] = []
    for seg in segments:
        if merged:
            cur = merged[-1]
            if (
                seg.speaker == cur.speaker
                and seg.start_ms - cur.end_ms <= MERGE_MAX_GAP_MS
                and (not _ends_sentence(cur.text) or cur.end_ms - cur.start_ms < MERGE_MIN_MS)
                and seg.end_ms - cur.start_ms <= MERGE_MAX_MS
                and len(cur.text) + len(seg.text) <= MERGE_MAX_CHARS
            ):
                merged[-1] = replace(cur, end_ms=seg.end_ms, text=cur.text + seg.text, emotion=cur.emotion or seg.emotion)
                continue
        merged.append(seg)
    return merged


def _speaker_runs(segments: list[Segment]) -> list[list[Segment]]:
    """同一个人连续说的、中间没有长停顿的片段归为一组。"""
    runs: list[list[Segment]] = []
    for seg in segments:
        if runs and seg.speaker == runs[-1][-1].speaker and seg.start_ms - runs[-1][-1].end_ms <= MERGE_MAX_GAP_MS:
            runs[-1].append(seg)
        else:
            runs.append([seg])
    return runs


def _split_long(sentence: str) -> list[str]:
    """超长的句子在逗号处切开，避免一段转写占满屏幕。"""
    parts: list[str] = []
    while len(sentence) > MERGE_MAX_CHARS:
        cut = max(sentence.rfind(c, 0, MERGE_MAX_CHARS) for c in "，、；,;")
        cut = cut + 1 if cut > 0 else MERGE_MAX_CHARS
        parts.append(sentence[:cut])
        sentence = sentence[cut:]
    return parts + [sentence] if sentence else parts


def _join(parts) -> str:
    """拼接片段：只在英文/数字之间补空格，中文直接相连。"""
    out = ""
    for p in parts:
        if out and p and out[-1].isascii() and out[-1].isalnum() and p[0].isascii() and p[0].isalnum():
            out += " "
        out += p
    return out


def _plain(text: str) -> str:
    """对齐用的纯文字：去标点和空白、统一大小写（标点模型会改英文的空格和大小写）。"""
    return _WS.sub("", _PUNCT.sub("", text)).casefold()


def resegment(segments: list[Segment], punctuate: Callable[[list[str]], list[str]]) -> list[Segment]:
    """去掉原标点，对每个人连续的一整段话重新打标点，再按新标点切句。

    FunASR 的分句标点经常错开一个字（「就是其。实他」），在碎片上合并只能将错就错。
    整段重打标点后句子边界才是对的；每个字的时间按它在原片段里的位置线性推算。
    punctuate 一次接收所有段落，批量调用模型比逐段调用快一个数量级。
    """
    runs = _speaker_runs(segments)
    texts, timelines = [], []
    for run in runs:
        times = []  # 每个对齐字符的 (开始, 结束) 时间
        for seg in run:
            n = len(_plain(seg.text))
            span = max(seg.end_ms - seg.start_ms, 1)
            times += [(seg.start_ms + span * k // n, seg.start_ms + span * (k + 1) // n) for k in range(n)]
        texts.append(_join(_PUNCT.sub("", seg.text).strip() for seg in run))
        timelines.append(times)

    todo = [i for i, t in enumerate(texts) if _plain(t)]
    results = dict(zip(todo, punctuate([texts[i] for i in todo]))) if todo else {}

    out: list[Segment] = []
    for i, run in enumerate(runs):
        if i not in results:
            continue
        punctuated, times = results[i], timelines[i]
        if _plain(punctuated) != _plain(texts[i]):
            # 标点模型改动了文字本身，无法对齐时间，退回到碎片合并
            log.warning("重打标点后文字不一致，该段落退回碎片合并")
            out += merge_fragments(run)
            continue

        pos = 0  # 在 times 中的位置
        for sentence in (s for m in _SENTENCE.finditer(punctuated) for s in _split_long(m.group())):
            n = len(_plain(sentence))
            if n == 0:
                if out and sentence.strip():  # 句首多出来的孤立标点，接到上一句
                    out[-1] = replace(out[-1], text=out[-1].text + sentence.strip())
                continue
            out.append(Segment(times[pos][0], times[pos + n - 1][1], run[0].speaker, sentence.strip(),
                               next((s.emotion for s in run if s.emotion), None)))
            pos += n
    return out


def postprocess(
    segments: list[Segment],
    punctuate: Optional[Callable[[list[str]], list[str]]] = None,
    num_speakers: Optional[int] = None,
) -> list[Segment]:
    if num_speakers == 1:
        segments = [replace(s, speaker="S1") for s in segments]
    else:
        segments = smooth_speakers(segments)
    if punctuate is None:
        return merge_fragments(segments)
    return resegment(segments, punctuate)
