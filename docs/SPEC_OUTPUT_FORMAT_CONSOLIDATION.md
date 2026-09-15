# SPEC — Consolidate and repair the output formats

- **Status:** SHIPPED — merged as PR #42 (2026-09-14), released as 3.1.0, tagged `v3.1.0` at `b4ce54b`
- **Reviewed by Codex —** APPROVED round 2 (round 1: 2 majors + 2 minors — F1 registration vs the retained implicit default, F2 the unscoped rollback claim, F3 gate terminology, F4 widget diagnostic precedence — all fixed; round 2 clean but for F5, a wording conflict between widget channel availability and the isolated-content restriction, fixed in place. Nothing contested.)
- **Target releases:** **3.1.0** (deprecation + repairs) and **4.0.0** (removal). Both numbers are published by 3.1.0.
- **Baseline:** 3.0.0, commit `d9a8b32577fcc353a80240f7206d0b5f41bd163f`
- **Supersedes:** the per-schema `mapping` regime of XUBB-ITC-1 §13.1 as the authority for envelope shape; amends A-1 / INV-11 (gate-less schemas, see §9.3)

## 1. Summary

The framework ships six output formats. They are not six views of one contract — they are six partly-specified contracts whose prompt, schema definition, parser and validator disagree with each other in ways that are individually small and jointly fatal: an agent authored against the published `default` contract emits nothing, a schema author's gate override changes neither the prompt nor the parser, a documented opt-in is inert, a silent response may write a channel its format never declared, a widget action may be any shape at all, and a misspelt format name silently registers the agent under a different envelope.

This spec consolidates authoring onto **two** formats — `insight_v1` for insight and state agents, `widget_control` for agents that also drive UI — gives each **one** authoritative machine-readable contract from which generation, projection and parsing are derived, repairs the seven verified disagreements, and ships a versioned migration in which the four superseded names keep working, loudly, for one release.

Reducing the number of JSON files is not the goal. The goal is that an agent can **speak, stay silent, and perform exactly its permitted state and UI operations, predictably**, and that every field the framework asks a model to produce has a defined decode and consumption path.

## 2. Verified baseline

Every finding below was reproduced against 3.0.0 `d9a8b32` **through the real engine** (`AgentEngine.process_turn`, faked model client), not by source inspection. The probe is carried into the suite as the regression set in §10.

| # | Finding | Observed at baseline |
|---|---|---|
| F1 | `default` publishes `message`; the parser reads `content` | `{"has_insight": true, "message": "...", "type": "suggestion"}` → **response rejected**, two `invalid_field` diagnostics, no insight. The same body with `content` is accepted. |
| F2a | A custom Boolean gate name is ignored | `mapping.check_field = "should_speak"`: prompt still says `has_insight`, parser still reads `has_insight` → `invalid_gate`. |
| F2b | A custom root name splits prompt from parser | `mapping.root_key = "advice"`: parser reads `advice` (accepted), generated prompt asks for `insight`. A model that obeys the prompt is silenced. |
| F3 | `speak_without_gate` is accepted and inert | Documented opt-in, honoured only by `resolve_gate_mode`, which no live path calls → `invalid_gate`. Registered today as a `strict=True` xfail. |
| F4 | A speech gate grants a write permission | `default` declares no event channel. Silent: `{"has_insight": false, "events": [...]}` → **accepted and committed**. Speaking: the same `events` key → whole response rejected. |
| F5 | A UI action may be any shape | `widget_control` with `"ui_actions": "a bare string"`, or an item naming an unknown widget and an unknown action, or `[{"nonsense": true}]` → all accepted and published to the host verbatim. |
| F6 | An unknown format name silently becomes `default` | `output_format: "does_not_exist"` → loads `default.json`, registers, runs. A typo re-homes an agent into a different envelope with different channels. |
| F7 | The provider projection requires fields no parser reads | `compile_schema(full=True)` makes **`state_updates` and `data` required** of the model for `insight_v1`, whose mapping reads neither (`state_field: null`, no `data_field`). Meaningful model output is silently discarded. |

F7 is the "provider-required field must not invite discarded output" case; it was not in the mandate's table and is added here.

## 3. Target formats

