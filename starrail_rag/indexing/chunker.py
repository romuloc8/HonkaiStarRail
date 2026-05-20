"""
Chunk Builder — 将各类文档切分为适合向量化的 Chunk。

策略（基于 BGE-M3 最大 8192 token）：
  对话场景文档  → 已是场景粒度，直接整体作为一个 chunk
  书籍          → 按段落（\n\n）切分，超过阈值再按句子切
  角色故事      → 每段一个 chunk
  遗器/光锥/道具 → 整体一个 chunk（本身已足够小）
"""
from __future__ import annotations

import re
from pathlib import Path
from starrail_rag.indexing.chunk import Chunk

# 中文字符的粗略 token 估算比：1.5 汉字 ≈ 1 token
MAX_CHARS = 8192 * 1  # 保守上限，约 5000 汉字（8192 token 的余量）
PARAGRAPH_OVERLAP_CHARS = 200  # 段落间 overlap


def _estimate_chars(text: str) -> int:
    return len(text)


def _dialogue_to_text(dialogues: list[dict]) -> str:
    """将对话行列表转为可读的文本格式。"""
    lines = []
    for dl in dialogues:
        speaker = dl.get("speaker", "")
        text = dl.get("text", "")
        if speaker:
            lines.append(f"{speaker}：{text}")
        else:
            lines.append(text)
    return "\n".join(lines)


def _split_by_paragraphs(text: str, max_chars: int = MAX_CHARS,
                          overlap_chars: int = PARAGRAPH_OVERLAP_CHARS) -> list[str]:
    """
    按自然段落（\n\n 或 \n）切分文本，超出 max_chars 时强制切。
    相邻 chunk 保留 overlap_chars 字符的重叠。
    """
    # 优先按双换行切，再按单换行切
    raw_paragraphs = [p.strip() for p in re.split(r'\n{2,}', text) if p.strip()]
    if not raw_paragraphs:
        raw_paragraphs = [p.strip() for p in text.split('\n') if p.strip()]

    chunks: list[str] = []
    current: list[str] = []
    current_len = 0

    for para in raw_paragraphs:
        para_len = _estimate_chars(para)

        # 单段超出限制 → 强制按句子切
        if para_len > max_chars:
            if current:
                chunks.append('\n\n'.join(current))
                current, current_len = [], 0
            # 按句切（。！？…）
            sentences = re.split(r'(?<=[。！？…\n])', para)
            sub_current, sub_len = [], 0
            for sent in sentences:
                if sub_len + len(sent) > max_chars and sub_current:
                    chunks.append(''.join(sub_current))
                    # overlap: 保留最后一句
                    last = sub_current[-1] if sub_current else ''
                    sub_current = [last, sent] if last else [sent]
                    sub_len = len(last) + len(sent)
                else:
                    sub_current.append(sent)
                    sub_len += len(sent)
            if sub_current:
                chunks.append(''.join(sub_current))
            continue

        if current_len + para_len + 2 > max_chars and current:
            chunks.append('\n\n'.join(current))
            # overlap: 把最后一段带到下个 chunk
            overlap_text = current[-1] if current else ''
            if _estimate_chars(overlap_text) <= overlap_chars:
                current = [overlap_text, para]
                current_len = _estimate_chars(overlap_text) + para_len
            else:
                current = [para]
                current_len = para_len
        else:
            current.append(para)
            current_len += para_len + 2  # +2 for \n\n

    if current:
        chunks.append('\n\n'.join(current))

    return [c for c in chunks if c.strip()]


