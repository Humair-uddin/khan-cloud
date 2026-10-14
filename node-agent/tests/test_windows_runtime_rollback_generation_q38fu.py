from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "deploy" / "install-runtime.ps1"


def source():
    return INSTALLER.read_text(encoding="utf-8")


def test_q38fu_runtime_backup_is_transaction_unique():
    text = source()

    assert '$RuntimeTransactionId = [Guid]::NewGuid().ToString("N")' in text
    assert '"runtime.rollback." + $RuntimeTransactionId' in text


def test_q38fu_does_not_delete_backup_before_runtime_backup_move():
    text = source()

    marker = 'Write-Host "===== BACKUP EXISTING RUNTIME ====="'
    start = text.index(marker)
    end = text.index(
        "$RuntimeTransactionActive = $true",
        start,
    )
    block = text[start:end]

    assert "Remove-Item" not in block
    assert "Move-Item" in block
    assert "Fresh runtime rollback generation unexpectedly already exists" in block


def test_q38fu_rollback_still_uses_transaction_owned_backup():
    text = source()

    # Existing rollback/commit paths must continue using $RuntimeBackup,
    # rather than reconstructing a fixed runtime.rollback pathname.
    assert text.count("$RuntimeBackup") >= 6

    assert (
        '$RuntimeBackup = Join-Path'
        in text
    )


def test_q38fu_preserves_q38fj_commit_boundary():
    text = source()

    marker = 'Write-Host "===== COMMIT RUNTIME TRANSACTION ====="'
    start = text.index(marker)
    block = text[start:]

    inactive = block.index(
        "$RuntimeTransactionActive = $false"
    )
    cleanup = block.index(
        "Remove-Item",
        inactive,
    )

    assert inactive < cleanup
    assert "Write-Warning" in block[cleanup:]