| Format | Disposition |
|---|---|
| `insight_v1` | **Supported.** Canonical insight + state envelope. Provider JSON Schema, negotiated long-form content. |
| `widget_control` | **Supported.** The single UI-action format: the canonical envelope plus a validated `ui_actions` channel. |
| `default` | Deprecated in 3.1.0, removed in 4.0.0. Input adapter → canonical. |
| `default_v2` | Deprecated in 3.1.0, removed in 4.0.0. Input adapter → canonical. |
| `v2_raw` | Deprecated in 3.1.0, removed in 4.0.0. Input adapter → canonical. |
| `ui_control` | Deprecated in 3.1.0, removed in 4.0.0. Input adapter → `widget_control`. |

A deprecated name is a **thin input adapter**: it accepts the old envelope and translates it into the canonical internal form, after which the *same* normalized validation and acceptance pipeline runs. A deprecated name is never an independently evolving contract, never has its own validator, and never has channels the canonical contract does not define.

**Widget support is retained, on evidence.** The mandate permits delivering only `insight_v1` if no maintained consumer uses UI actions. The inventory (§8.1) found the opposite: a maintained host reads `AgentResponse.data["ui_actions"]`, forwards it on its own socket envelope, and routes four widget targets client-side. Removing widget support would break a live consumer. Recorded here so the decision is auditable.

**Moving `ui_actions` into `insight_v1` is out of scope**, per the mandate. This milestone leaves two formats. Any later unification must first implement and test that channel's prompt, transport, decoding, validation and host delivery; §12 records it as a follow-on.

## 4. One canonical envelope

Both supported formats share one envelope. `widget_control` is `insight_v1` plus exactly one key.

```jsonc
{
  "has_insight": true | false,          // REQUIRED. JSON boolean. The gate.
  "insight": { ... } | null,            // object iff the gate is true; null iff false
  "events": [ {"name": "...", "payload": {}} ],
  "variable_updates": { },
  "queue_pushes": { "queue": [ ] },
  "facts": [ {"type": "...", "key": null, "value": ..., "confidence": 1.0} ],
  "memory_updates": { },
  "ui_actions": [ {"target_widget": "...", "action": "...", "payload": {}} ]   // widget_control only
}
```

### 4.1 Required, optional, null, empty

- `has_insight` is **required** and must be the JSON boolean. Missing, string, number or null ⇒ `invalid_gate`; nothing is committed.
- `has_insight: true` **requires** `insight` to be a non-empty object that passes candidate validation. `true` with `insight` null, absent, non-object or `{}` ⇒ `inconsistent_gate`.
- `has_insight: false` **requires** `insight` to be `null` or absent. `false` with a non-null `insight` ⇒ `inconsistent_gate`. A false gate is valid silence and **may still carry permitted channels**.
- A channel key is optional under the `json_object` transport; absent means "no proposal". Present-and-empty (`[]`, `{}`) is equivalent to absent.
- Under the `json_schema` transport the projection closes the object and requires every key it offers; silence is `has_insight: false, insight: null` with empty channels. This is a transport rule, not a second contract: both decode to the same logical response.
- A top-level key that the format does not define is `invalid_field` at path `$.<key>`, classification `unknown_envelope_key`, fatal. **Every accepted field is documented; every offered field has a decode path.**

### 4.2 Channel availability

The standard logical state channels are `variable_updates`, `events`, `facts`, `queue_pushes` and `memory_updates`. Membership in the framework's vocabulary grants nothing. A channel may be written only when it is available for **both** the format and the run:

| Format | events | variable_updates | queue_pushes | facts | memory_updates | ui_actions |
|---|---|---|---|---|---|---|
| `insight_v1` | ✅ | ✅ | ✅ | ✅ | ✅ | — |
| `widget_control` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ (host-declared, §6) |
| `default` (compat) | — | — | — | — | ✅ (private memory) | — |
| `default_v2` (compat) | ✅ | ✅ | ✅ | ✅ | ✅ | — |
| `v2_raw` (compat) | — | ✅ (from `state_snapshot`) | — | — | — | — |
| `ui_control` (compat) | — | ✅ (from `state_snapshot`) | — | — | — | ✅ (host-declared) |

Run-level narrowing already exists and is preserved: the isolated content path (§14.6.1) offers **no** channel, and its instruction says so.

A present key for an unavailable channel is `undeclared_channel` (fatal), **whatever the gate says**. This check runs **before** insight normalization, so a false gate can no longer smuggle a write past the field checks (F4). A speech gate never grants a write permission.

### 4.3 Diagnostics

