from pathlib import Path


def test_publish_workflow_builds_before_oidc_publish() -> None:
    workflow = Path(".github/workflows/publish.yml").read_text(encoding="utf-8")
    build = workflow.split("  build:\n", 1)[1].split("\n  publish:\n", 1)[0]
    publish = workflow.split("\n  publish:\n", 1)[1]

    assert workflow.count("id-token: write") == 1
    assert "id-token: write" not in build
    assert "environment:" not in build
    assert "contents: read" in build
    assert "needs: build" in publish
    assert "environment: pypi" in publish
    assert "id-token: write" in publish
    assert "run:" not in publish
    assert "actions/checkout@" not in publish
