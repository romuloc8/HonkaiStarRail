"""
TalkSentenceConfig index builder.

TalkSentenceConfig.json is ~1.9 M lines / 223 k records.  Loading it via
json.load is fine (≈ 2–3 s), but we index it once and reuse the lookup dict.

Each record looks like:
    {
      "TalkSentenceID": 200010201,
      "VoiceID": 200010201,
      "TextmapTalkSentenceName": {"Hash": 13442442258855365591},
      "TalkSentenceText": {"Hash": 18377528490008794216}
    }

Some records are missing "TextmapTalkSentenceName" (narration lines).
Some records are missing "TalkSentenceID" altogether (malformed entries);
those are silently skipped.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

from starrail_rag.core.textmap import TextMapResolver

logger = logging.getLogger(__name__)


@dataclass
class ResolvedSentence:
    sentence_id: int
    speaker: str   # empty = narration
    text: str
    voice_id: int | None


class TalkSentenceIndex:
    """
    Prebuilt lookup: TalkSentenceID (int) -> ResolvedSentence.

    Pass a TextMapResolver so the index can resolve hashes at build time,
    avoiding repeated map lookups during extraction.
    """

    def __init__(self, data_root: str | Path, resolver: TextMapResolver) -> None:
        self._data_root = Path(data_root)
        self._resolver = resolver
        self._index: dict[int, ResolvedSentence] = {}
        self._built = False

    def _build(self) -> None:
        path = self._data_root / "ExcelOutput" / "TalkSentenceConfig.json"
        logger.info("Building TalkSentence index from %s …", path)
        with open(path, encoding="utf-8") as f:
            records = json.load(f)

        skipped = 0
        for record in records:
            sid = record.get("TalkSentenceID")
            if sid is None:
                skipped += 1
                continue

            speaker_hash = (record.get("TextmapTalkSentenceName") or {}).get("Hash")
            text_hash = (record.get("TalkSentenceText") or {}).get("Hash")

            self._index[sid] = ResolvedSentence(
                sentence_id=sid,
                speaker=self._resolver.resolve(speaker_hash),
                text=self._resolver.resolve(text_hash),
                voice_id=record.get("VoiceID"),
            )

        logger.info(
            "TalkSentence index built: %d entries, %d skipped",
            len(self._index),
            skipped,
        )
        self._built = True

    def ensure_built(self) -> None:
        if not self._built:
            self._build()

    def get(self, sentence_id: int) -> ResolvedSentence | None:
        self.ensure_built()
        return self._index.get(sentence_id)

    def get_many(self, sentence_ids: list[int]) -> list[ResolvedSentence]:
        self.ensure_built()
        return [s for sid in sentence_ids if (s := self._index.get(sid)) is not None]
