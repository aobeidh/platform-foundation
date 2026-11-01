"""JSONata provider (jsonata-python, imported lazily: F5)."""
from __future__ import annotations

import json
import time
from typing import Any

from ..core import DomainError, Err, Ok, Result
from .engine import Compiled, Limits

_CHILD_ATTRS = ("lhs", "rhs", "expression", "expressions", "steps", "stages", "arguments", "procedure", "condition",
                "then", "_else", "else_", "predicate", "group", "lhs_terms", "update", "delete", "pattern", "body",
                "terms", "focus", "index", "tuple", "seeking_parent", "next_function")


DYNAMIC_ACCESS = frozenset({"lookup", "keys", "each", "sift", "spread", "eval"})


class _LimitExceeded(Exception):
    pass


def _refusing_regex_engine(pattern: str, flags: Any) -> Any:
    raise _LimitExceeded("regular expressions are not allowed")


def _variables(nodes: list[Any]) -> set[str]:
    return {str(n.value) for n in nodes if getattr(n, "type", None) == "variable" and n.value is not None}


def _walk(node: Any, seen: set[int] | None = None):
    seen = seen if seen is not None else set()
    if node is None or id(node) in seen:
        return
    seen.add(id(node))
    yield node
    for attr in _CHILD_ATTRS:
        child = getattr(node, attr, None)
        if child is None:
            continue
        items = child if isinstance(child, list | tuple) else [child]
        for item in items:
            if isinstance(item, list | tuple):
                for sub in item:
                    if hasattr(sub, "type"):
                        yield from _walk(sub, seen)
            elif hasattr(item, "type"):
                yield from _walk(item, seen)


def _root_references(ast: Any) -> tuple[set[str], bool]:
    """Top-level input fields the expression reads, and whether it reads the root dynamically (wildcards,
    descendants). `$` and `$$` as the first step mean the root, so `$.secret` reads `secret`."""
    refs: set[str] = set()
    dynamic = False
    if getattr(ast, "type", None) == "name":
        refs.add(str(ast.value))
    for node in _walk(ast):
        if getattr(node, "type", None) != "path":
            continue
        steps = list(getattr(node, "steps", None) or [])
        while steps and getattr(steps[0], "type", None) == "variable" and steps[0].value in ("", "$"):
            steps = steps[1:]
        if not steps:
            continue
        first = getattr(steps[0], "type", None)
        if first == "name":
            refs.add(str(steps[0].value))
        elif first in ("wildcard", "descendant"):
            dynamic = True
    return refs, dynamic


