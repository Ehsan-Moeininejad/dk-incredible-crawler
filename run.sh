#!/bin/bash
# Wrapper used by launchd. Keeps paths absolute so the job works
# regardless of the working directory launchd starts it in.

cd "$(dirname "$0")" || exit 1

# If you use a virtualenv or conda env, point PYTHON at its interpreter.
PYTHON="${DK_PYTHON:-python3}"

"$PYTHON" crawler.py >> logs/run.out 2>&1
exit $?
