"""Family B baselines from the RCAEval suite (S4.8, design s4_8_baselines_design.md).

The baselines never share an environment with HELIOS: each run exports the
sealed window into RCAEval's file layout (``export``), runs the method in a
pinned container with no network (``container``), and stores the ranking
(``executor``) for the same scoring path as HELIOS.
"""

from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance
