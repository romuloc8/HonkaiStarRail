"""
starrail_rag.scripts — 工具脚本包。

各脚本通过 python3 -m starrail_rag.scripts.XXX 运行，
不在此处导入（避免 import 时执行脚本逻辑）。

可用脚本：
  build_sparse_index      - 构建 BM25 Sparse 索引
  verify_index            - 验证 Chroma + BM25 索引状态
  check_lightrag_progress - 查看 LightRAG 建图进度
  dedup_entity_names      - 实体名称去重（DeepSeek）
  validate_cleaning       - 验证数据清洗质量
  preview_eval            - 预览/运行评估题目
"""