Added to `DIAGNOSTIC_CODES`: `undeclared_channel`, `invalid_ui_action`, `unauthorized_ui_action`. Stray top-level keys reuse `invalid_field` with classification `unknown_envelope_key`, symmetric with the existing in-insight `unexpected_key`. Every new code is fatal under §8.4 atomicity and is listed in the CHANGELOG for embedders that enumerate codes.

## 5. One authoritative contract per format

`src/xubb_agents/library/contract/output_formats.json` becomes the single source of truth. Per format it declares: `id`, `status` (`supported` | `deprecated`), `envelope` (gate key, gate kind, insight key, allowed top-level keys), `channels` (which of the six, and the wire key each arrives under), `transports`, `content_contracts`, `deprecation` (`deprecated_in`, `removed_in`, `replacement`), and for a deprecated name its `compat` translation rules.

Derived from that file, not hand-maintained beside it:

1. **The generated output instruction** — key names, the gate sentence, the channel list, the silence rule, the forbidden-field list, and the permitted widget targets and actions for the run.
2. **The provider projection** — `compile_schema` takes the format's channel set; it no longer emits every channel in the descriptor (F7).
3. **Parsing and normalization** — the gate key, the insight key, the allowed top-level key set, the channel key map, and the compatibility translation.
4. **Registration** — which names exist, which are deprecated, and the exact migration text.

Where derivation is impossible the agreement is enforced by conformance tests (§10): every packaged schema JSON's `mapping`/`descriptor` must agree with the contract file, and every format's generated prompt must name exactly the keys its parser reads.

The per-schema `mapping` stops being an authority. `dynamic.py` keeps reading it for the fields the contract does not own (`content_field` aliasing inside a compat adapter, `expiry`/`action_label` passthrough), and a mapping that **diverges structurally** from its format's contract is a registration error (§9.2) rather than a silent half-applied override.

### 5.1 Three layers, kept distinct

Documentation and tests keep these separate and never assume one implies another:

- **Logical response** — the canonical envelope of §4, after any compat translation. What validation operates on.
- **Provider wire encoding** — the `json_schema` projection, with `map_entries_v1` for open maps, closed objects, every offered key required. Decoded losslessly before local validation, which remains mandatory on every transport.
- **Host-facing `AgentResponse`** — `insights`, `events`, `facts`, `variable_updates`, `queue_pushes`, `memory_updates`, `state_updates`, `data` / `data_by_agent`.

`state_updates` and `data` are **host-facing projections only** and are removed from `provider_response_contract.json`'s model-facing channel list (F7). `state_updates[f"memory_{agent_id}"]` remains exactly as it is — it is how the `default` compat adapter's private memory reaches the blackboard bridge, and it is a host compatibility projection, not a model-facing alias. No new model-facing alias is invented.

## 6. Widget actions as a validated capability

### 6.1 The action contract

`ui_actions` is an array. Each item is an object with exactly three keys:

- `target_widget` — non-empty string;
- `action` — non-empty string;
- `payload` — object (may be `{}`).

Anything else — a non-array, a non-object item, a missing or empty `target_widget` / `action`, a non-object `payload`, an extra key — is `invalid_ui_action` (fatal).

### 6.2 Host-owned authorization

The model cannot grant itself a capability. Permitted targets, actions and payload rules come from the host:

```python
class WidgetActionDeclaration(BaseModel):
    action: str
    required_payload_keys: List[str] = []
    optional_payload_keys: List[str] = []
    allow_additional_payload_keys: bool = False

class WidgetDeclaration(BaseModel):
    target_widget: str
    actions: List[WidgetActionDeclaration]

class HostWidgetCapabilities(BaseModel):
    widgets: List[WidgetDeclaration] = []
```

carried on `AgentContext.widget_capabilities` (default empty), frozen per run and propagated through phase copies like `insight_capabilities`. An optional engine-level hook `AgentEngine(widget_payload_validator=...)` — `(action: dict) -> Optional[str]`, a non-empty string meaning "rejected, and this is the bounded classification" — runs **after** the declaration checks pass, for payload rules a key list cannot express.

**Missing declarations authorize nothing.** One precedence rule, used everywhere:

