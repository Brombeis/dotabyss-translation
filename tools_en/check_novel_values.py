"""
Common checks for user errors in the translated lines.

  * keeping the speaker name in the translated EN line
  * using %user instead of <user> (%user% is a legacy placeholder used by the old mod)
  * empty values
  * ja.json drifting out of sync with en.json (fucks with weblate)

Usage:
    PYTHONUTF8=1 python tools_en/check_novel_values.py
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths

SPEAKER_PREFIX = re.compile(r"^\s*《[^》]*》")
MAX_REPORTED = 10


def main():
    problems = {
        "speaker prefix copied into the translation": [],
        "%user% should be <user>": [],
        "value is only whitespace": [],
        "ja.json and en.json have different keys": [],
    }

    scenes = paths.scene_dirs()
    if not scenes:
        sys.exit("No scene directories under translations/novels/.")

    for scene_id in scenes:
        scene_dir = os.path.join(paths.NOVELS_DIR, scene_id)
        en = paths.load_json(os.path.join(scene_dir, "en.json"))
        ja = paths.load_json(os.path.join(scene_dir, "ja.json"))

        if en is None or ja is None:
            problems["ja.json and en.json have different keys"].append(
                f"{scene_id}: missing {'en.json' if en is None else 'ja.json'}")
            continue
        if list(en.keys()) != list(ja.keys()):
            problems["ja.json and en.json have different keys"].append(
                f"{scene_id}: {len(ja)} ja / {len(en)} en")

        for jp, value in en.items():
            if not value:
                continue
            if SPEAKER_PREFIX.match(value):
                problems["speaker prefix copied into the translation"].append(
                    f"{scene_id}: {value[:60]!r}")
            if "%user%" in value:
                problems["%user% should be <user>"].append(f"{scene_id}: {value[:60]!r}")
            if not value.strip():
                problems["value is only whitespace"].append(f"{scene_id}: {jp[:40]!r}")

    failed = False
    for label, items in problems.items():
        if not items:
            continue
        failed = True
        print(f"\n{len(items)} × {label}:")
        for item in items[:MAX_REPORTED]:
            print(f"  {item}")
        if len(items) > MAX_REPORTED:
            print(f"  … and {len(items) - MAX_REPORTED} more")

    if failed:
        print("\nFAILED")
        return 1
    print(f"OK — {len(scenes)} scene(s) checked, no problems found.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
