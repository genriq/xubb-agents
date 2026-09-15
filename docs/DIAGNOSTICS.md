# Diagnostics reference

**Applies to runtime:** 3.1.4 · Every code in `DIAGNOSTIC_CODES`, with what it means and what
to do about it.

When the engine refuses something, it says so in a `InsightDiagnostic` on the `AgentResponse`.
This page exists because those codes reach your logs and you need somewhere to look them up
that is not the source.

## How to read a diagnostic

```python
for d in response.diagnostics:
    print(d.code, d.field_path, d.classification, d.agent_id, d.execution_id)
```

- **`code`** — from the fixed vocabulary below.
- **`field_path`** — where in the envelope, e.g. `insight.content`, `events[0]`, `$` for the
  whole response.
- **`classification`** — a **bounded** string the framework chose (a type name, a reason, a
  truncated value). It is never raw model text, so it is safe to log.
- **`agent_id` / `execution_id`** — which agent, and which run of it.

## A diagnostic is not automatically a failure

Read `acceptance_status` alongside the diagnostics; the two answer different questions.

| Status | Meaning |
|---|---|
| `accepted` | The response was accepted and an insight was published |
| `accepted_silent` | Valid silence — no insight, and any permitted channels committed |
| `rejected` | Nothing from this response committed |

**Rejection is whole-response.** A rejected response commits none of its effects — not its
insight, not its state updates, not its actions. So a diagnostic never means "part of this was
applied".

And the converse: **an accepted response can carry diagnostics.** `capability_unavailable` and
`unsupported_structured_output` are observability, not refusal. Do not write
`if response.diagnostics: discard()`.

**Per-agent aggregation.** On the merged turn response, `acceptance_by_agent` tells you which
agents were accepted; one rejected agent does not discard the others' work.

**Retrying unchanged input does not help** for any code below except
`unsupported_structured_output` and the transport-failure classifications of
`invalid_envelope` (`timeout`, `rate_limit`, `server`). Everything else is a deterministic
verdict on the content or the configuration: the same input produces the same refusal.

**These are operator diagnostics.** They are not text to show the assisted user.

---

## Envelope and gate

### `invalid_envelope`

**Status:** active

No JSON object arrived from the model at all. The `classification` carries the model client's
failure category — `timeout`, `rate_limit`, `server`, `refusal`, `malformed`, `truncated`,
`auth`, `misconfig`, `not_initialized`, `unknown` — or `none` when the client reported none,
so you can tell a provider outage from a refusal without parsing prose. A non-object body
reports its type name instead.

**Effect:** whole response rejected. Usage and diagnostics survive.
**Do:** treat `timeout` / `rate_limit` / `server` as retryable; treat `refusal` and `malformed`
as a prompt or model-choice problem.

### `invalid_gate`

**Status:** active

The speech gate was missing or malformed — `has_insight` absent, or a string/number where the
JSON boolean belongs. Truthiness is never accepted: `"false"` is not `false`.

**Effect:** whole response rejected.
**Do:** check the agent's output format matches what the model is being told to produce.

### `inconsistent_gate`

**Status:** active

The gate and the insight disagree: `has_insight: true` with a null or empty insight, or
`false` with an insight present.

**Effect:** whole response rejected.

---

## Insight fields

### `invalid_field`

**Status:** active — the most common code

A field in the candidate insight is missing, the wrong type, or not asked for. The
`classification` says which: `missing`, `unexpected_key`, `engine_owned` (a producer tried to
set a field the engine stamps), `unknown_envelope_key`, `content_alias_conflict`,
`hypothesis_requires_rationale`, and similar.

**Effect:** whole response rejected.
**Do:** read `field_path` and `classification` together — they name the exact field and rule.

### `invalid_metadata`

**Status:** active

`insight.metadata` was not a plain object with string keys.

### `invalid_confidence`

**Status:** active

A confidence value that is not a finite number in `[0, 1]`. Note that an *absent* confidence is
not an error — it yields a placeholder value with `confidence_provided: false`.

### `invalid_urgency`

**Status:** active

An explicit urgency outside `now` / `soon` / `whenever`.

---

## Types and capabilities

### `unknown_type`

**Status:** active

The model wrote a type label that is not a recognised wire value. It is rejected, never
relabelled — nothing in the framework maps an unknown label onto `suggestion`.

### `type_not_allowed`

**Status:** active

A recognised type the agent or the host did not permit for this run.

**Do:** widen `InsightConfig.allowed_types`, or the host's
`HostInsightCapabilities.supported_types`, if the purpose is genuinely wanted.

### `capability_unavailable`

**Status:** active — **observability, not refusal**

A purpose the agent is configured for was unavailable this run: the host does not support it,
or a prerequisite is missing (a `reply` or `question` with no `principal_id`). The response can
still be accepted.

**Do:** this is the code that tells you a capability silently narrowed. If you expected an agent
to be able to ask questions and it never does, look here first.

### `no_supported_insight_types`

**Status:** **retired — no current emitter.** Registered in `DIAGNOSTIC_CODES`, but no path in
3.1.3 emits it; the empty-allowed-set case is handled as a silence-only envelope instead.

It is kept in the vocabulary deliberately: removing a registered code is a compatibility
decision for hosts that may branch on it, not documentation tidying.

