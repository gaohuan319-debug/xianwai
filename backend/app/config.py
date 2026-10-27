"""运行配置，全部来自环境变量（见仓库根目录 .env.example）。"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parent.parent
_REPO_DIR = _BACKEND_DIR.parent


def _bool(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).strip().lower() in ("1", "true", "yes", "on")


@dataclass
class Settings:
    data_dir: Path = field(default_factory=lambda: Path(os.getenv("XW_DATA_DIR", _REPO_DIR / "data")).resolve())
    frontend_dir: Path = field(default_factory=lambda: Path(os.getenv("XW_FRONTEND_DIR", _REPO_DIR / "frontend")).resolve())

    # 语音识别引擎：funasr（本地真实识别）| mock（演示数据，无需下载模型）
    asr_engine: str = field(default_factory=lambda: os.getenv("XW_ASR_ENGINE", "funasr"))

    # 任意 OpenAI 兼容接口：DeepSeek / 通义 / Kimi / 智谱 / Ollama ...
    llm_base_url: str = field(default_factory=lambda: os.getenv("XW_LLM_BASE_URL", "https://api.deepseek.com/v1").rstrip("/"))
    llm_api_key: str = field(default_factory=lambda: os.getenv("XW_LLM_API_KEY", ""))
    llm_model: str = field(default_factory=lambda: os.getenv("XW_LLM_MODEL", "deepseek-chat"))
    llm_json_mode: bool = field(default_factory=lambda: _bool("XW_LLM_JSON_MODE", True))
    llm_timeout: float = field(default_factory=lambda: float(os.getenv("XW_LLM_TIMEOUT", "120")))

    # 处理完成后是否保留原始音频（关闭后只保留文字，更省空间也更隐私）
    keep_audio: bool = field(default_factory=lambda: _bool("XW_KEEP_AUDIO", True))

    @property
    def audio_dir(self) -> Path:
        return self.data_dir / "audio"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "xianwai.db"

    @property
    def analyzer_dirs(self) -> list[Path]:
        # 后面的目录同 id 覆盖前面的：用户可以在 data/analyzers 里改写内置分析器
        return [_BACKEND_DIR / "analyzers", self.data_dir / "analyzers"]

    @property
    def llm_configured(self) -> bool:
        return bool(self.llm_api_key)


settings = Settings()
