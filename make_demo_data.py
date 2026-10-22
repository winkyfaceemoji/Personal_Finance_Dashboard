"""
Write the made-up demo exports in Test Data/RAW/. Every merchant, person,
amount and date is invented; nothing comes from a real export (ADR 0024).

The files copy the shapes the importer has to handle: Chase credit and
checking exports that overlap, an empty export, Discover statements plus
its archive, card payments that pair up as transfers, refunds (a merchant
with money in and out), and real-time payments with no merchant name.

Seeded, so a rerun writes the same bytes:
    .venv/Scripts/python.exe make_demo_data.py
"""
import random
import shutil
from datetime import date, timedelta
from pathlib import Path

RAW = Path(__file__).parent / "Test Data" / "RAW"
START, END = date(2023, 2, 10), date(2026, 7, 2)
rng = random.Random(20261022)

# (account, description, category, uses per month, low $, high $, first day, last day)
# "{n}" becomes a store or reference number, which merchant grouping strips.
SPEND = [
    ("3094", "MAPLE STREET GROCERY #{n}", "Groceries", 5, 18, 95, START, date(2026, 4, 11)),
    ("3094", "CITYLINE TRANSIT FARE", "Travel", 10, 2.9, 2.9, START, date(2026, 4, 11)),
    ("3094", "SQ *LITTLE FERN BAKERY", "Food & Drink", 3, 4, 16, START, date(2026, 4, 11)),
    ("3094", "TST* COPPER POT DINER", "Food & Drink", 1.5, 18, 64, START, date(2026, 4, 11)),
    ("3094", "BRIGHTLEAF PHARMACY {n}", "Health & Wellness", 1.2, 5, 40, START, date(2026, 4, 11)),
    ("3094", "HARBOR OUTFITTERS", "Shopping", 0.5, 30, 160, START, date(2026, 4, 11)),
    ("3094", "PAYPAL *PIXELFORGE", "Shopping", 0.3, 10, 70, START, date(2026, 4, 11)),
    ("7156", "SUNDIAL CINEMAS {n}", "Entertainment", 1, 12, 40, START, END),
    ("7156", "NORTHGATE AIRLINES", "Travel", 0.15, 180, 520, START, END),
    ("7156", "SP LANTERN GOODS", "Shopping", 0.4, 15, 90, START, END),
    ("7156", "QUILLFIELD BOOKS", "Shopping", 0.6, 9, 45, START, END),
    ("7156", "OAKRIDGE HOTEL", "Travel", 0.1, 140, 420, START, END),
    ("6471", "CITYLINE TRANSIT FARE", "Travel", 12, 2.9, 2.9, date(2026, 1, 1), END),
    ("6471", "MAPLE STREET GROCERY #{n}", "Groceries", 4, 18, 95, date(2026, 1, 1), END),
    ("discover", "STARLIGHT GAMES STORE", "Merchandise", 0.8, 5, 60, START, date(2026, 4, 12)),
    ("discover", "OPEN HANDS FUND {n}", "Services", 0.5, 10, 50, START, date(2026, 4, 12)),
    ("discover", "IRONWORKS GYM #{n}", "Services", 1, 25, 25, START, date(2026, 4, 12)),
]
# (account, description, category, day of month, price, new price, price changes on)
MONTHLY = [
    ("3094", "STREAMLY.COM", "Bills & Utilities", 3, 11.99, 13.99, date(2025, 1, 1)),
    ("7156", "CLOUDNOTE SUBSCRIPTION", "Bills & Utilities", 12, 8.00, 10.00, date(2024, 6, 1)),
    ("discover", "PIXELPLAY MONTHLY", "Services", 20, 15.00, 15.00, START),
]
PEOPLE = ["JORDAN RIVERS", "SAM OKAFOR", "PRIYA NANDAN", "ALEX MORROW", "CASEY LIN"]


def days(first=START, last=END):
    d = first
    while d <= last:
        yield d
        d += timedelta(days=1)


def money(lo, hi):
    return round(rng.uniform(lo, hi), 2)


