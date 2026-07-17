"""
Extract story text from bundles and write/update translations/novels/<scene>/{en,ja}.json.

Same line count
    Lines are paired positionally. If a JP line changed (minor punctuation fix etc.),
    the key is updated in both files and the existing EN translation is carried forward.

Different line count
    difflib aligns old and new JP sequences. Within each replaced block, lines are
    paired positionally and their character similarity is measured:
      >= 0.75  minor edit  — update key, carry EN forward
      <  0.75  new content — leave EN empty (needs retranslation)
    Inserted lines get an empty EN. Deleted lines are dropped from both files.

New files
    Creates the scene directory and both JSON files with all EN values empty.

After writing, updates the manifest hashes for any changed scene.

Usage:
    PYTHONUTF8=1 python tools/extract_story.py
    PYTHONUTF8=1 python tools/extract_story.py mas_1001000101 evs_10200010101
"""

import argparse
import difflib
import glob
import hashlib
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bundle_common as bc

SIMILARITY_THRESHOLD = 0.75


def scene_id_from_filename(filename):
    m = re.search(r"((?:mas|hmr|hmn|men|evs)_\d+)", filename)
    return m.group(1) if m else None


def similarity(a, b):
    return difflib.SequenceMatcher(None, a, b, autojunk=False).ratio()


def merge_same_count(old_jp_list, old_en, new_jp_list):
    """Pair lines positionally; carry EN forward even when JP key changes."""
    ja, en, changed = {}, {}, []
    for old_jp, new_jp in zip(old_jp_list, new_jp_list):
        ja[new_jp] = new_jp
        en[new_jp] = old_en.get(old_jp, "")
        if old_jp != new_jp:
            changed.append((old_jp, new_jp))
    return ja, en, changed


def merge_diff_count(old_jp_list, old_en, new_jp_list):
    """Align with difflib; use character similarity to distinguish edits from new lines."""
    ja, en = {}, {}
    changed, added, removed = [], [], []
    opcodes = difflib.SequenceMatcher(None, old_jp_list, new_jp_list, autojunk=False).get_opcodes()

    for tag, i1, i2, j1, j2 in opcodes:
        old_block = old_jp_list[i1:i2]
        new_block = new_jp_list[j1:j2]

        if tag == "equal":
            for jp in new_block:
                ja[jp] = jp
                en[jp] = old_en.get(jp, "")

        elif tag == "replace":
            for idx in range(max(len(old_block), len(new_block))):
                has_old = idx < len(old_block)
                has_new = idx < len(new_block)
                if has_new:
                    new_jp = new_block[idx]
                    ja[new_jp] = new_jp
                    if has_old:
                        old_jp = old_block[idx]
                        if similarity(old_jp, new_jp) >= SIMILARITY_THRESHOLD:
                            en[new_jp] = old_en.get(old_jp, "")
                            if old_jp != new_jp:
                                changed.append((old_jp, new_jp))
                        else:
                            en[new_jp] = ""
                            added.append(new_jp)
                            removed.append(old_jp)
                    else:
                        en[new_jp] = ""
                        added.append(new_jp)
                elif has_old:
                    removed.append(old_block[idx])

        elif tag == "insert":
            for jp in new_block:
                ja[jp] = jp
                en[jp] = ""
                added.append(jp)

        elif tag == "delete":
            removed.extend(old_block)

    return ja, en, changed, added, removed


def get_hash(d):
    parts = []
    for k in sorted(d.keys()):
        parts.extend([k, "\0", d[k], "\0"])
    return hashlib.md5("".join(parts).encode("utf-8")).hexdigest()


def process_scene(scene_id, bundle_path):
    text, _ = bc.read_story_text(bundle_path)
    new_jp_list, _ = bc.parse_story_lines(text)
    if not new_jp_list:
        return None

    scene_dir = os.path.join(bc.NOVELS_DIR, scene_id)
    ja_path = os.path.join(scene_dir, "ja.json")
    en_path = os.path.join(scene_dir, "en.json")

    if not os.path.exists(ja_path):
        ja = {jp: jp for jp in new_jp_list}
        en = {jp: "" for jp in new_jp_list}
        bc.save_weblate_pair(scene_dir, ja, en)
        print(f"  {scene_id}: {len(ja)} lines (new)")
        return scene_id, en

    old_ja = bc.load_json(ja_path, {}) or {}
    old_en = bc.load_json(en_path, {}) or {}
    old_jp_list = list(old_ja.keys())

    if len(old_jp_list) == len(new_jp_list):
        ja, en, changed = merge_same_count(old_jp_list, old_en, new_jp_list)
        added = removed = []
    else:
        ja, en, changed, added, removed = merge_diff_count(old_jp_list, old_en, new_jp_list)

    if ja == old_ja and en == old_en:
        untranslated = sum(1 for v in en.values() if not v)
        print(f"  {scene_id}: no changes ({len(ja)} lines, {untranslated} untranslated)")
        return None

    bc.save_weblate_pair(scene_dir, ja, en)
    untranslated = sum(1 for v in en.values() if not v)

    parts = []
    if changed:
        parts.append(f"{len(changed)} JP updated")
    if added:
        parts.append(f"{len(added)} added")
    if removed:
        parts.append(f"{len(removed)} removed")
    summary = ", ".join(parts) if parts else "no structural changes"
    print(f"  {scene_id}: {len(ja)} lines ({summary}, {untranslated} untranslated)")
    for old_jp, new_jp in changed[:3]:
        print(f"    - {old_jp[:70]!r}")
        print(f"    + {new_jp[:70]!r}")

    return scene_id, en


def main():
    ap = argparse.ArgumentParser(
        description="Extract story from bundles into translations/novels/<scene>/{en,ja}.json"
    )
    ap.add_argument("scenes", nargs="*",
                    help="Scene IDs to process (default: all bundles in bundles_cache/)")
    args = ap.parse_args()

    scene_prefixes = ("mas", "hmr", "hmn", "men", "evs")
    all_bundles = {}
    for prefix in scene_prefixes:
        for p in glob.glob(os.path.join(bc.BUNDLES_CACHE, f"*{prefix}_*.txt_*.bundle")):
            sid = scene_id_from_filename(os.path.basename(p))
            if sid and re.fullmatch(r"(?:mas|hmr|hmn|men|evs)_\d+", sid):
                all_bundles[sid] = p

    if not all_bundles:
        sys.exit("No story bundles in bundles_cache/. Run tools/download_bundles.py first.")

    if args.scenes:
        missing = [sid for sid in args.scenes if sid not in all_bundles]
        if missing:
            print(f"Warning: not found in bundles_cache/: {', '.join(missing)}")
        to_process = {sid: all_bundles[sid] for sid in args.scenes if sid in all_bundles}
    else:
        to_process = all_bundles

    print(f"Processing {len(to_process)} bundle(s)...")
    updated = []
    for scene_id in sorted(to_process):
        try:
            result = process_scene(scene_id, to_process[scene_id])
            if result:
                updated.append(result)
        except Exception as e:
            print(f"  {scene_id}: ERROR — {e}")

    if not updated:
        print("Nothing changed.")
        return

    man_path = os.path.join(bc.REPO_ROOT, "translations", "manifest", "en.json")
    manifest = bc.load_json(man_path, {}) or {}
    manifest.setdefault("novels", {})
    for scene_id, en in updated:
        manifest["novels"][scene_id] = get_hash(en)
    with open(man_path, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, ensure_ascii=False)

    print(f"\nDone. {len(updated)} scene(s) written. Manifest updated.")
    print("Review the diff and commit when ready — do not push without explicit approval.")


if __name__ == "__main__":
    main()
