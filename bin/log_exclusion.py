#!/usr/bin/env python3
"""Stub for the exclusion ledger CLI.

Will mirror log_deviation.py but for runtime metric-integrity-gate failures
(Execution Plan §6.4). Implement when the orchestrator can emit exclusion
events programmatically (Stage 1+).
"""
from __future__ import annotations

import sys


def main() -> int:
    sys.stderr.write("log_exclusion.py is a Stage 1+ stub. Not yet implemented.\n")
    return 1


if __name__ == "__main__":
    sys.exit(main())
