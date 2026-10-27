from app.asr.base import Segment
from app.asr.mock_engine import MockEngine
from app.asr.postprocess import merge_fragments, postprocess, resegment, smooth_speakers


def seg(start, end, spk, text):
    return Segment(start, end, spk, text)


def test_smooth_relabels_mid_sentence_flip():
    segs = [seg(0, 2000, "S1", "但是这个孩子，"), seg(2000, 3000, "S2", "他也有他的优点，"), seg(3000, 5000, "S1", "他特别善良。")]
    assert [s.speaker for s in smooth_speakers(segs)] == ["S1", "S1", "S1"]


def test_smooth_keeps_real_short_reply():
    # 对方说完一整句后的短回应是真实插话，不能抹掉
    segs = [seg(0, 4000, "S1", "要我把钱转到安全账户。"), seg(4400, 5600, "S2", "你没转吧？"), seg(6000, 9000, "S1", "还没有。")]
    assert [s.speaker for s in smooth_speakers(segs)] == ["S1", "S2", "S1"]


def test_smooth_keeps_long_interjection():
    segs = [seg(0, 2000, "S1", "我觉得，"), seg(2000, 8000, "S2", "等一下我先说一个很长的不同意见，"), seg(8000, 9000, "S1", "好吧。")]
    assert [s.speaker for s in smooth_speakers(segs)] == ["S1", "S2", "S1"]


def test_merge_joins_unfinished_fragments():
    segs = [seg(0, 1000, "S1", "然后他就跟我说，"), seg(1100, 2500, "S1", "他说我们上了他。"), seg(2600, 5000, "S1", "我当时挺吃惊的。")]
    out = merge_fragments(segs)
    assert [s.text for s in out] == ["然后他就跟我说，他说我们上了他。", "我当时挺吃惊的。"]
    assert (out[0].start_ms, out[0].end_ms) == (0, 2500)


def test_mock_dialogue_unchanged():
    mock = MockEngine().transcribe(None)
    assert [(s.speaker, s.text) for s in postprocess(mock)] == [(s.speaker, s.text) for s in mock]


def test_resegment_fixes_shifted_punctuation():
    # FunASR 的标点错开了一个字：「就是其。」「实他」
    segs = [seg(0, 4000, "S1", "我就觉得他坐不住就是其。"), seg(4000, 7000, "S1", "实他对什么都不感兴趣。")]

    def punctuate(texts):
        assert texts == ["我就觉得他坐不住就是其实他对什么都不感兴趣"]
        return ["我就觉得他坐不住。就是其实他对什么都不感兴趣。"]

    out = resegment(segs, punctuate)
    assert [s.text for s in out] == ["我就觉得他坐不住。", "就是其实他对什么都不感兴趣。"]
    assert out[0].start_ms == 0 and out[1].end_ms == 7000
    assert out[0].end_ms <= out[1].start_ms


def test_resegment_falls_back_when_text_changes():
    segs = [seg(0, 1000, "S1", "你好，"), seg(1000, 2000, "S1", "世界。")]
    out = resegment(segs, lambda ts: ["您好，世界。"])  # 模型改了字，无法对齐时间
    assert [s.text for s in out] == ["你好，世界。"]


def test_resegment_keeps_speakers_apart():
    segs = [seg(0, 3000, "S1", "要我转到安全账户。"), seg(3400, 4600, "S2", "你没转吧？")]
    out = resegment(segs, lambda ts: [t + ("？" if t.endswith("吧") else "。") for t in ts])
    assert [(s.speaker, s.text) for s in out] == [("S1", "要我转到安全账户。"), ("S2", "你没转吧？")]


def test_resegment_tolerates_english_spacing_and_case():
    segs = [seg(0, 2000, "S1", "PPT 基本做完了，"), seg(2000, 4000, "S1", "就差 ai 报价。")]
    out = resegment(segs, lambda ts: ["ppt基本做完了，就差AI报价。"])
    assert [s.text for s in out] == ["ppt基本做完了，就差AI报价。"]
    assert (out[0].start_ms, out[0].end_ms) == (0, 4000)


def test_smooth_keeps_real_turn_after_comma():
    # 回归：领导的一句完整请求（约 3.8 秒）夹在员工两句话之间，前一句恰好以逗号结尾，不能被抹掉
    segs = [seg(13230, 13690, "S2", "好的，"), seg(13690, 16210, "S2", "我五点之前发您邮箱，"),
            seg(16210, 18510, "S1", "还有下周三去上海出差的机票，"), seg(18510, 19970, "S1", "你帮我订一下，"),
            seg(19970, 20450, "S2", "没问题，")]
    assert [s.speaker for s in smooth_speakers(segs)] == ["S2", "S2", "S1", "S1", "S2"]


def test_single_speaker_overrides_diarization():
    segs = [seg(0, 2000, "S1", "我觉得，"), seg(2000, 8000, "S2", "这件事很重要。"), seg(8000, 9000, "S3", "好的。")]
    assert {s.speaker for s in postprocess(segs, num_speakers=1)} == {"S1"}
