# expressions

**Purpose:** The expression engine port (ADR 0001): compile at design time with a schema check, evaluate at run time inside limits (P15).

**Use it when:** A governed record holds a transform, a routing condition or a computed field written by an administrator.

**Do not use it when:** The logic is fixed product behavior; write it in code. Never evaluate expressions from untrusted sources without limits.

**Ports and API:** `ExpressionEngine` (compile, evaluate), `ExpressionRegistry` (several languages side by side; a stored expression names its language), `Limits`, `Compiled`.

**Providers:** `JsonataEngine` (jsonata-python). A FEEL subset is planned as a second provider. `EXPRESSION_LANGUAGE` picks the default.

**Example:**

```python
compiled = platform.expressions.compile("$sum(lines.amount)", input_schema=schema).value
platform.expressions.evaluate(compiled, payload).value
```

**Failure modes:** Unknown fields fail compilation when the input schema is closed (`additionalProperties: false`), otherwise they are warnings. Limits on time, depth, steps and output size are checked between evaluation steps; a single built-in call is not interrupted, but its result is discarded if it overran. Regular expressions are refused unless `Limits(allow_regex=True)`, because Python's `re` cannot be interrupted. Codes: `EXPRESSION_INVALID`, `EXPRESSION_FAILED`, `EXPRESSION_LIMIT`, `EXPRESSION_LANGUAGE_UNKNOWN`.

**Telemetry:** None yet.
