"""
Chunk 数据模型。
"""
from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class Chunk:
    """向量库中的最小索引单元。"""
    chunk_id:  str               # 全局唯一 ID
    doc_id:    str               # 来源文档 ID
    doc_type:  str               # main_mission_scene | book | character_story | ...
    text:      str               # 用于 embedding 的文本内容
    metadata:  dict = field(default_factory=dict)

    def __post_init__(self):
        # metadata 中必须包含 doc_type（用于 Chroma 过滤）
        self.metadata.setdefault("doc_type", self.doc_type)
        self.metadata.setdefault("doc_id", self.doc_id)
