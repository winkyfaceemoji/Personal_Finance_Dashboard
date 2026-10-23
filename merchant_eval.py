"""Hand-run, not CI: how many name-similarity suggestions (Modules/similar.py)
are right at CUTOFF, against the local answer key in the git-ignored research
folder. It holds real names, so this only reads it and prints counts.

Usage: .venv/Scripts/python.exe merchant_eval.py http://127.0.0.1:8093
"""
import runpy
import sys
from pathlib import Path

import pandas as pd

from Modules.similar import CUTOFF, http_embedder, similar_merchants

FOLDER = Path(__file__).resolve().parent / ".claude" / "research" / "merchant-aliasing"


def main(url: str) -> None:
    if not (FOLDER / "truth.py").exists() or not (FOLDER / "keys.csv").exists():
        print(f"No answer key in {FOLDER}; nothing to measure.")
        return
    same = runpy.run_path(str(FOLDER / "truth.py"))["SAME"]
    keys = [k for k in pd.read_csv(FOLDER / "keys.csv", keep_default_na=False)["key"] if k]
    merchant = {k: m for m, ks in same.items() for k in ks}
    # No aliases yet: every spelling is its own merchant
    got = similar_merchants(keys, {k: [k] for k in keys}, http_embedder(url, timeout=300))
    if not got and keys:
        print(f"No suggestions: is the embedding server up at {url}?")
        return
    right = sum(1 for k, (m, _) in got.items() if k in merchant and merchant.get(m) == merchant[k])
    wrong = sum(1 for k in got if k not in merchant)
    others = sum(1 for k in keys if k not in merchant)
    print(f"cutoff {CUTOFF}: right suggestions {right}/{len(merchant)} | suggestions on other spellings {wrong}/{others}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
