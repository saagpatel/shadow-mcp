import json

from shadow_mcp.cli import main


def test_scan_json_end_to_end(fake_home, capsys, tmp_path):
    rc = main(
        [
            "scan",
            "--home",
            str(fake_home),
            "--no-processes",
            "--no-cli",
            "--no-mcpaudit",
            "--registry-db",
            str(tmp_path / "absent.db"),
            "--format",
            "json",
        ]
    )
    assert rc == 0
    data = json.loads(capsys.readouterr().out)
    names = {s["entry"]["canonical_name"] for s in data["servers"]}
    # personal-ops merged across claude_code + codex into one entry
    assert "personal-ops" in names
    assert "bridge-db" in names
    assert "context7" in names
    # source tallies present
    assert data["source_summary"]["codex"] == 3
    # no secret values leaked into the JSON (only env key NAMES)
    assert "s3cr3t-sentinel-DO-NOT-LEAK" not in json.dumps(data)


def test_scan_writes_json_file(fake_home, tmp_path, capsys):
    out = tmp_path / "inv.json"
    rc = main(
        [
            "scan",
            "--home",
            str(fake_home),
            "--no-processes",
            "--no-cli",
            "--no-mcpaudit",
            "--registry-db",
            str(tmp_path / "absent.db"),
            "--json",
            str(out),
        ]
    )
    assert rc == 0
    assert out.exists()
    data = json.loads(out.read_text())
    assert data["host"]
    assert len(data["servers"]) >= 5


def test_discover_skips_grading(fake_home, capsys, tmp_path):
    rc = main(
        ["discover", "--home", str(fake_home), "--no-processes", "--no-cli", "--format", "json"]
    )
    assert rc == 0
    data = json.loads(capsys.readouterr().out)
    assert all(s["risk"]["headline"] == "ungraded" for s in data["servers"])


def test_sources_subcommand(fake_home, capsys):
    rc = main(["sources", "--home", str(fake_home), "--no-processes", "--no-cli"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "codex" in out
    assert "claude_code" in out
