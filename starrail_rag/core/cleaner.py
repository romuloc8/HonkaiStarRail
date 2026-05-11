"""
Text cleaning pipeline.

Game strings contain engine-specific markup that must be stripped before
indexing.  Each cleaner is a pure function str -> str; the pipeline applies
them in order.

Adding a new cleaning rule:
    1. Write a function with signature (text: str) -> str
    2. Register it in CLEANER_REGISTRY
    3. Include its name in the desired CleaningProfile
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable

from starrail_rag.core.models import DialogueLine, Document

# ---------------------------------------------------------------------------
# Individual cleaning functions
# ---------------------------------------------------------------------------

# Matches layout-conditional blocks: {LAYOUT_MOBILE#Tap} {LAYOUT_KEYBOARD#Click}
_LAYOUT_TAG = re.compile(r"\{LAYOUT_\w+#([^}]*)\}")

# Matches <unbreak>…</unbreak> (used for non-breaking number spans)
_UNBREAK_TAG = re.compile(r"<unbreak>(.*?)</unbreak>", re.DOTALL)

# Matches all remaining XML/HTML-style tags
_XML_TAG = re.compile(r"<[^>]+>")

# Colour/style tags like {RUBY_B#word}text{RUBY_E} used for ruby annotations
_RUBY_TAG = re.compile(r"\{RUBY_B#[^}]*\}(.*?)\{RUBY_E\}", re.DOTALL)

# Gender-conditional: {F#她}{M#他}
_GENDER_TAG = re.compile(r"\{F#([^}]*)\}\{M#([^}]*)\}")

# Rich text tags used in book content: <size=28>, <align="center">, etc.
_RICH_TEXT_TAG = re.compile(r'</?(?:size|align|color)[^>]*>', re.IGNORECASE)

# Trailing/leading whitespace normalisation (after tag removal)
_MULTI_SPACE = re.compile(r"[ \t]{2,}")
_MULTI_NEWLINE = re.compile(r"\n{3,}")


def strip_layout_tags(text: str) -> str:
    """Replace {LAYOUT_X#Label} with just the label text."""
    return _LAYOUT_TAG.sub(r"\1", text)


def strip_unbreak_tags(text: str) -> str:
    """Remove <unbreak> wrappers, keeping inner content."""
    return _UNBREAK_TAG.sub(r"\1", text)


def strip_ruby_annotations(text: str) -> str:
    """Remove ruby annotation wrappers, keeping the annotated text."""
    return _RUBY_TAG.sub(r"\1", text)


def strip_gender_tags(text: str) -> str:
    """For gender-conditional text, keep the female form (first option)."""
    return _GENDER_TAG.sub(r"\1", text)


def strip_rich_text_tags(text: str) -> str:
    """Remove rich-text formatting tags used in book/item content."""
    return _RICH_TEXT_TAG.sub("", text)


def strip_remaining_xml(text: str) -> str:
    """Remove any other remaining XML/HTML-style tags."""
    return _XML_TAG.sub("", text)


def normalise_whitespace(text: str) -> str:
    """Collapse redundant whitespace."""
    text = _MULTI_SPACE.sub(" ", text)
    text = _MULTI_NEWLINE.sub("\n\n", text)
    return text.strip()


# ---------------------------------------------------------------------------
# Registry + profiles
# ---------------------------------------------------------------------------

CleanerFn = Callable[[str], str]

CLEANER_REGISTRY: dict[str, CleanerFn] = {
    "layout_tags": strip_layout_tags,
    "unbreak_tags": strip_unbreak_tags,
    "ruby_annotations": strip_ruby_annotations,
    "gender_tags": strip_gender_tags,
    "rich_text_tags": strip_rich_text_tags,
    "remaining_xml": strip_remaining_xml,
    "normalise_whitespace": normalise_whitespace,
}

# Default profile applied to all dialogue / body text
DEFAULT_PROFILE: list[str] = [
    "layout_tags",
    "unbreak_tags",
    "ruby_annotations",
    "gender_tags",
    "rich_text_tags",
    "remaining_xml",
    "normalise_whitespace",
]


@dataclass
class CleaningPipeline:
    """
    Ordered sequence of cleaning steps applied to Document text.

    profile:  List of cleaner names from CLEANER_REGISTRY.
              Defaults to DEFAULT_PROFILE.
    """

    profile: list[str] = field(default_factory=lambda: list(DEFAULT_PROFILE))

    def __post_init__(self) -> None:
        unknown = set(self.profile) - set(CLEANER_REGISTRY)
        if unknown:
            raise ValueError(f"Unknown cleaners: {unknown}")
        self._fns: list[CleanerFn] = [CLEANER_REGISTRY[name] for name in self.profile]

    def clean_text(self, text: str) -> str:
        for fn in self._fns:
            text = fn(text)
        return text

    def clean_document(self, doc: Document) -> Document:
        """Return a new Document with all text fields cleaned in-place."""
        doc.title = self.clean_text(doc.title)
        doc.body = self.clean_text(doc.body)
        doc.dialogues = [
            DialogueLine(
                sentence_id=line.sentence_id,
                speaker=self.clean_text(line.speaker),
                text=self.clean_text(line.text),
                voice_id=line.voice_id,
            )
            for line in doc.dialogues
        ]
        return doc
