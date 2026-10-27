"""FunASR 本地识别：Paraformer 转写 + FSMN 断句 + 标点 + CAM++ 说话人分离。

首次运行会从 ModelScope 下载模型（约 1GB），国内网络可直接访问。
"""
from __future__ import annotations

import logging
import threading
import time
from pathlib import Path
from typing import Optional

from .base import Segment
from .postprocess import postprocess

log = logging.getLogger(__name__)


def _local_model_dir(name: str) -> Optional[str]:
    """已下载过的模型返回本地目录，没下载过返回 None。"""
    try:
        from funasr.download.name_maps_from_hub import name_maps_ms
        from modelscope.hub.snapshot_download import snapshot_download

        return snapshot_download(name_maps_ms.get(name, name), local_files_only=True)
    except Exception:
        return None


class FunASREngine:
    needs_wav = True

    def __init__(self) -> None:
        self._model = None
        self._lock = threading.Lock()

    def _load(self):
        with self._lock:
            if self._model is None:
                from funasr import AutoModel  # 可选依赖，见 requirements-asr.txt

                log.info("正在加载 FunASR 模型（首次会自动下载）...")
                t0 = time.time()
                names = {"model": "paraformer-zh", "vad_model": "fsmn-vad", "punc_model": "ct-punc", "spk_model": "cam++"}
                paths = {k: _local_model_dir(v) for k, v in names.items()}
                offline = all(paths.values())
                try:
                    self._model = AutoModel(
                        **{k: paths[k] or v for k, v in names.items()},
                        # 已全部下载时跳过联网检查更新，否则每次启动都要逐个访问 ModelScope，网络慢时要好几分钟
                        check_latest=not offline,
                        disable_update=True,
                    )
                except Exception as e:
                    if offline:
                        raise
                    # 下载失败时 FunASR 只会报「model is not registered」，很难看出是网络问题
                    missing = [names[k] for k, p in paths.items() if not p]
                    raise RuntimeError(
                        f"语音模型 {', '.join(missing)} 尚未下载，且从 ModelScope 下载失败。"
                        "请检查能否访问 modelscope.cn（Docker 部署请确认容器能联网，见 README「常见问题」）。"
                        f"原始错误：{e}"
                    ) from e
                log.info("模型加载完成（%s），用时 %.0fs", "离线" if offline else "联网", time.time() - t0)
        return self._model

    def transcribe(self, audio_path: Path, num_speakers: Optional[int] = None) -> list[Segment]:
        model = self._load()
        t0 = time.time()
        # FunASR 只从初始化参数里读 preset_spk_num，generate() 传参无效，所以临时改模型上的配置
        with self._lock:
            if num_speakers and num_speakers > 1:
                model.kwargs["preset_spk_num"] = num_speakers
            else:
                model.kwargs.pop("preset_spk_num", None)
            res = model.generate(input=str(audio_path), batch_size_s=300)
        log.info("识别完成，用时 %.0fs", time.time() - t0)
        if not res:
            return []
        result = res[0]
        sentences = result.get("sentence_info") or []
        if not sentences:
            # 没有分句信息时（例如音频很短）退化为单段
            text = (result.get("text") or "").strip()
            return [Segment(0, 0, "S1", text)] if text else []
        raw = [
            Segment(
                start_ms=int(s["start"]),
                end_ms=int(s["end"]),
                speaker=f"S{int(s.get('spk', 0)) + 1}",
                text=s["text"].strip(),
            )
            for s in sentences
            if s.get("text", "").strip()
        ]
        t0 = time.time()
        out = postprocess(raw, self._punctuate if getattr(model, "punc_model", None) else None, num_speakers)
        log.info("后处理完成：%d 段 → %d 段，用时 %.0fs", len(raw), len(out), time.time() - t0)
        return out

    def _punctuate(self, texts: list[str]) -> list[str]:
        # 复用主模型里已加载的 ct-punc，不额外占内存；一次传入全部段落
        model = self._model
        res = model.inference(texts, model=model.punc_model, kwargs=model.punc_kwargs)
        return [r["text"] for r in res]
