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
    with tempfile.TemporaryDirectory(prefix="convert_check_") as tmp:
        shutil.copytree(Path(source) / "SORTED", Path(tmp) / "SORTED", ignore=shutil.ignore_patterns("backups"))
        os.environ["FINANCE_DATA_DIR"] = tmp
        os.environ.pop("FINANCE_EMBED_URL", None)
        with contextlib.redirect_stdout(io.StringIO()):     # the import's console lines
            import app
        return report(app)


def report(app) -> int:
    from Modules.labels import row_ids
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
    before = app.df.set_index(row_ids(app.df))[["master_category", "sub_category"]].fillna("")
    status = app._do_convert(pending, 0)[0]
    print(f"Confirm: {status}\n")
    after = app.df.set_index(row_ids(app.df))[["master_category", "sub_category"]].fillna("")
    after = after[~after.index.duplicated()].reindex(before.index[~before.index.duplicated()])
    before = before[~before.index.duplicated()]
    moved = (before != after).any(axis=1)
    print(f"{int(moved.sum())} rows show a different label or category after converting")
    for rid in before.index[moved][:50]:
        print(f"  {rid}: {app.describe_label(*before.loc[rid])} -> {app.describe_label(*after.loc[rid])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
