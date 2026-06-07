#!/usr/bin/env bash
# Architectural invariants as a CI/lint check (NOT runtime guardrails).
# Each is a single grep that proves a structural rule still holds. Exit 1 on
# any violation so the build fails loudly.
set -uo pipefail
cd "$(dirname "$0")/.."

fail=0

echo "== Invariant 1: the LLM cannot reach the number path =="
# tools/ and data/ must never import the Anthropic SDK or howmid.llm.
hits=$(grep -rnE 'import +anthropic|from +anthropic|howmid\.llm' \
        src/howmid/tools src/howmid/data src/howmid/guardrails 2>/dev/null || true)
if [ -n "$hits" ]; then
  echo "  FAIL — LLM reference found in the number path:"; echo "$hits"; fail=1
else
  echo "  PASS — no LLM imports under tools/ data/ guardrails/"
fi

echo "== Invariant 2: Riegel/fatigue constants have one source of truth =="
# The literal constants may appear ONLY in config.py. Anywhere else = a drift-prone copy.
hits=$(grep -rnE '1\.06|1\.04|1\.03|1\.12' \
        src/howmid --include='*.py' 2>/dev/null \
        | grep -v 'src/howmid/config.py' || true)
if [ -n "$hits" ]; then
  echo "  FAIL — model constant hard-coded outside config.py:"; echo "$hits"; fail=1
else
  echo "  PASS — model constants live only in config.py"
fi

[ "$fail" -eq 0 ] && echo "ALL INVARIANTS HOLD" || echo "INVARIANT VIOLATION(S) FOUND"
exit "$fail"