class ChunkBuilder:
    """
    遍历 output/ 下的所有 JSONL 文件，将文档切分为 Chunk。
    """

    def __init__(self, output_root: str | Path = "/workspace/output"):
        self.output_root = Path(output_root)

    def build_all(self) -> list[Chunk]:
        """构建所有数据源的 Chunk 列表。"""
        chunks: list[Chunk] = []
        stats: dict[str, int] = {}

        # ── 对话场景文档（main_story / companion / continuance / adventure / activity）
        for subdir in ["main_story", "companion", "continuance", "adventure", "activity"]:
            dir_path = self.output_root / subdir
            if not dir_path.exists():
                continue
            for jsonl_file in sorted(dir_path.glob("*.jsonl")):
                file_chunks = self._build_dialogue_chunks(jsonl_file, subdir)
                chunks.extend(file_chunks)
                stats[subdir] = stats.get(subdir, 0) + len(file_chunks)

        # ── Lore 文档
        lore_dir = self.output_root / "lore"
        if lore_dir.exists():
            for jsonl_file in sorted(lore_dir.glob("*.jsonl")):
                lore_chunks = self._build_lore_chunks(jsonl_file)
                chunks.extend(lore_chunks)
                stats[f"lore/{jsonl_file.stem}"] = len(lore_chunks)

        total = sum(stats.values())
        print(f"ChunkBuilder: {total} chunks built")
        for key, count in sorted(stats.items()):
            print(f"  {key}: {count}")
        return chunks

    # ──────────────────────────────────────────────────────────────────────
    # 对话场景文档
    # ──────────────────────────────────────────────────────────────────────

    def _build_dialogue_chunks(self, jsonl_file: Path, category: str) -> list[Chunk]:
        """对话场景：整个场景作为一个 chunk（已是最小语义单元）。"""
        import json
        chunks = []
        with open(jsonl_file, encoding="utf-8") as f:
            for line in f:
                doc = json.loads(line.strip())
                dialogues = doc.get("dialogues", [])
                if not dialogues:
                    continue

                text = _dialogue_to_text(dialogues)
                if not text.strip():
                    continue

                meta = dict(doc.get("metadata", {}))
                meta["category"] = category
                meta["filename"] = jsonl_file.name

                chunk = Chunk(
                    chunk_id=f"chunk_{doc['doc_id']}",
                    doc_id=doc["doc_id"],
                    doc_type=doc.get("doc_type", "main_mission_scene"),
                    text=text,
                    metadata=meta,
                )
                chunks.append(chunk)
        return chunks

    # ──────────────────────────────────────────────────────────────────────
    # Lore 文档
    # ──────────────────────────────────────────────────────────────────────

    def _build_lore_chunks(self, jsonl_file: Path) -> list[Chunk]:
        """Lore 文档按类型使用不同切分策略。"""
        import json
        stem = jsonl_file.stem   # books | character_stories | relic_sets | ...
        chunks = []
        with open(jsonl_file, encoding="utf-8") as f:
            for line in f:
                doc = json.loads(line.strip())
                body = doc.get("body", "").strip()
                if not body:
                    continue

                meta = dict(doc.get("metadata", {}))
                meta["filename"] = jsonl_file.name
                meta["lore_title"] = doc.get("title", "")
                doc_type = doc.get("doc_type", stem)

                if stem in ("books", "character_stories"):
                    # 按段落切分
                    parts = _split_by_paragraphs(body)
                    for idx, part in enumerate(parts):
                        chunk_meta = dict(meta)
                        chunk_meta["chunk_index"] = idx
                        chunk_meta["total_chunks"] = len(parts)
                        chunks.append(Chunk(
                            chunk_id=f"chunk_{doc['doc_id']}_{idx:03d}",
                            doc_id=doc["doc_id"],
                            doc_type=doc_type,
                            text=f"【{doc.get('title', '')}】\n{part}",
                            metadata=chunk_meta,
                        ))
                else:
                    # relic_sets / light_cones / item_lore → 整体一个 chunk
                    title = doc.get("title", "")
                    chunks.append(Chunk(
                        chunk_id=f"chunk_{doc['doc_id']}",
                        doc_id=doc["doc_id"],
                        doc_type=doc_type,
                        text=f"【{title}】\n{body}" if title else body,
                        metadata=meta,
                    ))
        return chunks
