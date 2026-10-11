"""
Recurring charges — subscriptions, memberships, rent, utilities: the same
merchant charging about the same amount on a regular schedule. Read-only
analysis for the dashboard's Recurring charges card.
"""
import pandas as pd

from Modules.labels import looks_like_transfer, merchant_key, row_ids

# cadence: (typical days between charges, window a gap must fall in,
#           fewest charges to call it a pattern, charges per year)
CADENCES = {
    "monthly":        (30,  (20, 40),   3, 12),
    "every 2 months": (61,  (50, 70),   3, 6),
    "quarterly":      (91,  (75, 105),  3, 4),
    "twice a year":   (182, (160, 200), 3, 2),
    "yearly":         (365, (330, 400), 3, 1),
}
# Three charges for every cadence: two yearly charges of a similar size are
# too often a coincidence (the same flight twice, an annual trip).
#
# A schedule is "regular" when this share of the gaps fits the cadence, and an
# amount is "steady" when this share of charges is within AMOUNT_TOLERANCE of
# the median or of the latest charge — so one odd month doesn't hide a
# subscription, and neither does a price rise (old and new price both count)
REGULAR_SHARE    = 0.75
AMOUNT_TOLERANCE = 0.25


def recurring_charges(df: pd.DataFrame, as_of=None, exclude_row_ids=None) -> list[dict]:
    """
    Money going out (amount < 0) to a merchant (merchant_key), repeating on a
    regular schedule (CADENCES) at a steady amount. Transfers aren't charges:
    rows labeled Transfer or Income are left out, and so are unlabeled rows
    with transfer wording (looks_like_transfer) and exclude_row_ids — the
    caller passes the sides of certain transfer pairs.

    Each dict: merchant, cadence, amount (the current price: the latest
    charge near the typical amount — a one-off fee from the same payee isn't
    the subscription — or, when the last two charges agree on a new price,
    that), yearly (amount × charges per year), count, first, last,
    active (charged within 1.5 cadences of as_of, which defaults to the
    newest transaction). Biggest yearly cost first.
    """
    if df.empty:
        return []
    as_of = pd.Timestamp(as_of) if as_of is not None else df["date"].max()
    out = df[(df["amount"] < 0) & df["date"].notna() & df["description"].notna()
             & ~df["master_category"].isin(["Transfer", "Income"])]
    keys = {d: merchant_key(d) for d in out["description"].unique()}     # descriptions repeat a lot
    out = out.assign(_mk=out["description"].map(keys), _day=out["date"].dt.normalize())
    out = out[out["_mk"] != ""]
    # Cheap, vectorised filters before the per-merchant loop, which is the
    # slow part on a long history with thousands of merchants: a pattern
    # needs 3+ charge days and a steady amount
    days = out.groupby("_mk")["_day"].transform("nunique")
    out = out[days >= min(c[2] for c in CADENCES.values())]
    out = out.sort_values("date", kind="stable")
    median = out.groupby("_mk")["amount"].transform("median")
    latest = out.groupby("_mk")["amount"].transform("last")
    near = (((out["amount"] - median).abs() <= AMOUNT_TOLERANCE * median.abs())
            | ((out["amount"] - latest).abs() <= AMOUNT_TOLERANCE * latest.abs()))
    steady_share = near.groupby(out["_mk"]).transform("mean")
    out = out[steady_share >= REGULAR_SHARE]
    unlabeled = ~out["master_category"].isin(["Expense"])
    out = out[~(unlabeled & out["description"].map(looks_like_transfer).astype(bool))]
    if exclude_row_ids and not out.empty:
        out = out[~row_ids(out).isin(set(exclude_row_ids))]
    if out.empty:
        return []
    # ...and a median gap between charge days that fits some cadence
    dd = out[["_mk", "_day"]].drop_duplicates().sort_values(["_mk", "_day"])
    med_gap = dd.groupby("_mk")["_day"].diff().dt.days.groupby(dd["_mk"]).median()
    fits = pd.Series(False, index=med_gap.index)
    for _, (lo, hi), _, _ in CADENCES.values():
        fits |= med_gap.between(lo, hi)
    out = out[out["_mk"].isin(fits[fits].index)]

    found = []
    for mk, g in out.groupby("_mk", sort=False):
        g = g.sort_values("date", kind="stable")
        amounts = -g["amount"]
        typical, last = amounts.median(), amounts.iloc[-1]
        steady = (amounts - typical).abs() <= AMOUNT_TOLERANCE * typical
        if (steady | ((amounts - last).abs() <= AMOUNT_TOLERANCE * last)).mean() < REGULAR_SHARE:
            continue
        # A new price: the last two charges agree with each other, not with
        # the old typical amount
        repriced = (len(amounts) >= 2 and not steady.iloc[-1]
                    and abs(amounts.iloc[-2] - last) <= AMOUNT_TOLERANCE * last)
        dates = g["_day"].drop_duplicates()
        gaps = dates.diff().dt.days.dropna()
        if gaps.empty:
            continue
        for cadence, (days_, (lo, hi), fewest, per_year) in CADENCES.items():
            if len(dates) < fewest or not lo <= gaps.median() <= hi:
                continue
            if gaps.between(lo, hi).mean() < REGULAR_SHARE:
                continue
            amount = round(float(last if repriced else amounts[steady].iloc[-1]), 2)
            found.append({
                "merchant": mk.upper(),
                "cadence": cadence,
                "amount": amount,
                "yearly": round(amount * per_year, 2),
                "count": int(len(dates)),
                "first": dates.iloc[0],
                "last": dates.iloc[-1],
                "active": (as_of - dates.iloc[-1]).days <= days_ * 1.5,
            })
            break
    return sorted(found, key=lambda r: r["yearly"], reverse=True)
