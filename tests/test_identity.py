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


def test_node_script_qualified_by_dir():
    # a script file is identified by its path, not its bare basename
    spec = _stdio("node", "/a/b/start.mjs")
    assert stdio_reference(spec) == "b/start.mjs"


def test_plain_binary_uses_basename():
    spec = _stdio("/Users/dev/.claude/bin/personal-ops-mcp")
    assert stdio_reference(spec) == "personal-ops-mcp"


def test_signature_distinguishes_url_and_command():
    assert signature(ServerSpec(transport="http", url="https://x.y/mcp")).startswith("url:")
    assert signature(_stdio("engraph", "serve")) == "cmd:engraph"


def test_script_name_keeps_parent_dir():
    # a script basename alone is not an identity: keep the parent dir so two
    # different project-local `server.js` servers don't collide.
    assert stdio_reference(_stdio("node", "/projA/server.js")) == "proja/server.js"
    assert stdio_reference(_stdio("node", "/projB/server.js")) == "projb/server.js"


def test_any_script_extension_is_qualified_not_just_known_names():
    # the rule is structural (by file extension), so a script name no hardcoded
    # allowlist would have carried is still disambiguated.
    assert stdio_reference(_stdio("node", "/svcA/worker.js")) == "svca/worker.js"
    assert stdio_reference(_stdio("python", "/svcB/handler.py")) == "svcb/handler.py"


def test_generic_script_distinct_dirs_have_distinct_signatures():
    a = signature(_stdio("node", "/projA/server.js"))
    b = signature(_stdio("node", "/projB/server.js"))
    assert a != b


def test_direct_command_script_keeps_parent_dir():
    # the script invoked directly as the command (no launcher) also disambiguates
    assert stdio_reference(_stdio("/projA/main.py")) == "proja/main.py"


def test_non_script_binary_stays_bare():
    # a non-script executable is a distinctive identity; don't path-qualify it
    # (cross-host merge for these rides on the name union in the inventory layer)
    assert stdio_reference(_stdio("/Users/x/.codex/bin/github-mcp")) == "github-mcp"


def test_shim_wrapped_generic_script_disambiguates_by_dir():
    # `sh -c "node /proj/server.js"` must resolve to the script's dir, not "sh";
    # otherwise every shim-wrapped generic-script server collides on "cmd:sh".
    a = stdio_reference(_stdio("sh", "-c", "node /projA/server.js"))
    b = stdio_reference(_stdio("sh", "-c", "python /projB/main.py"))
    assert a == "proja/server.js"
    assert b == "projb/main.py"
    assert a != b