class JsonataEngine:
    language = "jsonata"

    def compile(self, text: str, input_schema: dict[str, Any] | None = None,
                limits: Limits | None = None) -> Result[Compiled, DomainError]:
        import jsonata

        limits = limits or Limits()
        if len(text) > 20_000:
            return Err(DomainError("EXPRESSION_INVALID", "The expression is longer than 20,000 characters."))
        if limits.allow_eval and not limits.allow_regex:
            return Err(DomainError("EXPRESSION_INVALID", "$eval cannot be allowed while regular expressions are "
                                                         "banned: it can build a regular expression at run time."))
        try:
            engine = jsonata.Jsonata(text) if limits.allow_regex else jsonata.Jsonata(
                text, regex_engine=_refusing_regex_engine)
        except _LimitExceeded:
            return Err(DomainError("EXPRESSION_INVALID", "Regular expressions are not allowed in this context: they "
                                                         "cannot be interrupted once they start."))
        except Exception as exc:  # noqa: BLE001 - the parser raises its own exception types
            if isinstance(exc.__cause__, _LimitExceeded) or "regular expressions are not allowed" in str(exc):
                return Err(DomainError("EXPRESSION_INVALID", "Regular expressions are not allowed in this context: "
                                                             "they cannot be interrupted once they start."))
            return Err(DomainError("EXPRESSION_INVALID", f"The expression is not valid JSONata: {exc}"))
        handle = engine
        nodes = list(_walk(handle.ast))
        uses_regex = any(getattr(n, "type", None) == "regex" for n in nodes)
        if uses_regex and not limits.allow_regex:
            return Err(DomainError("EXPRESSION_INVALID", "Regular expressions are not allowed in this context: they "
                                                         "cannot be interrupted once they start."))
        variables = _variables(nodes)
        if "eval" in variables and not limits.allow_eval:
            return Err(DomainError("EXPRESSION_INVALID", "$eval is not allowed: it runs code built at run time."))
        refs, dynamic = _root_references(handle.ast)
        warnings: list[str] = []
        schema = input_schema or {}
        props = schema.get("properties")
        if isinstance(props, dict):
            closed = schema.get("additionalProperties") is False
            unknown = sorted(r for r in refs if r not in props)
            if closed and unknown:
                return Err(DomainError("EXPRESSION_INVALID", "The expression reads fields the input does not have: "
                                       + ", ".join(unknown) + "."))
            if closed and (dynamic or variables & DYNAMIC_ACCESS):
                return Err(DomainError("EXPRESSION_INVALID", "Dynamic access to the input (wildcards, descendants, "
                                       "$lookup, $keys, $each, $sift, $spread, $eval) is not allowed when the input "
                                       "schema is closed."))
            warnings += [f"field {u!r} is not in the input schema" for u in unknown]
        max_chars = limits.max_output_bytes

        def bounded_pad(s: Any, width: Any, char: Any = " ") -> Any:
            # The built-in allocates the whole string in one call, before any limit can run.
            if s is None:
                return None
            w = int(width)
            if abs(w) > max_chars:
                raise _LimitExceeded(f"a $pad width above {max_chars}")
            fill = (str(char) or " ")[0]
            return str(s).ljust(w, fill) if w >= 0 else str(s).rjust(-w, fill)

        handle.register_lambda("pad", bounded_pad)
        return Ok(Compiled("jsonata", text, handle, frozenset(refs), tuple(warnings), uses_regex))

    def evaluate(self, compiled: Compiled, data: Any, bindings: dict[str, Any] | None = None,
                 limits: Limits | None = None) -> Result[Any, DomainError]:
        limits = limits or Limits()
        if compiled.uses_regex and not limits.allow_regex:
            return Err(DomainError("EXPRESSION_LIMIT", "Regular expressions are not allowed in this context."))
        expr = compiled.handle
        frame = expr.create_frame()
        for name, value in (bindings or {}).items():
            frame.bind(name, value)
        started = time.monotonic()
        state = {"depth": 0, "steps": 0}

        def entry(exp: Any, inp: Any, env: Any) -> None:
            state["steps"] += 1
            if not getattr(env, "is_parallel_call", False):
                state["depth"] += 1
            if state["depth"] > limits.max_depth:
                raise _LimitExceeded(f"deeper than {limits.max_depth} levels")
            if state["steps"] > limits.max_steps:
                raise _LimitExceeded(f"more than {limits.max_steps} evaluation steps")
            if (time.monotonic() - started) * 1000 > limits.timeout_ms:
                raise _LimitExceeded(f"longer than {limits.timeout_ms} ms")

        max_items = max(1, limits.max_output_bytes // 8)

        def exit_(exp: Any, inp: Any, env: Any, res: Any) -> None:
            if not getattr(env, "is_parallel_call", False):
                state["depth"] -= 1
            # Bound intermediate values, so repeated concatenation or array growth stops early.
            if isinstance(res, str) and len(res) > limits.max_output_bytes:
                raise _LimitExceeded(f"into a string longer than {limits.max_output_bytes} characters")
            if isinstance(res, list) and len(res) > max_items:
                raise _LimitExceeded(f"into an array longer than {max_items} items")

        frame.set_evaluate_entry_callback(entry)
        frame.set_evaluate_exit_callback(exit_)
        try:
            result = expr.evaluate(data, frame)
        except _LimitExceeded as exc:
            return Err(DomainError("EXPRESSION_LIMIT", f"The expression ran {exc}."))
        except RecursionError:
            return Err(DomainError("EXPRESSION_LIMIT", "The expression recursed too deeply."))
        except Exception as exc:  # noqa: BLE001 - evaluation errors are data errors, not crashes
            cause = exc.__cause__ if isinstance(exc.__cause__, _LimitExceeded) else None
            if cause is not None:
                return Err(DomainError("EXPRESSION_LIMIT", f"The expression ran {cause}."))
            return Err(DomainError("EXPRESSION_FAILED", f"The expression failed: {exc}"))
        if (time.monotonic() - started) * 1000 > limits.timeout_ms:
            # Limits are checked between evaluation steps; a single built-in call cannot be interrupted, but its
            # result is not used once it overran.
            return Err(DomainError("EXPRESSION_LIMIT", f"The expression ran longer than {limits.timeout_ms} ms."))
        try:
            size = len(json.dumps(result, default=str))
        except (TypeError, ValueError):
            return Err(DomainError("EXPRESSION_FAILED", "The expression returned a value that is not JSON."))
        if size > limits.max_output_bytes:
            return Err(DomainError("EXPRESSION_LIMIT", f"The result is larger than {limits.max_output_bytes} bytes."))
        return Ok(result)
