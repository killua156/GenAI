"""Make kalshi_bot/ importable when running pytest from any cwd."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
