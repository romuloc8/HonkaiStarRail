"""
TextMap resolver: converts xxhash-derived integer keys to Chinese strings.

The game stores all display text as unsigned 64-bit hash values.
TextMapCHS.json maps these as decimal string keys → Chinese string values.

Some hashes exceed int64 range and are stored as unsigned; we try both
the raw unsigned representation and the sign-extended int64 interpretation.

Logical string keys (e.g. "MissionChapterConfig_ChapterName_100000") are
resolved by computing xxhash64 of the string itself, then doing a normal
hash lookup.  This is how the game engine stores localised config values.
"""

from __future__ import annotations

import ctypes
import json
import logging
from pathlib import Path

import xxhash

logger = logging.getLogger(__name__)


class TextMapResolver:
    """
    Lazy-loading, singleton-per-locale resolver.

    Usage:
        resolver = TextMapResolver(data_root)
        text = resolver.resolve(7313040413849220147)  # -> '混乱行至深处'
        text = resolver.resolve_field({"Hash": 7313040413849220147})  # same
    """

    _instances: dict[str, TextMapResolver] = {}

    def __new__(cls, data_root: str | Path, locale: str = "CHS") -> TextMapResolver:
        key = f"{data_root}:{locale}"
        if key not in cls._instances:
            instance = super().__new__(cls)
            instance._loaded = False
            cls._instances[key] = instance
        return cls._instances[key]

    def __init__(self, data_root: str | Path, locale: str = "CHS") -> None:
        if self._loaded:
            return
        self._data_root = Path(data_root)
        self._locale = locale
        self._map: dict[str, str] = {}
        self._loaded = False

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        path = self._data_root / "TextMap" / f"TextMap{self._locale}.json"
        logger.info("Loading TextMap from %s …", path)
        with open(path, encoding="utf-8") as f:
            self._map = json.load(f)
        logger.info("TextMap loaded: %d entries", len(self._map))
        self._loaded = True

    def resolve(self, hash_value: int | None) -> str:
        """
        Resolve a hash integer to a Chinese string.
        Returns empty string if not found.
        """
        if not hash_value:
            return ""
        self._ensure_loaded()
        key = str(hash_value)
        if key in self._map:
            return self._map[key]
        # The game sometimes stores values that overflow signed int64.
        # Try interpreting the raw bits as signed.
        signed = ctypes.c_int64(hash_value).value
        return self._map.get(str(signed), "")

    def resolve_field(self, field_value: dict | str | None) -> str:
        """
        Convenience: accepts either a {"Hash": N} dict or a plain string key.

        Plain string keys (e.g. "MissionChapterConfig_ChapterName_100000")
        are resolved by computing xxhash64 of the string itself, then doing
        a normal hash lookup — this mirrors the game engine's own behaviour.
        """
        if field_value is None:
            return ""
        if isinstance(field_value, str):
            if not field_value:
                return ""
            h = xxhash.xxh64(field_value).intdigest()
            return self.resolve(h)
        if isinstance(field_value, dict):
            return self.resolve(field_value.get("Hash"))
        return ""