def make_transactions():
    """Every made-up transaction: (account, date, description, category, amount),
    with amount < 0 for money out, as the dashboard sees it."""
    tx = []
    for acct, desc, cat, per_month, lo, hi, first, last in SPEND:
        for d in days(first, last):
            if rng.random() < per_month / 30:
                text = desc.format(n=rng.choice(["0142", "0377", "1189"]))
                tx.append((acct, d, text, cat, -money(lo, hi)))
                if desc == "HARBOR OUTFITTERS" and rng.random() < 0.3:      # a refund: money in and out
                    tx.append((acct, d + timedelta(days=9), text, cat, money(lo, hi)))
    for acct, desc, cat, day, price, new, change in MONTHLY:
        for d in days():
            if d.day == day:
                tx.append((acct, d, desc, cat, -(new if d >= change else price)))
    for d in days():
        if d.weekday() == 4 and (d - START).days % 14 == 0:
            tx.append(("4823", d, "NORTHWIND LABS PAYROLL PPD ID: 9100000001", "", money(1450, 1550)))
        if d.day == 1:
            tx.append(("4823", d, "Zelle payment to ALEX MORROW JPM99a1b2c3", "", -1650.0))   # rent
            tx.append(("4823", d, "MONTHLY SERVICE FEE", "", -12.0 if d.month % 5 == 0 else 0.0))
        if rng.random() < 0.12:
            tx.append(("4823", d, "VENMO            PAYMENT    1000000001   WEB ID: 3000000001", "", -money(8, 60)))
        if rng.random() < 0.06:
            tx.append(("4823", d, "VENMO            CASHOUT                    PPD ID: 5000000001", "", money(10, 80)))
        if rng.random() < 0.05:
            who = rng.choice(PEOPLE)
            tx.append(("4823", d, f"Zelle payment from {who} WFCT0{rng.randint(1000, 9999)}", "", money(15, 120)))
        if rng.random() < 0.02:
            tx.append(("4823", d, "ATM WITHDRAWAL 000123 05/01 MAIN ST", "", -float(rng.choice([40, 60, 100]))))
        if rng.random() < 0.01:
            tx.append(("4823", d, f"REAL TIME PAYMENT RECEIVED {d:%Y%m%d} {rng.randint(10000, 99999)}", "",
                       money(20, 300)))
    tx = [t for t in tx if t[4] != 0.0]
    tx += card_payments(tx)
    return sorted(tx, key=lambda t: (t[0], t[1], t[2]))


def card_payments(tx):
    """Each month checking pays every card's last-month charges. Both sides
    post, a day or two apart, with the exact same amount: a transfer pair."""
    out = []
    for acct in ("3094", "7156", "6471", "discover"):
        months = sorted({(t[1].year, t[1].month) for t in tx if t[0] == acct})
        for y, m in months:
            owed = -round(sum(t[4] for t in tx if t[0] == acct and (t[1].year, t[1].month) == (y, m)), 2)
            paid = date(y + (m == 12), m % 12 + 1, 8)
            if owed <= 0 or paid > END:
                continue
            if acct == "discover":
                out.append(("4823", paid, "DISCOVER E-PAYMENT 7400 WEB ID: 2510020270", "", -owed))
                out.append(("discover", paid + timedelta(days=1), "INTERNET PAYMENT - THANK YOU",
                            "Payments and Credits", owed))
            else:
                out.append(("4823", paid, f"Payment to Chase card ending in {acct} {paid:%m/%d}", "", -owed))
                out.append((acct, paid + timedelta(days=1), "Payment Thank You-Mobile", "", owed))
    return out


def window(tx, acct, first, last):
    return [t for t in tx if t[0] == acct and first <= t[1] <= last]


def write(name, header, rows):
    path = RAW / name
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as f:
        f.write(",".join(header) + "\r\n")
        for r in rows:
            f.write(",".join(str(x) for x in r) + "\r\n")


def chase_credit(name, tx):
    def row(t):
        _, d, desc, cat, amt = t
        kind = "Payment" if desc.startswith("Payment Thank") else ("Return" if amt > 0 else "Sale")
        return [f"{d:%m/%d/%Y}", f"{d + timedelta(days=rng.choice([0, 1, 2])):%m/%d/%Y}", desc, cat, kind,
                f"{amt:.2f}", ""]
    write(name, ["Transaction Date", "Post Date", "Description", "Category", "Type", "Amount", "Memo"],
          [row(t) for t in tx])


