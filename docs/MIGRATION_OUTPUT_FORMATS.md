# Migrating output formats (3.1.0 → 4.0.0)

3.1.0 consolidates authoring onto **two** output formats and repairs seven verified
disagreements between what the framework told a model to produce and what it actually
read. Nothing is removed in 3.1.0: the four superseded names keep working, loudly, for
one release.

| | |
|---|---|
| **Supported** | `insight_v1` (insight + state), `widget_control` (insight + state + UI actions) |
| **Deprecated in 3.1.0, removed in 4.0.0** | `default`, `default_v2`, `v2_raw`, `ui_control` |
| **Implicit runtime default** | `default` in 3.1.0 → **`insight_v1` in 4.0.0** |

Design and rationale: [SPEC_OUTPUT_FORMAT_CONSOLIDATION.md](SPEC_OUTPUT_FORMAT_CONSOLIDATION.md).

## Start here

```bash
python tools/migrate_output_formats.py path/to/agent-configs.json
```

It reports, per agent: the current format (naming every one that **inherits** the
implicit default), the target, and the work it cannot do for you. `--dry-run` shows the
rewrite; `--write` applies the mechanical part only.

If you do not use the tool, the checklist is:

1. **Set `output_format` explicitly on every agent.** An omitted key is the single most
   expensive thing to leave: it silently changes meaning at 4.0.0.
2. **Move each agent to its target format** (table below).
3. **Strip envelope instructions from handwritten prompt bodies.** The framework
   generates the envelope instruction per run from the format contract and the run's
   permissions; a hand-written `has_insight`/`message`/`state_snapshot` block in your
   `text` can only disagree with it.
4. **Declare your widgets** if you have widget agents (see below). Without declarations
   no action is authorized.
5. **Run your agents against the new engine and read the diagnostics.** Every tightening
   below fails loudly; none of them fails silently.

## Target formats

| From | To | What changes on the wire |
|---|---|---|
| `default` | `insight_v1` | flat fields move into a nested `insight`; `content` is the field (`message` accepted as an input alias during the window); the private scratchpad stays `memory_updates` |
| `default_v2` | `insight_v1` | flat fields move into a nested `insight`; the five channels keep their names |
| `v2_raw` | `insight_v1` | root presence becomes the explicit `has_insight` gate; `state_snapshot` becomes `variable_updates` |
| `ui_control` | `widget_control` | as `v2_raw`, plus actions under the validated `ui_actions` contract |
| `widget_control` | `widget_control` | **its shape changes**: canonical envelope (`has_insight` + nested `insight`), `variable_updates` instead of `state_snapshot`. The legacy shape is still accepted until 4.0.0 — see the window rule below |

## Before and after

### Speaking

```jsonc
// default / default_v2 (deprecated)
{"has_insight": true, "type": "warning", "content": "The date depends on an approval.", "confidence": 0.7}

// insight_v1
{"has_insight": true,
 "insight": {"type": "warning", "content": "The date depends on an approval.", "confidence": 0.7}}
```

```jsonc
// v2_raw (deprecated) — presence is the gate
{"insight": {"type": "warning", "content": "The date depends on an approval.", "confidence": 0.7}}

// insight_v1 — the gate is explicit and required
{"has_insight": true,
 "insight": {"type": "warning", "content": "The date depends on an approval.", "confidence": 0.7}}
```

### Silence with state updates

```jsonc
// v2_raw (deprecated): silence is "no insight key"
{"state_snapshot": {"phase": "closing"}}

// insight_v1: silence is an explicit false gate, and it may still write
{"has_insight": false, "insight": null, "variable_updates": {"phase": "closing"}}
```

### Private memory

```jsonc
// default (deprecated) and insight_v1 use the same key; the scratchpad is unchanged
{"has_insight": false, "insight": null, "memory_updates": {"seen": 1}}
```

`default`'s memory still reaches the blackboard through
`AgentResponse.state_updates["memory_<agent id>"]`, exactly as before. That is a
host-facing compatibility projection and it is preserved deliberately.

### Widget actions

```jsonc
// ui_control / legacy widget_control (deprecated)
{"insight": null,
 "ui_actions": [{"target_widget": "goals_widget", "action": "update", "payload": {"goal_id": "g1"}}],
 "state_snapshot": {"phase": "closing"}}

// widget_control
{"has_insight": false, "insight": null,
 "ui_actions": [{"target_widget": "goals_widget", "action": "update", "payload": {"goal_id": "g1"}}],
 "variable_updates": {"phase": "closing"}}
```

Acting without speaking is still valid, and still the point of the format.

## Host integration: declaring widgets

An action is a **host** capability. The model cannot grant itself one, and missing
declarations authorize **nothing** — never everything.

```python
from xubb_agents import (
    AgentContext, HostWidgetCapabilities, WidgetDeclaration, WidgetActionDeclaration,
)

context = AgentContext(
    ...,
    widget_capabilities=HostWidgetCapabilities(widgets=[
        WidgetDeclaration(target_widget="goals_widget", actions=[
            WidgetActionDeclaration(action="update",
                                    required_payload_keys=["goal_id"],
                                    optional_payload_keys=["done"]),
        ]),
        WidgetDeclaration(target_widget="flash_zone", actions=[
            WidgetActionDeclaration(action="flash", allow_additional_payload_keys=True),
        ]),
    ]),
)
```

