"""
Shared helpers for the various scripts.
"""

import json
import os
import re
import struct

import UnityPy

CDN_HOST = "api.abyss-prod-r18.dotabyss.dmmgames.com"
CDN_CHANNEL = "r18"
CDN_VERSION = "6994"
CDN_BASE = (f"https://{CDN_HOST}/resources/webgl/"
            f"{CDN_CHANNEL}/aas/{CDN_VERSION}/aa/")
CATALOG_URL = CDN_BASE + "catalog_1.bin"


def bundle_url(filename):
    return CDN_BASE + filename


def list_catalog_bundles(catalog_bytes, downloadable_only=True):
    """Extract bundle filenames from a binary Addressables catalog.

    Strings are stored length-prefixed (int32 LE + ASCII bytes). We scan for
    every such string ending in ".bundle".
    downloadable_only keeps only the real CDN paths (containing "_assets_" or
    "_project_"); the rest are internal names that 403 at the CDN.
    """
    # R18 catalog has names up to ~201 bytes; too small silently drops names.
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


REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUNDLES_CACHE = os.path.join(REPO_ROOT, "bundles_cache")
TRANSLATIONS = os.path.join(REPO_ROOT, "translations")
STORY_DIR = os.path.join(TRANSLATIONS, "story")
NAMES_FILE = os.path.join(TRANSLATIONS, "names.json")

# Notes which commands in the game's .txt assets actually contain text to
# be translated.
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
    """Return (text, name) for the single TextAsset inside a story bundle."""
    env = UnityPy.load(bundle_path)
    for obj in env.objects:
        if obj.type.name == "TextAsset":
            data = obj.read()
            return _script_to_str(data.m_Script), data.m_Name
    raise ValueError(f"No TextAsset found in {bundle_path}")


def parse_story(text):
    """Split a script into translatable records.

    Returns (records, names):
      records = [{line, cmd, field, name, jp, en}] for text-kind fields
      names   = {jp_name: suggested_en} from name-kind fields
    """
    records = []
    names = {}
    for line_no, raw in enumerate(text.splitlines()):
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
                suggestion = names.get(value, "")
                if parts[0] == "objectload" and field_idx == 4:
                    handle = parts[1] if len(parts) > 1 else ""
                    # Suggest the ASCII handle as the English name (e.g. "Sophia").
                    # Skip internal codes like "mi_solA", "slm", "chara_1".
                    if handle and re.fullmatch(r"[A-Z][A-Za-z]+\d*", handle):
                        suggestion = handle
                names[value] = suggestion or names.get(value, "")
            else:
                name_val = ""
                for fi, fkind in spec.items():
                    if fkind == "name" and fi < len(parts):
                        name_val = parts[fi]
                        break
                records.append({
                    "line": line_no,
                    "cmd": parts[0],
                    "field": field_idx,
                    "name": name_val,
                    "jp": value,
                    "en": "",
                })
    return records, names


def _comma_safe(value):
    """Replace ASCII commas with fullwidth ，to avoid breaking the CSV format.
    Trailing space is also removed (", " → "，") since fullwidth has its own spacing."""
    return value.replace(", ", "，").replace(",", "，")


def load_json(path, default):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8-sig") as fh:
            try:
                return json.load(fh)
            except json.JSONDecodeError as e:
                raise json.JSONDecodeError(f"{path}: {e.msg}", e.doc, e.pos) from None
    return default


def save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
        fh.write("\n")


def _script_to_str(m_script):
    """Normalise m_Script (bytes or str from UnityPy) to a clean Python str."""
    if isinstance(m_script, (bytes, bytearray, memoryview)):
        return bytes(m_script).decode("utf-8", "replace")
    # surrogateescape round-trip: some UnityPy versions decode m_Script this way.
    return m_script.encode("utf-8", "surrogateescape").decode("utf-8", "replace")