def chase_debit(name, tx, balance):
    rows = []
    for _, d, desc, _, amt in tx:
        balance = round(balance + amt, 2)
        kind = ("LOAN_PMT" if desc.startswith("Payment to Chase") else "ATM" if desc.startswith("ATM")
                else "FEE_TRANSACTION" if "FEE" in desc else "QUICKPAY_DEBIT" if amt < 0 and "Zelle" in desc
                else "QUICKPAY_CREDIT" if "Zelle" in desc else "ACH_DEBIT" if amt < 0 else "ACH_CREDIT")
        rows.append(["DEBIT" if amt < 0 else "CREDIT", f"{d:%m/%d/%Y}", desc, f"{amt:.2f}", kind,
                     f"{balance:.2f}", ""])
    write(name, ["Details", "Posting Date", "Description", "Amount", "Type", "Balance", "Check or Slip #"], rows)


def discover(name, tx):
    # Discover exports purchases as positive amounts; the importer negates them
    write(name, ["Trans. Date", "Post Date", "Description", "Amount", "Category"],
          [[f"{d:%m/%d/%Y}", f"{d + timedelta(days=1):%m/%d/%Y}", desc, f"{-amt:.2f}", cat or "Merchandise"]
           for _, d, desc, cat, amt in tx])


def main():
    if RAW.exists():
        shutil.rmtree(RAW)
    tx = make_transactions()
    D = date
    # Chase credit: yearly downloads that overlap, plus short ones (ChaseNNNN_Activity<from>_<to>_<downloaded>)
    for acct, spans in {
        "3094": [(D(2023, 2, 10), D(2024, 2, 9), "20250210"), (D(2023, 2, 10), D(2025, 2, 10), "20250210"),
                 (D(2024, 4, 11), D(2026, 4, 11), "20260411"), (D(2025, 2, 1), D(2025, 3, 1), "20250301"),
                 (D(2025, 2, 1), D(2025, 3, 21), "20250321")],
        "7156": [(D(2023, 2, 10), D(2024, 2, 9), "20250210"), (D(2023, 2, 10), D(2025, 2, 10), "20250210"),
                 (D(2023, 3, 21), D(2025, 3, 21), "20250321"), (D(2024, 4, 11), D(2026, 4, 11), "20260411"),
                 (D(2025, 2, 1), D(2025, 3, 1), "20250301"), (D(2026, 1, 1), D(2026, 7, 2), "20260702")],
        "6471": [(D(2026, 1, 1), D(2026, 7, 2), "20260702")],
    }.items():
        for first, last, got in spans:
            chase_credit(f"Chase/Chase{acct}_Activity{first:%Y%m%d}_{last:%Y%m%d}_{got}.CSV",
                         window(tx, acct, first, last))
    # Chase checking: downloads named by day, each covering a stretch before it; one came out empty
    chase_debit("Chase/Chase4823_Activity_20250210.CSV", [], 0)
    for first, last in [(D(2023, 2, 10), D(2025, 2, 13)), (D(2025, 2, 1), D(2025, 3, 1)),
                        (D(2025, 2, 20), D(2025, 3, 21)), (D(2024, 4, 11), D(2026, 4, 11)),
                        (D(2026, 3, 1), D(2026, 7, 2))]:
        chase_debit(f"Chase/Chase4823_Activity_{last:%Y%m%d}.CSV", window(tx, "4823", first, last), 4200.0)
    # Discover: monthly statements to Feb 2025, then the archive and this year's summary
    for y, m in [(y, m) for y in (2023, 2024, 2025) for m in range(1, 13)]:
        close = D(y, m, 27)
        if D(2023, 3, 1) <= close <= D(2025, 2, 28):
            opened = D(y - (m == 1), (m - 2) % 12 + 1, 28)
            discover(f"Discover/Discover-Statement-{close:%Y%m%d}.csv", window(tx, "discover", opened, close))
    discover("Discover/Discover-AllAvailable-20260412.csv", window(tx, "discover", D(2025, 1, 28), D(2026, 4, 12)))
    discover("Discover/Discover-2026-YearToDateSummary.csv", window(tx, "discover", D(2026, 1, 1), D(2026, 4, 12)))
    print(f"wrote {len(list(RAW.rglob('*.*')))} files, {len(tx)} transactions, to {RAW}")


if __name__ == "__main__":
    main()
