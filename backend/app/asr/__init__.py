from __future__ import annotations

from functools import lru_cache

from .base import ASREngine, Segment


@lru_cache(maxsize=None)
def get_engine(name: str) -> ASREngine:
    if name == "mock":
        from .mock_engine import MockEngine

        return MockEngine()
    if name == "funasr":
        from .funasr_engine import FunASREngine

        return FunASREngine()
    raise ValueError(f"未知的 ASR 引擎: {name}（可选 funasr / mock）")


__all__ = ["ASREngine", "Segment", "get_engine"]
