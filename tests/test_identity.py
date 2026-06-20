from shadow_mcp.identity import normalize_name, normalize_url, signature, stdio_reference
from shadow_mcp.models import ServerSpec


def _stdio(command, *args):
    return ServerSpec(transport="stdio", command=command, args=list(args))


def test_normalize_name_folds_separators_and_case():
    assert normalize_name("Personal_Ops") == "personal-ops"
    assert normalize_name("personal-ops") == "personal-ops"


def test_normalize_url_strips_scheme_and_trailing_slash():
    assert normalize_url("https://mcp.context7.com/mcp/") == "mcp.context7.com/mcp"


def test_npx_package_is_the_identity():
    spec = _stdio("npx", "-y", "@modelcontextprotocol/server-github")
    assert stdio_reference(spec) == "@modelcontextprotocol/server-github"


def test_npx_package_strips_version():
    spec = _stdio("npx", "@upstash/context7-mcp@latest")
    assert stdio_reference(spec) == "@upstash/context7-mcp"


def test_python_module_after_dash_m():
    spec = _stdio("uv", "run", "--directory", "/x", "python", "-m", "portfolio_health")
    assert stdio_reference(spec) == "portfolio_health"


def test_node_script_basename():
    spec = _stdio("node", "/a/b/start.mjs")
    assert stdio_reference(spec) == "start.mjs"


def test_plain_binary_uses_basename():
    spec = _stdio("/Users/dev/.claude/bin/personal-ops-mcp")
    assert stdio_reference(spec) == "personal-ops-mcp"


def test_signature_distinguishes_url_and_command():
    assert signature(ServerSpec(transport="http", url="https://x.y/mcp")).startswith("url:")
    assert signature(_stdio("engraph", "serve")) == "cmd:engraph"