1. **Channel availability is a property of the format and the run, never of the host declarations.** Declarations authorize items; they never make the channel appear or disappear. `ui_actions` is an available channel for `widget_control` and `ui_control` whenever the run offers channels at all, declarations or not — subject to the same run-level narrowing as every other channel, including the isolated-content path, which offers none (§4.2). `undeclared_channel` is raised for the key on a format that does not offer it at all (`insight_v1`, `default`, `default_v2`, `v2_raw`) or on a run that offers no channels.
2. **Authorization is per item.** Each item is checked against the run's declarations. With **no** declarations for the run, every item is `unauthorized_ui_action`, classification `no_widgets_declared`. With declarations, an unknown target is `unknown_target`, an action not declared for that target is `unknown_action`, a missing required payload key is `missing_payload_key:<key>`, and an undeclared payload key when `allow_additional_payload_keys` is false is `unexpected_payload_key:<key>`.
3. **Shape precedes authorization.** A malformed array or item is `invalid_ui_action` and no authorization check runs on it.

So an absent capability and an unknown action inside a declared channel are the same code with different classifications, and neither is ever reported as an undeclared channel. The migration note and the tests use exactly this rule.

The run's declarations also shape the **prompt**: the generated instruction lists exactly the permitted `target_widget` / `action` pairs and their required payload keys. With nothing declared it names no target, and requires `"ui_actions": []` — the **empty array**, not the omission of the key. *(Amended 3.1.1, R5 in §17. The first draft said the instruction omits the key, which contradicts §4.1: the channel belongs to the format, so the strict projection requires it, and no strictly constrained response could obey both.)* Either way the model is never invited to produce an action the boundary will reject.

### 6.3 Where it is enforced

The same function runs at two points: in `DynamicAgent` staging, so a bad action rejects its own agent's response atomically; and at the engine's **final acceptance boundary**, so custom `BaseAgent` producers and callback-modified responses are held to the identical contract. Invalid or unauthorized actions reject the **entire originating agent response** — its insight and every proposed state effect — under the existing §8.4 rule. Unrelated agents keep their existing aggregation behaviour.

Valid actions may occur with `has_insight: false`: acting without speaking is the point of the format.

Validation and delivery are separate from execution. The framework validates and publishes; the host executes. Nothing here claims atomic execution of an external UI effect, and the documentation says so.

## 7. Transport

- `strict` never silently falls back. `auto` may downgrade once, only on an exact enabled signature, unchanged.
- **Both** supported formats get a projection, decoder and tests, so `strict` is honestly available to both. `widget_control`'s projection adds `ui_actions` as an array of closed objects whose `payload` is a `map_entries_v1` map, decoded losslessly before validation. Until those tests pass, `widget_control` declares `json_object` only and `strict` refuses it at registration with the existing named error — the claim and the implementation ship together or not at all.
- Local validation remains mandatory on every transport; the projection is a structural superset, never a substitute.
- Wire ⇄ logical agreement is tested per format: projection lint, representative wire validation against fixtures, and codec round trips including nested maps in action payloads.

## 8. Migration

### 8.1 Inventory (recorded 2026-09-14)

Across the maintained integrations of this program:

- **105 agent configurations.** 93 set **no `output_format`** and ride the implicit runtime default (`default` — the format with F1). 6 are `v2_raw`, 4 are `widget_control`, 2 are `default_v2`. Zero are `insight_v1`.
- **Consumers of UI actions:** one maintained host reads `result.data["ui_actions"]`, emits it on its own socket envelope (including a sidecar-only path for silent actions), and routes four widget targets client-side, warning and dropping unknown ones. It also logs `data_by_agent`. These four targets and their actions are the declarations that host must supply under §6.2.
- **Consumers of raw model JSON:** none found outside the framework; hosts consume the normalized `AgentResponse`. Normalized-response consumers still get regression checks — a shared output class does not prove equivalent state behaviour.
- **Handwritten output instructions:** agent `text` bodies that restate an envelope are the residual manual work; the tool in §8.4 flags them by pattern rather than claiming to rewrite them.
- **Custom schema files:** none. `_load_schema` only reads the packaged directory, so after F6's repair there is no user-authored-schema path left (§9.3).
- **Unresolved coverage gap:** live-provider behaviour. The suite is fully offline; §10 reports offline evidence as offline.

### 8.2 Releases

**3.1.0 — deprecation and repair.** Two supported formats with authoritative contracts; all seven repairs; the four deprecated names keep working through compat adapters, each emitting a `DeprecationWarning` and a log line naming the agent, the requested format, the replacement and the removal version; new templates, examples and documentation set `output_format: "insight_v1"` **explicitly**; the implicit runtime default stays `default`.

**4.0.0 — removal.** The four deprecated names are refused by name with migration text, exactly as `custom1` is today (deleting the file is not how — the missing-file fallback would re-home the agent, which is the defect, not the fix). The implicit runtime default becomes `insight_v1`. The legacy widget wire shape (§8.3) is no longer accepted.

