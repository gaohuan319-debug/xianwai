"""分析器评测：用固定的对话用例调用真实大模型，检查结果是否符合期望。

用法（在 backend 目录下）：
    python -m evals.run                  # 跑全部用例
    python -m evals.run -c boss_pressure  # 只跑某个用例
    python -m evals.run -a anti_fraud -r 3  # 只测某个分析器，每个用例重复 3 次看稳定性

会读取仓库根目录的 .env。每次的完整输出保存在 evals/results/ 下，方便对比 prompt 改动。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

import yaml

EVALS_DIR = Path(__file__).resolve().parent
REPO_DIR = EVALS_DIR.parent.parent
LEVELS = ["none", "info", "notice", "warning"]
SHOWN = 0.5  # 和前端一致：低于这个置信度的结果会被淡化，不算「展示给用户」


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())


def shown(items: list[dict]) -> list[dict]:
    out = []
    for i in items:
        try:
            c = float(i.get("confidence", 1))
        except (TypeError, ValueError):
            c = 1.0
        if c >= SHOWN:
            out.append(i)
    return out


def check(kind: str, data: dict, exp: dict) -> list[str]:
    """返回不符合期望的描述，空列表表示通过。"""
    fails = []
    if kind == "todo":
        todos = shown(data.get("todos") or [])
        lo, hi = exp.get("count", [0, 99])
        if not lo <= len(todos) <= hi:
            fails.append(f"待办数 {len(todos)}，期望 {lo}~{hi}")
        text = " ".join(f"{t.get('title', '')} {t.get('detail') or ''}" for t in todos)
        fails += [f"缺少包含「{kw}」的待办" for kw in exp.get("include", []) if kw not in text]
        fails += [f"不应出现包含「{kw}」的待办" for kw in exp.get("exclude", []) if kw in text]
    elif kind == "insight":
        items = shown(data.get("insights") or [])
        if "count" in exp:
            lo, hi = exp["count"]
            if not lo <= len(items) <= hi:
                fails.append(f"洞察数 {len(items)}，期望 {lo}~{hi}")
        top = max((LEVELS.index(i.get("level")) for i in items if i.get("level") in LEVELS), default=0)
        if "min_level" in exp and top < LEVELS.index(exp["min_level"]):
            fails.append(f"最高等级 {LEVELS[top]}，期望至少 {exp['min_level']}")
        if "max_level" in exp and top > LEVELS.index(exp["max_level"]):
            fails.append(f"最高等级 {LEVELS[top]}，期望不超过 {exp['max_level']}")
    return fails


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("-c", "--case", action="append", help="只跑指定用例 id，可多次指定")
    ap.add_argument("-a", "--analyzer", action="append", help="只测指定分析器 id，可多次指定")
    ap.add_argument("-r", "--repeat", type=int, default=1, help="每个组合重复次数")
    ap.add_argument("-j", "--jobs", type=int, default=6, help="并发请求数")
    args = ap.parse_args()

    load_dotenv(REPO_DIR / ".env")
    from app.analyzers import load_analyzers  # 读取环境变量之后再导入
    from app.config import settings
    from app.pipeline import call_analyzer, format_transcript

    if not settings.llm_configured:
        print("未配置 XW_LLM_API_KEY，请先在仓库根目录的 .env 中填写。")
        return 2

    cases = yaml.safe_load((EVALS_DIR / "cases.yaml").read_text(encoding="utf-8"))
    if args.case:
        cases = [c for c in cases if c["id"] in args.case]
    analyzers = {a.id: a for a in load_analyzers() if a.enabled and a.kind in ("todo", "insight")}
    if args.analyzer:
        analyzers = {k: v for k, v in analyzers.items() if k in args.analyzer}

    jobs = []
    for case in cases:
        rows = [
            {"idx": i + 1, "start_ms": i * 4000, "speaker": spk, "person": case.get("speakers", {}).get(spk), "text": text}
            for i, (spk, text) in enumerate(case["lines"])
        ]
        transcript = format_transcript(rows)
        for aid, exp in case.get("expect", {}).items():
            if aid in analyzers:
                jobs += [(case["id"], analyzers[aid], exp, transcript) for _ in range(args.repeat)]

    def run(job):
        case_id, analyzer, exp, transcript = job
        t0 = time.time()
        try:
            data = call_analyzer(analyzer, transcript)
            fails = check(analyzer.kind, data, exp)
        except Exception as e:
            data, fails = {}, [f"调用失败: {e}"]
        return {"case": case_id, "analyzer": analyzer.id, "pass": not fails, "fails": fails,
                "seconds": round(time.time() - t0, 1), "output": data}

    print(f"模型 {settings.llm_model} · {len(cases)} 个用例 · {len(jobs)} 次调用\n")
    with ThreadPoolExecutor(args.jobs) as pool:
        results = list(pool.map(run, jobs))

    for r in results:
        mark = "✅" if r["pass"] else "❌"
        print(f"{mark} {r['case']:<18} {r['analyzer']:<14} {r['seconds']:>5}s  {'；'.join(r['fails'])}")

    passed = sum(r["pass"] for r in results)
    print(f"\n通过 {passed}/{len(results)}")

    out_dir = EVALS_DIR / "results"
    out_dir.mkdir(exist_ok=True)
    out = out_dir / f"{datetime.now():%Y%m%d-%H%M%S}.json"
    out.write_text(json.dumps({"model": settings.llm_model, "results": results}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"完整输出：{out.relative_to(REPO_DIR)}")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
