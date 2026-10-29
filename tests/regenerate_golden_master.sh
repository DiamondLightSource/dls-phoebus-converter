#!/usr/bin/env bash
# Run test_front_ends and replace the golden master clone's front_ends/ with the output,
# for review with git. Never commits.
set -euo pipefail
cd "$(dirname "$0")/.."

rm -rf test_output
# Ensure this command is always reported as succeeding to allow script to continue. This
# allows us to compare output even if run would fail.
pytest --run-dls tests/integration/test_conversion_dls.py || true

# Note that the test doesn't start conversion if golden master is on wrong commit
if [ -z "$(ls -A test_output 2>/dev/null)" ]; then
    echo "Not copying: the conversion did not run. See the test output above." >&2
    exit 1
fi

rm -rf tests/golden_master/front_ends
cp -a test_output tests/golden_master/front_ends
git -C tests/golden_master status
