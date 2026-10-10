#!/usr/bin/env bash
# RESET CORE DEMO — restores demo data, settings, filters, scenarios, budget, review queue and decisions (also available as the RESET DEMO button).
set -e
cd "$(dirname "$0")/.."
if [ -d .venv ]; then source .venv/bin/activate; fi
python scripts/init_demo.py --reset
