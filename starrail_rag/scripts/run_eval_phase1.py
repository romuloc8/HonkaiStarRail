"""
端到端评估脚本 — Phase 1（黑塔/贝洛伯格/仙舟 + 通用 lore）

用法：
    python3 -m starrail_rag.scripts.run_eval_phase1

输出：
    output/eval_results_phase1_v2.json
    output/eval_results_phase1_v2.md
"""
from __future__ import annotations
import asyncio, json, os, time
from pathlib import Path

EVAL_PATH    = Path("starrail_rag/eval_set_phase1.json")
RESULTS_PATH = Path("output/eval_results_phase1_v2.json")
REPORT_PATH  = Path("output/eval_results_phase1_v2.md")

DIFFICULTY_LABELS = {"easy": "Easy", "medium": "Medium", "hard": "Hard"}


async def run_eval():
    from starrail_rag.retrieval.query_engine import AgentQueryEngine

    engine = AgentQueryEngine(
        deepseek_key=os.environ.get("HSR_DEEPSEEK_API_KEY"),
        ali_key=os.environ.get("ALI_API_KEY"),
    )

    eval_data  = json.load(open(EVAL_PATH))
    questions  = eval_data["questions"]
    results    = []

    print(f"共 {len(questions)} 题（Agent ReAct 工作流），开始评估…\n")

    for i, q in enumerate(questions, 1):
        print(f"[{i:02d}/{len(questions)}] {q['id']} ({q['difficulty']}) — {q['question'][:50]}…")
        t0 = time.time()
        try:
            result = await engine.query(q["question"])
            elapsed = time.time() - t0
            iterations = getattr(result, 'iterations', 0)
            chunks = getattr(result, 'chunks_used', 0)
            print(f"       模式: {result.mode}  迭代: {iterations}  片段: {chunks}  耗时: {elapsed:.1f}s")
            answer_preview = result.answer[:120].replace("\n", " ")
            print(f"       答案: {answer_preview}…\n")
            results.append({
                "id":            q["id"],
                "difficulty":    q["difficulty"],
                "question":      q["question"],
                "answer":        result.answer,
                "mode":          result.mode,
                "iterations":    iterations,
                "chunks_used":   chunks,
                "elapsed_s":     round(elapsed, 1),
                "answer_key_points": q["answer_key_points"],
                "score":         None,
                "notes":         "",
            })
        except Exception as e:
            elapsed = time.time() - t0
            print(f"       ERROR: {e}\n")
            results.append({
                "id": q["id"], "difficulty": q["difficulty"],
                "question": q["question"], "answer": f"[ERROR] {e}",
                "mode": "error", "iterations": 0, "chunks_used": 0,
                "elapsed_s": round(elapsed, 1),
                "answer_key_points": q["answer_key_points"],
                "score": 0, "notes": "query failed",
            })

    output = {
        "eval_set":   "eval_set_phase1.json",
        "engine":     "AgentQueryEngine (ReAct)",
        "run_time":   time.strftime("%Y-%m-%d %H:%M UTC"),
        "total":      len(results),
        "results":    results,
    }
    RESULTS_PATH.parent.mkdir(exist_ok=True)
    RESULTS_PATH.write_text(json.dumps(output, ensure_ascii=False, indent=2))
    print(f"\n✓ JSON 结果 → {RESULTS_PATH}")

    _write_report(output)
    print(f"✓ Markdown 报告 → {REPORT_PATH}")
    return results


def _write_report(output: dict):
    results = output["results"]
    by_diff: dict[str, list] = {"easy": [], "medium": [], "hard": []}
    for r in results:
        by_diff[r["difficulty"]].append(r)

    lines = [
        f"# Phase 1 评估报告 — Agent ReAct 工作流",
        f"",
        f"> 运行时间：{output['run_time']}",
        f"> 引擎：{output['engine']}",
        f"> 评估集：{output['eval_set']}（{output['total']} 题）",
        f"",
        "---", "",
        "## 评分说明",
        "- **2 分**：答案命中全部关键点",
        "- **1 分**：答案命中部分关键点，方向正确",
        "- **0 分**：答案错误、无关或直接报错",
        "", "---", "",
    ]

    for diff in ["easy", "medium", "hard"]:
        qs = by_diff[diff]
        lines.append(f"## {DIFFICULTY_LABELS[diff]}（{len(qs)} 题）\n")
        for r in qs:
            lines.append(f"### {r['id']} — {r['question']}")
            lines.append(f"**模式**: `{r['mode']}` **迭代**: {r['iterations']} **片段**: {r['chunks_used']} **耗时**: {r['elapsed_s']}s  **评分**: ___/2\n")
            lines.append(f"**参考关键点**:")
            for kp in r["answer_key_points"]:
                lines.append(f"- {kp}")
            lines.append(f"\n**系统答案**:\n\n{r['answer']}\n\n---\n")

    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


def main():
    asyncio.run(run_eval())


if __name__ == "__main__":
    main()
