#!/usr/bin/env python3
"""Print the FRED macro snapshot as JSON.

    python3 -m tools.macro

Replaces the `python3 -c "from adapters.fred import snapshot ..."` line in the
premarket-brief skill. A `python3 -c` command cannot be allow-listed (auto mode
strips `Bash(python3 -c:*)`), so it went to the auto-mode classifier on every
open. That is the same exposure that refused the 2026-09-25 open (F-1). A named
module can be allowed exactly.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main(fetch=None) -> int:
    if fetch is None:
        from adapters.fred import snapshot as fetch
    print(json.dumps(fetch(), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