---

## Evidence and references

### `missing_evidence`

**Status:** active

A purpose that requires an evidence basis was emitted without one — a consulting hypothesis or
implication, or a correction.

### `unknown_reference`

**Status:** active

A citation named an id that was not in what the agent was actually shown. Identity is checked
against the run's snapshot; the model cannot invent one.

### `cross_session_reference`

**Status:** active

A citation reached into another session.

### `invalid_input_reference`

**Status:** active

A host-supplied reference or answer failed validation at turn start — before any agent saw it.

**Do:** this one is about *your* input, not the model's.

---

## Interactive operations

### `missing_principal`

**Status:** active

An operation that needs a present, matching principal identity was attempted without one.
`principal_id` is host-supplied and the framework never infers it from transcript speakers.

### `invalid_correction_target`

**Status:** active

A correction named a target that is not correctable: not the agent's own earlier insight, not
retained, from the current turn, or marked `correctable: false`.

### `correction_conflict`

**Status:** active

Two corrections in the same turn targeted the same insight. Arbitration rejects rather than
picking one.

### `invalid_question_contract`

**Status:** active

A `question` insight's payload was missing or malformed — no reason, or an unsupported response
format.

---

## Channels and state

### `undeclared_channel`

**Status:** active — added 3.1.0

A channel key the agent's output format does not bind, or that this run does not offer (the
isolated content path offers none). Enforced identically whether the agent speaks or stays
silent: **a speech gate never grants a write permission.**

**Effect:** whole response rejected.
**Do:** check the format's channel bindings in
[MIGRATION_OUTPUT_FORMATS.md](MIGRATION_OUTPUT_FORMATS.md).

### `invalid_domain_payload`

**Status:** active

A bound channel was present with the wrong shape — events that are not a list, a fact with a
non-finite confidence, a map with non-string keys, a channel present as `null`.

### `reserved_state_write`

**Status:** active

A proposed write to the engine-reserved `sys.*` variable namespace.

---

## UI actions

### `invalid_ui_action`

**Status:** active — added 3.1.0

A `ui_actions` value that is not an array, or an item that is not an object carrying exactly
`target_widget`, `action` and `payload`. Shape is checked before authorization, so this code
means the item never reached the host's declarations.

### `unauthorized_ui_action`

**Status:** active — added 3.1.0

A well-formed action the host did not authorize. The `classification` names the rule:
`no_widgets_declared`, `unknown_target`, `unknown_action`, `missing_payload_key:<key>`,
`unexpected_payload_key:<key>`, or a string your own `widget_payload_validator` returned.

**Do:** `no_widgets_declared` almost always means the host did not populate
`AgentContext.widget_capabilities` — including by misspelling it, which is silently accepted.

---

## Provider transport

### `unsupported_structured_output`

**Status:** active — **observability, not refusal**

The provider would not accept the JSON Schema request. The `classification` distinguishes
`downgraded:*` (an enabled signature authorised one fallback) from `fail_closed:*` (none did,
and strict mode does not silently downgrade).

### `provider_schema_error`

**Status:** active

The compiled provider projection failed its own lint, so **no call was made**. This is a
framework defect rather than a model or configuration problem.

**Effect:** whole response rejected, with no provider cost.

---

## Long-form content

These arise only for agents with a negotiated `long_form_v1` content block.

### `content_extension_not_enabled`

**Status:** active — the extension's fields appeared on output that never negotiated it.

### `content_contract_unavailable`

**Status:** active — the host did not declare the content contract the agent asks for.

### `invalid_content_policy`

**Status:** active — the operator or agent content policy is itself malformed (a missing byte
ceiling, a non-positive limit). A configuration error, not a model one.

### `unsupported_depth`

**Status:** active — a depth the agent or host does not offer.

### `unsupported_content_format`

**Status:** active — a `content_format` outside the negotiated set.

### `content_too_large`

**Status:** active — the body exceeded the effective character ceiling. Nothing is shortened and
accepted.

### `preview_too_large`

**Status:** active — the preview exceeded its ceiling. A preview never salvages a rejected body.

### `response_too_large`

**Status:** active — the serialized response exceeded the operator's byte ceiling.

### `incomplete_generation`

**Status:** active — generation stopped on length. The result is incomplete, billed, and never
salvaged.

### `completion_unknown`

**Status:** active — the client reported no trustworthy completion status, so the result cannot
be certified complete. Fail-closed: an unknown completion is not treated as a good one.

### `content_execution_not_allowed`

**Status:** active — the declared execution context does not permit this generation: an isolated
path not issued by the engine, a live-turn depth beyond the operator's ceiling, or domain
effects on a result-only request.

### `invalid_content_execution_context`

**Status:** active — the execution declaration itself was malformed or missing required
operator limits.

---

## Retired

### `partial_legacy_response`

**Status:** **retired — no current emitter.** It reported the `legacy_v2` contract's partial
acceptance, where a recoverable insight error still committed valid channels. 3.0.0 removed
that contract and the `partial` acceptance status with it; under the single contract, rejection
is whole-response.

Kept in `DIAGNOSTIC_CODES` deliberately — see `no_supported_insight_types` above for the same
reasoning. Retiring a registered code is a compatibility decision, and it has not been taken.
