"""
Extracts character widths for the game's font (FOT-UDMarugo_SmallPr6-E SDF)
so wrap_text.py can use them to properly generate line wraps.

Usage:
    PYTHONUTF8=1 python tools_en/extract_font_metrics.py
"""

import json
import os
import sys

import UnityPy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common
import paths

FONT_BUNDLE_PREFIX = (
    "general-textmeshpro_assets_assets_project_lazyassets_general_textmeshpro_"
    "materials_sdf_fot-udmarugo_smallpr6-esdf.asset_"
)
OUT_PATH = os.path.join(paths.REPO_ROOT, "data", "font_metrics.json")
CATALOG_PATH = os.path.join(common.BUNDLES_CACHE, "catalog_1.bin")


def resolve_font_bundle():
    if not os.path.exists(CATALOG_PATH):
        sys.exit("bundles_cache/catalog_1.bin missing. Run tools_en/download_bundles.py first.")
    with open(CATALOG_PATH, "rb") as fh:
        names = common.list_catalog_bundles(fh.read())

    matches = [n for n in names if n.startswith(FONT_BUNDLE_PREFIX)]
    if not matches:
        sys.exit(f"No catalog entry starting with {FONT_BUNDLE_PREFIX!r}. "
                 f"The font asset may have been renamed.")
    if len(matches) > 1:
        print(f"Warning: {len(matches)} font bundles match, using the first.")

    path = os.path.join(common.BUNDLES_CACHE, matches[0])
    if not os.path.exists(path):
        sys.exit(f"Font bundle not cached. Run:\n"
                 f"  python tools_en/download_bundles.py --match {FONT_BUNDLE_PREFIX[:40]}")
    return path


def main():
    bundle_path = resolve_font_bundle()
    env = UnityPy.load(bundle_path)

    font_asset = None
    for obj in env.objects:
        if obj.type.name == "MonoBehaviour":
            tree = obj.read_typetree()
            if "m_CharacterTable" in tree and "m_GlyphTable" in tree:
                font_asset = tree
                break

    if font_asset is None:
        sys.exit("Could not find a TMP_FontAsset MonoBehaviour in the bundle.")

    glyph_advance = {
        g["m_Index"]: g["m_Metrics"]["m_HorizontalAdvance"]
        for g in font_asset["m_GlyphTable"]
    }
    spacing_offset = font_asset.get("normalSpacingOffset", 0.0)
    face_info = font_asset["m_FaceInfo"]

    widths = {}
    for c in font_asset["m_CharacterTable"]:
        advance = glyph_advance.get(c["m_GlyphIndex"])
        if advance is None:
            continue
        # Effective advance TMP uses when laying out text: glyph advance plus
        # the font asset's normal-style character spacing offset.
        widths[chr(c["m_Unicode"])] = advance + spacing_offset

    out = {
        "source": "FOT-UDMarugo_SmallPr6-E SDF",
        "point_size": face_info["m_PointSize"],
        "units_per_em": face_info["m_UnitsPerEM"],
        "widths": dict(sorted(widths.items())),
    }

    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2)
        fh.write("\n")

    print(f"Wrote {len(widths)} glyph widths to {OUT_PATH}")
    print(f"Reference point size: {face_info['m_PointSize']}")
    print("Re-run tools_en/wrap_en.py --check afterwards: changed metrics reflow text.")


if __name__ == "__main__":
    main()
