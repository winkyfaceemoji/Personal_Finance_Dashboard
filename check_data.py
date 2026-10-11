"""
Read-only health check of your own data — run it on your machine:

    python check_data.py                    # report
    python check_data.py --save before.csv  # also save per-account monthly totals
    python check_data.py --compare before.csv   # after an update + Reload: what moved

It reads RAW/ and SORTED/ in your data folder (the one the dashboard uses, or
--data-dir) and reports what the code review's findings would do to *your*
files: one card split across two accounts (double counting), Capital One rows
left out where exports overlap, partly covered first months and years, and
export file-name dates. Nothing is written except the --save file.
"""
import argparse
import contextlib
import io
import os
import sys
from collections import defaultdict
from pathlib import Path

import pandas as pd

from config import get_data_dir, get_master_path
from main import _merge_by_coverage, filename_date, load_and_normalize
from Modules.safety import orphan_count, read_overlap_only
from Modules.transforms import load_transactions

BASE_DIR = Path(__file__).parent


def _money(v: float) -> str:
    return f"-${abs(v):,.2f}" if v < 0 else f"${v:,.2f}"


def _day(d) -> str:
    return "—" if pd.isna(d) else f"{d:%Y-%m-%d}"


def read_raw(raw: Path) -> tuple[list[dict], list[tuple[str, str]]]:
    """Every RAW file as the import reads it (format, account, rows, dates),
    plus the files it would skip. Read-only; the import's console lines are
    swallowed."""
    files, skipped = [], []
    for f in sorted(p for p in raw.rglob("*") if p.suffix.lower() == ".csv"):
        with contextlib.redirect_stdout(io.StringIO()):
            d = load_and_normalize(f, raw, skipped)
        if d is None or d.empty:
            continue
        d["date"] = pd.to_datetime(d["date"], errors="coerce")
        files.append({
            "file": str(f.relative_to(raw)), "format": d.attrs.get("format", "?"), "df": d,
            "account": (d["institution"].iat[0], d["source"].iat[0], d["card_last4"].iat[0]),
            "rows": len(d), "first": d["date"].min(), "last": d["date"].max(),
            "name_date": filename_date(f.name),
        })
    return files, skipped


def account_name(key: tuple) -> str:
    institution, source, card = key
    return f"{source}{' ' + card if card else ''} (folder: {institution or 'RAW/'})"


def split_cards(accounts: dict[tuple, pd.DataFrame]) -> list[dict]:
    """Accounts with the same source and card but a different institution:
    the same card filed twice. Rows on the dates both cover are counted twice
    by the import today."""
    by_card = defaultdict(list)
    for key, d in accounts.items():
        by_card[(key[1], key[2])].append(key)
    out = []
    for keys in by_card.values():
        for i, a in enumerate(keys):
            for b in keys[i + 1:]:
                da, db = accounts[a], accounts[b]
                lo = max(da["date"].min(), db["date"].min())
                hi = min(da["date"].max(), db["date"].max())
                rows = []
                if lo <= hi:
                    for k, d in ((a, da), (b, db)):
                        w = d[d["date"].between(lo, hi)]
                        rows.append((k, len(w), float(-w.loc[w["amount"] < 0, "amount"].sum())))
                out.append({"a": a, "b": b, "from": lo, "to": hi, "overlap": rows})
    return out


def snapshot(master: Path, rules: Path) -> pd.DataFrame:
    """What the dashboard counts: labeled spending and income per account
    (source) per month, with rules applied as the app applies them."""
    df = load_transactions(master, rules_path=rules)
    df = df[df["date"].notna()]
    month = df["date"].dt.strftime("%Y-%m")
    spent = -df["amount"].where(df["master_category"] == "Expense", 0.0)
    income = df["amount"].where(df["master_category"] == "Income", 0.0)
    out = (pd.DataFrame({"source": df["source"], "month": month, "rows": 1,
                         "spent": spent, "income": income})
           .groupby(["source", "month"], as_index=False).sum())
    out[["spent", "income"]] = out[["spent", "income"]].round(2)
    return out


def compare(before: pd.DataFrame, after: pd.DataFrame) -> pd.DataFrame:
    """Months where an account's rows, spending or income changed."""
    m = before.merge(after, on=["source", "month"], how="outer", suffixes=("_before", "_after")).fillna(0)
    changed = ((m["rows_before"] != m["rows_after"])
               | ((m["spent_before"] - m["spent_after"]).abs() >= 0.5)
               | ((m["income_before"] - m["income_after"]).abs() >= 0.5))
    return m[changed].sort_values(["source", "month"])


