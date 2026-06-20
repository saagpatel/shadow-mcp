from shadow_mcp.models import ServerSpec
from shadow_mcp.redact import scrub_args, scrub_url


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
