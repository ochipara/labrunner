#!/usr/bin/env bash

# runner.sh - Entrypoint for LabRunner CLI
# Sets up the Python environment and invokes the CLI module

# Ensure the root of the repository is in PYTHONPATH
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export PYTHONPATH="${REPO_ROOT}/src:${PYTHONPATH:-}"
export PATH="${REPO_ROOT}/bin:$PATH"

# Pass all arguments directly to the python CLI
exec python3 -m labrunner.cli "$@"
