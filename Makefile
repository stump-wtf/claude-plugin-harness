# Plugin Checks
#
# This repo ships documentation that models copy verbatim, so "test" means
# "every TOML example in a SKILL.md is config the harness parser accepts" and
# "lint" means "the plugin metadata and frontmatter are well-formed". Both run
# in CI via the same targets.
#
# `make test` uses the real `harness` binary when one is on PATH and falls back
# to tomllib plus the schema rules otherwise, so it works on a bare runner.
#
# @joestump-agent 08/20/2026 - Added alongside the harness_d skill refresh.

PYTHON ?= python3

.PHONY: check test lint

check: lint test

test:
	$(PYTHON) scripts/validate-examples.py

lint:
	$(PYTHON) scripts/lint-plugin.py
