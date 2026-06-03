#!/bin/bash
if [ "$1" = "-h" ]; then
  echo "Usage: ./tests/run.sh [pytest args]"
  echo ""
  echo "Runs the Light Controllers test suite under CPython with fake hardware"
  echo "modules (machine, neopixel, network, espnow, uhashlib, ubinascii)."
  echo "Any extra arguments are passed through to pytest, e.g.:"
  echo "  ./tests/run.sh -k election      run tests matching 'election'"
  echo "  ./tests/run.sh tests/unit       run only the unit tests"
  echo ""
  echo "Flags:"
  echo "  -h  Show this help message"
  exit 0
fi

cd "$(dirname "$0")/.."

if ! python3 -c "import pytest" 2>/dev/null; then
  echo "pytest not found. Install the test dependencies first:"
  echo "  pipx run pytest   # or:  python3 -m pip install -r tests/requirements.txt"
  exit 1
fi

python3 -m pytest tests "$@"