Both version numbers are published in 3.1.0's CHANGELOG, README and migration note before the migration ships.

### 8.3 What each adapter translates

| From | To canonical |
|---|---|
| `default` | `has_insight` gate unchanged; flat insight fields → `insight`; **`message` accepted as an input alias for `content`**; `memory_updates` → the private-memory channel, still staged as `state_updates["memory_<id>"]` with the merged committed-plus-new view. |
| `default_v2` | Flat insight fields → `insight`; the five channels keep their names. |
| `v2_raw` | Root presence → explicit gate: root absent, `null` or `{}` ⇒ `has_insight: false`; a non-empty object ⇒ `true`; a non-object root ⇒ `invalid_gate`. `state_snapshot` → `variable_updates`. `expiry` / `metadata` passthrough preserved. |
| `ui_control` | As `v2_raw`, plus `ui_actions` under the §6 contract. |
| `widget_control`, legacy wire shape | Accepted during the window by the same root-presence translation, selected by one documented rule: **`has_insight` present ⇒ canonical; absent ⇒ legacy adapter**, with a deprecation warning. Deterministic and total; removed in 4.0.0. |

The `message` alias carries an explicit conflict rule: `message` alone ⇒ used as `content`; both present and equal ⇒ accepted; **both present and different ⇒ fatal** `invalid_field`, classification `content_alias_conflict`. Silently preferring one would be the same class of defect as F1.

Adapters preserve valid intended behaviour. They do **not** preserve the F4 loophole or any other verified defect.

**Deliberate tightenings**, each documented in the migration note and the CHANGELOG. Two kinds, kept apart because they roll back differently (§13):

- *Of accepted model output:* undeclared channels rejected under both gates; unknown top-level keys rejected; widget actions require host declarations; the `message` alias requires a conflict-free body.
- *Of accepted configuration:* an unknown, `null`, empty or non-string format name; `speak_without_gate`; and a **structural `mapping` / `descriptor` override** — a different gate key, root key, channel key or adapter identifier — each now fail at registration instead of being half-applied or ignored.

### 8.4 Tooling

`tools/migrate_output_formats.py` — offline, read-only by default. Given a JSON catalogue or a directory of agent configurations it reports, per agent: the current format (naming the 93 that inherit the implicit default), the target format, whether the change is mechanical, and the manual work it cannot do (a handwritten envelope in `text`, a widget agent needing host declarations, a config depending on a tightened behaviour). `--dry-run` prints the rewritten configuration; `--write` applies the mechanical subset. It never edits a host's database.

The migration note `docs/MIGRATION_OUTPUT_FORMATS.md` carries the same checklist for anyone not using the tool, before/after examples for **speaking, silence with state updates, private memory, and widget actions**, and the transport section: `insight_v1` on `strict` adds the schema to the request and requires every offered key, which raises request size modestly and constrains provider choice to endpoints supporting JSON Schema; `auto` and `json_object` are unchanged in size and latency; fallback and retry bounds are unchanged.

## 9. Registration and configuration errors

All raise `AgentConfigurationError` **before any registry mutation** (registration stays all-or-nothing), and every message names the format, the reason, and what to do.

1. **Format-name resolution, in order.** An **omitted** `output_format` key resolves to the implicit runtime default — `default` in 3.1.0, `insight_v1` in 4.0.0 (§8.2) — and is then handled exactly like an explicit name, so in 3.1.0 an omitted key inherits `default`'s deprecation warning and the migration nudge it carries. Resolution happens **before** name validation, so the 93 implicit-default configurations of §8.1 keep registering unchanged.

   Every other unresolved case is an error, with no fallback: an explicit `null`, an empty or whitespace-only string, a non-string value, and an unknown name each raise, naming the value received and the supported names. `_load_schema`'s missing-file fallback and its hard-coded emergency envelope are removed — a packaged schema file that is missing, unreadable or malformed is an error, never a different contract (F6). Each of the five cases — omitted, `null`, empty, non-string, unknown — has its own test.
2. **Structural override** — a `mapping` or `descriptor` that diverges from its format's authoritative contract (a different gate key, root key, channel key or adapter identifier), or an unknown `typed_adapter` identifier, is refused with a named migration error. An override either controls generation *and* parsing, or it fails loudly; nothing is accepted and ignored (F2a, F2b).
3. **`speak_without_gate`** — refused with migration guidance (F3).

