"""
Apply line-breaking to each EN line

Usage:
    PYTHONUTF8=1 python tools_en/wrap_en.py
    PYTHONUTF8=1 python tools_en/wrap_en.py --check     # exit 1 if anything would change
    PYTHONUTF8=1 python tools_en/wrap_en.py --scene mas_1001010701
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths
import wrap_text

REPORT_PATH = os.path.join(paths.REPO_ROOT, "reports", "overflow.md")

# What a line is assumed to be when data/wrap_exceptions.json doesn't mention it.
DEFAULT_COMMAND = "message"

# Commands whose text is rendered somewhere other than the two-line dialogue
# box; they get the shared substitutions but no wrapping.
NO_WRAP_COMMANDS = frozenset({"messageTextCenter", "messageTextUnder", "title"})


def format_value(value, cmd, context):
    """Return the game-ready form of one EN translation."""
    if not value:
        return value

    text = wrap_text.normalize(value)
    # Re-wrapping has to start from the unwrapped text, or the trailing "<br> "
    # of an already-processed value would be measured as if it were glyphs and
    # every run would reflow the file.
    text = wrap_text.strip_trailing_br(text)

    if cmd == "dotmessage":
        return wrap_text.format_dotmessage_text(text)
    if cmd in wrap_text.MESSAGE_COMMANDS:
        # The box renders two lines, so a value carrying more than one break is
        # already broken. Drop the manual breaks and let the wrapper re-decide;
        # a single <br> is left in place, since format_message_text honours it
        # when both halves fit.
        if len(wrap_text.BR_RE.findall(text)) > 1:
            text = wrap_text.BR_RE.sub(" ", text)
        return wrap_text.format_message_text(text, context=context)
    if cmd in NO_WRAP_COMMANDS:
        # Rendered outside the two-line box; substitutions only, keep the
        # translator's own line breaks.
        return wrap_text.normalize(value)
    return value


def process_scene(scene_id, exceptions, write):
    """Returns (changed_count, total_count)."""
    en_path = os.path.join(paths.NOVELS_DIR, scene_id, "en.json")
    en = paths.load_json(en_path)
    if en is None:
        return 0, 0

    changed = 0
    out = {}
    for jp, value in en.items():
        # Absent from the exception list means plain two-line dialogue, which
        # is 97.5% of lines.
        cmd = exceptions.get(jp, DEFAULT_COMMAND)
        new_value = format_value(value, cmd, context=f"{scene_id}:{jp[:24]}")
        out[jp] = new_value
        if new_value != value:
            changed += 1

    if changed and write:
        paths.save_novel_json(en_path, out)
    return changed, len(en)


def main():
    ap = argparse.ArgumentParser(description="Wrap EN story translations to the dialogue box width.")
    ap.add_argument("--check", action="store_true",
                    help="don't write; exit 1 if any value would change")
    ap.add_argument("--scene", action="append", default=None,
                    help="limit to these scene ids (repeatable)")
    ap.add_argument("--quiet", action="store_true", help="only print the summary")
    args = ap.parse_args()

    scenes = args.scene if args.scene else paths.scene_dirs()
    if not scenes:
        sys.exit("No scene directories under translations/novels/.")

    doc = paths.load_json(paths.WRAP_EXCEPTIONS_PATH)
    if doc is None:
        sys.exit(f"{os.path.relpath(paths.WRAP_EXCEPTIONS_PATH, paths.REPO_ROOT)} is missing. "
                 f"Run tools_en/extract_story.py — without it every title and dotmessage "
                 f"would be wrapped as ordinary dialogue.")
    known = set(doc.get("scenes", []))
    all_exceptions = doc.get("exceptions", {})

    # A scene absent from the file was never extracted, so we have no idea which
    # of its lines are titles. Guessing would silently mangle them.
    unknown_scenes = [s for s in scenes if s not in known]
    if unknown_scenes:
        sys.exit(f"{len(unknown_scenes)} scene(s) missing from "
                 f"{os.path.basename(paths.WRAP_EXCEPTIONS_PATH)}: "
                 f"{', '.join(sorted(unknown_scenes)[:5])}"
                 f"{' …' if len(unknown_scenes) > 5 else ''}\n"
                 f"Run tools_en/extract_story.py to refresh it.")

    total_changed = total_lines = 0
    changed_scenes = []
    for scene_id in scenes:
        changed, count = process_scene(scene_id, all_exceptions.get(scene_id, {}),
                                       write=not args.check)
        total_changed += changed
        total_lines += count
        if changed:
            changed_scenes.append((scene_id, changed))
            if not args.quiet:
                print(f"  {scene_id}: {changed}/{count} value(s) rewrapped")

    print(f"\n{total_lines} value(s) checked, {total_changed} changed "
          f"across {len(changed_scenes)} scene(s).")

    if wrap_text.OVERFLOW_WARNINGS:
        print(f"\n{len(wrap_text.OVERFLOW_WARNINGS)} line(s) overflow the dialogue box "
              f"(translation too long or has an unbreakable word). "
              f"See reports/overflow.md")
        write_report()

    if args.check and total_changed:
        print("\n--check: values are not in wrapped form.")
        return 1
    return 0


def write_report():
    os.makedirs(os.path.dirname(REPORT_PATH), exist_ok=True)
    with open(REPORT_PATH, "w", encoding="utf-8") as fh:
        fh.write("# Dialogue lines overflowing the box\n\n")
        fh.write(f"{len(wrap_text.OVERFLOW_WARNINGS)} line(s). The second line of the "
                 f"dialogue box is wider than the {wrap_text.MESSAGE_WIDTH_BUDGET}-unit "
                 f"budget, usually because the translation is longer than the Japanese "
                 f"or contains an unbreakable word.\n\n")
        for w in wrap_text.OVERFLOW_WARNINGS:
            fh.write(f"-{w}\n")


if __name__ == "__main__":
    sys.exit(main())