For payload rules a key list cannot express, pass a validator once at the engine:

```python
engine = AgentEngine(api_key=..., widget_payload_validator=my_validator)
# my_validator(action) -> None to allow, or a short string naming why it was refused
```

The declarations also shape the **prompt**: the model is told exactly which targets,
actions and required payload keys exist. With nothing declared it names no target and is
required to send `"ui_actions": []` — the empty array, which is also what the strict
projection requires — so it is never invited to produce an action the boundary will reject.

**Validation and delivery are not execution.** The framework validates an action and
publishes it on `AgentResponse.data["ui_actions"]` (attributed per agent in
`data_by_agent`). Your host executes it. An accepted action means "this was well-formed and
authorized", never "this happened": nothing here is an atomic transaction over an external
UI effect, and a response accepted by the engine can still fail in your widget.

## The `widget_control` compatibility window

During 3.1.0 `widget_control` accepts both shapes under one rule, which is deterministic
and decides for every body:

- the top-level object **has** `has_insight` → the canonical envelope;
- it **does not** → the legacy root-presence envelope, plus a `DeprecationWarning`.

In 4.0.0 only the canonical envelope is accepted.

## Deliberate tightenings

Each of these rejects something 3.0.0 accepted. Each fails **loudly**, with a diagnostic
or a configuration error naming the rule. None of them is a silent behaviour change.

**Of accepted model output**

| Tightening | Diagnostic |
|---|---|
| A channel key the format does not bind — whether the agent speaks or stays silent. `default` accepting `events` while silent and rejecting it while speaking was the defect | `undeclared_channel` |
| An unknown top-level key on a nested envelope | `invalid_field` / `unknown_envelope_key` |
| A UI action that is malformed, or names an undeclared target or action, or carries an undeclared payload key | `invalid_ui_action`, `unauthorized_ui_action` |
| A `default` body carrying both `message` and `content` with different text | `invalid_field` / `content_alias_conflict` |
| A channel key present with the value `null`. Absent means "no proposal"; `[]` and `{}` are the empty forms; a present null is a value of the wrong shape (3.1.1) | `invalid_domain_payload`, or `invalid_ui_action` on the action channel |
| A channel key on an isolated content run, which offers none — even empty (3.1.1) | `undeclared_channel` |

**Of accepted configuration** (all `AgentConfigurationError`, all before any registry
mutation)

| Tightening | Why |
|---|---|
| An unknown, `null`, empty or non-string `output_format` | the old fallback to `default` re-homed a typo'd agent into a different envelope, silently |
| A structural `mapping` / `descriptor` override — a different gate key, root key, content field, channel key or adapter identifier | an override used to change the parser without changing the generated prompt |
| `speak_without_gate` | documented, accepted, and read by nothing since 2.2 |

An **omitted** `output_format` is deliberately not in that list: it resolves to the
implicit default before name validation, so existing configurations keep registering. It
inherits that format's deprecation warning, which is the nudge to set it explicitly.

## New diagnostic codes

`undeclared_channel`, `invalid_ui_action`, `unauthorized_ui_action`. All are fatal: a host
that ignores unknown codes sees a rejection, never a silent acceptance.

## Transport

- `insight_v1` and `widget_control` both support `strict` (provider JSON Schema) and
  `json_object`. The projection now offers **exactly** the channels the format binds; it
  used to require `state_updates` and `data` of the model on a format whose parser read
  neither.
- **Request size:** `strict` adds the schema to each request — a modest, fixed increase,
  slightly smaller than 3.0.0's for `insight_v1` because two channels are gone.
  `auto` and `json_object` are unchanged.
- **Latency:** unchanged. Fallback and retry bounds are unchanged; `strict` still never
  silently falls back.
- **Provider compatibility:** `strict` requires an endpoint supporting JSON Schema
  response formats. `auto` downgrades only on an enabled signature; `json_object` works
  everywhere.
- Local validation remains mandatory on every transport.

## Rolling back

**Pin-only** — if your host passes no `widget_capabilities` and no
`widget_payload_validator`, no agent changed format, and no `widget_control` agent moved
to the canonical envelope: downgrade the library pin. No configuration change is needed.
The tested subset is `tests/fixtures/rollback_safe_3_0/fixtures.json`.

**Coordinated** — once you have adopted the new surface, in this order:

1. remove `widget_capabilities` / `widget_payload_validator` from host code (a 3.0.0
   engine raises `TypeError` on the former and `AgentContext` rejects the latter);
2. revert any handwritten prompt body you updated for the canonical envelope (generated
   instructions need no action — a rolled-back library regenerates the old shape);
3. restore the pin.

There is no backward translation from the canonical envelope to the root-presence one.
The 3.1.0 window runs forward only.

## Before 4.0.0

- every agent sets `output_format` explicitly;
- no agent is on `default`, `default_v2`, `v2_raw` or `ui_control`;
- every widget agent emits the canonical envelope and its host declares its widgets.

Run the tool again; it exits 0 when there is nothing left to do.