### 9.1 Deprecated names

A deprecated name registers, warns once per agent (`DeprecationWarning` + log), and runs. In 4.0.0 it raises.

### 9.2 What this removes

`resolve_gate_mode`'s inference, `evaluate_gate`'s `content_presence` and `gateless` modes, `_warn_on_gateless_misconfig`, and the `speak_without_gate` flag all become unreachable once every agent runs a named format with a fixed contract, and are removed. `GATE_MODES` reduces to the two kinds the contract file uses: `boolean` (the canonical gate, and the only kind a supported format declares) and `root_presence` (declared by the `v2_raw`, `ui_control` and legacy-widget compat adapters, which translate root presence into the canonical Boolean gate before validation, §8.3). A root-presence **adapter** is a declared, supported translation with a defined gate rule; a gate-**less** schema override — no declared rule at all — is what can no longer be registered. The two are distinguished by name everywhere in the docs and tests.

### 9.3 A-1 / INV-11 is amended, not erased

A-1 gave gate-less, rootless **user-authored** schemas a documented default of silence. With no user-authored-schema path (§8.1) and no format lacking a gate, the condition cannot arise. The `GATELESS-SILENCE` registry entry is **amended in place** — statement rewritten to "every format declares a gate rule, and every normalized response carries an explicit Boolean gate; a schema with no declared gate rule cannot be registered", pointing at the new refusal test — with a dated note recording what it used to say and why it changed. Its history stays traceable in `CONTRACTS.yaml`, the CHANGELOG and this section. The `strict=True` xfail for F3 is replaced by a passing test asserting the refusal; the xfail's reason text is quoted in the CHANGELOG so the escape is not erased.

## 10. Test plan

Every changed behavioural contract gets a `CONTRACTS.yaml` entry naming a rule-asserting test, each with its negative control. Everything runs through the real engine with faked model clients. No entry is weakened, no failure becomes a skip, and the debt ratchet stays at 0.

