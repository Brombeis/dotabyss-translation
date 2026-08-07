"""
Extract story text from bundles into translations/novels/<scene>/{ja,en}.json.

For both ja.json and en.json the key is always the originale Japanese lines,
and they should never drift apart or else weblate starts acting up.

In the ja.json file we include the speaker name inside the value so they're visible
during the translation process, be it MTL or inside weblate's own interface.

Existing translations are preserved when possible.

Usage:
    PYTHONUTF8=1 python tools_en/extract_story.py
    PYTHONUTF8=1 python tools_en/extract_story.py mas_1001000101 evs_10200010101
"""

import argparse
import difflib
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common
import paths

# Single source of truth for the hash: it has to stay byte-identical to the
# mod's own check in TranslationCache.cs.
sys.path.insert(0, os.path.join(paths.REPO_ROOT, "tools"))
from update_manifest import get_hash

SIMILARITY_THRESHOLD = 0.75

SPEAKER_OPEN = "《"   # 《
SPEAKER_CLOSE = "》"  # 》

# (scene_id, jp, en) for every translated line whose source text disappeared.
DROPPED = []
DROPPED_REPORT = "reports/dropped_translations.md"

# Commands wrap_en.py wraps into the two-line dialogue box. Everything else is
# recorded as an exception, since a translator's new text gives no clue which
# surface it is rendered on.
WRAPPED_COMMANDS = frozenset({"message", "l2dmessage"})

CATALOG_PATH = os.path.join(common.BUNDLES_CACHE, "catalog_1.bin")
SCENE_ID_RE = re.compile(r"((?:mas|hmr|hmn|men|evs)_\d+)")
TAG_RE = re.compile(r"<[^>]*>")


def similarity(a, b):
    return difflib.SequenceMatcher(None, a, b, autojunk=False).ratio()


def clean_speaker(name):
    """Strip markup from a speaker field (some carry <color=…> wrappers)."""
    return TAG_RE.sub("", name).strip()


def decorate(jp, speaker):
    """Prefix the source string with the speaker, for Weblate to display.

    《》 rather than 【】: two character names are themselves bracketed
    (【水着】ニナ), and 《》 occurs in neither the names glossary nor any of the
    42k JP lines, so the prefix stays unambiguous to read and to strip.
    """
    return f"{SPEAKER_OPEN}{speaker}{SPEAKER_CLOSE}{jp}" if speaker else jp


def catalog_story_bundles():
    """Map scene_id -> bundle filename, from the catalog of the configured CDN version.

    Reading the catalog rather than globbing bundles_cache/ matters: after a
    version bump the cache holds both the old and the new bundle for a scene
    (the filename embeds a content hash) and a glob would pick either one.
    """
    if not os.path.exists(CATALOG_PATH):
        sys.exit("bundles_cache/catalog_1.bin missing. Run tools_en/download_bundles.py first.")
    with open(CATALOG_PATH, "rb") as fh:
        catalog = fh.read()

    scenes = {}
    for name in common.list_catalog_bundles(catalog):
        if ".txt_" not in name:
            continue
        m = SCENE_ID_RE.search(name)
        if not m:
            continue
        scene_id = m.group(1)
        if scene_id in scenes and scenes[scene_id] != name:
            print(f"  WARNING {scene_id}: two catalog entries, using the first")
            continue
        scenes[scene_id] = name
    return scenes


def extract_lines(text):
    """Return ([(jp, speaker)], {jp_name: suggested_en}) in scene order, jp deduped."""
    records, names = common.parse_story(text)
    seen = set()
    lines = []
    for rec in records:
        jp = rec["jp"]
        if jp in seen:
            continue
        seen.add(jp)
        lines.append((jp, clean_speaker(rec["name"]), rec["cmd"]))
    return lines, names


def pair(old_jp, new_jp, old_en, en_out, stats):
    """Carry an EN translation across a (possibly edited) key."""
    if old_jp == new_jp:
        en_out[new_jp] = old_en.get(old_jp, "")
        return
    if similarity(old_jp, new_jp) >= SIMILARITY_THRESHOLD:
        en_out[new_jp] = old_en.get(old_jp, "")
        stats["changed"].append((old_jp, new_jp))
    else:
        en_out[new_jp] = ""
        stats["added"].append(new_jp)
        stats["removed"].append(old_jp)


