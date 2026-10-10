#!/usr/bin/env python3
"""Install or refresh the Canadian public datasets that power the Alberta map.

The importer never replaces a validated cache with a failed or partial download:
if a source is unreachable, returns nothing, or has changed its schema, the run
reports the failure and the previous cache stays active.

Examples
--------
  # what is installed right now
  python scripts/update_alberta_data.py --status

  # install / refresh everything (AER ST37 + facilities + pipelines + 12 months of Petrinex)
  python scripts/update_alberta_data.py --all

  # one AER source
  python scripts/update_alberta_data.py --source st37

  # 24 months of Petrinex reported volumes, ending at a specific reporting month
  python scripts/update_alberta_data.py --petrinex 24 --end-month 2026-07

  # an AER dataset distributed as a file (casing failures, vent flow, abandoned wells,
  # well licence list) that you downloaded from the AER catalogue
  python scripts/update_alberta_data.py --file casing_failures=/path/to/report.csv
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from backend import config
from backend.data import alberta, arcgis, petrinex_cache


def _print_status() -> None:
    print("Installed Canadian public datasets")
    print("-" * 72)
    for source in alberta.source_status():
        meta = source["meta"] or {}
        mark = "installed" if source["connected"] else "not installed"
        rows = f"{meta.get('stats', {}).get('rows', 0):,}" if source["connected"] else "—"
        how = "refreshable from this script" if source["refreshable"] else "import a downloaded AER file"
        print(f"{source['kind']:<16} {mark:<14} rows={rows:<12} {how}")
        if meta.get("retrieved_at"):
            print(f"{'':<16} retrieved {meta['retrieved_at']}"
                  + (f" · source last edited {meta['source_last_edit']}" if meta.get("source_last_edit") else ""))
    pmeta = petrinex_cache.cache_meta()
    if pmeta:
        print(f"{'petrinex':<16} {'installed':<14} rows={pmeta['records']:,}  "
              f"{pmeta['months'][0]} → {pmeta['latest_month']} ({pmeta['wells']:,} wells)")
    else:
        print(f"{'petrinex':<16} {'not installed':<14} rows=—")
    join = alberta.join_report()
    if join.get("available"):
        print("-" * 72)
        print("Join validation (ST37 ↔ Petrinex)")
        for key in ("st37_wells_imported", "st37_wells_linked", "st37_wells_unlinked",
                    "st37_links_blocked_by_shared_location", "ambiguous_cells_excluded",
                    "petrinex_cells_without_st37_match"):
            if key in join:
                print(f"  {key.replace('_', ' '):<42} {join[key]:,}")


def _progress(kind: str):
    def report(done: int, total: int) -> None:
        if done % 25000 < 2500 or done >= total:
            print(f"  {kind}: {done:,} / {total:,}", flush=True)
    return report


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--status", action="store_true", help="show what is installed and exit")
    ap.add_argument("--all", action="store_true", help="refresh every refreshable source plus Petrinex")
    downloadable_files = [k for k, s in alberta.FILE_SOURCES.items() if s.get("url")]
    ap.add_argument("--source", action="append", default=[],
                    choices=sorted(list(alberta.ARCGIS_SOURCES) + downloadable_files),
                    help="refresh one AER open-data source (ArcGIS-served, or a direct-download AER CSV)")
    ap.add_argument("--petrinex", type=int, metavar="MONTHS", help="download N months of Petrinex reported volumes")
    ap.add_argument("--end-month", metavar="YYYY-MM", help="last Petrinex reporting month to download")
    ap.add_argument("--file", action="append", default=[], metavar="KIND=PATH",
                    help="import an AER dataset you downloaded as a file")
    args = ap.parse_args()

    if args.status or not (args.all or args.source or args.petrinex or args.file):
        _print_status()
        if not (args.all or args.source or args.petrinex or args.file):
            print("\nNothing requested. Use --all, --source, --petrinex or --file (see --help).")
        return 0

    failures: list[str] = []
    arcgis_sources = (list(alberta.ARCGIS_SOURCES) if args.all
                      else [k for k in args.source if k in alberta.ARCGIS_SOURCES])
    for kind in arcgis_sources:
        print(f"\n{alberta.ARCGIS_SOURCES[kind]['name']}")
        started = time.time()
        try:
            meta = alberta.sync_arcgis(kind, progress=_progress(kind))
            stats = meta["stats"]
            print(f"  imported {stats['rows']:,} rows in {time.time() - started:.0f}s")
            for key in ("valid_coordinates", "invalid_coordinates", "parsed_legal_locations",
                        "unparsed_legal_locations", "distinct_ats_cells"):
                if key in stats:
                    print(f"    {key.replace('_', ' '):<28} {stats[key]:,}")
        except arcgis.SourceUnavailable as exc:
            failures.append(f"{kind}: {exc}")
            print(f"  FAILED — {exc}\n  previous valid cache preserved", file=sys.stderr)
        except Exception as exc:
            failures.append(f"{kind}: {exc}")
            print(f"  FAILED — {exc}\n  previous valid cache preserved", file=sys.stderr)

    file_sources = (downloadable_files if args.all
                    else [k for k in args.source if k in downloadable_files])
    for kind in file_sources:
        spec = alberta.FILE_SOURCES[kind]
        print(f"\n{spec['name']} (direct download from AER)")
        started = time.time()
        try:
            meta = alberta.download_file_source(kind, progress=lambda s: print(f"  {s}", flush=True))
            print(f"  imported {meta['stats']['rows']:,} rows in {time.time() - started:.0f}s; "
                  f"invalid coordinates={meta['stats'].get('invalid_coordinates', 0):,}")
        except Exception as exc:
            failures.append(f"{kind}: {exc}")
            print(f"  FAILED — {exc}", file=sys.stderr)

    if args.all or args.petrinex:
        months = petrinex_cache.available_months(args.petrinex or 12, end=args.end_month)
        print(f"\nPetrinex Alberta conventional volumetrics — {months[0]} → {months[-1]}")
        started = time.time()
        try:
            meta = petrinex_cache.build(months, progress=lambda stage, i, n: print(f"  [{i + 1}/{n}] {stage}", flush=True))
            print(f"  imported {meta['records']:,} monthly records for {meta['wells']:,} wells "
                  f"in {time.time() - started:.0f}s")
            print(f"    unambiguous legal locations   {meta['unambiguous_cells']:,}")
            print(f"    ambiguous legal locations     {meta['ambiguous_cells']:,} (excluded from the production link)")
        except Exception as exc:
            failures.append(f"petrinex: {exc}")
            print(f"  FAILED — {exc}\n  previous valid cache preserved", file=sys.stderr)

    for item in args.file:
        if "=" not in item:
            raise SystemExit(f"--file expects KIND=PATH, got: {item}")
        kind, raw_path = item.split("=", 1)
        source = Path(raw_path).expanduser()
        if not source.is_file():
            raise SystemExit(f"Source file does not exist: {source}")
        print(f"\n{alberta.SOURCE_CATALOG.get(kind, {}).get('name', kind)} — {source.name}")
        with tempfile.NamedTemporaryFile(dir=config.ALBERTA_RAW_DIR, suffix=source.suffix, delete=False) as tmp:
            staged = Path(tmp.name)
        try:
            shutil.copyfile(source, staged)
            meta = alberta.import_file(staged, kind)
            print(f"  imported {meta['stats']['rows']:,} rows; "
                  f"invalid coordinates={meta['stats'].get('invalid_coordinates', 0):,}")
        except Exception as exc:
            failures.append(f"{kind}: {exc}")
            print(f"  FAILED — {exc}\n  previous valid cache preserved", file=sys.stderr)
        finally:
            staged.unlink(missing_ok=True)

    print()
    _print_status()
    if failures:
        print("\nFailures (previous data was kept for each):", file=sys.stderr)
        for failure in failures:
            print(f"  - {failure}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
