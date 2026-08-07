"""
Text-wrapping utils based on the character widths defined 
in data/font_metrics.json (generated via tools_en/extract_font_metrics.py)
"""

import json
import os
import re

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONT_METRICS_PATH = os.path.join(REPO_ROOT, "data", "font_metrics.json")

MESSAGE_FONT_SIZE = 28
DOTMESSAGE_FONT_SIZE = 24

# Max total glyph width per line, in the same units as CHAR_WIDTHS.
# Calibrated in-game: a line of 44 uppercase M's fits without overflowing,
# so budget = 44 * M's width, minus a small safety margin for rounding.
MESSAGE_WIDTH_BUDGET = 1530

# useProportional renders spaces at nearly zero width; repeat them to compensate.
PROPORTIONAL_MODE = True
PROPORTIONAL_SPACE = " " * 1

# messageTextCenter and messageTextUnder are intentionally excluded due to not needing spaces
# duplicated due to their proportional text implementation being correct.
MESSAGE_COMMANDS = frozenset({"dotmessage", "message", "l2dmessage"})

with open(FONT_METRICS_PATH, "r", encoding="utf-8-sig") as _fh:
    _font_metrics = json.load(_fh)

CHAR_WIDTHS = dict(_font_metrics["widths"])
# Override space width since they're handled differently by the fontSpacing plugin
CHAR_WIDTHS[" "] = 0.4375 * CHAR_WIDTHS["M"]
_AVG_CHAR_WIDTH = sum(CHAR_WIDTHS.values()) / len(CHAR_WIDTHS)

OVERFLOW_WARNINGS = []

# The "<br> " every finished value ends with. Stripped before re-wrapping so
# running the wrapper over its own output is a no-op instead of measuring the
# tag's characters as if they were glyphs.
_TRAILING_BR = re.compile(r"<br>\s*$", re.IGNORECASE)
BR_RE = re.compile(r"<br>", re.IGNORECASE)


def normalize(text):
    """Substitutions that apply to every value, wrapped or not.

    The player placeholder is normalised *to* <user>, the reverse of what the
    assetbundle pipeline this code came from did. %user% is the message-log
    form: TranslationPatch.cs converts <user> → %user% on the way into the log
    and back again for lookup. The novel path hands values straight to the
    game's own NovelText.Parse, which resolves <user> — the same form the raw
    script and every JSON key already use.
    """
    text = text.replace("%user%", "<user>")
    return re.sub(r"…+", "...", text)


def strip_trailing_br(text):
    return _TRAILING_BR.sub("", text)


def format_dotmessage_text(en):
    """Size-tag a dotmessage text field without adding line breaks."""
    if re.search(r"<size=", en, re.IGNORECASE):
        return en
    return f"<size={DOTMESSAGE_FONT_SIZE}>{en}"


def format_message_text(en, context=""):
    """Wrap and size-tag a message text field.

    Passes through unchanged if already tagged. If the translation contains a
    <br> and both halves fit within the budget, the manual split is respected.
    Otherwise the text is re-wrapped.
    """
    if re.search(r"<size=", en, re.IGNORECASE):
        return en

    fs = MESSAGE_FONT_SIZE
    budget = MESSAGE_WIDTH_BUDGET

    br_match = re.search(r"<br>", en, re.IGNORECASE)
    if br_match:
        half1 = en[:br_match.start()]
        half2 = en[br_match.end():]
        if display_width(half1) <= budget and display_width(half2) <= budget:
            line1, line2 = half1, half2
        else:
            stripped = half1 + " " + half2
            line1, line2 = word_wrap_at(stripped, budget)
    else:
        line1, line2 = word_wrap_at(en, budget)

    # word_wrap_at only guarantees line1 fits; line2 gets whatever's left
    # over (the box only renders 2 lines), so it's the one that can silently
    # overflow when the translation is too long or has an unbreakable word.
    # Overflow <=2% is tolerated (within measurement/rounding slack).
    if line2:
        over_pct = (display_width(line2) / budget - 1) * 100
        if over_pct > 2:
            OVERFLOW_WARNINGS.append(
                f"  [{context}] line 2 overflows by {over_pct:.0f}%: {line2!r}"
            )

    if PROPORTIONAL_MODE:
        line1 = _expand_spaces(line1)
        line2 = _expand_spaces(line2) if line2 else ""
        if line2:
            return f"{line1}<br>{line2}<br> "
        return f"{line1}<br> "

    if line2:
        line1_padded = pad_to(line1, budget)
        return f"<size={fs}>{line1_padded}<br><size={fs}>{line2}<br> "
    return f"<size={fs}>{line1}<br> "


def _expand_spaces(text):
    """Replace each space with PROPORTIONAL_SPACE, preserving tags and markup."""
    return text.replace(" ", PROPORTIONAL_SPACE)


def _tokenize_wrappable(text):
    """Split text into chunks at each literal space and after each fullwidth
    comma. Concatenating the returned chunks reproduces text exactly."""
    tokens = []
    current = ""
    for ch in text:
        current += ch
        if ch == " " or ch == "，":
            tokens.append(current)
            current = ""
    if current:
        tokens.append(current)
    return tokens


def word_wrap_at(text, width_budget):
    """Split text at the last word boundary within width_budget display width."""
    if display_width(text) <= width_budget:
        return text, ""

    tokens = _tokenize_wrappable(text)
    current = ""
    last_good_split = 0

    for i, tok in enumerate(tokens):
        candidate = current + tok
        # A token carries its own trailing space (see _tokenize_wrappable).
        # If this token ends the line, that space is dropped at the <br>, so
        # it must not count against the budget when fit-checking.
        if display_width(candidate.rstrip(" ")) <= width_budget:
            current = candidate
            last_good_split = i + 1
        else:
            break

    if last_good_split == 0:
        # First word already too long; hard-split at width_budget.
        pos = 0
        dlen = 0.0
        while pos < len(text):
            dlen += char_width(text[pos])
            pos += 1
            if dlen >= width_budget:
                break
        return text[:pos], text[pos:].lstrip()

    return current.rstrip(" "), "".join(tokens[last_good_split:])


def pad_to(text, target_width):
    current = display_width(text)
    space_w = char_width(" ")
    while current < target_width:
        text += " "
        current += space_w
    return text


def char_width(ch):
    return CHAR_WIDTHS.get(ch, _AVG_CHAR_WIDTH)


def display_width(text):
    """Sum of glyph advance widths for wrap purposes."""
    return sum(char_width(ch) for ch in text)
