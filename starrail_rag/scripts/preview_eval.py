"""
评估集预览脚本：显示评估问题并支持手动打分。

用法：
    python3 -m starrail_rag.scripts.preview_eval [--difficulty easy|medium|hard] [--n 5]
    python3 -m starrail_rag.scripts.preview_eval --run --n 3   # 实际运行查询
"""
import argparse, json, asyncio, os
from pathlib import Path

EVAL_PATH = Path("starrail_rag/eval_set.json")


def show_questions(difficulty=None, n=5):
    data = json.load(open(EVAL_PATH))
    questions = data["questions"]
    if difficulty:
        questions = [q for q in questions if q["difficulty"] == difficulty]
    questions = questions[:n]

    print(f"=== 评估集预览（{difficulty or '全部'}，共 {len(questions)} 题）===\n")
    for q in questions:
        print(f"[{q['id']} · {q['difficulty'].upper()}]")
        print(f"问题: {q['question']}")
        print(f"关键答案: {' / '.join(q['answer_key_points'])}")
        print(f"推理类型: {q['reasoning_type']}  |  跳数: {q['requires_hops']}")
        print()


async def run_and_score(difficulty=None, n=3):
    from starrail_rag.retrieval.query_engine import QueryEngine
    engine = QueryEngine(
        deepseek_key=os.environ.get("HSR_DEEPSEEK_API_KEY"),
        ali_key=os.environ.get("ALI_API_KEY") or os.environ.get("DASHSCOPE_API_KEY"),
    )
    data = json.load(open(EVAL_PATH))
    questions = data["questions"]
    if difficulty:
        questions = [q for q in questions if q["difficulty"] == difficulty]
    questions = questions[:n]

    print(f"=== 运行评估（{difficulty or '全部'}，{n} 题）===\n")
    for q in questions:
        result = await engine.query(q["question"])
        print(f"[{q['id']} · {q['difficulty'].upper()}] {q['question']}")
        print(f"模式: {result.mode.value}")
        print(f"答案: {result.answer[:300]}{'...' if len(result.answer) > 300 else ''}")
        print(f"参考关键点: {' / '.join(q['answer_key_points'])}")
        print()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--difficulty", "-d", choices=["easy", "medium", "hard"], default=None)
    parser.add_argument("--n", type=int, default=5)
    parser.add_argument("--run", action="store_true", help="实际运行查询（需要 API key）")
    args = parser.parse_args()

    if args.run:
        asyncio.run(run_and_score(args.difficulty, args.n))
    else:
        show_questions(args.difficulty, args.n)


if __name__ == "__main__":
    main()
