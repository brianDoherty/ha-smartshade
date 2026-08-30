"""Packaging consistency: the things HACS, hassfest and the UI care about."""

import json
import pathlib
import re

ROOT = pathlib.Path(__file__).parent.parent
COMPONENT = ROOT / "custom_components" / "smartshade"
STRINGS = json.loads((COMPONENT / "strings.json").read_text())


def test_translations_match_strings():
    assert json.loads((COMPONENT / "translations" / "en.json").read_text()) == STRINGS


def test_manifest_has_everything_hassfest_wants():
    manifest = json.loads((COMPONENT / "manifest.json").read_text())
    assert {
        "domain", "name", "codeowners", "config_flow", "documentation",
        "integration_type", "iot_class", "issue_tracker", "requirements", "version",
    } <= set(manifest)
    assert manifest["domain"] == "smartshade"
    assert re.fullmatch(r"\d+\.\d+\.\d+", manifest["version"])


def test_manifest_version_matches_changelog():
    manifest = json.loads((COMPONENT / "manifest.json").read_text())
    changelog = (ROOT / "CHANGELOG.md").read_text()
    assert f"## [{manifest['version']}]" in changelog


def test_every_config_step_has_strings():
    source = (COMPONENT / "config_flow.py").read_text()
    steps = set(re.findall(r"async def async_step_(\w+)\(", source)) - {"init", "reauth"}
    assert steps == set(STRINGS["config"]["step"])


def test_every_abort_reason_has_strings():
    source = (COMPONENT / "config_flow.py").read_text()
    reasons = set(re.findall(r'async_abort\(\s*reason="(\w+)"', source))
    assert reasons <= set(STRINGS["config"]["abort"])


def test_every_entity_translation_key_has_strings():
    for path in COMPONENT.glob("*.py"):
        keys = set(re.findall(r'_attr_translation_key = "(\w+)"', path.read_text()))
        if keys:
            assert keys <= set(STRINGS.get("entity", {}).get(path.stem, {})), path.stem


def test_declared_platforms_have_modules():
    declared = {
        m.lower() for m in re.findall(r"Platform\.(\w+)", (COMPONENT / "__init__.py").read_text())
    }
    assert declared <= {p.stem for p in COMPONENT.glob("*.py")}


def test_commands_are_serialised_on_command_platforms():
    """Overlapping presses would compute the same next CID."""
    for name in ("cover.py", "button.py"):
        assert "PARALLEL_UPDATES = 1" in (COMPONENT / name).read_text()


def test_hacs_manifest_is_valid():
    hacs = json.loads((ROOT / "hacs.json").read_text())
    assert hacs["name"] and hacs["content_in_root"] is False


def test_no_bytecode_is_shipped():
    assert not list(COMPONENT.rglob("__pycache__"))
