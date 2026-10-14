"""Opt-in isolated PostgreSQL financial regression."""

import os
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.skipif(
    os.environ.get("KHAN_RUN_PG_INTEGRATION") != "1",
    reason="Requires explicitly enabled isolated PostgreSQL",
)
def test_deferred_stop_financial_invariants():
    script = Path(__file__).with_name(
        "deferred_stop_financial_invariants.py"
    )

    result = subprocess.run(
        [sys.executable, str(script)],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )

    assert result.returncode == 0, (
        result.stdout + "\n" + result.stderr
    )

    assert "EXACT_RESERVATION_AMOUNTS=PASS" in result.stdout
    assert "EXACT_LEDGER_TRANSACTION_COUNTS=PASS" in result.stdout
    assert "DOUBLE_ENTRY_BALANCE=PASS" in result.stdout
    assert "TEMPORARY_SCHEMA_CLEANUP=PASS" in result.stdout
