"""
Import translated en.json files that come from outside the repo (a translator's
drop, a CSV export, ...) into translations/novels/.

The repo's ja.json defines the key set of a scene, so the imported file is only
mined for values: a value lands on the repo key it is stored under, and keys the
repo does not have are reported and left out. The repo file is then written
back through paths.save_novel_json, which is the format Weblate writes, so the
formatting of the imported file (indent, newline, line endings) never matters.

Existing translations are kept unless --overwrite is given. Files are only
rewritten when their content changes, so untouched scenes stay byte-identical.

PATH is a folder of scene folders, a single scene folder, or an en.json file
inside a scene folder (the scene id is the folder name).

Usage:
    PYTHONUTF8=1 python tools_en/import_translations.py PATH [PATH ...]
    PYTHONUTF8=1 python tools_en/import_translations.py PATH --dry-run
    PYTHONUTF8=1 python tools_en/import_translations.py PATH --overwrite
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths


def find_sources(path):
    """Return [(scene_id, en_json_path)] for a PATH argument."""
    path = os.path.abspath(path)
    if os.path.isfile(path):
        return [(os.path.basename(os.path.dirname(path)), path)]

    own = os.path.join(path, "en.json")
    if os.path.isfile(own):
        return [(os.path.basename(path), own)]

    found = []
    for name in sorted(os.listdir(path)):
        candidate = os.path.join(path, name, "en.json")
        if os.path.isfile(candidate):
            found.append((name, candidate))
    return found


def import_scene(scene_id, source_path, overwrite, dry_run):
    repo_path = os.path.join(paths.NOVELS_DIR, scene_id, "en.json")
    if not os.path.isfile(repo_path):
        return {"error": "scene is not in the repo"}

    repo = paths.load_json(repo_path)
    source = paths.load_json(source_path)

    result = {"added": 0, "same": 0, "kept": [], "replaced": [], "unmatched": [], "empty": 0}
    merged = dict(repo)

    for key, value in source.items():
        if key not in repo:
            result["unmatched"].append(key)
            continue
        if not value:
            result["empty"] += 1
            continue

        current = repo[key]
        if current == value:
            result["same"] += 1
        elif not current:
            merged[key] = value
            result["added"] += 1
        elif overwrite:
            merged[key] = value
            result["replaced"].append(key)
        else:
            result["kept"].append(key)

    result["changed"] = merged != repo
    if result["changed"] and not dry_run:
        paths.save_novel_json(repo_path, merged)
    return result


def preview(text, limit=60):
    text = text.replace("\n", " ")
    return text if len(text) <= limit else text[:limit] + "..."


def main():
    ap = argparse.ArgumentParser(description="Import external en.json translations by key.")
    ap.add_argument("paths", nargs="+", metavar="PATH")
    ap.add_argument("--overwrite", action="store_true",
                    help="replace translations that already exist in the repo")
    ap.add_argument("--dry-run", action="store_true", help="report only, write nothing")
    args = ap.parse_args()

    sources = []
    for p in args.paths:
        if not os.path.exists(p):
            sys.exit(f"{p}: no such file or folder")
        sources.extend(find_sources(p))
    if not sources:
        sys.exit("No en.json files found.")

    written = []
    total_unmatched = 0
    for scene_id, source_path in sources:
        r = import_scene(scene_id, source_path, args.overwrite, args.dry_run)
        if "error" in r:
            print(f"  {scene_id}: SKIPPED, {r['error']}")
            continue

        total_unmatched += len(r["unmatched"])
        if r["changed"]:
            written.append(scene_id)
        print(f"  {scene_id}: {r['added']} added, {len(r['replaced'])} replaced, "
              f"{r['same']} already identical, {len(r['kept'])} kept (differ from repo), "
              f"{len(r['unmatched'])} not in repo")
        for key in r["kept"]:
            print(f"      kept existing: {preview(key)}")

    verb = "would change" if args.dry_run else "changed"
    print(f"\n{len(written)} scene(s) {verb}; {total_unmatched} imported line(s) had no matching key.")
    if written and not args.dry_run:
        print("Next: tools_en/wrap_en.py --scene <id> for these scenes, then tools/update_manifest.py.")


if __name__ == "__main__":
    main()
