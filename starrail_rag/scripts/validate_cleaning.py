"""
数据清洗验证脚本：检查 output/ 下的 JSONL 文件是否存在残留标签。

用法：
    python3 -m starrail_rag.scripts.validate_cleaning [--path output/main_story]
"""
import argparse, json, re
from pathlib import Path

DIRTY_PATTERNS = re.compile(r'<[a-zA-Z]|\{NICKNAME\}|\{LAYOUT_|<unbreak>')


def check_file(path: Path) -> int:
    dirty = 0
    with open(path, encoding="utf-8") as f:
        for line in f:
            doc = json.loads(line.strip())
            for dl in doc.get("dialogues", []):
                if DIRTY_PATTERNS.search(dl.get("text", "")):
                    dirty += 1
            if DIRTY_PATTERNS.search(doc.get("body", "")):
                dirty += 1
    return dirty


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--path", default="output", help="检查目录（默认 output/）")
    args = parser.parse_args()

    root = Path(args.path)
    total_files = total_dirty = 0

    for jsonl in sorted(root.rglob("*.jsonl")):
        dirty = check_file(jsonl)
        total_files += 1
        if dirty:
            total_dirty += dirty
            print(f"  ⚠ {jsonl.relative_to(root)}: {dirty} 条含残留标签")

    print(f"\n共检查 {total_files} 个文件，{total_dirty} 条含残留标签", end="")
    print(" ✓ 全部干净" if total_dirty == 0 else " → 建议重跑清洗层")


if __name__ == "__main__":
    main()
