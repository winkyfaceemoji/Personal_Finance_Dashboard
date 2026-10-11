"""
What the dashboard says for your data — read-only. Prints the period line,
the headline and the three stat cards for the latest week, month and year,
every earlier year, and the first month of your data and the same month a
year later. Run it before and after an update to see what changed:

    python screen_check.py > before.txt
    (update, then)
    python screen_check.py > after.txt

It uses the data folder the dashboard uses and writes nothing.
"""
import contextlib
import io
import sys


def texts(component) -> list[str]:
    """The visible strings in a Dash component tree, in order."""
    out = []

    def walk(c):
        if c is None:
            return
        if isinstance(c, (str, int, float)):
            if str(c).strip():
                out.append(str(c).strip())
        elif isinstance(c, (list, tuple)):
            for x in c:
                walk(x)
        elif hasattr(c, "children"):
            walk(c.children)
    walk(component)
    return out


def main() -> int:
    with contextlib.suppress(AttributeError, ValueError):
        sys.stdout.reconfigure(errors="replace")
    with contextlib.redirect_stdout(io.StringIO()):     # the import's console lines
        import app
    df = app.df
    if df.empty:
        print("No data loaded — open the dashboard once to set the data folder.")
        return 1
    import pandas as pd
    from Modules.transforms import to_period

    as_of, first = app._as_of(), df["date"].min()
    views = [(f, to_period(as_of, f)) for f in ("week", "month", "year")]
    views += [("year", to_period(pd.Timestamp(y, 1, 1), "year")) for y in range(as_of.year - 1, first.year - 1, -1)]
    views += [("month", to_period(first, "month")), ("month", to_period(first, "month") + 12)]

    print(f"Data {first:%Y-%m-%d} to {as_of:%Y-%m-%d}\n")
    for freq, p in views:
        store = {"freq": freq, "start": f"{p.start_time:%Y-%m-%d}"}
        label, sub, *_ = app.update_period_header(store)
        cards, headline, _ = app.update_stats(store, "dark", 0)
        print(f"{freq.upper():5}  {label}" + (f"  ({sub})" if sub else ""))
        print("       headline: " + " | ".join(texts(headline)))
        for card in cards:
            print("       " + " | ".join(texts(card)))
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
