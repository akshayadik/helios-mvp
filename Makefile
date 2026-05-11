# HELIOS MVP — Makefile targets
#
# Run validators and tests without depending on pre-commit being installed.
 
.PHONY: validate-tracking test-tracking install-hooks
 
validate-tracking:
	@python scripts/validate_tracking.py
 
test-tracking:
	@python -m pytest tests/test_validate_tracking.py -v
 
install-hooks:
	@pip install pre-commit
	@pre-commit install
	@echo "Pre-commit hooks installed. The tracking validator will run on every commit"
	@echo "that touches docs/tracking/helios_mvp_tracking.md."