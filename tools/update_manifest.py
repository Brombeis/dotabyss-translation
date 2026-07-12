"""
Recompute manifest/en.json hashes for every dictionary under translations/.

Usage:
    python tools/update_manifest.py
    python tools/update_manifest.py --only add-on/ui_misc
    python tools/update_manifest.py --check   # exit 1 if manifest is stale, no write
"""

import argparse
import glob
import hashlib
import json
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TRANS_DIR = os.path.join(REPO_ROOT, "translations")

FLAT_TYPES = {
    "names", "titles", "descriptions", "another_name",
    "ability_descriptions", "ui_texts",
}


def load_json(path, default):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8-sig") as fh:
            return json.load(fh)
    return default


def get_hash(d):
    parts = []
    for k in sorted(d.keys()):
        parts.extend([k, "\0", d[k], "\0"])
    return hashlib.md5("".join(parts).encode("utf-8")).hexdigest()


def classify(rel_path):
    """rel_path relative to translations/, forward-slashed en.json path."""
    parts = rel_path.split("/")
    if len(parts) == 2 and parts[0] in FLAT_TYPES:
        return "flat", parts[0]
    if len(parts) == 3 and parts[0] == "add-on":
        return "add_on", parts[1]
    if len(parts) == 3 and parts[0] == "novels":
        return "novels", parts[1]
    if len(parts) == 3 and parts[0] == "other":
        return "other", parts[1]
    if len(parts) == 2 and parts[0].startswith("m_"):
        return "m_star", parts[0]
    return None, None


def main():
    ap = argparse.ArgumentParser(description="Recompute dotabyss-translation manifest hashes.")
    ap.add_argument("--only", nargs="*", default=None,
                     help="Restrict to specific dict dirs, e.g. add-on/ui_misc names ability_descriptions")
    ap.add_argument("--language", default="en")
    ap.add_argument("--check", action="store_true",
                     help="Don't write; exit 1 if the manifest would change (for CI gating)")
    args = ap.parse_args()

    man_path = os.path.join(TRANS_DIR, "manifest", f"{args.language}.json")
    manifest = load_json(man_path, {}) or {}
    before = json.dumps(manifest, sort_keys=True, ensure_ascii=False)
    manifest.setdefault("add_on", {})
    manifest.setdefault("novels", {})
    manifest.setdefault("other", {})

    only = set(args.only) if args.only else None
    updated = []

    for path in sorted(glob.glob(os.path.join(TRANS_DIR, "**", f"{args.language}.json"), recursive=True)):
        rel = os.path.relpath(path, TRANS_DIR).replace("\\", "/")
        dict_dir = os.path.dirname(rel)
        if dict_dir == "manifest":
            continue
        if only is not None and dict_dir not in only:
            continue

        kind, key = classify(rel)
        if kind is None:
            continue

        data = load_json(path, None)
        if not isinstance(data, dict):
            print(f"  skip (not a flat dict): {rel}")
            continue

        h = get_hash(data)
        if kind == "flat" or kind == "m_star":
            if manifest.get(key) != h:
                updated.append((dict_dir, manifest.get(key), h))
            manifest[key] = h
        else:
            if manifest[kind].get(key) != h:
                updated.append((dict_dir, manifest[kind].get(key), h))
            manifest[kind][key] = h

    after = json.dumps(manifest, sort_keys=True, ensure_ascii=False)

    if args.check:
        if before != after:
            print(f"Manifest is stale: {len(updated)} hash(es) out of date")
            for dict_dir, old, new in updated:
                print(f"  {dict_dir}: {old} -> {new}")
            sys.exit(1)
        print("Manifest is up to date.")
        return

    if updated:
        with open(man_path, "w", encoding="utf-8") as fh:
            json.dump(manifest, fh, ensure_ascii=False)
        print(f"Updated {len(updated)} hash(es) in manifest/{args.language}.json:")
        for dict_dir, old, new in updated:
            print(f"  {dict_dir}: {old} -> {new}")
    else:
        print("Manifest already up to date, nothing written.")


if __name__ == "__main__":
    main()
