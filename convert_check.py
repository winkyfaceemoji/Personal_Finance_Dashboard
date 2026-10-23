"""
What CONVERT → would do to your data — read-only. Copies the data folder's
SORTED/ to a temp folder, converts the rules.csv keywords there with the
default review, and prints the proposals, the preview, and every row whose
label or category differs after the conversion (there should be none):

    python convert_check.py > convert.txt

It reads the data folder the dashboard uses and writes only the temp copy.
"""
import contextlib
import io
import os
import shutil
import sys
import tempfile
from pathlib import Path


def main() -> int:
    with contextlib.suppress(AttributeError, ValueError):
        sys.stdout.reconfigure(errors="replace")
    from config import get_data_dir, get_rules_path
    source = get_data_dir()
    if not source or not get_rules_path(source).exists():
        print("No rules.csv keywords to convert.")
        return 1
    if not (Path(source) / "SORTED" / "edited_combined_transactions.csv").exists():
        print("No master yet: open the dashboard once to import your statements.")
        return 1
    with tempfile.TemporaryDirectory(prefix="convert_check_") as tmp:
        shutil.copytree(Path(source) / "SORTED", Path(tmp) / "SORTED", ignore=shutil.ignore_patterns("backups"))
        os.environ["FINANCE_DATA_DIR"] = tmp
        os.environ.pop("FINANCE_EMBED_URL", None)
        with contextlib.redirect_stdout(io.StringIO()):     # the import's console lines
            import app
        return report(app)


def report(app) -> int:
    props = app._convert_proposals()
    print(f"{len(props)} proposals\n")
    for p in props:
        rule = app.describe_label(p["label"], p["category"]) if (p["label"] or p["category"]) else "no rule"
        why = " (keywords used text beyond the spelling)" if p["partial"] else ""
        print(f"  {p['keyword']!a} -> {p['name']!a}: {rule}{why}, {len(p['spellings'])} spellings, {p['rows']} rows")
    pending, text = app._convert_preview(props)
    print(f"\nPreview: {text}\n")
    if pending is None:
        return 1
    before = labels(app.df)
    status = app._do_convert(pending, 0)[0]
    print(f"Confirm: {status}\n")
    if not status.startswith("Converted"):
        return 1
    after = labels(app.df)
    # Identical twin rows share a row id, so compare how many rows carry each label
    gone, new = before - after, after - before
    print(f"{sum(gone.values())} rows show a different label or category after converting")
    for rid in sorted({k[0] for k in gone | new})[:50]:
        was = sorted(app.describe_label(*k[1:]) for k in gone.elements() if k[0] == rid)
        now = sorted(app.describe_label(*k[1:]) for k in new.elements() if k[0] == rid)
        print(f"  {rid}: {', '.join(was) or '-'} -> {', '.join(now) or '-'}")
    return 0


def labels(df):
    """How many rows carry each (row id, label, category)."""
    from collections import Counter

    from Modules.labels import row_ids
    return Counter(zip(row_ids(df), df["master_category"].fillna(""), df["sub_category"].fillna("")))


if __name__ == "__main__":
    sys.exit(main())
