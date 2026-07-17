"""
Shared helpers for story bundle downloading and extraction.
Requires: UnityPy  (pip install unitypy)
"""

import json
import os
import re
import struct

import UnityPy

# Bump CDN_VERSION when the game updates (old version 404s at the CDN).
CDN_HOST = "api.abyss-prod-r18.dotabyss.dmmgames.com"
CDN_CHANNEL = "r18"
CDN_VERSION = "6074"
CDN_BASE = f"https://{CDN_HOST}/resources/webgl/{CDN_CHANNEL}/aas/{CDN_VERSION}/aa/"
CATALOG_URL = CDN_BASE + "catalog_1.bin"

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUNDLES_CACHE = os.path.join(REPO_ROOT, "bundles_cache")
NOVELS_DIR = os.path.join(REPO_ROOT, "translations", "novels")


def bundle_url(filename):
    return CDN_BASE + filename


def list_catalog_bundles(catalog_bytes, downloadable_only=True):
    """Extract bundle filenames from a binary Addressables catalog."""
    max_name_len = 1024
    found = set()
    i = 0
    while True:
        j = catalog_bytes.find(b".bundle", i)
        if j < 0:
            break
        end = j + 7
        for s in range(max(0, end - max_name_len), end - 7):
            if s - 4 < 0:
                continue
            if struct.unpack_from("<i", catalog_bytes, s - 4)[0] == end - s:
                chunk = catalog_bytes[s:end]
                if all(32 <= b < 127 for b in chunk):
                    found.add(chunk.decode())
                    break
        i = end
    if downloadable_only:
        found = {n for n in found if "_assets_" in n or "_project_" in n}
    return sorted(found)


# Which fields in each command carry on-screen text vs. internal handles.
TRANSLATABLE = {
    "dotmessage":        {1: "name", 2: "text"},
    "message":           {1: "name", 2: "text"},
    "l2dmessage":        {1: "name", 2: "text"},
    "messageTextCenter": {2: "text"},
    "messageTextUnder":  {1: "name", 2: "text"},
    "title":             {1: "text"},
    "objectload":        {4: "name"},
    "charaload":         {3: "name"},
}

_JP_RE = re.compile(r"[぀-ヿ㐀-鿿ｦ-ﾟ…！？]")


def has_japanese(text):
    return bool(_JP_RE.search(text or ""))


def read_story_text(bundle_path):
    """Return (text, asset_name) for the single TextAsset inside a story bundle."""
    env = UnityPy.load(bundle_path)
    for obj in env.objects:
        if obj.type.name == "TextAsset":
            data = obj.read()
            return _script_to_str(data.m_Script), data.m_Name
    raise ValueError(f"No TextAsset found in {bundle_path}")


def parse_story_lines(text):
    """Extract translatable JP text from a scene script.

    Returns (jp_lines, names):
      jp_lines — unique JP strings in scene order (duplicates collapsed)
      names    — {jp_name: suggested_en} from name-kind fields
    """
    seen = set()
    jp_lines = []
    names = {}

    for raw in text.splitlines():
        if not raw.strip() or raw.lstrip().startswith("//"):
            continue
        parts = raw.split(",")
        spec = TRANSLATABLE.get(parts[0])
        if not spec:
            continue
        for field_idx, kind in spec.items():
            if field_idx >= len(parts):
                continue
            value = parts[field_idx]
            if not value or not has_japanese(value):
                continue
            if kind == "name":
                if parts[0] == "objectload" and field_idx == 4:
                    handle = parts[1] if len(parts) > 1 else ""
                    if handle and re.fullmatch(r"[A-Z][A-Za-z]+\d*", handle):
                        names.setdefault(value, handle)
                    else:
                        names.setdefault(value, "")
                else:
                    names.setdefault(value, "")
            else:
                if value not in seen:
                    seen.add(value)
                    jp_lines.append(value)

    return jp_lines, names


def load_json(path, default):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8-sig") as fh:
            try:
                return json.load(fh)
            except json.JSONDecodeError as e:
                raise json.JSONDecodeError(f"{path}: {e.msg}", e.doc, e.pos) from None
    return default


def save_weblate_pair(scene_dir, ja, en):
    """Write ja.json and en.json matching Weblate's output format (indent=4, no trailing newline)."""
    os.makedirs(scene_dir, exist_ok=True)
    for name, d in (("ja", ja), ("en", en)):
        with open(os.path.join(scene_dir, f"{name}.json"), "w", encoding="utf-8") as fh:
            fh.write(json.dumps(d, ensure_ascii=False, indent=4))


def _script_to_str(m_script):
    if isinstance(m_script, (bytes, bytearray, memoryview)):
        return bytes(m_script).decode("utf-8", "replace")
    return m_script.encode("utf-8", "surrogateescape").decode("utf-8", "replace")
