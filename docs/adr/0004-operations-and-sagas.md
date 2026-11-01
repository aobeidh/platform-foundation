# ADR 0004: Long-running operations and sagas on an in-process orchestrator

Status: accepted
Date: 2026-11-01   Principles: P39, I12, P10, F9

## Context

Bulk files, replays and partner onboarding outlive a request. Base principle P39 asks for 202 with a status resource,
and sagas with compensations for work that spans steps or services. P10 asks for lightweight defaults with heavy
infrastructure (Temporal) optional.

## Decision

- An `operation` table per service schema (row-level security) records kind, input, status, progress, result or
  error, a cancellation flag and saga state. `accepted()` answers 202 with `Location: /api/v1/operations/{id}`.
- `OperationRunner` executes work in a background pool with the caller's identity and tenant, the same correlation
  id and its own deadline. Every status change commits with its event (`<service>.operation.<status>.v1`) in one
  unit of work.
- A `Saga` is a list of steps with optional compensations. State is saved after every step and every compensation.
  On failure or cancellation the completed steps are compensated in reverse order. `resume_unfinished()` at startup
  continues pending and running operations from their saved state.
- `Orchestrator` is the port; Temporal will be a provider behind it.

## Consequences

- Steps and compensations must be idempotent: after a crash, the step that was running may run again.
- Every change locks the operation row. A runner claims an operation with a lease equal to the operation deadline;
  another instance takes over only after the lease ends, so an operation never runs twice at the same time.
- A failing compensation sets the status `stalled` (not finished). `resume_unfinished()` retries it from the
  compensation that failed. Resumed work runs with the creator's stored roles.
- One process runs a given operation; competing runners across processes need a lease, planned with the broker work.
- Cancellation is cooperative: handlers call `check_cancelled()`, and sagas check between steps.
