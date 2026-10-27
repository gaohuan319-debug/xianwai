from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Protocol


@dataclass
class Segment:
    start_ms: int
    end_ms: int
    speaker: str  # 引擎给出的匿名标签：S1 / S2 ...
    text: str
    emotion: Optional[str] = None


class ASREngine(Protocol):
    # 是否需要先把音频转成 16k 单声道 wav
    needs_wav: bool

    # num_speakers：用户指定的说话人数，None 表示自动判断
    def transcribe(self, audio_path: Path, num_speakers: Optional[int] = None) -> list[Segment]: ...
