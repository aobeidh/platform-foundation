# ADR 0001: The expression language is a port with providers, not a fixed choice

Status: accepted
Date: 2026-11-01   Principles: P8, P9, P15, F4

## Context

Transforms, routing conditions and rule tables need a bounded expression language. The candidates were JSONata
(widely known, made for JSON transformation, several implementations), a FEEL subset (natural for DMN decision
tables) and JMESPath (simple queries, weak transformation). Choosing one in the kernel would lock every product into
it, which contradicts our own rule that every dependency sits behind an interface with swappable providers.

## Decision

- The kernel defines an `ExpressionEngine` port: `compile(text, input_schema) -> Compiled`, which validates syntax and
  field references at design time, and `evaluate(compiled, data, limits)`, which enforces time, step and memory
  limits.
- Each language is a provider. Planned providers: JSONata and a FEEL subset. Configuration chooses the provider per
  deployment, and a governed record may name the language it is written in, so more than one can run side by side.
- All providers pass one conformance suite in `spec/conformance/expressions/` and are fuzz tested (F18, F19).

## Alternatives considered

- **Pick JSONata for everything.** Simple, but decision tables read better in FEEL, and a fixed choice cannot be
  undone without migrating every stored expression.
- **Pick the FEEL subset for everything.** Consistent with DMN, but less familiar to integration engineers and weaker
  for reshaping JSON.

## Consequences

- No language is built into the kernel; milestone 0.1 does not ship the module yet (see the milestone scope).
- Stored expressions carry their language, so a deployment can add a provider without rewriting old records.
- Every provider costs a conformance suite and fuzzing; that is the price of being swappable.
