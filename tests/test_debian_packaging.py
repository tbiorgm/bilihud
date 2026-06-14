from pathlib import Path


def test_debian_package_build_skips_upstream_tests() -> None:
    rules = Path("packaging/debian/rules").read_text(encoding="utf-8")

    assert "override_dh_auto_test" in rules
    assert "dh_auto_test" not in rules.split("override_dh_auto_test", maxsplit=1)[1]


def test_github_test_workflow_runs_pytest_separately() -> None:
    workflow = Path(".github/workflows/test.yml").read_text(encoding="utf-8")

    assert "pip install \".[test]\"" in workflow
    assert "xvfb-run pytest" in workflow
