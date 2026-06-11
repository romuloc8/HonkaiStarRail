"""
starrail_rag.scripts — 工具脚本包。

各脚本通过 python3 -m starrail_rag.scripts.XXX 运行，
不在此处导入（避免 import 时执行脚本逻辑）。

可用脚本：
  build_sparse_index      - 构建 BM25 Sparse 索引
  verify_index            - 验证 Chroma + BM25 索引状态
  validate_cleaning       - 验证数据清洗质量
  preview_eval            - 预览/运行评估题目
  run_eval_phase1         - 运行 Phase 1 评估（21题，黑塔/贝洛伯格/仙舟）
  extract_mission_order   - 提取任务顺序
  gen_mission_mermaid     - 生成任务顺序 Mermaid 概览图
  gen_xianzhou_mermaid    - 生成仙舟弧任务结构 Mermaid 图
"""
