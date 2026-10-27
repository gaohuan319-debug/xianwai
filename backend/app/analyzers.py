"""分析器插件：每个分析器就是一个 YAML 文件（prompt + 输出类型）。

kind 决定输出格式和前端展示方式，写新分析器时只需要关心 prompt：
  summary  日记摘要（每段录音一份）
  todo     待办事项，进入跨天追踪的待办列表
  insight  沟通洞察 / 风险信号，带等级和置信度
"""
from __future__ import annotations

import logging
import re
from dataclasses import asdict, dataclass
from pathlib import Path

import yaml

from .config import settings
from .db import connect

log = logging.getLogger(__name__)

KINDS = ("summary", "todo", "insight")
ID_PATTERN = re.compile(r"^[a-z0-9_]{1,40}$")
MAX_PROMPT_CHARS = 4000

# 每种 kind 要求模型输出的 JSON 结构。示例本身必须是合法 JSON，否则模型会照抄占位符。
OUTPUT_SPECS = {
    "summary": """{"title": "妈妈接到诈骗电话", "summary": "下班后和妈妈通了电话……", "highlights": [{"text": "明天上午陪妈妈去银行柜台", "evidence": [7]}]}
字段说明：title 不超过 15 字；summary 用日记口吻写 2~5 句；highlights 是值得记住的要点，可以为空数组。""",
    "todo": """{"todos": [{"title": "周六中午回家修打印机", "detail": "", "owner": "我", "due": "周六中午", "confidence": 0.9, "evidence": [8, 9]}]}
字段说明：title 以动词开头；owner 填转写中的说话人名称；due 保留原文，没有就填空字符串；没有待办时返回 {"todos": []}。""",
    "insight": """{"insights": [{"title": "一句话结论", "detail": "依据和建议", "level": "notice", "confidence": 0.7, "evidence": [3, 5]}]}
字段说明：level 只能是 info、notice、warning 之一；detail 语气中立，不给人贴标签；没有发现时返回 {"insights": []}。""",
}

# 所有 kind 通用的字段约定
COMMON_SPEC = "confidence 是 0 到 1 之间的小数；evidence 是片段编号组成的整数数组，例如 [3, 5]，不要带 #；title 和 detail 是给用户看的，不要写片段编号。"


@dataclass
class Analyzer:
    id: str
    name: str
    kind: str
    prompt: str
    description: str = ""
    version: int = 1
    enabled: bool = True
    rule: str = ""  # 从自定义规则生成时，用户写的原始描述
    source: str = ""
    custom: bool = False  # 放在 data/analyzers/ 里、可以在界面上编辑的分析器

    def public(self) -> dict:
        d = self.detail()
        d.pop("prompt")
        d.pop("rule")
        return d

    def detail(self) -> dict:
        d = asdict(self)
        d.pop("source")  # 不把服务器上的文件路径暴露给前端
        return d


def _user_dir() -> Path:
    return settings.analyzer_dirs[-1]


def _load_file(path: Path) -> Analyzer:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    missing = [k for k in ("id", "name", "kind", "prompt") if not raw.get(k)]
    if missing:
        raise ValueError(f"缺少字段 {missing}")
    if raw["kind"] not in KINDS:
        raise ValueError(f"kind 必须是 {KINDS} 之一，而不是 {raw['kind']!r}")
    fields = {k: raw[k] for k in Analyzer.__dataclass_fields__ if k in raw and k not in ("source", "custom")}
    return Analyzer(**fields, source=str(path), custom=path.parent == _user_dir())


def load_analyzers() -> list[Analyzer]:
    found: dict[str, Analyzer] = {}
    for d in settings.analyzer_dirs:
        if not d.is_dir():
            continue
        for path in sorted(d.glob("*.y*ml")):
            try:
                a = _load_file(path)
            except Exception as e:  # 坏掉的社区分析器不应拖垮整个流程
                log.warning("跳过分析器 %s: %s", path.name, e)
                continue
            found[a.id] = a
    return list(found.values())


def effective_analyzers() -> list[Analyzer]:
    """在 YAML 的基础上叠加用户在界面上的启用/停用设置。"""
    with connect() as conn:
        overrides = {r["analyzer_id"]: bool(r["enabled"]) for r in conn.execute("SELECT * FROM analyzer_settings")}
    analyzers = load_analyzers()
    for a in analyzers:
        a.enabled = overrides.get(a.id, a.enabled)
    return analyzers


def set_enabled(analyzer_id: str, enabled: bool) -> None:
    with connect() as conn:
        conn.execute(
            "INSERT INTO analyzer_settings (analyzer_id, enabled) VALUES (?, ?) "
            "ON CONFLICT(analyzer_id) DO UPDATE SET enabled = excluded.enabled",
            (analyzer_id, int(enabled)),
        )


class _Dumper(yaml.SafeDumper):
    pass


# 多行的提示词写成 | 块，和手写的分析器一样方便阅读和修改
_Dumper.add_representer(
    str, lambda d, s: d.represent_scalar("tag:yaml.org,2002:str", s, style="|" if "\n" in s else None)
)


def save_custom(a: Analyzer) -> None:
    if not ID_PATTERN.match(a.id):
        raise ValueError(f"分析器 id 不合法: {a.id!r}")
    data = {"id": a.id, "name": a.name, "kind": a.kind, "version": a.version,
            "description": a.description, "prompt": a.prompt.strip() + "\n"}
    if a.rule:
        data["rule"] = a.rule
    d = _user_dir()
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{a.id}.yaml").write_text(
        yaml.dump(data, Dumper=_Dumper, allow_unicode=True, sort_keys=False), encoding="utf-8")


def delete_custom(a: Analyzer) -> None:
    Path(a.source).unlink(missing_ok=True)
    with connect() as conn:
        conn.execute("DELETE FROM analyzer_settings WHERE analyzer_id = ?", (a.id,))
