"""Tests for scripts/run_aeh_eval_check.py."""

from __future__ import annotations

from pathlib import Path

from scripts.run_aeh_eval_check import main


def test_skips_when_disabled(tmp_path: Path) -> None:
    root = tmp_path / "submission"
    root.mkdir()
    rc = main(["--root", str(root), "--enabled", "false"])
    assert rc == 0


def test_skips_when_inventory_missing(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "submission"
    root.mkdir()
    monkeypatch.setattr(
        "scripts.run_aeh_eval_check._resolve_inventory_script",
        lambda: None,
    )
    rc = main(["--root", str(root)])
    assert rc == 0


def test_writes_report_and_stays_advisory(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "submission"
    root.mkdir()
    fake = tmp_path / "harness_inventory.py"
    fake.write_text(
        "import sys\n"
        "print('skills: 1')\n"
        "sys.exit(1)\n"
    )
    monkeypatch.setattr(
        "scripts.run_aeh_eval_check._resolve_inventory_script",
        lambda: fake,
    )
    out = tmp_path / "inventory.yaml"
    rc = main(["--root", str(root), "--output", str(out)])
    assert rc == 0
    assert "skills: 1" in out.read_text()
