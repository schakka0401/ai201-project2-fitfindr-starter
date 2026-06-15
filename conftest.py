"""
Makes the project root importable from tests/ so `from tools import ...` and
`from agent import ...` work when running `pytest tests/` from the repo root.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
