import sys
from pathlib import Path

# Let tests import Modules.* and main from the repo root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