def run(data_dir: Path, save: Path | None = None, against: Path | None = None, out=sys.stdout) -> int:
    def p(*a):
        print(*a, file=out)

    raw = data_dir / "RAW"
    master = get_master_path(data_dir)
    rules = Path(os.environ.get("FINANCE_RULES_PATH") or BASE_DIR / "rules.csv")
    p(f"FINANCE DATA CHECK — read-only{' (saves ' + str(save) + ')' if save else ''}")
    p(f"Data folder: {data_dir}\n")
    problems = 0

    files, skipped = read_raw(raw)
    p("1. FILES IN RAW (by folder)")
    by_folder = defaultdict(list)
    for f in files:
        folder = str(Path(f["file"]).parent)
        by_folder[(folder if folder != "." else "RAW/", f["format"], f["account"])].append(f)
    for (folder, fmt, key), fs in sorted(by_folder.items()):
        firsts = [f["first"] for f in fs if pd.notna(f["first"])]
        lasts = [f["last"] for f in fs if pd.notna(f["last"])]
        p(f"  {folder}: {len(fs)} {fmt} file{'s' if len(fs) != 1 else ''} → {account_name(key)} · "
          f"{_day(min(firsts) if firsts else pd.NaT)} … {_day(max(lasts) if lasts else pd.NaT)}")
    for name, why in skipped:
        p(f"  ⚠ {name}: not imported ({why})")
    if not files:
        p("  (no files the import can read)")

    groups = defaultdict(list)
    for f in files:
        groups[f["account"]].append(f["df"])
    accounts = {k: _merge_by_coverage(v) for k, v in groups.items()}

    p("\n2. ACCOUNTS (after merging each account's overlapping exports)")
    for k, d in sorted(accounts.items()):
        p(f"  {account_name(k)}: {len(d)} rows · {_day(d['date'].min())} … {_day(d['date'].max())}")
    splits = split_cards(accounts)
    for s in splits:
        problems += 1
        p(f"  ⚠ SAME CARD, TWO ACCOUNTS: {account_name(s['a'])} and {account_name(s['b'])}")
        if s["overlap"]:
            p(f"    Both cover {_day(s['from'])} … {_day(s['to'])}; today every row there is counted twice:")
            for k, n, out_ in s["overlap"]:
                p(f"      {account_name(k)}: {n} rows, {_money(out_)} out")
        else:
            p("    Their dates don't overlap, so nothing is counted twice yet.")
    if not splits:
        p("  ✓ no card is split across two accounts")

    p("\n3. FIRST MONTH AND YEAR OF EACH ACCOUNT")
    for k, d in sorted(accounts.items()):
        first = d["date"].min()
        if pd.isna(first):
            continue
        month_note = "complete" if first.day == 1 else f"starts on day {first.day} (partly covered)"
        year_note = "complete" if (first.month, first.day) == (1, 1) else f"starts {first:%b %d} (partly covered)"
        p(f"  {account_name(k)}: first month {first:%b %Y} {month_note}; first year {first.year} {year_note}")

    p("\n4. IS EACH CARD UP TO DATE? (the dashboard's \"only through …\" warning)")
    # Today the dashboard treats a card as up to date through the newest date
    # in ANY of its export file names — a download date, not where data ends
    by_source = defaultdict(list)
    for f in files:
        by_source[f["account"][1]].append(f)
    for source, fs in sorted(by_source.items()):
        ends = max((f["last"] for f in fs if pd.notna(f["last"])), default=pd.NaT)
        named = [f for f in fs if f["name_date"] is not None]
        if not named:
            p(f"  {source}: data ends {_day(ends)} · no dates in its file names")
            continue
        newest = max(named, key=lambda f: f["name_date"])
        gap = (newest["name_date"] - ends).days if pd.notna(ends) else 0
        line = (f"  {source}: data ends {_day(ends)} · treated as up to date through "
                f"{_day(newest['name_date'])} (from {Path(newest['file']).name})")
        if gap > 7:
            line += (f"\n    ⚠ {gap} days later than the data — a \"behind\" warning for this card "
                     f"can be hidden")
        p(line)

    p("\n5. ROWS LEFT OUT WHERE EXPORTS OVERLAP (SORTED/overlap_only.csv)")
    left = read_overlap_only(master) if master else pd.DataFrame()
    if left.empty:
        p("  ✓ none")
    else:
        p(f"  {len(left)} rows ({_money(left['amount'].abs().sum())}):")
        for r in left.head(15).itertuples():
            p(f"    {r.date}  {_money(r.amount):>12}  {r.description}  [{r.file}]")

    p("\n6. WHAT THE DASHBOARD COUNTS NOW")
    if not master or not master.exists():
        p("  (no master file yet — run the import or open the dashboard first)")
        return problems
    snap = snapshot(master, rules)
    for source, g in snap.groupby("source"):
        p(f"  {source}: {int(g['rows'].sum())} rows · spent {_money(g['spent'].sum())} · "
          f"income {_money(g['income'].sum())} · {g['month'].min()} … {g['month'].max()}")
    p(f"  Unmatched labels (the red line's \"match no transaction\"): {orphan_count(master)}")

    if save:
        snap.to_csv(save, index=False)
        p(f"\n  Saved per-account monthly totals to {save}. After updating and pressing Reload, run:\n"
          f"    python check_data.py --compare {save}")
    if against:
        p(f"\n7. CHANGES SINCE {against}")
        try:
            before = pd.read_csv(against, dtype={"month": str})
            changed = compare(before, snap)
        except (OSError, ValueError, KeyError) as e:
            p(f"  ⚠ can't read {against} ({e.__class__.__name__}) — save one first with --save")
            return problems
        if changed.empty:
            p("  ✓ no account's monthly rows, spending or income changed")
        for r in changed.itertuples():
            p(f"  {r.source} {r.month}: rows {int(r.rows_before)}→{int(r.rows_after)} · "
              f"spent {_money(r.spent_before)}→{_money(r.spent_after)} · "
              f"income {_money(r.income_before)}→{_money(r.income_after)}")
    return problems


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Read-only health check of your finance data.")
    ap.add_argument("--data-dir", type=Path, help="data folder (default: the one the dashboard uses)")
    ap.add_argument("--save", type=Path, help="save per-account monthly totals to this CSV")
    ap.add_argument("--compare", type=Path, help="compare with totals saved earlier by --save")
    args = ap.parse_args(argv)
    # A Windows console or redirected file may not take ⚠ / ✓ / …
    with contextlib.suppress(AttributeError, ValueError):
        sys.stdout.reconfigure(errors="replace")
    data_dir = args.data_dir or get_data_dir()
    if not data_dir:
        print("No data folder configured — open the dashboard once, or pass --data-dir.")
        return 2
    run(Path(data_dir), save=args.save, against=args.compare)
    return 0


if __name__ == "__main__":
    sys.exit(main())
