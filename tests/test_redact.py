from shadow_mcp.collectors.processes import parse_ps_output
from shadow_mcp.inventory import build_inventory
from shadow_mcp.models import GradedServer, Provenance, RiskAssessment, ServerSpec
from shadow_mcp.redact import scrub_args, scrub_url
from shadow_mcp.report import build_report


def test_scrub_args_redacts_key_value_pairs():
    assert scrub_args(["--api-key=abc123", "--read-only"]) == ["--api-key=REDACTED", "--read-only"]


def test_scrub_args_redacts_value_after_secret_flag():
    assert scrub_args(["--token", "supersecret", "stdio"]) == ["--token", "REDACTED", "stdio"]


def test_scrub_args_leaves_benign_flags_untouched():
    benign = ["stdio", "--read-only", "--toolsets=default,actions", "-y", "@scope/pkg"]
    assert scrub_args(benign) == benign


def test_scrub_url_redacts_query_secret_and_userinfo():
    assert scrub_url("https://h/mcp?token=abc&x=1") == "https://h/mcp?token=REDACTED&x=1"
    assert scrub_url("https://user:pass@h/mcp") == "https://user:REDACTED@h/mcp"


def test_scrub_value_shapes_catches_credentials_regardless_of_flag():
    # a bearer/provider token whose flag name is not in our vocabulary still goes
    assert scrub_args(["--header", "Bearer ghx123tokenvalue"]) == ["--header", "REDACTED"]
    assert "sk-" not in " ".join(scrub_args(["--x", "sk-abcdefABCDEF0123456789"]))
    out = scrub_args(["run", "ghp_0123456789ABCDEFGHIJ0123456789abcd"])
    assert "ghp_" not in " ".join(out)


def test_scrub_url_catches_path_embedded_token():
    assert "sk-" not in scrub_url("https://h/v1/sk-abcdefABCDEF0123456789/stream")


def test_serverspec_scrubs_on_construction():
    # the model is the chokepoint: secrets never survive into a stored spec
    spec = ServerSpec(
        transport="stdio",
        command="some-mcp",
        args=["--access-token", "leaky", "--ok"],
        url="https://h/mcp?api_key=leaky",
    )
    assert "leaky" not in spec.args
    assert "leaky" not in (spec.url or "")


def test_report_redacts_parent_command_and_url_argument():
    process_servers = parse_ps_output(
        "42 1 claude --api-key SENTINEL\n"
        "43 42 /opt/github-mcp-server --endpoint https://u:SENTINEL@h/mcp"
    )
    entries = build_inventory(process_servers)
    graded = [
        GradedServer(entry=entry, risk=RiskAssessment(band="unknown", headline="ungraded"))
        for entry in entries
    ]
    report = build_report(
        graded,
        host="fixture",
        generated_at="2026-01-01T00:00:00+00:00",
        source_counts={"process": len(process_servers)},
    )
    serialized = report.model_dump_json()
    assert "SENTINEL" not in serialized
    assert "u:REDACTED@h" in serialized
    assert scrub_args(["--read-only", "stdio"]) == ["--read-only", "stdio"]


def test_provenance_scrubs_parent_command():
    provenance = Provenance(
        source="process",
        location="ps",
        declared_name="fixture",
        parent="claude --api-key SENTINEL",
    )
    assert "SENTINEL" not in provenance.model_dump_json()


def test_scrub_args_redacts_url_userinfo():
    assert scrub_args(["--endpoint", "https://u:SENTINEL@h/mcp"])[1] == ("https://u:REDACTED@h/mcp")