def merge(old_jp_list, old_en, new_jp_list):
    en = {}
    stats = {"changed": [], "added": [], "removed": []}

    if len(old_jp_list) == len(new_jp_list):
        for old_jp, new_jp in zip(old_jp_list, new_jp_list):
            pair(old_jp, new_jp, old_en, en, stats)
        return en, stats

    opcodes = difflib.SequenceMatcher(None, old_jp_list, new_jp_list,
                                      autojunk=False).get_opcodes()
    for tag, i1, i2, j1, j2 in opcodes:
        old_block = old_jp_list[i1:i2]
        new_block = new_jp_list[j1:j2]

        if tag == "equal":
            for jp in new_block:
                en[jp] = old_en.get(jp, "")
        elif tag == "replace":
            for idx in range(max(len(old_block), len(new_block))):
                has_old = idx < len(old_block)
                has_new = idx < len(new_block)
                if has_new and has_old:
                    pair(old_block[idx], new_block[idx], old_en, en, stats)
                elif has_new:
                    en[new_block[idx]] = ""
                    stats["added"].append(new_block[idx])
                else:
                    stats["removed"].append(old_block[idx])
        elif tag == "insert":
            for jp in new_block:
                en[jp] = ""
                stats["added"].append(jp)
        elif tag == "delete":
            stats["removed"].extend(old_block)

    return en, stats


def process_scene(scene_id, bundle_name):
    bundle_path = os.path.join(common.BUNDLES_CACHE, bundle_name)
    text, _ = common.read_story_text(bundle_path)
    lines, scene_names = extract_lines(text)
    if not lines:
        return None

    new_jp_list = [jp for jp, _, _ in lines]
    ja = {jp: decorate(jp, speaker) for jp, speaker, _ in lines}

    scene_dir = os.path.join(paths.NOVELS_DIR, scene_id)
    ja_path = os.path.join(scene_dir, "ja.json")
    en_path = os.path.join(scene_dir, "en.json")

    old_ja = paths.load_json(ja_path, {}) or {}
    old_en = paths.load_json(en_path, {}) or {}

    if old_ja:
        en, stats = merge(list(old_ja.keys()), old_en, new_jp_list)
    else:
        en = {jp: "" for jp in new_jp_list}
        stats = {"changed": [], "added": new_jp_list, "removed": []}

    # A dropped line that carried a translation is the only way work can be
    # lost here, so record it instead of letting it vanish into the diff.
    for old_jp in stats["removed"]:
        if old_en.get(old_jp):
            DROPPED.append((scene_id, old_jp, old_en[old_jp]))

    exceptions = {jp: cmd for jp, _, cmd in lines if cmd not in WRAPPED_COMMANDS}

    untranslated = sum(1 for v in en.values() if not v)
    if ja == old_ja and en == old_en:
        print(f"  {scene_id}: no changes ({len(ja)} lines, {untranslated} untranslated)")
        return scene_id, en, scene_names, exceptions, False

    paths.save_novel_json(ja_path, ja)
    paths.save_novel_json(en_path, en)

    parts = []
    if not old_ja:
        parts.append("new scene")
    if stats["changed"]:
        parts.append(f"{len(stats['changed'])} JP updated")
    if stats["added"]:
        parts.append(f"{len(stats['added'])} added")
    if stats["removed"]:
        parts.append(f"{len(stats['removed'])} removed")
    summary = ", ".join(parts) if parts else "speaker names only"
    print(f"  {scene_id}: {len(ja)} lines ({summary}, {untranslated} untranslated)")
    for old_jp, new_jp in stats["changed"][:3]:
        print(f"    - {old_jp[:70]!r}")
        print(f"    + {new_jp[:70]!r}")

    return scene_id, en, scene_names, exceptions, True


def update_names(all_names):
    """Add newly seen speakers to the glossary; never touch existing entries."""
    ja_path = os.path.join(paths.NAMES_DIR, "ja.json")
    en_path = os.path.join(paths.NAMES_DIR, "en.json")
    ja = paths.load_json(ja_path, {}) or {}
    en = paths.load_json(en_path, {}) or {}

    added = 0
    for name in all_names:
        if name not in en:
            en[name] = ""
            added += 1
        ja[name] = name

    if added:
        paths.save_indented_json(ja_path, ja)
        paths.save_indented_json(en_path, en)
    print(f"\nNames glossary: {len(en)} entries ({added} new, "
          f"{sum(1 for v in en.values() if not v)} untranslated)")
    return en, added > 0


