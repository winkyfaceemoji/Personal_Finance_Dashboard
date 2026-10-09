"""
Applying an edited export (IMPORT CSV) back onto the master file.

The round-trip goes through Excel, which re-saves CSVs in its own way:
UTF-8 with a BOM or Windows-1252, dates as 3/15/2024, amounts as
-$1,234.50 or ($1,234.50), and card numbers without their leading zero.
Everything here tolerates that.
"""
import io

import pandas as pd


def read_import_csv(raw: bytes) -> pd.DataFrame:
    """Decode an uploaded CSV; every column as text, blanks as ''."""
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            text = raw.decode(encoding)
        except UnicodeDecodeError:
            continue
        return pd.read_csv(io.StringIO(text), dtype=str, keep_default_na=False)
    raise ValueError("the file isn't UTF-8 or Windows-1252 text")


def _amount(value) -> float | None:
    text = str(value).strip().replace("$", "").replace(",", "")
    negative = text.startswith("(") and text.endswith(")")
    try:
        number = float(text.strip("()"))
    except ValueError:
        return None
    return round(-number if negative else number, 2)


def _dates(values: pd.Series) -> pd.Series:
    return pd.to_datetime(values, errors="coerce", format="mixed").dt.normalize()


def _last4(value) -> str:
    text = str(value).strip()
    if text.endswith(".0"):
        text = text[:-2]
    return text.zfill(4) if text.isdigit() else text


def apply_label_import(master: pd.DataFrame, imp: pd.DataFrame) -> tuple[pd.DataFrame, int, int]:
    """
    Write master_category / sub_category from `imp` onto matching `master`
    rows. A row matches on description + amount + source, plus date when the
    file has a date column, plus card when the row names one.

    Returns (updated master, master rows updated, import rows skipped). An
    import row is skipped when its amount or date can't be read, or when it
    matches nothing — a row with a date column but a blank date is skipped
    rather than applied to every date. Rows with no labels are ignored.
    """
    master = master.copy()
    for col in ("master_category", "sub_category", "card_last4"):
        if col not in master.columns:
            master[col] = ""
        master[col] = master[col].fillna("").astype(str)

    m_desc  = master["description"].astype(str).str.strip()
    m_amt   = pd.to_numeric(master["amount"], errors="coerce").round(2)
    m_src   = master["source"].astype(str)
    m_date  = _dates(master["date"])
    m_last4 = master["card_last4"].map(_last4)

    has_date, has_sub, has_card = ("date" in imp.columns, "sub_category" in imp.columns,
                                   "card_last4" in imp.columns)
    updated = skipped = 0
    for _, row in imp.iterrows():
        cat = str(row.get("master_category", "")).strip()
        sub = str(row.get("sub_category", "")).strip() if has_sub else ""
        if not cat and not sub:
            continue
        amount = _amount(row["amount"])
        if amount is None:
            skipped += 1
            continue
        mask = (m_desc == str(row["description"]).strip()) & (m_amt == amount) & (m_src == str(row["source"]))
        if has_date:
            day = _dates(pd.Series([row["date"]])).iat[0]
            if pd.isna(day):
                skipped += 1
                continue
            mask &= m_date == day
        if has_card and _last4(row["card_last4"]):
            mask &= m_last4 == _last4(row["card_last4"])
        n = int(mask.sum())
        if n == 0:
            skipped += 1
            continue
        if cat:
            master.loc[mask, "master_category"] = cat
        if sub:
            master.loc[mask, "sub_category"] = sub
        updated += n
    return master, updated, skipped
