"""
开拓任务（Main Mission）剧情提取器。

数据链路
--------
MainMission.json  (Type in filter_types)
    ↓  mission_id, chapter_id, name hash
MissionChapterConfig.json
    ↓  chapter_name (logical textmap key)
PerformanceE.json
    ↓  PerformancePath  →  Config/Level/Mission/{id}/Act/*.json
                        or  Config/Level/Mission/{id}/Talk/*.json
Act/Talk JSON files
    ↓  RPG.GameCore.PlayAndWaitSimpleTalk / PlaySimpleTalk
       → TalkSentenceID list (ordered)
TalkSentenceIndex
    ↓  speaker + text (already resolved via TextMapCHS)
→  Document(doc_type=DocType.MAIN_MISSION, dialogues=[...])

Notes
-----
- Some PerformancePaths point to files that do not exist in this data dump;
  those are skipped with a debug-level warning.
- Dialogue ordering follows the order Act files are encountered via the
  PerformanceE index.  Within each Act file the TaskList order is preserved.
- `filter_types` defaults to ["Main"] (开拓主线) but can be extended to
  include "Companion", "Branch" etc. by the caller.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from starrail_rag.core.models import DialogueLine, DocType, Document
from starrail_rag.core.textmap import TextMapResolver
from starrail_rag.extractors.base import BaseExtractor
from starrail_rag.loaders.talk_sentence import TalkSentenceIndex

logger = logging.getLogger(__name__)

# GameCore task types that embed TalkSentenceID lists (SimpleTalkList)
_SIMPLE_TALK_TYPES = {
    "RPG.GameCore.PlayAndWaitSimpleTalk",
    "RPG.GameCore.PlaySimpleTalk",
    "RPG.GameCore.WaitSimpleTalkFinish",
    # Newer format (翁法罗斯+): same SimpleTalkList structure
    "RPG.GameCore.PlayMissionTalk",
}

# GameCore task types that embed TalkSentenceIDs in other list fields
_BUBBLE_TALK_TYPES = {
    # BubbleTalkInfoList[].TalkSentenceID
    "RPG.GameCore.PlayNPCBubbleTalk",
}

_OPTION_TALK_TYPES = {
    # OptionList[].TalkSentenceID  (player dialogue choices)
    "RPG.GameCore.PlayOptionTalk",
}


def _get_fixed_value(field: Any) -> int | None:
    """Extract integer from {IsDynamic, FixedValue: {Value: N}} wrapper."""
    if isinstance(field, dict):
        fv = field.get("FixedValue", {})
        if isinstance(fv, dict):
            v = fv.get("Value")
            if isinstance(v, int):
                return v
    if isinstance(field, int):
        return field
    return None


def _extract_sentence_ids_from_node(node: Any, result: list[int]) -> None:
    """Recursively walk a parsed JSON node and collect TalkSentenceIDs."""
    if isinstance(node, dict):
        task_type = node.get("$type", "")

        if task_type in _SIMPLE_TALK_TYPES:
            # Variant A: explicit SimpleTalkList
            for item in node.get("SimpleTalkList", []):
                sid = item.get("TalkSentenceID")
                if isinstance(sid, int):
                    result.append(sid)
            # Variant B (PlayMissionTalk only): StartSentenceID..EndSentenceID range
            start = _get_fixed_value(node.get("StartSentenceID"))
            end = _get_fixed_value(node.get("EndSentenceID"))
            if start is not None and end is not None and end >= start:
                result.extend(range(start, end + 1))

        elif task_type in _BUBBLE_TALK_TYPES:
            for item in node.get("BubbleTalkInfoList", []):
                sid = item.get("TalkSentenceID")
                if isinstance(sid, int):
                    result.append(sid)

        elif task_type in _OPTION_TALK_TYPES:
            for item in node.get("OptionList", []):
                sid = item.get("TalkSentenceID")
                if isinstance(sid, int):
                    result.append(sid)

        for value in node.values():
            _extract_sentence_ids_from_node(value, result)

    elif isinstance(node, list):
        for item in node:
            _extract_sentence_ids_from_node(item, result)


def _load_sentence_ids_from_path(abs_path: Path) -> list[int]:
    """Parse an Act/Talk file and return ordered TalkSentenceIDs."""
    try:
        with open(abs_path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        logger.debug("Cannot read %s: %s", abs_path, exc)
        return []
    result: list[int] = []
    _extract_sentence_ids_from_node(data, result)
    return result


class MainMissionExtractor(BaseExtractor):
    """
    Extracts narrative dialogue for 开拓任务 (and optionally related types).

    Parameters
    ----------
    data_root:
        Root of the StarRailData repository.
    resolver:
        Shared TextMapResolver (CHS by default).
    talk_index:
        Pre-built TalkSentenceIndex.  Pass one in if you are running
        multiple extractors so the large JSON is only parsed once.
    filter_types:
        Which MainMission.Type values to include.
        Defaults to ["Main"].  Pass ["Main", "Companion"] to also pull
        同行任务.
    mission_ids:
        Optional whitelist of MainMissionIDs.  None means all matching types.
    """

    def __init__(
        self,
        data_root: str | Path,
        resolver: TextMapResolver,
        talk_index: TalkSentenceIndex | None = None,
        filter_types: list[str] | None = None,
        mission_ids: list[int] | None = None,
    ) -> None:
        super().__init__(data_root, resolver)
        self._talk_index = talk_index or TalkSentenceIndex(data_root, resolver)
        self._filter_types = set(filter_types or ["Main"])
        self._mission_ids = set(mission_ids) if mission_ids else None

    @property
    def name(self) -> str:
        return "MainMissionExtractor"

    # ------------------------------------------------------------------
    # Internal loaders
    # ------------------------------------------------------------------

    def _load_missions(self) -> list[dict]:
        path = self.data_root / "ExcelOutput" / "MainMission.json"
        with open(path, encoding="utf-8") as f:
            all_missions = json.load(f)
        missions = [
            m for m in all_missions
            if m.get("Type") in self._filter_types
            and (self._mission_ids is None or m.get("MainMissionID") in self._mission_ids)
        ]
        logger.info(
            "Loaded %d missions (types=%s)", len(missions), self._filter_types
        )
        return missions

    def _load_chapter_map(self) -> dict[int, str]:
        """chapter_id → resolved Chinese chapter name."""
        path = self.data_root / "ExcelOutput" / "MissionChapterConfig.json"
        with open(path, encoding="utf-8") as f:
            rows = json.load(f)
        return {
            row["ID"]: self.resolver.resolve_field(row.get("ChapterName", ""))
            for row in rows
        }

    def _build_performance_index(self) -> dict[int, str]:
        """PerformanceID → relative PerformancePath string."""
        path = self.data_root / "ExcelOutput" / "PerformanceE.json"
        with open(path, encoding="utf-8") as f:
            rows = json.load(f)
        return {row["PerformanceID"]: row["PerformancePath"] for row in rows}

    # ------------------------------------------------------------------
    # Act / Talk file discovery
    # ------------------------------------------------------------------

    def _collect_performance_paths(
        self, mission_id: int, perf_index: dict[int, str]
    ) -> list[Path]:
        """
        Return an ordered list of script files for a given mission.

        Two formats exist:
        - Old (序章–匹诺康尼): PerformanceE.json indexes Act/*.json and Talk_*.json
        - New (翁法罗斯+):     Mission_*.json files live directly in
          Config/Level/Mission/{mission_id}/, bypassing PerformanceE entirely.

        We collect both and deduplicate.
        """
        mission_str = str(mission_id)
        paths: list[Path] = []
        seen: set[Path] = set()

        def _add(p: Path) -> None:
            if p not in seen and p.exists():
                seen.add(p)
                paths.append(p)

        # --- Old format: PerformanceE index ---
        for perf_path in perf_index.values():
            if mission_str not in perf_path:
                continue
            abs_path = self.data_root / perf_path
            if abs_path.exists():
                _add(abs_path)
            else:
                logger.debug("Performance path not found on disk: %s", perf_path)

        # --- New format: Mission_*.json directly in mission folder ---
        mission_dir = self.data_root / "Config" / "Level" / "Mission" / mission_str
        if mission_dir.exists():
            for f in sorted(mission_dir.iterdir()):
                if f.name.startswith("Mission_") and f.suffix == ".json":
                    _add(f)

        # Deterministic ordering: Act/ before Talk_/ before Mission_, then by name
        def _sort_key(p: Path) -> tuple:
            name = p.name
            parent = p.parent.name
            if parent == "Act":
                return (0, name)
            if name.startswith("Talk_"):
                return (1, name)
            if name.startswith("Mission_"):
                return (2, name)
            return (3, name)

        paths.sort(key=_sort_key)
        return paths

    # ------------------------------------------------------------------
    # Main extraction logic
    # ------------------------------------------------------------------

    def _extract_mission(
        self,
        mission: dict,
        chapter_map: dict[int, str],
        perf_index: dict[int, str],
    ) -> Document | None:
        mission_id: int = mission["MainMissionID"]
        mission_name = self.resolver.resolve_field(mission.get("Name", {}))
        chapter_id: int = mission.get("ChapterID", 0)
        chapter_name = chapter_map.get(chapter_id, "")
        mission_type: str = mission.get("Type", "")

        perf_paths = self._collect_performance_paths(mission_id, perf_index)
        if not perf_paths:
            logger.debug("No performance paths found for mission %d", mission_id)

        # Collect TalkSentenceIDs preserving scene order
        all_sentence_ids: list[int] = []
        for path in perf_paths:
            ids = _load_sentence_ids_from_path(path)
            all_sentence_ids.extend(ids)

        # De-duplicate while preserving first-occurrence order
        seen_ids: set[int] = set()
        unique_ids: list[int] = []
        for sid in all_sentence_ids:
            if sid not in seen_ids:
                seen_ids.add(sid)
                unique_ids.append(sid)

        # Resolve to dialogue lines
        self._talk_index.ensure_built()
        dialogues: list[DialogueLine] = []
        for sid in unique_ids:
            sentence = self._talk_index.get(sid)
            if sentence is None:
                logger.debug("TalkSentenceID %d not in index", sid)
                continue
            if not sentence.text:
                continue
            dialogues.append(
                DialogueLine(
                    sentence_id=sid,
                    speaker=sentence.speaker,
                    text=sentence.text,
                    voice_id=sentence.voice_id,
                )
            )

        doc = Document(
            doc_id=f"main_mission_{mission_id}",
            doc_type=DocType.MAIN_MISSION,
            title=mission_name,
            dialogues=dialogues,
            metadata={
                "mission_id": mission_id,
                "mission_type": mission_type,
                "chapter_id": chapter_id,
                "chapter_name": chapter_name,
                "world_id": mission.get("WorldID"),
                "next_mission": mission.get("NextTrackMainMission"),
                "performance_file_count": len(perf_paths),
                "sentence_count": len(dialogues),
            },
        )
        return doc

    def extract(self) -> list[Document]:
        missions = self._load_missions()
        chapter_map = self._load_chapter_map()
        perf_index = self._build_performance_index()

        documents: list[Document] = []
        for mission in missions:
            mid = mission.get("MainMissionID")
            try:
                doc = self._extract_mission(mission, chapter_map, perf_index)
                if doc is not None:
                    documents.append(doc)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Failed to extract mission %s: %s", mid, exc)

        non_empty = [d for d in documents if not d.is_empty()]
        logger.info(
            "Extracted %d/%d non-empty mission documents",
            len(non_empty),
            len(documents),
        )
        return documents
