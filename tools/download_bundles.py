"""
Download asset bundles from the CDN into bundles_cache/.

Usage:
    python tools/download_bundles.py --list [--match SUBSTR]
    python tools/download_bundles.py --match SUBSTR [--match SUBSTR2]
    python tools/download_bundles.py --all

Already-downloaded files are skipped.
"""

import argparse
import os
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bundle_common as bc

CATALOG_NAME = "catalog_1.bin"
SRC_CATALOG = os.path.join(bc.BUNDLES_CACHE, CATALOG_NAME)


def main():
    parser = argparse.ArgumentParser(description="Download bundles listed in the catalog.")
    parser.add_argument("--match", action="append", default=[],
                        help="only filenames containing this substring (repeatable)")
    parser.add_argument("--all", action="store_true", help="download every bundle (large)")
    parser.add_argument("--list", action="store_true", help="list matching bundles, don't download")
    parser.add_argument("--workers", type=int, default=8, help="parallel downloads (default 8)")
    args = parser.parse_args()

    catalog = ensure_catalog()
    names = bc.list_catalog_bundles(catalog)

    if args.match:
        names = [n for n in names if any(m in n for m in args.match)]
    elif not args.all and not args.list:
        sys.exit("Refusing to download all 7000+ bundles. Use --match <substr> or --all.\n"
                 "Tip: run with --list first to find names.")

    print(f"{len(names)} bundle(s) match.")
    if args.list:
        for n in names:
            print("  ", n)
        return

    ok = skipped = failed = 0
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(fetch, n): n for n in names}
        for i, fut in enumerate(as_completed(futures), 1):
            name, size, err = fut.result()
            if err == "cached":
                skipped += 1
            elif err:
                failed += 1
                print(f"  [{i}/{len(names)}] FAIL {name[:55]}: {err}")
            else:
                ok += 1
                print(f"  [{i}/{len(names)}] {size:>9,}B  {name[:60]}")

    print(f"\nDone. downloaded={ok} skipped(cached)={skipped} failed={failed} -> bundles_cache/")


def ensure_catalog():
    os.makedirs(bc.BUNDLES_CACHE, exist_ok=True)
    if not os.path.exists(SRC_CATALOG):
        print(f"Fetching catalog: {bc.CATALOG_URL}")
        urllib.request.urlretrieve(bc.CATALOG_URL, SRC_CATALOG)
    return open(SRC_CATALOG, "rb").read()


def fetch(filename):
    dest = os.path.join(bc.BUNDLES_CACHE, filename)
    if os.path.exists(dest):
        return filename, os.path.getsize(dest), "cached"
    try:
        req = urllib.request.Request(bc.bundle_url(filename), headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=60) as r:
            data = r.read()
        with open(dest, "wb") as fh:
            fh.write(data)
        return filename, len(data), None
    except Exception as e:
        return filename, None, str(e)


if __name__ == "__main__":
    main()