| Evidence | Passing condition |
|---|---|
| Format inventory and registration | Exactly two `supported` formats and four `deprecated` aliases; invalid names, malformed schema files and unsupported adapter settings raise before any registry mutation (asserted by checking the registry is unchanged). |
| Prompt/parser agreement | For every format and adapter: the generated instruction names exactly the keys the parser reads, the gate rule it enforces, and the channels it accepts. A structural override fails at registration. Negative control: a deliberately divergent contract entry fails the conformance test. |
| Migration equivalence | Representative old/new pairs produce equivalent normalized insights **and** permitted state effects, including private memory, except for the tightenings listed in §8.3 — each of which has its own test asserting the new behaviour. |
| Gates and channels | Speaking and silent responses enforce identical channel permissions (F4's exact bodies, both directions); an undeclared or invalid write rejects the whole response with nothing committed. |
| Known defects | F1–F7 reproduce the baseline failure at the old behaviour and pass at the intended behaviour, as permanent probes in `tests/qa_probes/`. |
| Widget actions | Valid silent actions pass; malformed arrays, malformed items, unknown targets, undeclared actions and invalid payloads fail through **every** producer path — dynamic agent, custom `BaseAgent`, and callback-modified response. |
| Provider transport | Projection lint, representative wire validation, codec round trips (including nested payload maps) and transport-policy tests pass for both supported formats. Offline results are reported as offline; no live-provider claim is made. |
| Rollback-safe subset | Every fixture in `tests/fixtures/rollback_safe_3_0/` — one configuration + envelope per format, valid on 3.0.0 and 3.1.0 alike — is accepted at 3.1.0 with the same normalized insight and the same committed channels (§13.1). Negative control: a fixture using a new surface (host widget declarations) is asserted **not** to be in the set. |
| Existing behaviour | Full suite, `--strict` contract gate, all permanent probes, README quickstart, clean-wheel smoke. Long-form, evidence, correction/question and interactive-operation regressions stay covered. |
| Documentation | README, PLAYBOOK, technical reference, prompt guide, descriptors, examples and migration note describe the shipped behaviour; superseded sections are marked superseded, not deleted. |

## 11. Ownership

- **Framework** (this repository): the contract file and its derivations, adapters, validation, projection and decoder, diagnostics, registration errors, the migration tool, tests and the registry.
- **Host integration** (the embedder): supplying `widget_capabilities` for every run that permits UI actions, handling three new diagnostic codes, and moving agent configurations off the implicit default before 4.0.0. The framework's obligation is to make each of those a loud, named failure rather than a silent difference.
- **Documentation** (this repository): README, PLAYBOOK, technical spec, prompt guide, migration note, CHANGELOG.

## 12. Explicitly not in scope

- Moving `ui_actions` into `insight_v1` (§3). Follow-on; requires its own prompt, transport, decode, validation and host-delivery work.
- Renaming `state_updates`, `memory_{agent_id}` or `_sync_state_to_legacy` — host-facing names, out of this change's blast radius.
- Agent purposes, scheduling, trigger semantics, insight permissions, evidence handling, correction/question behaviour and long-form policy, except where §4–§9 state an output-contract change.
- Live-provider certification.

## 13. Rollback

Rollback has **two** procedures, and which one applies depends on what the integration has adopted. The distinction is the point: a pin-only claim that ignores newly adopted APIs and wire shapes is the kind of promise that fails at 2 a.m.

### 13.1 Pin-only — an integration that has adopted nothing new

Applies when the host passes no `widget_capabilities` and no `widget_payload_validator`, has no agent on a format it was not on at 3.0.0, and has not had a `widget_control` agent re-prompted onto the canonical envelope. Then downgrading the library pin is sufficient and needs no configuration change: 3.1.0 adds no required configuration, and a configuration valid at 3.0.0 stays valid. The tightenings reject **bodies** 3.0.0 would have mishandled, not configurations 3.0.0 accepted — with three named exceptions, all of which were already broken at 3.0.0 and all of which fail loudly rather than silently: an agent on an unknown format name (F6), an agent setting `speak_without_gate` (F3), and an agent carrying a structural `mapping` / `descriptor` override (F2a/F2b, §9 item 2).

**This subset is a tested artifact, not a promise.** `tests/fixtures/rollback_safe_3_0/` pins one configuration and one envelope per supported and deprecated format that are valid on **both** 3.0.0 and 3.1.0; a conformance test asserts 3.1.0 accepts every one of them with the same normalized insight and the same committed channels. Anything outside that fixture set is §13.2, and the migration note says so in those words.

### 13.2 Coordinated — an integration that has adopted the new surface

Once the host passes `widget_capabilities` or `widget_payload_validator`, or a `widget_control` agent is live on the canonical envelope, rollback is a **coordinated host + library** step, in this order:

1. Remove the new constructor and context arguments from host code. A 3.0.0 `AgentEngine` raises `TypeError` on `widget_payload_validator`, and a 3.0.0 `AgentContext` (`extra="forbid"`) raises on `widget_capabilities`. Both fail at construction, not at runtime — loud, but they must be removed first.
2. Accept the wire consequence for widget agents. The instruction is generated per release, so a rolled-back library re-prompts widget agents onto the root-presence shape automatically and no stored prompt needs editing — but any **handwritten** `text` body that was updated to describe the canonical envelope must be reverted with the pin, and 3.0.0 will not validate the actions it accepts.
3. Restore the pin.

There is no backward translation from the canonical envelope to the root-presence one and this spec does not invent one: 3.1.0's dual-shape window (§8.3) runs in the forward direction only.

### 13.3 4.0.0

A 4.0.0 rollback to 3.1.0 is a pin change under the same two cases. A **roll-forward** to 4.0.0 requires that every configuration set `output_format` explicitly first, which is what the migration tool reports. Library version and configuration change stay independently reversible, in that order.

## 14. Risks

1. **The 93 implicit-default agents.** Changing the implicit default in 3.1.0 would move them onto a different envelope silently — exactly the failure mode this spec exists to end. Mitigated by resolving an omitted key to the implicit default *before* name validation (§9 item 1), keeping that default at `default` until 4.0.0, letting each one inherit the deprecation warning, and having the tool report every one by name.
2. **Widget agents go quiet until the host declares widgets.** Deliberate: "missing declarations must not authorize unrestricted actions". Mitigated by a named `unauthorized_ui_action` diagnostic per rejected action, the declaration-shaped prompt, and a migration-note section that leads with it.
3. **`widget_control`'s wire shape changes.** Mitigated by the documented dual-shape window (§8.3), which is deterministic and removed in 4.0.0.
4. **New diagnostic codes reach hosts that enumerate codes.** Mitigated by listing them in the CHANGELOG and migration note, and by their being fatal-only (a host that ignores unknown codes sees a rejection, never a silent acceptance).

## 15. Review chain

- Independent review: `spec-review` (Codex), rounds recorded in `docs/.spec-review/SPEC_OUTPUT_FORMAT_CONSOLIDATION/`.
- Implementation follows the repository's spec-first process: contract registry entry plus rule-asserting test and negative control for every changed behavioural contract; the gate green at `--strict`; permanent probes never skipped.

## 17. Post-implementation review (2026-09-14, repaired in 3.1.1)

An independent review of the shipped `b4ce54b` found six defects and one spec/implementation
discrepancy. All were reproduced locally before any repair, and all are fixed in 3.1.1. The
architectural direction was not challenged; every finding was a case where the implementation
did not follow the contract this spec states.

**The shape of the miss matters more than the count.** Five of the six were registered
contracts whose statement was correct and whose named test exercised a path the defect did not
live on — the F-1 escape `docs/PROCESS.md` exists to prevent, found by a reviewer rather than by
the gate. A green gate proves every registered rule has a passing test; it does not prove the
test reaches the input path a user does.

| | Finding | Repair |
|---|---|---|
| R1 | The migration tool rewrote rows it had just reported as needing a person, then printed that they were unchanged. Its test checked one manual record's prompt body and missed the changed format beside it. | One eligibility predicate shared by reporting, `--dry-run` and `--write`; the test compares whole records. |
| R2 | A catalogue configuration carrying `mapping` / `descriptor` overrides was discarded in silence and registered clean — every 3.1.0 test mutated the attribute *after* construction. | The supplied keys are validated before they are replaced; the registration-time check stays for post-construction mutation. |
| R3 | An `on_agent_finish` callback could add a host-authorized `ui_actions` array to an `insight_v1` response and have it published. Host authorization is not channel availability. | The final boundary checks the originating format's binding first; a custom `BaseAgent` keeps its documented producer path. |
| R4 | With no declarations the instruction forbade `ui_actions` while the strict projection required it. | The instruction requires the empty array. §6.2 amended above. |
| R5 | §4.2 says the isolated path offers no channels; the prompt implemented it, the projection and the parser did not. | One effective channel set per run, used by all three. |
| R6 | `result.get(wire)` conflated an absent key with a present JSON null, so `"ui_actions": null` skipped validation and let the rest of the response commit. | Presence is checked before value, at the parser and at the final boundary. |
| — | §9 item 1 says a missing or malformed **packaged schema file** is an error; the implementation logged and returned an empty document. | The refusal is implemented, naming it as a broken installation rather than a configuration error. |

**Correction to the delivery record below:** its handwritten-envelope subtotal was wrong. The
tool flags **31** of the 105 configurations for handwritten envelope markers — that is all 31
manual rows, including all four widget agents, which carry both. 27 are handwritten-only. The
totals (105 / 74 mechanical / 31 manual / 93 implicit) reproduce unchanged. Counting rule: a
row is "handwritten" if its `text` contains any envelope marker the tool lists; catalogue
SHA-256 begins `d25fad7d75389dc7`.

## 16. Delivery record (2026-09-14, 3.1.0)

Added after approval; it records what was built, not a change to what was approved.

- **§7's conditional is resolved.** `widget_control` declares `json_schema` **and**
  `json_object`, because the projection, the decoder and the tests exist: the `ui_actions`
  provider shape is compiled from the response descriptor, its `payload` rides the
  `map_entries_v1` codec, and a real strict turn projects, decodes and stages it
  (`tests/test_provider_schema_g2.py::TestWidgetControlStrictTransport`), with a negative
  control asserting `insight_v1`'s projection offers no action channel. Offline evidence
  only; no live-provider claim.
- **§8.1's inventory, measured by the shipped tool** over the maintained catalogue
  (`tools/migrate_output_formats.py`): 105 configurations — **74** need only the
  mechanical rewrite, **31** need a person (28 carry a handwritten envelope in their
  prompt body; 4 are widget agents needing host declarations, one of which also carries a
  handwritten envelope), and **93** inherit the implicit default.
- **Registry:** 102 contracts, 100% covered, `--strict` green. Suite: 1055 passed, 0
  skipped, 0 xfail. The 3.0.0 `speak_without_gate` xfail is resolved by removal, its
  reason text quoted in `tests/test_dynamic_agent.py` and in the CHANGELOG.
- **Still owed by the process, and not something a session can do:** the
  architectural-change issue `CONTRIBUTING.md` asks for is opened on GitHub by the owner.
