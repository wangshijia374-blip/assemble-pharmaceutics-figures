from __future__ import annotations

import os
import sys
from pathlib import Path


project = Path(os.environ.get("PHARMFIG_PROJECT_ROOT", Path(__file__).resolve().parents[3]))
source_tree = project / "src"
if source_tree.is_dir():
    sys.path.insert(0, str(source_tree))

from pharmfig.cli import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
