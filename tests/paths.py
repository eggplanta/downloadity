import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "tests" / "output"

sys.path[:0] = [str(ROOT / "src"), str(ROOT / "UI")]
