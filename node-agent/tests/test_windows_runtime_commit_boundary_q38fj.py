from pathlib import Path


INSTALLER = (
    Path(__file__).resolve().parents[1]
    / "deploy"
    / "install-runtime.ps1"
)


def _source() -> str:
    return INSTALLER.read_text(encoding="utf-8")


def test_transaction_is_committed_before_backup_cleanup():
    source = _source()

    commit_marker = source.index(
        'Write-Host "===== COMMIT RUNTIME TRANSACTION ====="'
    )
    inactive = source.index(
        "$RuntimeTransactionActive = $false",
        commit_marker,
    )
    cleanup = source.index(
        "Remove-Item `",
        inactive,
    )

    assert inactive < cleanup


def test_committed_backup_cleanup_is_non_transactional():
    source = _source()

    commit_marker = source.index(
        'Write-Host "===== COMMIT RUNTIME TRANSACTION ====="'
    )
    block = source[commit_marker:]

    assert "$RuntimeTransactionActive = $false" in block
    assert "$RuntimeBackupCreated = $false" in block
    assert "-ErrorAction Stop" in block
    assert "Write-Warning" in block
    assert "rollback backup cleanup failed" in block


def test_cleanup_failure_cannot_enter_runtime_restore():
    source = _source()

    commit_marker = source.index(
        'Write-Host "===== COMMIT RUNTIME TRANSACTION ====="'
    )
    catch_marker = source.index(
        "catch {",
        commit_marker,
    )

    prefix = source[commit_marker:catch_marker]

    assert "$RuntimeTransactionActive = $false" in prefix
