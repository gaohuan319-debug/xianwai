"""用 ffmpeg 统一转成 16k 单声道 wav，兼容浏览器录的 webm、手机录音的 m4a 等格式。"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Optional


def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


def to_wav16k(src: Path, dst: Path) -> Path:
    if not ffmpeg_available():
        raise RuntimeError("未找到 ffmpeg，请先安装（macOS: brew install ffmpeg）")
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-i", str(src), "-ac", "1", "-ar", "16000", str(dst)],
        check=True,
    )
    return dst


def probe_duration_ms(path: Path) -> Optional[int]:
    if shutil.which("ffprobe") is None:
        return None
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        capture_output=True,
        text=True,
    )
    try:
        return int(float(out.stdout.strip()) * 1000)
    except ValueError:
        return None
