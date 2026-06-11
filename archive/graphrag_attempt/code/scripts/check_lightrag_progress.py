"""
LightRAG 建图进度查看脚本。

用法：
    python3 -m starrail_rag.scripts.check_lightrag_progress
"""
import json, os, subprocess
from pathlib import Path

LIGHTRAG_DIR = Path("output/lightrag_db")

print("=== LightRAG 建图状态 ===")

status_file = LIGHTRAG_DIR / "kv_store_doc_status.json"
if status_file.exists():
    data = json.load(open(status_file))
    total = len(data)
    done  = sum(1 for v in data.values() if v.get("status") == "processed")
    dup   = sum(1 for v in data.values() if "[DUPLICATE]" in v.get("content_summary", ""))
    print(f"批次进度: {done}/{total} ({done/total*100:.1f}%)")
    print(f"去重跳过: {dup} 批（正常）")
else:
    print("状态文件不存在（LightRAG 尚未启动或目录不存在）")

graph_file = LIGHTRAG_DIR / "graph_chunk_entity_relation.graphml"
if graph_file.exists():
    size_mb = os.path.getsize(graph_file) / 1024 / 1024
    content = open(graph_file).read()
    nodes = content.count("<node ")
    edges = content.count("<edge ")
    print(f"知识图谱: {nodes:,} 节点  {edges:,} 边  ({size_mb:.1f} MB)")
else:
    print("图谱文件不存在")

proc = subprocess.run(["pgrep", "-f", "lightrag_builder"], capture_output=True, text=True)
print(f"进程状态: {'🔄 运行中' if proc.returncode == 0 else '✅ 已完成（或未启动）'}")