def write_wrap_exceptions(processed):
    """Merge this run's line-kind exceptions into data/wrap_exceptions.json.

    `scenes` lists every scene that has been extracted, so wrap_en.py can tell
    "this scene has no exceptions" apart from "this scene was never extracted".
    Merged rather than overwritten so a single-scene run doesn't wipe the rest.
    """
    doc = paths.load_json(paths.WRAP_EXCEPTIONS_PATH, {}) or {}
    scenes = set(doc.get("scenes", []))
    exceptions = doc.get("exceptions", {})

    for scene_id, scene_exceptions in processed.items():
        scenes.add(scene_id)
        if scene_exceptions:
            exceptions[scene_id] = scene_exceptions
        else:
            exceptions.pop(scene_id, None)

    total = sum(len(v) for v in exceptions.values())
    paths.save_indented_json(paths.WRAP_EXCEPTIONS_PATH, {
        "comment": "Lines that are NOT plain two-line dialogue. wrap_en.py wraps "
                   "anything absent from here as a message.",
        "scenes": sorted(scenes),
        "exceptions": {k: exceptions[k] for k in sorted(exceptions)},
    })
    print(f"Wrap exceptions: {total} line(s) across {len(exceptions)} scene(s) "
          f"({len(scenes)} scenes known)")


def write_dropped_report():
    path = os.path.join(paths.REPO_ROOT, *DROPPED_REPORT.split("/"))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("# Translations dropped by the last extraction\n\n")
        fh.write("These lines had an English translation, but the Japanese source no longer\n"
                 "appears in the game script — usually because the writers merged, split or\n"
                 "rewrote it. The text is kept here so it can be reused on the new line.\n\n")
        for scene_id, jp, en in DROPPED:
            fh.write(f"## {scene_id}\n\n- JP: `{jp}`\n- EN: `{en}`\n\n")


def main():
    ap = argparse.ArgumentParser(
        description="Extract story bundles into translations/novels/<scene>/{ja,en}.json"
    )
    ap.add_argument("scenes", nargs="*", help="scene IDs (default: every scene in the catalog)")
    ap.add_argument("--no-names", action="store_true",
                    help="don't touch translations/names/")
    args = ap.parse_args()

    catalog_scenes = catalog_story_bundles()
    if args.scenes:
        unknown = [s for s in args.scenes if s not in catalog_scenes]
        if unknown:
            print(f"Warning: not in catalog: {', '.join(unknown)}")
        wanted = {s: catalog_scenes[s] for s in args.scenes if s in catalog_scenes}
    else:
        wanted = catalog_scenes

    missing = [s for s, b in wanted.items()
               if not os.path.exists(os.path.join(common.BUNDLES_CACHE, b))]
    if missing:
        print(f"Skipping {len(missing)} scene(s) whose bundle isn't cached "
              f"(run download_bundles.py): {', '.join(sorted(missing)[:5])}"
              f"{' …' if len(missing) > 5 else ''}")
        wanted = {s: b for s, b in wanted.items() if s not in missing}

    print(f"Processing {len(wanted)} scene(s)...")
    written, all_names, failures, exceptions = [], {}, [], {}
    for scene_id in sorted(wanted):
        try:
            result = process_scene(scene_id, wanted[scene_id])
        except Exception as e:
            print(f"  {scene_id}: ERROR — {e}")
            failures.append(scene_id)
            continue
        if not result:
            continue
        sid, en, scene_names, scene_exceptions, changed = result
        exceptions[sid] = scene_exceptions
        for jp_name in scene_names:
            all_names.setdefault(clean_speaker(jp_name) or jp_name, "")
        if changed:
            written.append((sid, en))

    write_wrap_exceptions(exceptions)

    names_en = None
    if not args.no_names:
        names_en, names_changed = update_names(all_names)
        if not names_changed:
            names_en = None

    if written or names_en is not None:
        manifest = paths.load_json(paths.MANIFEST_PATH, {}) or {}
        manifest.setdefault("novels", {})
        for scene_id, en in written:
            manifest["novels"][scene_id] = get_hash(en)
        if names_en is not None:
            manifest["names"] = get_hash(names_en)
        paths.save_manifest(manifest)

    if DROPPED:
        write_dropped_report()
        print(f"\n{len(DROPPED)} translated line(s) dropped because their Japanese source "
              f"no longer exists in the script.\nRecovered text saved to {DROPPED_REPORT}")

    print(f"\nDone. {len(written)} scene(s) written, {len(failures)} error(s).")
    if failures:
        print("  failed: " + ", ".join(failures))
    print("Review the diff and commit when ready — do not push without explicit approval.")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
