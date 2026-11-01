# ADR 0006: Approval policy in the governed-record engine

## Status

Accepted (milestone 0.4).

## Context

Until 0.3 every governed kind used maker-checker with a required test, or single approval when the deployment turned
maker-checker off. The Integration Hub, the second product on the foundation, needs what its own spec defines: an
`auto` mode where submitting activates the change (a developer embedding the hub), `single` approval, and
`maker_checker` for regulated deployments, each with or without a required test, set for the whole deployment or per
kind and changeable at run time. It also needs a returned state that keeps the approver's reason, and a way to discard
a draft. Building these in the hub would give the platform two lifecycle engines (F11). Two products now need them in
the same shape, so they belong in the foundation (F2).

## Decision

- `ApprovalRule(approval: "auto" | "single" | "maker_checker", require_test: bool)` and an `ApprovalPolicy` port
  (`rule_for(kind)`). The default provider, `StaticApprovalPolicy`, comes from settings (`APPROVAL`, `REQUIRE_TEST`);
  products pass their own with `with_approval_policy(...)`, for example one backed by governed settings.
- The engine reads the rule at submission and at approval; the stricter applies at approval. A kind may still declare
  a floor (`maker_checker="always"`) or a ceiling (`"never"`), so a deployment can never relax a kind below what its
  owner requires.
- `auto`: submitting activates in the same unit of work, and an `approved` transition is still audited and published,
  so consumers of approval events see every activation.
- Rejecting returns the version (`returned`, with the reason; the test no longer counts). `discard` drops a pending
  version (`discarded`); a record that never ran is retired, an active one keeps running.
- Transitions refuse with specific codes (`NO_DRAFT`, `DRAFT_SUBMITTED`, `NOT_SUBMITTED`, `NOT_ACTIVE`, `NOT_PAUSED`,
  `RECORD_RETIRED`) instead of one generic `INVALID_TRANSITION`, so portals and products can explain and map them.
- Versions record who tested them and when. Migration 0004 adds the columns (expand only).
- The portal API reports each kind's rule; the web kit offers discard, shows returned versions and their reason, and
  enables submit and approve by the rule.

## Consequences

- Behavior of existing deployments does not change: the default rule is maker-checker with a required test.
- Clients that matched `INVALID_TRANSITION` for lifecycle refusals must match the specific codes (the web kit does).
- `GovernedKind.maker_checker` is deprecated as the way to choose a mode; it remains as a floor or ceiling.
