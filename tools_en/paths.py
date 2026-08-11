"""
File path utils
"""

import json
import os

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TRANSLATIONS = os.path.join(REPO_ROOT, "translations")
NOVELS_DIR = os.path.join(TRANSLATIONS, "novels")
NAMES_DIR = os.path.join(TRANSLATIONS, "names")
MANIFEST_PATH = os.path.join(TRANSLATIONS, "manifest", "en.json")

WRAP_EXCEPTIONS_PATH = os.path.join(REPO_ROOT, "data", "wrap_exceptions.json")

SCENE_PREFIXES = ("mas", "hmr", "hmn", "men", "evs")


def load_json(path, default=None):
    if not os.path.exists(path):
        return default
    with open(path, "r", encoding="utf-8-sig") as fh:
        try:
            return json.load(fh)
        except json.JSONDecodeError as e:
            raise json.JSONDecodeError(f"{path}: {e.msg}", e.doc, e.pos) from None


def _write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def save_indented_json(path, data):
    _write(path, json.dumps(data, ensure_ascii=False, indent=4) + "\n")

save_novel_json = save_indented_json

def save_manifest(data):
    """manifest/en.json — single line, no indent, no trailing newline."""
    _write(MANIFEST_PATH, json.dumps(data, ensure_ascii=False))


def scene_dirs():
    """Every scene id that currently has a translation directory."""
    if not os.path.isdir(NOVELS_DIR):
        return []
    return sorted(
        d for d in os.listdir(NOVELS_DIR)
        if d.startswith(SCENE_PREFIXES)
        and os.path.isdir(os.path.join(NOVELS_DIR, d))
    )
