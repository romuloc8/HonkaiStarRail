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

# {NICKNAME} → 开拓者
_NICKNAME_TAG = re.compile(r"\{NICKNAME\}")

# Matches layout-conditional blocks: {LAYOUT_MOBILE#Tap} {LAYOUT_KEYBOARD#Click}
_LAYOUT_TAG = re.compile(r"\{LAYOUT_\w+#([^}]*)\}")

# Matches <unbreak>…</unbreak> (used for non-breaking number spans)
_UNBREAK_TAG = re.compile(r"<unbreak>(.*?)</unbreak>", re.DOTALL)

# Colour/style tags like {RUBY_B#word}text{RUBY_E} used for ruby annotations
_RUBY_TAG = re.compile(r"\{RUBY_B#[^}]*\}(.*?)\{RUBY_E\}", re.DOTALL)

# Gender-conditional: {F#她}{M#他} — keep female (F#) form
_GENDER_TAG = re.compile(r"\{F#([^}]*)\}\{M#([^}]*)\}")
# Also handle: {M#少年}{F#少女} order
_GENDER_TAG_MF = re.compile(r"\{M#([^}]*)\}\{F#([^}]*)\}")

# Rich text tags used in book content: <size=28>, <align="center">, <color=#xxx>, etc.
_RICH_TEXT_TAG = re.compile(r'</?(?:size|align|color|b|i|s|u)[^>]*>', re.IGNORECASE)

# Wiki markup: '''bold''' and ''italic''
_WIKI_BOLD_ITALIC = re.compile(r"'{2,3}([^']+)'{2,3}")

# HTML <br> and <br/> → newline
_BR_TAG = re.compile(r"<br\s*/?>", re.IGNORECASE)

# Matches all remaining XML/HTML-style tags (catch-all, after more specific rules)
_XML_TAG = re.compile(r"<[^>]+>")

# Remaining { } curly-brace tokens (game engine placeholders not matched above)
_CURLY_PLACEHOLDER = re.compile(r"\{[^}]{0,40}\}")

# Trailing/leading whitespace normalisation (after tag removal)
_MULTI_SPACE = re.compile(r"[ \t]{2,}")
_MULTI_NEWLINE = re.compile(r"\n{3,}")


def replace_nickname(text: str) -> str:
    """{NICKNAME} → 开拓者"""
    return _NICKNAME_TAG.sub("开拓者", text)


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
    """For gender-conditional text, keep the female form (少女 / 她 etc.)."""
    # {F#少女}{M#少年} → 少女
    text = _GENDER_TAG.sub(r"\1", text)
    # {M#少年}{F#少女} → 少女  (reversed order)
    text = _GENDER_TAG_MF.sub(r"\2", text)
    return text


def strip_rich_text_tags(text: str) -> str:
    """Remove rich-text formatting tags (<size=>, <align=>, <color=>, <b>, <i>, etc.)"""
    text = _BR_TAG.sub("\n", text)
    return _RICH_TEXT_TAG.sub("", text)


def strip_wiki_markup(text: str) -> str:
    """Remove wiki bold/italic markup ('''bold''' and ''italic'')."""
    return _WIKI_BOLD_ITALIC.sub(r"\1", text)


def strip_remaining_xml(text: str) -> str:
    """Remove any other remaining XML/HTML-style tags."""
    return _XML_TAG.sub("", text)


def strip_curly_placeholders(text: str) -> str:
    """Remove residual {engine_placeholder} tokens not matched by earlier rules."""
    return _CURLY_PLACEHOLDER.sub("", text)


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
    "nickname": replace_nickname,
    "layout_tags": strip_layout_tags,
    "unbreak_tags": strip_unbreak_tags,
    "ruby_annotations": strip_ruby_annotations,
    "gender_tags": strip_gender_tags,
    "rich_text_tags": strip_rich_text_tags,
    "wiki_markup": strip_wiki_markup,
    "remaining_xml": strip_remaining_xml,
    "curly_placeholders": strip_curly_placeholders,
    "normalise_whitespace": normalise_whitespace,
}

# Default profile applied to all dialogue / body text
DEFAULT_PROFILE: list[str] = [
    "nickname",
    "layout_tags",
    "unbreak_tags",
    "ruby_annotations",
    "gender_tags",
    "rich_text_tags",
    "wiki_markup",
    "remaining_xml",
    "curly_placeholders",
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
