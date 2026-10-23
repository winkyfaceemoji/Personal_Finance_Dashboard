import contextlib
import io
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def _files(folder: Path) -> dict[str, bytes]:
    return {str(p.relative_to(folder)): p.read_bytes() for p in folder.rglob("*") if p.is_file()}


def test_convert_check_converts_a_copy_moves_no_label_and_writes_nothing(tmp_path, old_demo_rules):
    from main import main as run_ingest
    data = tmp_path / "data"
    shutil.copytree(REPO / "Test Data" / "RAW", data / "RAW")
    with contextlib.redirect_stdout(io.StringIO()):
        run_ingest(data)
    shutil.copy(old_demo_rules, data / "SORTED" / "rules.csv")       # the demo before its keywords were merchants
    before = _files(data)
    env = dict(os.environ, FINANCE_DATA_DIR=str(data))
    env.pop("FINANCE_EMBED_URL", None)
    out = subprocess.run([sys.executable, str(REPO / "convert_check.py")], cwd=REPO, env=env,
                         capture_output=True, text=True, timeout=300)
    assert out.returncode == 0, out.stderr
    assert "18 proposals" in out.stdout
    assert "Preview: Convert 18 rules.csv keywords into merchants: no labels change" in out.stdout
    assert "0 rows show a different label or category after converting" in out.stdout
    assert _files(data) == before                                     # the data folder is untouched


def test_convert_check_says_when_there_is_nothing_to_convert(tmp_path):
    (tmp_path / "SORTED").mkdir()
    env = dict(os.environ, FINANCE_DATA_DIR=str(tmp_path))
    out = subprocess.run([sys.executable, str(REPO / "convert_check.py")], cwd=REPO, env=env,
                         capture_output=True, text=True, timeout=120)
    assert out.returncode == 1 and "No rules.csv keywords to convert." in out.stdout
