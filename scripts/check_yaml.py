"""Validate a YAML file — used in CI setup checks."""

import sys

import yaml

path = sys.argv[1] if len(sys.argv) > 1 else ".github/workflows/ci.yml"
with open(path) as f:
    yaml.safe_load(f)
print(f"YAML valid: {path}")
