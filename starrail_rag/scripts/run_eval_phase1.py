"""
端到端评估脚本 — Phase 1（黑塔/贝洛伯格/仙舟 + 通用 lore）

用法：
    python3 -m starrail_rag.scripts.run_eval_phase1

输出：
    output/eval_results_phase1.json
    output/eval_results_phase1.md
"""
from __future__ import annotations
import asyncio, json, os, time
from pathlib import Path

EVAL_PATH    = Path("starrail_rag/eval_set_phase1.json")
RESULTS_PATH = Path("output/eval_results_phase1.json")
REPORT_PATH  = Path("output/eval_results_phase1.md")

DIFFICULTY_LABELS = {"easy": "Easy", "medium": "Medium", "hard": "Hard"}


async def run_eval():
    from starrail_rag.retrieval.query_engine import QueryEngine

    engine = QueryEngine(
        deepseek_key=os.environ.get("HSR_DEEPSEEK_API_KEY"),
        ali_key=os.environ.get("ALI_API_KEY"),
    )

    eval_data  = json.load(open(EVAL_PATH))
    questions  = eval_data["questions"]
    results    = []

    print(f"共 {len(questions)} 题，开始评估…\n")

    for i, q in enumerate(questions, 1):
        print(f"[{i:02d}/{len(questions)}] {q['id']} ({q['difficulty']}) — {q['question'][:50]}…")
        t0 = time.time()
        try:
            result = await engine.query(q["question"])
            elapsed = time.time() - t0
            print(f"       模式: {result.mode.value}  耗时: {elapsed:.1f}s")
            answer_preview = result.answer[:150].replace("\n", " ")
            print(f"       答案: {answer_preview}…\n")
            results.append({
                "id":            q["id"],
                "difficulty":    q["difficulty"],
                "question":      q["question"],
                "answer":        result.answer,
                "mode":          result.mode.value,
                "elapsed_s":     round(elapsed, 1),
                "answer_key_points": q["answer_key_points"],
                "score":         None,   # 人工打分
                "notes":         "",
            })
        except Exception as e:
            elapsed = time.time() - t0
            print(f"       ERROR: {e}\n")
            results.append({
                "id":            q["id"],
                "difficulty":    q["difficulty"],
                "question":      q["question"],
                "answer":        f"[ERROR] {e}",
                "mode":          "error",
                "elapsed_s":     round(elapsed, 1),
                "answer_key_points": q["answer_key_points"],
                "score":         0,
                "notes":         "query failed",
            })

    # 保存 JSON
    output = {
        "eval_set":   "eval_set_phase1.json",
        "run_time":   time.strftime("%Y-%m-%d %H:%M UTC"),
        "total":      len(results),
        "results":    results,
    }
    RESULTS_PATH.parent.mkdir(exist_ok=True)
    RESULTS_PATH.write_text(json.dumps(output, ensure_ascii=False, indent=2))
    print(f"\n✓ JSON 结果保存到 {RESULTS_PATH}")

    # 生成 Markdown 报告
    _write_report(output)
    print(f"✓ Markdown 报告保存到 {REPORT_PATH}")
    return results


def _write_report(output: dict):
    results = output["results"]
    by_diff: dict[str, list] = {"easy": [], "medium": [], "hard": []}
    for r in results:
        by_diff[r["difficulty"]].append(r)

    lines = [
        f"# Phase 1 评估报告",
        f"",
        f"> 运行时间：{output['run_time']}",
        f"> 评估集：{output['eval_set']}（{output['total']} 题）",
        f"> LightRAG 覆盖：ch01-09（黑塔/贝洛伯格/仙舟/2.2 匹诺康尼主线结局）",
        f"> Chroma 覆盖：7819 chunks 全量",
        f"",
        f"---",
        f"",
        f"## 评分说明",
        f"",
        f"- **2 分**：答案命中全部关键点",
        f"- **1 分**：答案命中部分关键点，方向正确",
        f"- **0 分**：答案错误、无关或直接报错",
        f"",
        f"---",
        f"",
    ]

    for diff in ["easy", "medium", "hard"]:
        qs = by_diff[diff]
        lines.append(f"## {DIFFICULTY_LABELS[diff]}（{len(qs)} 题）")
        lines.append("")
        for r in qs:
            lines.append(f"### {r['id']} — {r['question']}")
            lines.append("")
            lines.append(f"**检索模式**: `{r['mode']}`  **耗时**: {r['elapsed_s']}s  **评分**: ___/2")
            lines.append("")
            lines.append(f"**参考关键点**:")
            for kp in r["answer_key_points"]:
                lines.append(f"- {kp}")
            lines.append("")
            lines.append(f"**系统答案**:")
            lines.append("")
            lines.append(r["answer"])
            lines.append("")
            lines.append("---")
            lines.append("")

    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


def main():
    asyncio.run(run_eval())


if __name__ == "__main__":
    main()
