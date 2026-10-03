The scripts for the English patch are contained in `tools_en/`, separate from the `tools/` 
scripts inherited from the Chinese patch.

When a new game patch comes out, open the web version of the game and check the CDN version
in the catalog_1.bin file's URL, then run the following scripts:

```bash
# 1. bump CDN_VERSION in tools_en/common.py, then:
python tools_en/download_bundles.py --match .txt_
PYTHONUTF8=1 python tools_en/extract_story.py
```

`extract_story.py` not only adds additional story chapters but also checks previous lines
for small changes in e.g. punctuation of the original line that make the line stop matching.

When it's a small change, the jp line gets replaced with the new one while keeping the EN 
the same, but if it's too different then the EN gets reset and a `reports/dropped_translations.md`
file is created for human review.

On every push to `translations/**`, CI runs:

```bash
python tools_en/wrap_en.py            # character-width aware line break
python tools_en/check_novel_values.py # some checks for common mistakes
python tools/update_manifest.py       # refresh file hashes in the manifest file so users download the new version
```

It's recommended to run `python tools_en/wrap_en.py --check` locally before committing hand-edited translations
e.g. ones done via MTL to check for line overflows.

