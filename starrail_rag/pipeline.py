"""
Orchestration pipeline: wire extractors → cleaner → serialiser.

Designed to be called from the CLI or from a Jupyter notebook.

Example
-------
    from starrail_rag.pipeline import run_pipeline, PipelineConfig

    cfg = PipelineConfig(
        data_root="/workspace",
        output_dir="/workspace/output",
        extractors=["main_mission"],
        mission_types=["Main"],
    )
    results = run_pipeline(cfg)
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path

from starrail_rag.core.cleaner import CleaningPipeline
from starrail_rag.core.models import Document
from starrail_rag.core.textmap import TextMapResolver
from starrail_rag.extractors.main_mission import MainMissionExtractor
from starrail_rag.extractors.wiki_mission import WikiMissionExtractor, CHAPTER_NAMES
from starrail_rag.extractors.character_story import CharacterStoryExtractor
from starrail_rag.extractors.light_cone import LightConeExtractor
from starrail_rag.extractors.relic_set import RelicSetExtractor
from starrail_rag.extractors.book import BookExtractor
from starrail_rag.extractors.item_lore import ItemLoreExtractor
from starrail_rag.extractors.wiki_category import WikiCategoryExtractor
from starrail_rag.loaders.talk_sentence import TalkSentenceIndex

logger = logging.getLogger(__name__)

# Registry mapping extractor name → class
_EXTRACTOR_REGISTRY = {
    "main_mission": MainMissionExtractor,
    "wiki_mission": WikiMissionExtractor,
    "character_story": CharacterStoryExtractor,
    "light_cone": LightConeExtractor,
    "relic_set": RelicSetExtractor,
    "book": BookExtractor,
    "item_lore": ItemLoreExtractor,
    "wiki_category": WikiCategoryExtractor,
}


@dataclass
class PipelineConfig:
    data_root: str | Path = "/workspace"
    output_dir: str | Path = "/workspace/output"
    locale: str = "CHS"
    extractors: list[str] = field(default_factory=lambda: ["main_mission"])
    mission_types: list[str] = field(default_factory=lambda: ["Main"])
    mission_ids: list[int] | None = None   # None = all matching types
    cleaning_profile: list[str] | None = None   # None = DEFAULT_PROFILE
    wiki_chapters: list[str] | None = None    # None = all chapters
    wiki_categories: list[str] | None = None  # None = all 4 categories
    wiki_request_delay: float = 1.0


@dataclass
class PipelineResult:
    extractor_name: str
    documents: list[Document]
    elapsed_seconds: float

    @property
    def non_empty_count(self) -> int:
        return sum(1 for d in self.documents if not d.is_empty())


def _document_to_dict(doc: Document) -> dict:
    return {
        "doc_id": doc.doc_id,
        "doc_type": doc.doc_type.value,
        "title": doc.title,
        "dialogues": [
            {
                "sentence_id": line.sentence_id,
                "speaker": line.speaker,
                "text": line.text,
                "voice_id": line.voice_id,
            }
            for line in doc.dialogues
        ],
        "body": doc.body,
        "metadata": doc.metadata,
    }


def run_pipeline(cfg: PipelineConfig) -> list[PipelineResult]:
    data_root = Path(cfg.data_root)
    output_dir = Path(cfg.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    resolver = TextMapResolver(data_root, locale=cfg.locale)
    cleaner = CleaningPipeline(
        profile=cfg.cleaning_profile or []
    ) if cfg.cleaning_profile is not None else CleaningPipeline()

    # Build shared TalkSentenceIndex once (avoids reloading for each extractor)
    talk_index = TalkSentenceIndex(data_root, resolver)

    results: list[PipelineResult] = []

    for extractor_name in cfg.extractors:
        cls = _EXTRACTOR_REGISTRY.get(extractor_name)
        if cls is None:
            logger.error(
                "Unknown extractor '%s'. Available: %s",
                extractor_name,
                list(_EXTRACTOR_REGISTRY),
            )
            continue

        logger.info("=== Running extractor: %s ===", extractor_name)
        t0 = time.perf_counter()

        # Pass shared index to extractors that accept it
        kwargs: dict = {}
        if extractor_name == "main_mission":
            kwargs = {
                "talk_index": talk_index,
                "filter_types": cfg.mission_types,
                "mission_ids": cfg.mission_ids,
            }
        elif extractor_name == "wiki_mission":
            kwargs = {
                "chapters": cfg.wiki_chapters,
                "request_delay": cfg.wiki_request_delay,
            }
        elif extractor_name == "wiki_category":
            kwargs = {
                "categories": cfg.wiki_categories or ["同行任务", "开拓续闻", "冒险任务", "活动任务"],
                "request_delay": cfg.wiki_request_delay,
            }

        extractor = cls(data_root, resolver, **kwargs)
        raw_docs = extractor.extract()

        # Clean all documents
        clean_docs = [cleaner.clean_document(doc) for doc in raw_docs]

        elapsed = time.perf_counter() - t0
        result = PipelineResult(
            extractor_name=extractor_name,
            documents=clean_docs,
            elapsed_seconds=elapsed,
        )
        results.append(result)

        # Persist to JSONL
        out_path = output_dir / f"{extractor_name}.jsonl"
        with open(out_path, "w", encoding="utf-8") as f:
            for doc in clean_docs:
                f.write(json.dumps(_document_to_dict(doc), ensure_ascii=False) + "\n")

        logger.info(
            "Extractor '%s' done: %d docs (%d non-empty) in %.1fs → %s",
            extractor_name,
            len(clean_docs),
            result.non_empty_count,
            elapsed,
            out_path,
        )

    return results
