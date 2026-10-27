"""调用任意 OpenAI 兼容的 Chat Completions 接口，并把回复解析成 JSON。"""
from __future__ import annotations

import json
import re
from typing import Any

import httpx

from .config import settings


class LLMError(RuntimeError):
    pass


class LLMNotConfigured(LLMError):
    pass


def chat_json(system: str, user: str) -> dict[str, Any]:
    if not settings.llm_configured:
        raise LLMNotConfigured("未配置大模型：请在 .env 中设置 XW_LLM_API_KEY（本地 Ollama 可填任意值）")

    body: dict[str, Any] = {
        "model": settings.llm_model,
        "temperature": 0.2,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
    }
    if settings.llm_json_mode:
        body["response_format"] = {"type": "json_object"}

    try:
        resp = httpx.post(
            f"{settings.llm_base_url}/chat/completions",
            headers={"Authorization": f"Bearer {settings.llm_api_key}"},
            json=body,
            timeout=settings.llm_timeout,
        )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
    except httpx.HTTPStatusError as e:
        raise LLMError(f"大模型接口返回 {e.response.status_code}: {e.response.text[:300]}") from e
    except (httpx.HTTPError, KeyError, IndexError) as e:
        raise LLMError(f"调用大模型失败: {e}") from e
    return parse_json(content)


_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)
# 模型偶尔照抄转写里的片段编号写成 [#3, #5]，这不是合法 JSON
_HASH_NUM = re.compile(r"(?<=[\[,\s])#(\d+)")
# 数组或对象末尾多出的逗号：[1, 2,] / {"a": 1,}
_TRAILING_COMMA = re.compile(r",\s*([\]}])")


def parse_json(text: str) -> dict[str, Any]:
    """容忍 ```json 代码块、前后多余文字、#编号、末尾多余逗号等常见的不规范输出。"""
    text = _HASH_NUM.sub(r"\1", _FENCE.sub("", text.strip()))
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end <= start:
            raise LLMError(f"模型输出不是 JSON: {text[:200]}")
        body = text[start : end + 1]
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            # 只在解析失败时才去掉多余的逗号，避免误改合法 JSON 里字符串的内容
            body = _TRAILING_COMMA.sub(r"\1", body)
            try:
                data = json.loads(body)
            except json.JSONDecodeError as e:
                near = body[max(0, e.pos - 60) : e.pos + 60]
                raise LLMError(f"模型输出不是合法 JSON: {e}；出错位置附近：{near!r}") from e
    if not isinstance(data, dict):
        raise LLMError("模型输出的 JSON 顶层必须是对象")
    return data
