import sys
from pathlib import Path

# Let tests import Modules.* and main from the repo root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

# The made-up keywords the demo used before they became the demo merchant
# files (ADR 0025). Tests of loading and converting rules.csv keywords use them.
OLD_DEMO_RULES = """keyword,master_category,sub_category,added
payroll,Income,,
cashout,Income,,
zelle payment from,Income,,
remote online deposit,Income,,
claim pmt,Income,,
atm cash deposit,Income,,
payment thank you,Transfer,,
automatic payment,Transfer,,
autopay,Transfer,,
e-payment,Transfer,,
internet payment,Transfer,,
payment to chase card,Transfer,,
misc pay,Transfer,,
zelle payment to,Expense,Zelle,
atm withdrawal,Expense,Cash,
venmo,,Venmo,
maple street grocery,Expense,,
brightleaf pharmacy,Expense,,
"""


@pytest.fixture(scope="session")
def old_demo_rules(tmp_path_factory):
    path = tmp_path_factory.mktemp("old_rules") / "old_demo_rules.csv"
    path.write_text(OLD_DEMO_RULES, encoding="utf-8")
    return path
