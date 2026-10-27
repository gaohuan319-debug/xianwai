"""演示引擎：不识别真实音频，返回一段固定对话。

用来在不下载模型的情况下体验完整流程（分析器、待办、说话人标注）。
对话里同时埋了待办和一段典型的电诈话术，方便看分析效果。
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from .base import Segment

_DEMO = [
    ("S1", "喂，妈，我刚下班。"),
    ("S2", "哎，今天下午有个自称银行客服的人给我打电话。"),
    ("S2", "说我的账户涉嫌洗钱，要我把钱转到一个安全账户配合调查。"),
    ("S1", "你没转吧？"),
    ("S2", "还没有，他说这事要保密，不能跟家里人说，让我今天晚上之前办好。"),
    ("S1", "这是诈骗，千万别转，也别告诉他验证码。"),
    ("S1", "我明天上午陪你去一趟银行柜台问清楚。"),
    ("S2", "好，那你周六记得回来吃饭，顺便帮我把打印机修一下。"),
    ("S1", "行，我周六中午到。"),
]


class MockEngine:
    needs_wav = False

    def transcribe(self, audio_path: Path, num_speakers: Optional[int] = None) -> list[Segment]:
        segments, t = [], 0
        for speaker, text in _DEMO:
            dur = 250 * len(text)
            segments.append(Segment(start_ms=t, end_ms=t + dur, speaker=speaker, text=text))
            t += dur + 400
        return segments
