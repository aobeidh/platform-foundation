from __future__ import annotations

import json
from pathlib import Path

import pytest
from platform_kernel.expressions import ExpressionRegistry, JsonataEngine, Limits
from platform_testing import ExpressionEngineContract

SPEC = Path(__file__).resolve().parents[3] / "spec" / "conformance" / "expressions"


class TestJsonata(ExpressionEngineContract):
    @pytest.fixture
    def engine(self):
        return JsonataEngine()

    @pytest.fixture
    def cases(self):
        return json.loads((SPEC / "jsonata.json").read_text(encoding="utf-8"))


def test_regex_can_be_allowed_explicitly():
    e = JsonataEngine()
    allowed = Limits(allow_regex=True)
    compiled = e.compile('$contains("abc", /b/)', limits=allowed).value
    assert e.evaluate(compiled, {}, limits=allowed).value is True
    assert e.evaluate(compiled, {}).error.code == "EXPRESSION_LIMIT"  # still refused under default limits


def test_open_schema_only_warns():
    c = JsonataEngine().compile("extra", {"type": "object", "properties": {"a": {}}}).value
    assert c.warnings and c.references == frozenset({"extra"})


def test_registry_routes_by_language():
    reg = ExpressionRegistry([JsonataEngine()], default="jsonata")
    compiled = reg.compile("a + 1").value
    assert reg.evaluate(compiled, {"a": 1}).value == 2
    assert reg.compile("a", language="feel").error.code == "EXPRESSION_LANGUAGE_UNKNOWN"
    with pytest.raises(ValueError):
        ExpressionRegistry([JsonataEngine()], default="feel")
