"""Browser-session settlement must not erase overlapping unconfirmed requests."""
from pathlib import Path
import shutil
import subprocess


def test_receipt_settlement_and_storage_boundaries():
    """One successful peer previously had no durable way to retain lost intent."""
    node = shutil.which("node")
    assert node, "Node is required for the receipt contract"
    result = subprocess.run([node, str(Path(__file__).with_name("js") / "paid_receipts_contract.mjs")],
        capture_output=True, text=True, encoding="utf-8", timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PASS paid receipt" in result.stdout
