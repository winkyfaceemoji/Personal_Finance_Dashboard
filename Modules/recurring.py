"""
Recurring charges — subscriptions, memberships, rent, utilities: the same
merchant charging about the same amount on a regular schedule. Read-only
analysis for the dashboard's RECURRING CHARGES card.
"""
import pandas as pd

from Modules.labels import merchant_key

# cadence: (typical days between charges, window a gap must fall in,
#           fewest charges to call it a pattern, charges per year)
CADENCES = {
    "monthly":   (30,  (20, 40),   3, 12),
    "quarterly": (91,  (75, 105),  3, 4),
    "yearly":    (365, (330, 400), 3, 1),
}
# Three charges for every cadence: two yearly charges of a similar size are
# too often a coincidence (the same flight twice, an annual trip).
#
# A schedule is "regular" when this share of the gaps fits the cadence, and an
# amount is "steady" when this share of charges is within AMOUNT_TOLERANCE of
# the median — so a price change or one odd month doesn't hide a subscription
REGULAR_SHARE    = 0.75
AMOUNT_TOLERANCE = 0.25


def recurring_charges(df: pd.DataFrame, as_of=None) -> list[dict]:
    """
    Money going out (amount < 0, not labeled Transfer or Income), grouped by
    merchant_key, where the charges repeat on a monthly, quarterly or yearly
    schedule at a steady amount. Same-day charges from one merchant count as
    one charge (their sum).

    Each dict: merchant, cadence, amount (the latest charge — prices change),
    yearly (amount × charges per year), count, first, last, active (charged
    within 1.5 cadences of as_of, which defaults to the newest transaction).
    Biggest yearly cost first.
    """
    if df.empty:
        return []
    as_of = pd.Timestamp(as_of) if as_of is not None else df["date"].max()
    out = df[(df["amount"] < 0) & ~df["master_category"].isin(["Transfer", "Income"])]
    out = out.assign(_mk=out["description"].map(merchant_key))
    out = out[out["_mk"] != ""]

    found = []
    for mk, g in out.groupby("_mk", sort=False):
        charges = (-g.groupby(g["date"].dt.normalize())["amount"].sum()).sort_index()
        gaps = charges.index.to_series().diff().dt.days.dropna()
        if gaps.empty:
            continue
        typical = charges.median()
        if ((charges - typical).abs() <= AMOUNT_TOLERANCE * typical).mean() < REGULAR_SHARE:
            continue
        for cadence, (days, (lo, hi), fewest, per_year) in CADENCES.items():
            if len(charges) < fewest or not lo <= gaps.median() <= hi:
                continue
            if gaps.between(lo, hi).mean() < REGULAR_SHARE:
                continue
            amount = round(float(charges.iloc[-1]), 2)
            found.append({
                "merchant": mk.upper(),
                "cadence": cadence,
                "amount": amount,
                "yearly": round(amount * per_year, 2),
                "count": int(len(charges)),
                "first": charges.index[0],
                "last": charges.index[-1],
                "active": (as_of - charges.index[-1]).days <= days * 1.5,
            })
            break
    return sorted(found, key=lambda r: r["yearly"], reverse=True)
