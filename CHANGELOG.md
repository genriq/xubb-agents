# Changelog

All notable changes to the Xubb Agents Framework are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this
project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

> Short codes like `F-1`, `WC-1`, or `INV-15` are spec item / invariant IDs — they trace an
> entry back to its section in the specs under [docs/](docs/) and to the contract registry
> ([docs/CONTRACTS.yaml](docs/CONTRACTS.yaml)).

---

## [Unreleased]

Nothing yet.

## [3.1.7] - 2026-09-24

A patch on 3.1.6 carrying only this repair, for hosts pinned to 3.1.x: nothing from 3.2.0 is
included. The same change is on `main` for 3.2.1.

### Fixed — the provider projection no longer invites what local validation always rejects

[`SPEC_PROVIDER_PROJECTION_ALIGNMENT`](docs/SPEC_PROVIDER_PROJECTION_ALIGNMENT.md), APPROVED at
review round 2. A downstream host's rehearsal with production prompts and current models saw most
typed insights rejected with `only_for_hypothesis`, `subtype_on_non_observation`,
`consulting_profile_required`, a question payload on a non-question, scalar queue values and
shortened evidence ids. The strict schema the engine sent allowed every one of those shapes: the
contract's conditional rules are local-only keywords the provider subset does not carry, and the
projection never knew the run's analysis profile. Prompts that used the field names as ordinary
words ("implication", "validation step", "question") were the trigger; the engine, which owns the
output contract, was the cause.

- **The per-run projection offers only what the run can have accepted.** `compile_schema` takes
  an optional `analysis_profile`. Without one, the generic projection is byte-identical to the
  packaged one. With one, which `DynamicAgent` always passes:
  - `observation_kind` and `validation_step` are null-only unless the profile is consulting and
    observation is allowed;
  - the question and correction payloads are null-only unless their type is allowed;
  - when any of them is available, the candidate becomes named branches, one per allowed type,
    with observation split into plain, implication and hypothesis, and `validation_step` carried
    only by the hypothesis.
  Every locally valid response for the run stays representable, and local validation is
  unchanged and authoritative. `PROVIDER-PROJECTION-FIELD-AVAILABILITY`.
- **Queues are lists in the projection.** The response descriptor marks `queue_pushes` with
  `"map_value": "array"`, and the per-run projection carries list values for it. The other maps
  keep arbitrary values. The codec is unchanged. `PROVIDER-PROJECTION-QUEUE-LISTS`.
- **The generated rules say where each field belongs,** in every structured-output mode, because
  `json_object` sends no schema: where the observation fields, `question` and `correction` must be
  null; that `validation_step` belongs only to a hypothesis; that a recommended check belongs in a
  suggestion's content; and that each queue holds a list. No rule tells the model to omit a
  required field. `GENERATED-RULES-FIELD-PLACEMENT`.
- **Citations are copied exactly.** The citation rule now says to copy each id exactly as shown,
  including its `snap:` prefix. Resolution is unchanged: exact match only. `CITATION-EXACT-COPY`.
- **Endpoint acceptance gates the release tag.** `tools/check_provider_acceptance.py` sends a
  representative set of the specialised projections to named models and reports each schema's
  digest, whether it was accepted, and whether the returned envelope validates. The maintainer
  runs it before tagging, with the models the pinned hosts use; it is tested offline and is not
  part of the suite. `PROVIDER-ACCEPTANCE-TOOL`.
- **An escaped-defect probe,** `tests/qa_probes/test_probe_provider_projection_alignment.py`,
  drives the engine end to end through a strict-decoding fake provider: before the repair the
  rehearsal's shapes were emitted and rejected; after it they cannot be emitted.

What changes for a host: the wire schema and the generated rules are different, so a host that
digests prompts or schemas sees new digests, which is a new treatment by design. Predicted
acceptance improvements are hypotheses until a host measures them in a fresh run.

## [3.1.6] - 2026-09-15

### Fixed — the two residuals of the documentation design review

No runtime behaviour changes. Tiers 1-3 closed every measured finding of the 2026-09-15
review except two, which a closure audit against the merged result found still open.

**The prompt guide no longer recommends a deprecated format.** Finding 3 was only half
repaired in tier 1: a superseded banner went in at the top of
[`prompt_engineering_guide.md`](docs/prompt_engineering_guide.md), but the instruction at
the bottom still read *"For anything that also writes the Blackboard, use `default_v2`"* -
a format removed in 4.0.0 - and both the worked example and the field reference described
that flat envelope rather than the canonical one.

Section 4 now documents **`insight_v1`**: the nested `insight` candidate, the explicit
Boolean gate, silence as `has_insight: false` that may still commit state, and
`widget_control` as the same envelope plus `ui_actions`. The field reference gains a
**Where** column, because *where* a field goes is the whole difference between the current
envelope and the deprecated ones. The four deprecated formats are described in one note as
an envelope difference, with a pointer to the migration guide.

The purpose table listed **5 of the 9** model-authorable types. It now lists all nine, says
that `reply`, `question` and `correction` need both a permission flag and a
`principal_id`, and records that `error` is a framework diagnostic no model may author.

Its header stamps are separated onto the two axes the review named: a document revision
(3.3) and an explicit **applies to runtime** line, replacing `Status: Production
(xubb_agents v2.8.1)`.

**`docs/PROCESS.md` now describes the documentation gate, and what a green gate proves.**
The A1-A5 checks have run in CI since 3.1.4, but the page of record for the registry and
gates never mentioned them and carried no statement of reach - the review's *"State what
the gate proves"*. Added: a table of A1-A5, and a section drawing the line explicitly. A
green contract gate proves every **registered** rule names a test that ran and passed; it
does not prove the registry is complete, that a test reaches the input path a user
supplies (two of the six defects found in 3.1.0 were exactly that shape, against a green
gate), or that any prose is true. A green documentation gate proves the declared surface is
present and its generated facts match the code; A1-A5 cannot read a paragraph.

### Added

- **`tests/test_prompt_guide_envelopes.py`** - the guide's documented JSON envelopes are
  executed against the real engine with only the provider boundary substituted. A spoken
  envelope must publish an insight; a silent one must read `accepted_silent` **and** still
  commit its state channels; neither may raise an engine deprecation warning. The negative
  control feeds the flat `default_v2` shape and requires the engine to **reject** it, so
  the envelope distinction the guide now teaches is proved rather than asserted.
  Registered as `PROMPT-GUIDE-ENVELOPES`. Correcting the prose alone would have left
  nothing to catch the next such error.

### Compatibility

Registry: **110 contracts**, 100% covered, strict gate green. API documentation gate: PASS.
Suite: 1127 passed. Relative links across the doc set: 0 broken.

Runtime stamps moved only where a check re-verifies the document against the runtime on
every build - `API_REFERENCE.md` and `DIAGNOSTICS.md` (gate-derived), the prompt guide
(revalidated by hand and now executed). `DESIGN_GUIDE.md` and the four task guides stay at
3.1.5: their runnable examples are verified, their prose was not revalidated for this
release, and the review's rule is to replace misleading runtime claims rather than bump
headers over unrevised bodies.

Version note: **3.2.0 remains reserved** for
[`SPEC_CONFIG_KEY_OWNERSHIP`](docs/SPEC_CONFIG_KEY_OWNERSHIP.md).

Still open from the review and **not** addressed here: `SECURITY.md` leaves 3.0.x
unstated. That is a maintainer policy statement, and the review's instruction was to record
the actual policy rather than invent one during editing.

## [3.1.5] - 2026-09-15

### Changed — the reader journey, and the Playbook split

**Tier 3** of the documentation design review, and the last of it. No runtime behaviour changes.

**The README now walks a newcomer from nothing to a result they understand.** Its order follows
the review's §5: what this is and what your host owns → install → **run it now with no API key**
→ run it with a model → read what came back → where to go next.

The offline example goes first deliberately. It exercises the real engine — eligibility,
concurrency, validation, acceptance, merge — with a rule-based agent, so a newcomer sees the
machinery work before adding a provider and a key to the things that could be wrong. It is
labelled for what it is: a demonstration of the framework, not of a model's judgement.

The model-backed example sets `output_format` explicitly, prints `acceptance_status`, and says
in as many words that **an empty `insights` list is a normal, successful turn.**

**The Playbook is split rather than patched.** At 355 KB and written against a v2.2 analysis, a
single superseded banner could not stop a reader landing halfway down and following an
instruction that no longer works.

| | |
|---|---|
| [`docs/DESIGN_GUIDE.md`](docs/DESIGN_GUIDE.md) | The doctrine: restraint as the product, many small observers, what the engine owns and what your host does, trust levels, fail-closed, **and when not to use this framework** |
| [`docs/guides/authoring-agents.md`](docs/guides/authoring-agents.md) | Both producer paths, narrowing purposes, triggers and cooldowns, memory, how to test |
| [`docs/guides/orchestration.md`](docs/guides/orchestration.md) | Blackboard containers and how to choose, events and the second phase, fact precedence, per-agent attribution |
| [`docs/guides/host-integration.md`](docs/guides/host-integration.md) | Declaring capabilities, reading the result, executing actions, questions, corrections, lifecycle |
| [`docs/guides/long-form-content.md`](docs/guides/long-form-content.md) | The negotiation, why nothing is truncated, the two lanes, when to reach for it |

The original is preserved unchanged at
[`docs/archive/PLAYBOOK_v2.2.md`](docs/archive/PLAYBOOK_v2.2.md), and `docs/PLAYBOOK.md` is now a
stub that keeps incoming links working and points at what replaced each part.

### Added

- **`tests/test_guides_runnable.py`** — every fenced example marked `<!-- runnable -->` is
  executed in CI against the real engine, and must emit no deprecation warnings. **A recipe
  labelled current is one that ran.** An unmarked block is illustrative and is not executed.
  Registered as `GUIDE-RECIPES-VERIFIED`.

### Fixed

- **The README's model example now exercises the real engine.** It previously replaced
  `AgentEngine.process_turn` wholesale, which proved the block constructed and printed while
  generation, parsing, validation and acceptance never ran — it could not have caught an example
  whose envelope the engine rejects. The substitution moved to the **provider boundary**, and a
  negative control feeds it an envelope the engine must refuse.

  Writing that control surfaced something worth documenting: the **merged** turn response reads
  `accepted` even when its only agent was rejected, because one rejected agent does not fail a
  turn. The README and the guides now say to read `acceptance_by_agent` when you need to know
  which agent was refused.

- Two stale status stamps: `SPEC_REMOVE_LEGACY_CONTRACT.md` read "APPROVED — ready to build" for
  work that shipped as 3.0.0 in September, and `EXECUTIVE_SUMMARY.md` claimed 2.8.1. The summary
  now carries its runtime **and** an explicit note that its narrative predates the 3.0.0 and
  3.1.x changes, rather than a bare version bump over unrevised prose.

### Compatibility

Registry: 109 contracts, 100% covered, strict gate green. API documentation gate: PASS. Suite:
1121 passed, 0 skipped, 0 xfail. Relative links across the doc set: 0 broken.

Version note: **3.2.0 is deliberately not used here.**
[`SPEC_CONFIG_KEY_OWNERSHIP`](docs/SPEC_CONFIG_KEY_OWNERSHIP.md) published that number for the
configuration-key work, and a documentation release should not consume it.

## [3.1.4] - 2026-09-15

### Added — a complete API reference, a diagnostics reference, and a gate that keeps them true

**Tier 2** of the documentation design review. No runtime behaviour changes: this release is
documentation, tooling and tests.

The contract gate proves every documented *behaviour* names a passing test. It never covered
the API reference, so that reference drifted three releases behind while the gate stayed green
— the same escape the gate exists to prevent, one level up. This closes it.

- **[`docs/API_REFERENCE.md`](docs/API_REFERENCE.md)** — the supported public surface: **37
  classes, 302 qualified members**. A hybrid, as the review directed: the facts (signatures,
  defaults, requiredness, enum values, serialization exclusions) are generated from the shipped
  code; the meaning (purpose, ownership, lifecycle, limits, failure behaviour) is written by
  hand, because no amount of introspection can say who owns a field.

  It leads with the three distinctions that cause most confusion here — **provider envelope vs
  Python response model vs host display**, and **model-authored vs host-supplied vs
  engine-derived** — and states the traps a flat field dump conceals: `api_key` is optional,
  `debug_info` never reaches a serialized payload, `usage` is per-agent and is not propagated
  into the merged turn response, and a `confidence` of `1.0` is not evidence that confidence was
  assessed (`confidence_provided` is). The custom `BaseAgent` producer path is documented as
  first-class rather than implied away.

- **[`docs/DIAGNOSTICS.md`](docs/DIAGNOSTICS.md)** — all **39** registered codes with stable
  anchors, grouped by what they are about, each with when it arises, its effect on acceptance,
  what an integrator can do, and a **lifecycle status**. It states plainly that a diagnostic is
  not automatically a failure (`capability_unavailable` and `unsupported_structured_output`
  appear on accepted responses), that rejection is whole-response, and that retrying unchanged
  input helps only for transport failures.

- **[`docs/api/inventory.yaml`](docs/api/inventory.yaml)** — the declared surface, by qualified
  name, plus the classes deliberately excluded **and why**, so "undocumented" is a decision
  someone made rather than a gap nobody noticed.

- **`tools/check_api_docs.py`** — five checks (A1–A5), wired into CI beside the contract gate,
  each with a deliberate failing fixture in `tests/test_api_docs_gate.py`. A gate nobody has
  watched fail is a gate nobody should trust.

  The inventory is a hand-maintained enumeration, and 3.1.2 was a lesson in how those rot. The
  difference is that this one is compared against reality **in both directions on every build**:
  a new constructor parameter fails until someone declares it, and a declared name the code no
  longer has fails too. Coverage is checked by **qualified** name — `Event.id` does not document
  `AgentInsight.id`, which is precisely the substring error that inflated the audit this work
  came from.

- **`tools/api_surface.py`** / **`tools/gen_api_facts.py`** — the derivation rules and the
  generator. Generation is idempotent and never touches the prose around its markers.

### Fixed

- A second diagnostic code was found to have no emitter: **`no_supported_insight_types`**, like
  `partial_legacy_response` before it. Both are documented as retired and **kept** in
  `DIAGNOSTIC_CODES`; A5 now fails the build if a code loses its last emitter and nobody says
  so, and equally if a code documented as retired is emitted again.

### Compatibility

Registry: 108 contracts, 100% covered, strict gate green. Suite: 1111 passed, 0 skipped, 0
xfail. API documentation gate: 37 classes, 302 members, 3 recorded exclusions, PASS.

## [3.1.3] - 2026-09-15

### Fixed — documentation that misled a current reader

A documentation design review of 3.1.2 found the reference-level docs several releases
behind the code. This is **tier 1 of its delivery order**: the things a newcomer or an
integrator hits first. The API-reference rebuild and the diagnostics reference are tier 2
and are not in this release.

- **The flagship Quickstart no longer teaches a deprecated practice.** It did not set
  `output_format`, so it inherited the deprecated `default` and warned at the first code a
  newcomer copied. It now sets `insight_v1` explicitly. `README-EXAMPLES-NOT-DEPRECATED`
  registers the rule, with a negative control proving the detector fires — the previous
  state passed CI precisely because nothing asserted this.
- **`AgentEngine(api_key=…)` was documented as required.** The constructor defaults it to
  `None`. Corrected, and the API Reference now carries a standing note that it covers
  roughly half the public surface and is being rebuilt — a reader should not have to
  discover that by being wrong.
- **The docs index presented a removed parameter as current API.** Its
  implementation-status paragraph is a 2.8.1 snapshot; it is now labelled as one, with
  `insight_contract=` (removed in 3.0.0, raises `TypeError`) and the renamed adapters
  called out explicitly.
- **The prompt guide recommended a deprecated format for new agents.** Its schema table
  now leads with `insight_v1` and `widget_control`, marks the other four as removed in
  4.0.0, and replaces the "typed contract (v2.8)" note, which described a selectable
  contract that no longer exists.
- **The 4.0.0 output-format plan contradicted the approved spec.** The README said the
  implicit default *changes to* `insight_v1`; `SPEC_CONFIG_KEY_OWNERSHIP` §5.3 amends that
  — the key becomes **required**. Current behaviour, approved-but-unshipped behaviour and
  history are now labelled separately.
- **The technical spec's blanket backward-compatibility claim** predated the deliberate
  3.0.0 break and now says so.

### Changed

- `docs/reference/insight_types_1.2.0/` is labelled a **partial historical snapshot**: 8 of
  the 31 files named by the original source manifest are present, and the executable
  conformance runner and sample adapter are not shipped here. Its run instructions are
  marked historical, and the docs index no longer describes it as "manifest-verified" —
  source-archive verification does not certify this checkout or any host. Nothing was
  deleted and the original manifest and provenance are preserved.
- `SPEC_V3_LIVE_ASSISTANCE.md` uses generic terminology for the embedding host.

### Not changed, deliberately

- **`partial_legacy_response` stays in `DIAGNOSTIC_CODES`.** 3.0.0 removed every path that
  emits it, but removing registered runtime vocabulary is a compatibility decision for
  hosts that may branch on it — not documentation tidying. It now carries a comment saying
  so, and a lifecycle status belongs in the tier-2 diagnostics reference.
- **`SECURITY.md`'s support table** lists 3.1.x and `< 3.0` and leaves 3.0.x unstated. That
  is the maintainer's policy to record, not an editor's to invent.

## [3.1.2] - 2026-09-14

### Fixed — R2's repair was incomplete, in the same shape as the defect it fixed

Re-testing merged 3.1.1 found two more accepted-and-ignored settings. One root cause:
**the enumeration was the bug.**

3.1.1 validated a supplied `mapping` in full but a supplied `descriptor` only for
`typed_adapter`, because both checks walked a hand-maintained list of "the structural
keys". Everything outside that list kept the old behaviour — accepted at construction,
silently replaced by the contract's value, never mentioned again.

| Was | Now |
|---|---|
| `descriptor.gate_mode`, `descriptor.channels`, `descriptor.supported_transports`, `descriptor.typed_supported_insight_types` and any invented descriptor key: accepted and silently replaced | Refused at construction with a named error |
| `mapping.confidence_field`, `mapping.metadata_field` and any key outside the twelve enumerated ones: same | Same |
| The migration planner read `mapping` only, against that same list, so a record with an unknown adapter was reported **mechanical** and rewritten | The planner runs registration's own rule over both blocks |
| The planner asked one question where there are two, so a valid `default_v2` record carrying its own `flat` adapter was rewritten to `insight_v1` — producing a configuration that cannot register | It checks the block against the **current** format *and* the **target**, and reports the second case with what to do about it |

**The rule no longer has a list.** What you supply must equal what the contract derives,
and a key the contract does not define is refused. A list of structural keys goes stale
every time the contract grows a field, and every gap it leaves is another setting accepted
and ignored — the defect class this release series exists to end.

### Removed

- `xubb_agents.core.output_format.STRUCTURAL_MAPPING_KEYS`. Introduced in 3.1.0, it was the
  enumeration above; nothing needs it now that the rule compares whole blocks.

### Compatibility

Registry: 104 contracts, 100% covered, strict gate green — no new entries, two amended again
in place with dated notes saying what the 3.1.1 coverage missed. Suite: 1096 passed, 0
skipped, 0 xfail. The maintained catalogue's totals are unchanged (105 / 74 / 31 / 93): no
record in it carries a `mapping` or `descriptor` block. Still offline only; still unadopted
by any host.

## [3.1.1] - 2026-09-14

### Fixed — six defects found by an independent post-implementation review of 3.1.0

An outside review of the shipped `b4ce54b` reproduced six defects and one
spec/implementation discrepancy. All are repaired here; none required reversing an
architectural choice. Details in
[`docs/SPEC_OUTPUT_FORMAT_CONSOLIDATION.md`](docs/SPEC_OUTPUT_FORMAT_CONSOLIDATION.md) §17.

**Five of the six were registered contracts whose test missed the path the defect lived
on** — the F-1 escape [`docs/PROCESS.md`](docs/PROCESS.md) exists to prevent, found by a
reviewer rather than by the gate. A green gate proves every registered rule has a passing
test; it does not prove that test reaches the input path a user does. The affected registry
entries are amended in place with dated notes saying what the coverage missed.

| | Was | Now |
|---|---|---|
| **R1** | `tools/migrate_output_formats.py --write` rewrote rows it had just reported as needing a person, then printed that they were unchanged — a handwritten flat-envelope agent silently became `insight_v1` while its prompt still asked for the old shape. | One eligibility predicate shared by reporting, `--dry-run` and `--write`. Manual rows are left byte-identical, and the test compares whole records. |
| **R2** | A configuration carrying `mapping` or `descriptor` overrides was **discarded in silence** and registered clean: construction replaced both with the contract's own before anything looked at them, and every test mutated the attribute afterwards. | The supplied keys are validated against the contract before they are replaced, so the promised refusal runs on the catalogue input path. The registration-time check stays for post-construction mutation. |
| **R3** | An `on_agent_finish` callback could add a host-authorized `ui_actions` array to an `insight_v1` response and have it published. Host authorization of an action is not the same thing as the format offering the channel. | The final boundary checks the originating format's binding first (`undeclared_channel`, whole response rejected). A custom `BaseAgent`, which has no format, keeps its documented producer path. |
| **R4** | With no host widget declarations the instruction said `Do NOT include "ui_actions"` while the strict projection still **required** the key — no strictly constrained response could obey both. | The instruction requires `"ui_actions": []`. Channel availability belongs to the format; item authorization belongs to the host. |
| **R5** | The isolated content path's "no channels" rule reached the prompt but not the provider projection or the parser, so a channel present on an isolated result was accepted. | One effective channel set per run, used by the instruction, the projection and domain validation alike. |
| **R6** | `result.get(wire)` conflated an absent key with a present JSON null, so `"ui_actions": null` skipped validation entirely and let the rest of the response commit. | Presence is checked before value, at the parser and at the final boundary. Absent is "no proposal"; `[]` and `{}` are the empty forms; a present null is a value of the wrong shape. |

### Changed

- A packaged `schemas/*.json` document that is missing, unreadable or malformed now raises
  `AgentConfigurationError` naming it as a broken installation, which is what §9 item 1 always
  said. 3.1.0 logged and returned an empty document — harmless for the envelope, since the
  contract file is the authority, but a silently broken install.
- New diagnostics on previously-accepted input: a present-null channel
  (`invalid_domain_payload` / `invalid_ui_action`), a channel key on an isolated run
  (`undeclared_channel`), and a callback-added action on a format that does not bind the
  channel (`undeclared_channel`). Each rejects the whole response, loudly.

### Corrected

- The 3.1.0 delivery record's handwritten-envelope subtotal was wrong. The tool flags **31**
  of 105 configurations for handwritten envelope markers — all 31 manual rows, including all
  four widget agents, which carry both; 27 are handwritten-only. The totals
  (105 / 74 mechanical / 31 manual / 93 implicit) reproduce unchanged.

### Compatibility

Registry: 104 contracts (2 new, 5 amended in place), 100% covered, strict gate green. Suite:
1080 passed, 0 skipped, 0 xfail. Still offline only — no live-provider claim. No host has
adopted 3.1.0, so nothing downstream is affected by these tightenings.

## [3.1.0] - 2026-09-14

### Changed — output formats consolidated onto two, and seven contract disagreements repaired

The library shipped six output formats. They were not six views of one contract but six
partly-specified contracts whose prompt, schema file, parser and validator disagreed.
Spec: [`docs/SPEC_OUTPUT_FORMAT_CONSOLIDATION.md`](docs/SPEC_OUTPUT_FORMAT_CONSOLIDATION.md).
Migration: [`docs/MIGRATION_OUTPUT_FORMATS.md`](docs/MIGRATION_OUTPUT_FORMATS.md).

**Two supported formats.** `insight_v1` (insight + state) and `widget_control` (insight +
state + validated UI actions), both on the same canonical envelope: an explicit Boolean
`has_insight` gate and a nested `insight`. `default`, `default_v2`, `v2_raw` and
`ui_control` are **deprecated** and become thin input adapters over the same validation
and acceptance pipeline. They keep working in 3.1.0 and are **removed in 4.0.0**.

**One authority per format.** `library/contract/output_formats.json` now defines every
format's gate, insight key, allowed top-level keys and channel bindings. The generated
output instruction, the provider projection and the parser are all derived from it; the
packaged `schemas/*.json` files became documentation whose agreement is conformance-tested.

**The seven repairs** (each reproduced through the real engine at 3.0.0 `d9a8b32` first,
and each now a permanent probe in `tests/qa_probes/test_probe_output_format_disagreements.py`):

| | Was | Now |
|---|---|---|
| F1 | `default` published `message`; the parser read `content`, so an agent authored against the published contract emitted nothing | one correct contract; `message` accepted as an input alias, a conflicting body refused with `content_alias_conflict` |
| F2 | a custom `check_field` was ignored by prompt and parser alike; a custom `root_key` was honoured by the parser while the prompt still asked for `insight` | a structural override fails at registration with a named migration error |
| F3 | `speak_without_gate` was documented, accepted, and read by nothing (a `strict=True` xfail at 3.0.0) | refused at registration with migration guidance |
| F4 | `default` accepted an undeclared `events` channel while **silent** and rejected it while speaking — a speech gate decided a write permission | channel permissions are checked before the insight is normalized and are identical under both gates (`undeclared_channel`) |
| F5 | a `ui_actions` payload could be any shape and was published to the host verbatim | a validated action contract, authorized by host declarations, enforced at the one acceptance boundary |
| F6 | an unknown format name silently fell back to `default` | every unresolved name raises, naming the supported formats |
| F7 | the provider projection made `state_updates` and `data` **required** of the model for `insight_v1`, whose parser read neither | the projection offers exactly the channels the format binds |

### Added

- `HostWidgetCapabilities` / `WidgetDeclaration` / `WidgetActionDeclaration` and
  `AgentContext.widget_capabilities` — host-owned declarations of permitted widget
  targets, actions and payload keys. **Missing declarations authorize nothing**, and the
  generated instruction says so rather than inviting actions the boundary will reject.
- `AgentEngine(widget_payload_validator=...)` — an optional host hook for payload rules a
  key list cannot express. It can only narrow what the declarations permit.
- Diagnostic codes `undeclared_channel`, `invalid_ui_action`, `unauthorized_ui_action`.
  All are fatal; a host that ignores unknown codes sees a rejection, never a silent accept.
- `tools/migrate_output_formats.py` — an offline inventory and dry-run migration tool that
  names every configuration inheriting the implicit default and every one needing a person.
- `tests/fixtures/rollback_safe_3_0/` — the configurations and envelopes that behave
  identically on 3.0.0 and 3.1.0, so "roll the pin back" is a tested claim (§13.1).

### Deprecated

- Output formats `default`, `default_v2`, `v2_raw` and `ui_control`. Each emits a
  `DeprecationWarning` naming the agent, the format, its replacement and `4.0.0`.
- `widget_control`'s legacy root-presence wire shape, accepted during the window under one
  deterministic rule: a top-level `has_insight` selects the canonical envelope, its absence
  selects the legacy one.
- The **implicit runtime default** stays `default` in 3.1.0 and becomes `insight_v1` in
  4.0.0. An omitted `output_format` resolves to it *before* name validation and inherits
  its deprecation warning, so existing configurations keep registering and still get told.

### Removed

- `resolve_gate_mode` and `evaluate_gate` (and with them the `content_presence`,
  `gateless` and `state_only` gate modes). They inferred a gate from a mapping and had no
  live caller once 3.0.0 deleted the legacy staging — which is exactly why
  `speak_without_gate` could be accepted and be inert.
- `DynamicAgent._warn_on_gateless_misconfig` and the missing-file fallback in
  `_load_schema`, including its hard-coded emergency envelope.
- `state_updates` and `data` from the model-facing provider response contract, and the
  literal `supported_insight_types` enum from every schema descriptor.

### Amended contracts

- `INV-11-gateless-silence` (A-1) — amended **in place** in `docs/CONTRACTS.yaml`, old
  statement and reason preserved in a dated comment. A-1's load-time warning protected a
  world where a schema could omit a gate; with every agent on a named format whose gate is
  declared, and overrides refused at registration, that state is unreachable and the
  guarantee is stronger than the warning was. The `speak_without_gate` xfail's reason text
  is quoted in `tests/test_dynamic_agent.py` so the escape stays traceable.
- `TYPED-ADAPTER-ROOT-V2-SIDECAR` (INV-49) — amended in place: `widget_control` moved to
  the canonical envelope, and the action block is generated from the host's declarations
  rather than a static `sidecar_instruction` in a descriptor (a descriptor could not say
  which widgets exist, which is why any action shape was accepted).

### Compatibility

Registry: 102 contracts, 100% covered, strict gate green. Suite: 1053 passed. Offline
only — no live-provider claim is made. Configurations valid at 3.0.0 remain valid, with
three named exceptions that were already broken then and now fail loudly: an unknown
format name, `speak_without_gate`, and a structural mapping override.

## [3.0.0] - 2026-09-13

### Removed — BREAKING: the `legacy_v2` insight contract

`typed_v1` (XUBB-ITC-1) was added in 2.8.0 **alongside** `legacy_v2` so embedders
could migrate. That migration is complete, and this release removes the superseded
regime, the parameter that selected between them, and everything that served only
the removed path.

**What an embedder does.**

| Before | After |
|---|---|
| `AgentEngine(..., insight_contract="typed_v1")` | `AgentEngine(...)` — the argument is **removed**, not ignored |
| `AgentEngine(...)` defaulting to `legacy_v2` | no default; the typed regime is the only regime |
| a descriptor declaring `supported_contracts` | the key is gone; `typed_adapter` is required |
| an agent on `custom1` | **must move** to a schema declaring a `typed_adapter` |
| a `partial_legacy_response` diagnostic | no longer emitted; there is no `partial` status |

The `insight_contract` argument raises `TypeError` rather than being accepted and
ignored. Silently moving an embedder to a different validation regime would change
what their agents may emit without telling them; a loud failure is the honest one.

**`custom1` is removed, and is refused by name.** Deleting the schema file alone
would NOT have failed an agent still configured for it: `_load_schema` falls back
to `default.json` for any name it cannot find, so such an agent would have
silently registered under a different envelope with different channels. The
identifier is rejected before that fallback, with a message naming where to go
instead. The fallback is unchanged for every other unrecognised name.

**Dispositions changed, not rules.** The legacy path answered a recoverable
insight error with `partial` — reject the insight, commit valid channels. The
typed path rejects the whole response (§8.4). Every rule that survived was
migrated rather than deleted: a malformed gate, an unknown or disallowed type, a
reserved `sys.*` write and a fatal domain payload all still reject and still
report the same diagnostic; what changed is that nothing from the response
commits.

**Legacy adapter coercions are gone.** Case-folding a type (`"WARNING"`) and
defaulting an absent type to `"suggestion"` were declared legacy normalisations.
Typed asks for an exact lowercase value and reports what the model actually wrote,
rather than guessing what it meant.

**The framework ERROR card is gone from the human channel.** A sanitized ERROR
insight used to survive rejection on the legacy surface (H1 / XA-07). A framework
error is a diagnostic everywhere now. The rule that mattered — no exception text
ever escapes — is unchanged and still asserted.

### Kept, despite the name

- `_sync_state_to_legacy` and the `memory_{agent_id}` variable channel are the
  E-2/E-3 state bridges, not the insight contract. Unchanged, and deliberately
  not renamed here: renaming a method embedders may reference is its own breaking
  change and does not belong in a release whose break is already stated precisely.
- The five values `fact`, `suggestion`, `warning`, `opportunity`, `praise` are not
  removed — they are five of the nine in the surviving vocabulary. What went is
  the regime that offered *only* those five.
- `HOST_DEFAULT_SUPPORTED_TYPES` (formerly `LEGACY_HUMAN_TYPES`) is the set a host
  is assumed to support when it declares no capabilities. It was doing two jobs;
  one of them survived, and it is now named for that one.

### Known gap

`speak_without_gate` — a schema author's opt-in to "content implies speak" — is
honoured by `resolve_gate_mode`, which only the removed legacy staging called. The
typed path hard-codes the boolean gate for flat adapters, so the opt-in is
silently inert. This is **pre-existing**, masked until now because a standalone
agent constructed itself as `legacy_v2`. Fixing it changes typed behaviour, which
this release's spec puts out of scope, so it is left failing and visible
(`xfail(strict=True)`) rather than re-baselined to the broken behaviour.

### Contracts

89 registered, 89 covered, strict gate green. No contract was dropped: the nine
bound to the removed path were restated under their existing ids, with what was
retired recorded in each statement, so the registry's history stays readable.
`INSIGHT-CONTRACT-SELECTION` is inverted rather than deleted — it now asserts that
the selection mechanism is absent, which is a stronger guarantee than silence.

## [2.8.1] - 2026-09-12

One diagnostic detail a host counting runs per agent needs. Cut from a green main after the
fix merged: 943 tests, contract gate 89/89 strict, clean-wheel smoke (CI).

### Fixed — the envelope failure category is host-visible (ENVELOPE-FAILURE-CATEGORY, INV-56)

- When no JSON object arrives from the model client, the agent's `invalid_envelope`
  diagnostic now carries the client's failure category as its classification
  (`timeout`, `rate_limit`, `server`, `refusal`, `malformed`, `truncated`, …) instead of
  `none`. The category is the sanitized word the client already logged, never model text;
  `none` remains for a client that reported no category, and a non-object body keeps its
  type name. A host that counts runs per agent can now exclude a provider transport
  failure and still see a refusal or a malformed body for what it is, from the
  diagnostics alone. Additive: only the classification string of one diagnostic changes.

## [2.8.0] - 2026-09-12

Typed reach ([docs/SPEC_V2_8_TYPED_REACH.md](docs/SPEC_V2_8_TYPED_REACH.md)): every shipped schema
registers under `typed_v1` or says why, evidence coordinates, the result-only isolated
instruction, urgency provenance, content-slot ordering, correctable targets, per-agent
sidecars (INV-49…INV-55). Cut from a green main: 930 tests, contract gate 88/88 strict,
clean-wheel smoke.

**Verification reported per layer.** *Framework:* every v2.8 leaf is implemented, registered
and tested with its negative control. *Distribution:* the installed wheel is exercised outside
the checkout by CI, and was run the same way locally before the feature merge (#37). *Provider:*
live acceptance of any generated schema is **not** claimed. *Host / end-to-end:* a host's use of
`source_index`, `evidence_citations`, `released`, `correctable` and `data_by_agent` needs a
version-identified conformance run; **none is claimed**.

### Added — typed reach (docs/SPEC_V2_8_TYPED_REACH.md; contracts TYPED-ADAPTER-FLAT-V1,
TYPED-ADAPTER-ROOT-V2-SIDECAR, TYPED-UNSUPPORTED-SCHEMA-NAMED, EVIDENCE-COORDINATES-AND-CITATIONS,
ISOLATED-INSTRUCTION-RESULT-ONLY, URGENCY-PROVENANCE, CONTENT-RESULT-AFTER-RELEASE,
CORRECTABLE-TARGETS, DATA-BY-AGENT; INV-49…INV-55)

- **Every shipped schema either registers under `typed_v1` or says why not (TA-1…TA-3).**
  `default` gains the `flat_v1` typed adapter (candidate at the root plus its
  `memory_updates` channel); `ui_control` and `widget_control` gain `root_v2` with the
  sidecar — the state block is named by the mapping's `variable_updates_field`, the
  `ui_actions` block and its rule by the descriptor's new `sidecar_instruction`; the
  silence-only envelope of a sidecar-bearing schema keeps the sidecar (a widget
  controller may act without speaking). `custom1` stays legacy-only and fails typed
  registration with its `typed_unsupported_reason` and the six adapters named; declaring
  `typed_v1` without a `typed_adapter` is now a registration error. Legacy instructions
  and parse paths are byte-identical.
- **Evidence coordinates and citations on demand (EC-1).** Framework-built segment
  entries carry `source_index` (the position in the `recent_segments` list the host
  passed, before trimming) and the segment's `timestamp`; accepted segment references are
  stamped with `EvidenceRef.source_index` (engine-owned: a model- or producer-authored
  value rejects). `HostInsightCapabilities.evidence_citations=True` exposes the citation
  markers, the reference contract and the citable host ids on every typed run.
- **Result-only instruction on the isolated path (IC-1).** An isolated content task's
  prompt offers the insight envelope only — no domain channels, no sidecar, no
  scratchpad section — and says so; live turns are unchanged.
- **`AgentInsight.urgency_provided` (UP-1).** Engine-owned and staged like
  `confidence_provided`: true only for a valid explicit urgency; false for the agent
  default, the per-type fallback and unknown provenance; `None` on legacy emissions.
- **`await handle.result()` returns after the slot is released (CS-1).**
  `ContentTaskHandle.released` is the same point as an awaitable; a refused handle is
  released already. A host sequencing replacement can admit the next task the moment
  `result()` returns.
- **`PriorInsightRecord.correctable` (CT-1).** Host-set, default true; false removes the
  record from the offered targets and rejects a correction naming it
  (`target_not_correctable`); answers still validate against it.
- **`AgentResponse.data_by_agent` (DS-1).** Aggregated responses attribute each committed
  sidecar to its agent (copies); the merged `data` keeps its v2.7 shape.
- The clean-wheel smoke now also registers a `default`-schema agent under `typed_v1` and
  checks a widget sidecar's attribution from the installed wheel.

### Migration notes (2.7 → 2.8)

Additive. New nullable keys — `AgentInsight.urgency_provided`, `EvidenceRef.source_index`,
`EvidenceCatalogEntry.source_index` / `timestamp`, `AgentResponse.data_by_agent`,
`HostInsightCapabilities.evidence_citations` (default off), `PriorInsightRecord.correctable`
(default true), `ContentTaskHandle.released` — none in `model_dump_legacy()`. Typed
prompts differ for `root_v2` schemas with a sidecar, on the isolated path, and when
`evidence_citations` is on; legacy prompts do not change. A typed batch containing
`default`, `ui_control` or `widget_control` agents now registers; one containing
`custom1` still fails, now by name.

## [2.7.0] - 2026-09-07

The insight contract (XUBB-ITC-1 1.2.0, gates G0–G3, C1, C2) and the three hardening
increments (H1–H3) driven by the independent audits of `e3dfaf1` and `0f3cc32`.
Cut from a green main: 884 tests, contract gate 79/79 strict, clean-wheel smoke.

**Verification reported per layer.** *Framework:* every framework-scope leaf is
implemented, registered and tested; the audited defects are closed and the audit's
regression suite runs verbatim in the suite. *Distribution:* the installed wheel is
exercised outside the checkout by CI. *Provider:* live acceptance of the generated
structured-output schema is **not** claimed. *Host / end-to-end:* every `.HOST` /
`.E2E` leaf still needs a version-identified conformance run; **none is claimed**.

### Migration notes (2.6 → 2.7)

The public API is additive and the legacy wire shape is preserved
(`AgentInsight.model_dump_legacy()`), but four behaviours tightened for existing
consumers on the default `legacy_v2` contract:

1. **Unknown insight types are rejected, never relabelled** (G0, D-LR). An agent whose
   schema emits a type outside the legacy five now produces a `partial` result
   (valid channels commit, insights dropped, diagnostics attached) instead of a
   coerced insight.
2. **Retained interactive records need a principal** (H1). A `PriorInsightRecord`
   without `principal_id` no longer matches any current principal for answers or
   corrections; hosts must record the principal on question/correction records.
3. **Content-policy numerics are strict** (H2). `"1000"` or `true` in a content profile
   or host limit fails at load time (`AgentConfigurationError`) instead of coercing.
4. **Framework ERROR cards** keep their legacy surface but are sanitized categories
   (never exception text); under `typed_v1` they are diagnostics only.

Everything under `typed_v1`, evidence, replies/questions/corrections, provider
structured outputs and long-form content is new in this release. Increment-by-increment
detail follows.


### Fixed — H3: two residual boundary cases (reassessment of `0f3cc32`)

- **Isolated content views carry validated answers only.** `start_content_request`
  now runs the same answer validator as the live turn (this session, open question,
  present matching principal) on the frozen view before the per-agent visibility
  filter; invalid events surface as diagnostics on the `ContentResult`. Previously an
  invalid answer for the agent's own question could reach an isolated prompt.
- **Negotiated limits are re-applied at final acceptance.** Staging hands the effective
  `long_form_v1` ceilings (body chars, preview chars, formats) to the engine with the
  other content values; the boundary re-checks the body, preview and format of the
  object that would commit. A finish callback can no longer grow an accepted body past
  the frozen policy. Contracts: CONTENT-VIEW-ANSWERS-VALIDATED, NEGOTIATED-LIMITS-AT-BOUNDARY
  (INV-47/48).

### Fixed — H2: content path and assurance (independent audit of `e3dfaf1`, findings XA-04/05/06/08)

- **Admission at the content entrypoint (XA-04).** `start_content_request` now refuses,
  before any snapshot copy, clone, task or model call: a non-typed engine
  (`typed_contract_required`), a non-isolatable agent, an agent without a content
  contract (`agent_has_no_content_contract`), and any request the negotiated policy
  rejects for THIS request (host capability, schema support, depth, execution
  declaration — evaluated through the agent's pure `content_admission` on a shallow
  view). A refusal is an immediate rejected `ContentResult` on a task-less handle.
- **Task lifecycle (XA-05).** Capacity is reserved synchronously at the entrypoint and
  released by the task's done-callback on every exit — completion, rejection,
  exception, cancellation while running, cancellation before the coroutine first ran.
  Completed handles leave the pending registry; their results stay readable; session
  closure revokes pending tasks only. The semaphore is gone; the bound is an explicit
  counter, described accurately: it limits content-task concurrency and reserves no
  live-provider capacity.
- **Prompt derived from the enabled contract (XA-06).** The forbidden-field rule is
  generated from the same effective descriptor as the requested fields, so a long-form
  run never forbids `preview` / `content_format` it just asked for. Citation markers,
  the evidence-reference contract and the host's citable ids are exposed whenever an
  enabled type needs an evidence basis — a permitted `correction` in the general
  profile included — so a general-profile DynamicAgent can now actually produce an
  acceptable correction (previously unreachable).
- **Strict primitives (XA-08).** `ContentProfile`, `AgentContentConfig.max_preview_chars`
  and the host's `max_content_chars` / `max_preview_chars` are strict at construction:
  `"1000"`, `True` and non-finite numbers are rejected through the real configuration
  path (`AgentConfigurationError`), never coerced.
- **Distribution evidence.** New CI job `wheel-smoke` builds the wheel, installs it into a
  fresh venv and runs `tools/wheel_smoke.py` from outside the checkout (typed live turn,
  custom-agent rejection, packaged artifacts, admitted content task). The script refuses
  a source-tree import unless explicitly allowed.
- The audit's regression file is adopted verbatim as
  `tests/test_audit_e3dfaf1_regressions.py` (assertions unchanged; 19/19 pass).
  Contracts: CONTENT-ENTRYPOINT-ADMISSION, CONTENT-TASK-LIFECYCLE,
  PROMPT-FIELDS-FROM-CONTRACT, CONTENT-CONFIG-STRICT-PRIMITIVES, DISTRIBUTION-CLEAN-WHEEL
  (INV-42…46).
- One existing G3 test narrowed its assertion: the correctable-messages listing still
  names own earlier messages only, while the new citable-evidence line may list other
  agents' insights as a BASIS (evidence, not correction authority).

### Fixed — H1: enforcement and identity (independent audit of `e3dfaf1`, findings XA-01/02/03/07)

The audit found that the strongest guarantees held on the DynamicAgent path but not
uniformly across every supported producer. H1 closes the four high-priority findings;
nothing in the design or the type vocabulary changes.

- **One acceptance pipeline for every producer (XA-01).** The engine boundary now re-runs
  the strict candidate validator on the producer-controlled projection of every insight —
  custom `BaseAgent` subclasses, DynamicAgent staging and callback-modified responses
  alike — so a `question` without its payload, a hypothesis without evidence, an empty
  body, a non-finite confidence, an unsupported urgency, an engine-owned key in metadata
  or an un-negotiated content field rejects the whole typed response whichever class
  produced it. Engine-owned public fields (`id`, `turn`, `contract_version`,
  `confidence_provided`, `content_contract`, `response_depth`, `content_request_id`,
  `source_snapshot_id`) can never be producer-set: trusted staging hands its
  runtime-derived values to the engine privately and the engine stamps them after
  validation. Reference authority comes from the invocation — host records plus the
  run's own snapshot held by the agent — never from a snapshot attached to the response.
- **Domain channels are revalidated on the object that commits (XA-01).** In both
  contracts the boundary shape-checks `events`, `variable_updates`, `queue_pushes`,
  `facts` (including confidence), `memory_updates`, `state_updates` and `data`, with
  reserved `sys.*` writes. A fatal domain error rejects the whole response; D-LR legacy
  partial acceptance for recoverable insight errors is preserved; typed atomicity holds.
- **Answer visibility is scoped on the invocation view (XA-02).** The engine builds a
  per-agent context whose `insight_answers` contain only the answers to that agent's
  own questions (or all, when the host authorised sharing) — for the live phases and for
  isolated content tasks — so the rule holds through direct access, template aliases
  of the full context and custom agents, not just the prompt shortcut.
- **Interactive operations require a present, matching principal (XA-03).** Answers are
  accepted only when the current principal is present and equals both the question's
  and the answer's principal; correction targets only when the current principal is
  present and equals the record's; correction capability, like reply and question, is
  unavailable without a principal (`missing_principal`). Missing identity is never a
  wildcard.
- **Typed failures are diagnostics only (XA-07).** An evaluation exception under
  `typed_v1` yields `invalid_envelope` / `agent_error:<ExceptionType>` and no insight;
  the sanitized ERROR card remains a `legacy_v2`-only surface.
- Contracts: BOUNDARY-UNIFIED-ACCEPTANCE, ANSWER-VISIBILITY-SCOPED,
  INTERACTIVE-PRINCIPAL-IDENTITY, TYPED-FAILURES-ARE-DIAGNOSTICS (INV-38…41). The
  audit's own regression file passes its 14 H1-scope cases unmodified; the 5 remaining
  cases are H2 scope.
- Behaviour change to note: a `PriorInsightRecord` without `principal_id` no longer
  matches any current principal for answers or corrections; hosts must record the
  principal on interactive records.

### Added — C2: isolated active-session extended generation (XUBB-ITC-1 §14.6.1, §14.9; DL-6)

The last contract gate. Extended content during an ACTIVE session now has a real
execution path instead of a refusal.

- **`AgentEngine.start_content_request(context, agent_id, request) → ContentTaskHandle`**
  runs one extended generation as its own task: a fresh agent instance cloned from its
  definition (custom `BaseAgent` instances are refused as shared mutable state), a frozen
  deep copy of the context (transcript, Blackboard snapshot, capabilities, references),
  and an **engine-issued** isolated declaration. A host-authored isolated declaration is
  still refused (`isolated_path_requires_engine_task`): a boolean never substitutes for
  the runtime.
- **Isolation by construction.** The task never enters the live turn path, never writes
  the live Blackboard or private memory, never bumps the live turn counter, never
  reserves correction targets, and fires no turn callbacks (no trace contamination).
  Live turns proceed concurrently on the same engine.
- **Result-only.** `ContentResult` carries the request id, the source snapshot id, the
  snapshot turn, status (`accepted | silent | rejected | cancelled`), the single insight
  (stamped with both ids), diagnostics and usage. Proposed domain effects, sidecars or
  interactive types reject the result; the host checks currentness against the snapshot
  before presenting it.
- **Bounded admission.** `content_limits.max_concurrent_content_tasks` (default 1);
  exhaustion rejects immediately (`provider_admission_exhausted`) rather than queueing.
  The bound limits content-task concurrency only; it does not reserve live-provider
  capacity for the live turn.
- **Closure.** `handle.cancel()` or `AgentEngine.close_session_content(session_id)`
  revokes publication: a cancelled or late result reports `cancelled` with usage and
  diagnostics retained and nothing published.
- Contract: CONTENT-ISOLATED-PATH (roadmap INV-37), with real concurrency tests.

### Added — C1: the long-form content contract `long_form_v1` (XUBB-ITC-1 §14.4–§14.10)

Under `typed_v1` an agent may opt into extended content. Type describes purpose, never
length; the default `legacy_v2` path is unchanged.

- **Negotiation.** `insight_config.content` (`AgentContentConfig`: contract, default
  depth, formats, preview limit, per-depth profiles with character cap, output-token cap
  and per-request timeout) + host `content_contracts` / `content_formats` /
  `expanded_reading` / limits + a schema adapter declaring the contract (`insight_v1`) +
  `AgentEngine(content_limits={...})` with a finite `max_response_bytes` and the live
  ceilings. A content block on a legacy engine or unsupporting schema fails registration;
  an unsupporting host rejects before any call.
- **Depth and admission before generation** (`core/content_contract.py`, the reference
  policy verbatim). Effective depth is the host's `insight_content_requests[agent]` or the
  agent's default. Admission runs against the host's trusted
  `AgentContext.content_execution_context`: in an active session only `brief` within the
  operator's live ceilings; `standard` / `detailed` need a declared pause or post-session
  execution; the isolated active path is refused until C2; no declaration →
  `invalid_content_execution_context`. FORCE is neither authorization nor isolation. The
  admitted profile's `max_output_tokens` and `llm_timeout_seconds` become the call budget.
- **Body, preview, limits, completion.** The complete body is `content`; `preview` is
  an optional plain-text entry point under the same id; limits are decoded code points
  (most restrictive of profile, host, operator) plus a UTF-8 byte ceiling on the transport
  body (`LLMResult.raw_bytes`); exactly the limit passes, one over rejects with nothing
  shortened. Only a complete generation (finish_reason `stop`) may emit; `length` is
  `incomplete_generation`, unreported is `completion_unknown`, model metadata cannot
  assert completeness. Rejections are atomic; a preview never salvages a body.
- **Output.** Negotiated insights carry `preview`, `content_format`,
  `content_contract="long_form_v1"`, `response_depth`, `content_request_id`,
  `source_snapshot_id`; non-negotiated output and `model_dump_legacy()` omit them. The
  generated instruction states the depth objective, limits, preview fidelity and formats;
  the provider projection includes the extension fields only when negotiated.
- Contracts: CONTENT-POLICY-DERIVATION (62 packaged fixtures reproduce),
  ITC-26/27/28/29/30/33/35 `.FW`. Reading retention, safe rendering and
  expand-without-generation (ITC-31/32/34) are host conformance runs; isolated
  active-session generation is C2.

### Added — G3 part 2: the correction lifecycle (XUBB-ITC-1 §10)

The last interactive purpose becomes available under `typed_v1`; all nine purposes are
now implemented on the typed path.

- **CORRECTION** needs `allow_correction`, membership, host `corrections` and a retained
  history snapshot this run (`insight_reference_context.prior_insights`; otherwise
  `capability_unavailable` / `missing_history`).
- **Target validation at the engine boundary** (DynamicAgent and custom agents alike):
  the target must be a previously emitted human-facing insight from an earlier turn, in
  this session, still `active`, for the same principal; same-turn and cross-session
  targets are deferred (rejected). Authority is own-agent output unless the host's
  `correction_agent_policy="allowlisted"` names the agent in `correction_agent_ids`;
  nothing in the payload or metadata widens it. A separate evidence basis is required
  and must resolve. Violations reject the whole response; a failed correction never
  becomes another card.
- **Whole-response arbitration at phase close** (`_arbitrate_corrections`), before
  anything from the phase commits: correction-bearing responses are ordered by
  descending priority then later registration (never arrival); a response is accepted
  only when all its targets are unreserved and reserves them together; otherwise it is
  rejected whole with `correction_conflict` (no sibling insight, state, event, memory or
  sidecar commits; one callback). Duplicate targets in one response reject it. Earlier-
  phase reservations stand; reservations reset each turn.
- The generated instruction lists the agent's own correctable earlier messages and the
  self-repair rule.
- Contracts: ITC-18.FW, ITC-20.FW. Host delivery (ITC-19 and the `.HOST` leaves) is a
  conformance run, not claimed. Deadline closure of the arbitration set arrives with the
  delivery workstream.

### Added — G3 part 1: reply drafts and correlated questions (XUBB-ITC-1 §9, §11)

Two of the three interactive purposes become available under `typed_v1`, each behind
its permission intersection. The correction lifecycle is G3 part 2.

- **REPLY** is emitted as a draft when `allow_reply` + `reply` in `allowed_types` +
  host `reply_drafts` + an explicit `principal_id` all hold; anything less is
  `type_not_allowed` / `capability_unavailable`. The engine invokes nothing for a draft;
  the generated instruction states the draft rule and the no-invented-commitments rule.
- **QUESTION** needs `allow_question` + membership + host `text_questions` + principal +
  a `question.reason`; the engine-assigned insight id is the answer correlation key.
- **Answer channel.** `AgentContext.insight_answers` (`InsightAnswer`: event id,
  question id, principal, `answered` with text or `dismissed` without) is validated
  once per turn against the retained question records (same session, active, same
  principal); invalid events are dropped with engine diagnostics; duplicate or
  conflicting event ids within a batch reject. Validated answers reach only the
  originating agent — an `[ANSWERS FROM THE PRINCIPAL]` prompt section and
  `{{ insight_answers }}` — unless the host sets `HostInsightCapabilities.answers_shared`.
  A dismissal is presented as not an answer and not consent. Answers are data: they
  change no permission or identity, and receiving one schedules nothing.
- Contracts: ITC-17.FW, ITC-21.FW, ITC-22.FW. Host leaves (draft distinction, input
  UI, open/closed tracking, durable idempotency) are conformance runs, not claimed.

### Added — G2 part 2: provider structured outputs (XUBB-ITC-1 §13.3, SO-1)

Typed runs on the `insight_v1` schema can now ask the provider to enforce the
contract on the wire. Local validation is unchanged and still mandatory.

- **`AgentEngine(structured_outputs="strict" | "auto" | "json_object")`** (default
  `auto`), an independent transport control passed to the `LLMClient` and preserved
  across key rotation (EN-1/INV-18). `fallback_signatures=[...]` lets an operator enable
  evidence-backed downgrade signatures; the shipped registry
  (`library/contract/provider_capability_registry.json`) enables none.
- **Derived provider projection** (`core/provider_schema.py`): compiled per run from the
  shipped authoritative contract, restricted to the effective type set, closed objects,
  every property required, optionals nullable, content-extension keys omitted until
  negotiated; linted before any call (a failing schema is `provider_schema_error`, no
  call made). Equals the packaged projections.
- **`map_entries_v1` codec** for open-ended dictionaries in the full domain envelope
  (`metadata`, `variable_updates`, `queue_pushes`, `memory_updates`, `state_updates`,
  `data`, fact values, event payloads); decoded losslessly before local validation; a
  malformed encoding is a fatal `invalid_domain_payload`.
- **Wire (INV-24).** A strict request carries `response_format.type == "json_schema"`,
  `strict: true` and the effective enum; `json_object` mode never sends a schema.
- **Fail-closed fallback (A2-4).** `strict` never downgrades. `auto` downgrades once per
  capability key (endpoint, model, adapter, adapter version, schema version) only on a
  400 the adapter classifies as unsupported-capability for the `json_schema` feature
  that exactly matches an enabled signature with an evidence id; recorded on the client
  and reported as an `unsupported_structured_output` diagnostic. Otherwise the response
  is rejected with that diagnostic. Message text never matches.
- **Refusals** are their own `refusal` category (billed, not malformed, never evidence
  of unsupported schemas).
- Typed adapters declare `supported_transports`: `insight_v1` supports `json_schema`;
  `default_v2` / `v2_raw` stay on `json_object`. `strict` with a `json_object`-only
  adapter fails at registration.
- Contracts: PROVIDER-SCHEMA-DERIVATION, MAP-ENTRIES-CODEC, STRUCTURED-OUTPUT-FALLBACK.
  Contract artifacts ship in `xubb_agents/library/contract/` (package-data added).
  **Not claimed:** live provider acceptance of the generated schema (integration test).

### Added — G2 part 1: per-agent snapshot evidence catalog (XUBB-ITC-1 §6.3–§6.4)

Under `typed_v1` evidence references now resolve, which unlocks consulting hypotheses
and implications. The `legacy_v2` path is unchanged.

- **Framework-built snapshot catalog.** For every typed invocation, after context
  trimming, the agent's exposed transcript window and RAG documents become catalog
  entries `snap:<id>:segment:<n>` / `snap:<id>:document:<n>` (one per occurrence,
  never deduplicated; sources copied). The snapshot id is the invocation's execution
  id; it is not a durable identity across windows.
- **Host reference context.** `AgentContext.insight_reference_context`
  (`InsightReferenceContext`: `evidence` catalog entries, `prior_insights` records)
  joins the catalog for the session; frozen per run and propagated through both
  phases. Entries owned by another session resolve to `cross_session_reference`.
- **Resolution rules.** A reference resolves only to a catalog entry at its revision:
  a null revision resolves to the current one and is filled on the emitted insight;
  a stated revision must match exactly; anything nothing exposed is
  `unknown_reference`. Hypotheses need evidence + rationale + validation step;
  implications need evidence + rationale; general observations need nothing.
- **Citation contract in the prompt** (consulting profile only): transcript lines and
  documents carry their reference ids in brackets, the instruction states the
  reference shape and lists host-supplied ids, and asks the model never to invent one.
- **Retention aid.** `AgentResponse.evidence_snapshot` (per agent) and
  `evidence_snapshots_by_agent` (aggregate) return the immutable invocation view so a
  host that wants durable cross-turn references can retain it.
- Contracts: ITC-15.FW, ITC-16.FW registered; ITC-14.FW amended.

### Added — G1 part 2: typed acceptance, `insight_contract="typed_v1"` (XUBB-ITC-1 §6, §8, §13; D-CR)

`typed_v1` is now selectable. The default `legacy_v2` path is unchanged.

- **Strict local validation of the normalized candidate** (`core/insight_validation.py`,
  `validate_typed_candidate`): exact wire-value types in the run's effective set;
  unknown keys and every engine-owned key (`id`, `turn`, `contract_version`,
  `confidence_provided`, `acceptance_status`, `source_snapshot_id`, …) rejected at the
  root and in `metadata`; strict confidence input; urgency precedence (explicit →
  `default_urgency` → per-type fallback, invalid explicit rejects); consulting subtype
  rules; interactive payload shapes; content-extension fields rejected until negotiated.
  Agreement with the packaged JSON Schema is pinned on all 71 shape fixtures.
- **Typed atomicity (§8.4).** A malformed or inconsistent gate, any invalid candidate,
  or an invalid domain payload rejects the whole agent response; usage and diagnostics
  survive; valid silence still commits. One `on_insight_validation_error` per result.
- **Engine-minted identity.** Accepted typed insights get a session-unique `id`, the
  host's `turn`, `contract_version="typed_v1"`, a resolved `urgency`, and runtime-derived
  `confidence_provided` (omitted/null → placeholder `1.0` + `false`; a custom agent that
  did not declare provenance → `false`). Producers cannot supply identity.
- **D-CR ranking helpers.** `rank_key` / `rank_candidates` use
  `(urgency_order, -agent_priority, stable_merge_order)` and ignore confidence for every
  candidate; the engine stamps `merge_order = (phase, agent index, ordinal)` on merged
  insights. No ranking stage is applied yet (LC-3 roadmap).
- **Generated typed instruction (§13.1).** Under `typed_v1` the model is sent an exact
  allowed-value instruction built from the effective set; the schema's static legacy
  enum is not sent; an empty set yields a silence-only envelope.
- **Typed adapters and schema.** New `insight_v1` schema (typed-only normalized
  envelope). `default_v2` (`flat_v2` adapter) and `v2_raw` (`root_v2` adapter) declare
  `typed_v1`; other schemas fail registration under `typed_v1`, and `insight_v1` fails
  under `legacy_v2`. Descriptors gain `typed_adapter`, `typed_supported_insight_types`,
  `supported_insight_fields`.
- **Availability in this release.** Typed acceptance implements the six ordinary
  purposes. `reply`, `correction` and `question` remain unavailable
  (`not_implemented_in_this_release`) until G3; evidence references are unresolvable
  (`unknown_reference`) until the per-agent catalog lands at G2, so consulting
  subtypes cannot yet be emitted; `preview`/`content_format` reject until C1.
- **`AgentInsight` typed fields** (all default/None on legacy emissions): `id`, `turn`,
  `contract_version`, `urgency`, `confidence_provided`, `observation_kind`,
  `evidence_refs`, `rationale`, `validation_step`, `assumptions`, `correction`,
  `question`; `model_dump_legacy()` projects the v2.6 wire shape; `merge_order` property.
- Eight contracts registered: ITC-03/07/08/09/10/11/12 `.FW`, TYPED-SCHEMA-DERIVATION;
  INSIGHT-CONTRACT-SELECTION amended. Package fixtures (manifest-verified) under
  `tests/fixtures/insight_contract_1.2.0/`; `jsonschema` added to the dev extras.

### Added — G1 part 1: vocabulary, alias, contract selection (XUBB-ITC-1 §3–§4, §7)

Inert on the wire: no behaviour of the default `legacy_v2` path changes.

- **`InsightType` gains the nine-purpose vocabulary.** New members `OBSERVATION`,
  `REPLY`, `CORRECTION`, `QUESTION`; `INFORMATION` is an alias of `FACT` (same member,
  wire value stays `"fact"`, `.name` stays `"FACT"`, no `@unique`). `HUMAN_INSIGHT_TYPES`
  is the canonical nine-tuple type-offering code must use; `INSIGHT_TYPE_LABELS` is the
  explicit display map. On the legacy path the four new values remain
  `type_not_allowed` (G0) — the enum members exist; the capabilities do not yet.
- **`AgentEngine(insight_contract="legacy_v2" | "typed_v1")`.** Default `legacy_v2`.
  `typed_v1` **fails closed** with `AgentConfigurationError` until typed acceptance
  lands (G1 part 2); any other value is a `ValueError`.
- **Per-agent `insight_config`** (`allowed_types`, `allow_reply` / `allow_question` /
  `allow_correction`, `analysis_profile`, `default_urgency`), typed with `extra="forbid"`;
  `allowed_types=[]` is state-only. Malformed blocks fail `DynamicAgent` construction;
  a flag/membership contradiction fails `register_agent` / `replace_agents` before any
  mutation (all-or-nothing, VL-1 pattern). Also accepted on `AgentConfig` for custom agents.
- **Trusted host inputs on `AgentContext`:** `principal_id` and `insight_capabilities`
  (`HostInsightCapabilities`, safe defaults: the five legacy values, all interactive
  capabilities off). Frozen per run and propagated through Phase 1 and Phase 2 copies.
- **`AgentEngine.effective_insight_types(agent, context)`** — the §7.2 intersection
  (framework ∩ agent ∩ schema ∩ host ∩ permission prerequisites) with a reason for every
  absent value. Under `legacy_v2` it returns the host-safe five; typed enforcement uses
  it at G1 part 2.
- Five contracts registered: ITC-01.FW, ITC-02.FW, ITC-14.FW, INSIGHT-CONTRACT-SELECTION,
  INSIGHT-CONFIG-LOAD-TIME.

### Changed — G0 legacy safety (XUBB-ITC-1 §8, FINAL_DECISIONS D-LR)

The insight contract's first dependency gate. Applies on the default `legacy_v2`
path to every agent; `typed_v1` (whole-response atomic rejection, the nine-purpose
vocabulary) lands at G1. Behavioural edges, all deliberate:

- **Gates are declared, never truthiness.** A Boolean gate speaks only on an actual
  `true`; `"true"`, `"false"`, `1`, `null` and a *missing* required gate are
  `invalid_gate` (the result never speaks; the malformed gate is reported).
  Presence-gated schemas (`v2_raw`, `ui_control`, `widget_control`) reject a
  non-object root instead of treating it as empty. `custom1` declares a
  `content_presence` gate. Each shipped schema now carries a versioned `descriptor`
  (`gate_mode`, `supported_insight_types`, `supported_contracts`).
- **Unknown insight types are rejected, never relabelled.** The parser no longer maps
  an unrecognised type to `SUGGESTION`. An unknown label is `unknown_type`; `error`
  and the future wire values `observation` / `reply` / `correction` / `question` are
  `type_not_allowed` on the legacy path. Case-folding (`"WARNING"`) and the absent-type
  default (`suggestion`) remain as declared legacy normalisations.
- **Legacy partial acceptance (D-LR).** A recoverable insight error rejects all
  insights from that result but commits its independently validated, authorized
  domain channels with an explicit `partial` status; action-bearing `data` sidecars
  are withheld. Invalid domain payloads (e.g. `"facts": "none"`), agent-proposed
  `sys.*` writes (`reserved_state_write`) and unparseable envelopes reject the whole
  response. Previously malformed channels were silently ignored and `sys.*` writes
  warned-and-applied (INV-4 amended: host writes still warn; agent writes reject).
- **No parse-time durable mutation.** `DynamicAgent` never touches `private_state`
  while parsing; memory becomes durable only through the engine merge (INV-14 sync).
  Hosts that evaluated agents outside an engine and relied on in-process
  `private_state` accumulation must run turns through `AgentEngine`.
- **Framework ERROR insights are sanitized.** Content is the category `agent_error`
  plus the exception class name in metadata; the exception text is only in the
  non-serializing `debug_info`. Provenance is runtime-established: an agent-authored
  `ERROR` insight is dropped at the engine boundary.

### Added — G0

- `AgentResponse.acceptance_status` (`accepted | accepted_silent | partial | rejected`),
  `AgentResponse.diagnostics` (sanitized `InsightDiagnostic` rows: execution id, agent,
  code, field path, bounded classification, retained/withheld channels),
  `AgentResponse.execution_id`, and `acceptance_by_agent` on the aggregated turn response.
- `AgentCallbackHandler.on_insight_validation_error(issue)` — fired by the engine exactly
  once per partial/rejected execution result.
- `core/insight_validation.py` — pure gate / type / domain-channel validators and the
  D-LR decision table, reused by `DynamicAgent` and the engine boundary check.
- `StructuredLogTracer` steps carry `acceptance` and `diagnostics`.
- Docs: the packaged reference artifacts (local/provider JSON schemas, response
  contract, fallback-signature registry, host-kit procedure, provenance, manifest)
  under `docs/reference/insight_types_1.2.0/`, alongside the contract documents merged
  in PR #22; the live-assistance roadmap `docs/SPEC_V3_LIVE_ASSISTANCE.md` with its
  item-level cross-reference to the contract. Six new framework contracts
  (ITC-04/05/06/13/23/24 `.FW`) registered and INV-4 amended; host and end-to-end
  leaves are not claimed.

### Changed

- **`src/` layout.** The package moved from repo-root to `src/xubb_agents/`; `pip install -e .`
  and `pytest` now work from a checkout with **any** directory name (previously the checkout
  had to be named `xubb_agents` or test collection failed). Wheels additionally ship a
  `py.typed` marker, and packaging metadata migrated to PEP 639.
- The all-or-nothing bulk-reload rejection message now reads
  `Agent reload rejected (...)` (was `Vault reload rejected (...)`).

### Added

- Community files for public contribution: `CODE_OF_CONDUCT.md`, issue forms
  (bug/feature), a fork-based contribution flow in `CONTRIBUTING.md`, and a CI matrix
  over Python 3.11–3.13.

### Fixed

- **Post-2.6.0 documentation sweep** — six stale spots the release DOC items
  didn't enumerate: `EXECUTIVE_SUMMARY.md` still said 2.4.0 (×2) and only named
  gpt-4o-era models; `technical_spec_agents.md` header said 2.4.0; the docs
  index still called SPEC_V2_2 "the current release spec"; PLAYBOOK Gate 3
  quoted the pre-OB-2 `evaluate()` call verbatim; the prompt guide's
  reliability checklist recommended "gpt-4o for complex reasoning" (now
  actively misleading — deep lane = reasoning model + explicit effort +
  budgets); README gained a "What's New in v2.5 / v2.6" section above the v2.2
  one.

---

## [2.6.0] - 2026-07-13

Per-agent reasoning configuration (Release B of `docs/SPEC_LLM_MODERN_MODELS.md`).
Additive config surface + **one deliberate load-time edge** (see Breaking below).
The two-lane pattern is now first-class: fast whisper agents pin effort off;
deep analysis agents opt into reasoning with validated budgets.

### Added

- **Per-agent LLM-call config on `AgentConfig` / `model_config`** (RC-1/RC-3,
  INV-15): `reasoning_effort`, `timeout`, `max_tokens` — forwarded by
  `DynamicAgent` **only when set** (the framework never injects a parameter the
  operator didn't write; omission leaves the model's own default; strict-
  signature fakes and downstream test doubles stay compatible). On custom `BaseAgent`
  subclasses the fields are a *declaration* consumed by validation — the
  subclass owns forwarding them into its own calls (PLAYBOOK snippet).
- **`model_config.model_params`** (RC-2): verbatim Chat-Completions passthrough
  for parameters the framework doesn't model (e.g. `verbosity`). Framework-owned
  keys (`model`, `messages`, `response_format`, both token-cap spellings,
  `timeout`, `reasoning_effort`) are rejected at load with
  `AgentConfigurationError`; the call-site merge is defensive regardless
  (framework keys always win). Documented as wire-shaped, not transport-portable.
- **Load-time validation at registration** (VL-1, INV-19): an ADVISORY
  model-name heuristic (payload-advisory — provably never alters outbound
  kwargs) drives warn-once signals: effort on a non-reasoning shape, deep
  effort with starved budgets (`timeout <= 10s` / `max_tokens < 4096` — billed
  timeouts/truncation), `temperature`/`top_p` on reasoning models.
- **`AgentEngine` LLM knobs** (EN-1, INV-18): `llm_timeout`, `llm_max_retries`,
  `llm_max_tokens`, `llm_base_url` (OpenAI-compatible endpoints, first-class),
  `llm_wire_max_tokens_param`, `strict_reasoning_config`. The resolved set is
  stored and **reused by `update_api_key`** — key rotation no longer silently
  resets the client to module defaults (previously it rebuilt bare).
- **`xubb_agents.AgentConfigurationError`** — the load-time config failure type.

### Breaking (deliberate, per spec D-1 ruling)

- **A model matching the reasoning heuristic without an explicit
  `reasoning_effort` now hard-fails registration** with a copy-pasteable fix
  (the API default — often `medium` — silently blows the real-time envelope
  and multiplies cost). One config field per affected agent. Escape hatch:
  `AgentEngine(strict_reasoning_config=False)` downgrades to a warning.
  `replace_agents` is all-or-nothing: one bad config rejects the whole bulk
  reload and the old registry keeps serving.

### Migration (hosts)

- Audit your agent configs before upgrading: every agent on a `gpt-5*` / `o1|o3|o4*`
  model needs `model_config.reasoning_effort` (`"none"` for 5.1+/5.6 mainline,
  `"minimal"` for the original gpt-5 family, `"low"` for o-series). Effort
  value validity is per-model; a wrong pair surfaces as `misconfig`.
- Recommended lanes: fast = gpt-5.4-nano + `"none"` (or gpt-5-nano +
  `"minimal"`); standard = gpt-5.4-mini / gpt-5.6-luna + `"none"`; deep
  (opt-in) = gpt-5.6-terra/sol + `low`–`high` + `timeout >= 30` +
  `max_tokens >= 25000`.
- Hosts that relied on `update_api_key` resetting LLM settings (unlikely;
  previously a bug) must now set them explicitly.

---

## [2.5.0] - 2026-07-13

Modern-model wire compatibility + observability (Release A of
`docs/SPEC_LLM_MODERN_MODELS.md`). Inert on the OpenAI-wire and
`generate_json`-return surfaces for every working config (one deliberate
deviation noted below); reasoning *configuration* (per-agent `reasoning_effort`
etc.) lands in 2.6.0.

### Added

- **`LLMClient.generate() -> LLMResult`** (OB-2, INV-17): per-call result object
  (`parsed`, `error_category`, `usage`, `finish_reason`) — attribution-safe under
  concurrent agents on the shared client, where the old `last_error_category`
  attribute can only report the last writer (it remains as a deprecated
  best-effort mirror with a single write site). `generate_json` is now a thin
  delegate; its dict-or-`None` never-raise contract is unchanged.
- **Token-usage telemetry** (OB-2): plain-int usage (`prompt_tokens`,
  `completion_tokens`, plus `reasoning_tokens`/`cached_tokens` when reported)
  flattened from the SDK response — populated even on billed failures
  (`truncated`/`malformed`). Surfaced on the new first-class
  **`AgentResponse.usage`** field (additive, default `None`; `debug_info` is
  `exclude=True` and never serializes) and in `debug_info["usage"]` for the tracer.
  `DynamicAgent` duck-types the client (`generate()` when present,
  `generate_json` fallback), so `generate_json`-only fakes and downstream
  test doubles keep working unmodified.
- **Error categories `misconfig` and `truncated`** (OB-1, INV-16): a 4xx
  parameter/model rejection is `misconfig` (an operator problem — previously
  miscategorized as `server`, paging the outage runbook); a length-stopped
  response (`finish_reason="length"` — the starved-reasoning signature) is
  `truncated` (previously masqueraded as `malformed`). Missing/non-int
  status_code falls to `server`. Contracts:
  `INV-16-error-taxonomy-misconfig-truncated`, `INV-17-per-call-attribution`.
- **`LLMClient(wire_max_tokens_param=...)`** (WC-1): legacy opt-out for old
  OpenAI-compatible proxies (`"max_tokens"`); ctor-validated.

### Changed

- **The token cap ships on the wire as `max_completion_tokens`** (WC-1) — the
  successor kwarg, required by reasoning models (gpt-5.x, o-series) and accepted
  by current non-reasoning models. The Python parameter name (`max_tokens`)
  does not change anywhere. Old configs keep working; reasoning models stop
  400-ing on the framework's requests.
- **openai SDK floor raised to `>=1.60.0`** — older SDKs TypeError on the new
  kwarg, and the never-raise wrapper would swallow every call into
  `category=unknown` (silent agent death).
- **Deliberate deviation:** a length-stopped response whose partial content
  happens to parse now returns `None` (`truncated`) instead of the parsed
  fragment — a truncated JSON object is not a trustworthy whisper.

### Fixed

- **`ui_control.json` violated JSON mode's precondition** (QW-1): its
  instruction never contained the word "json", so
  `response_format={"type":"json_object"}` 400s for any agent whose own prompt
  doesn't contain it. Reworded; a drift-lock test (globbed over
  `library/schemas/*.json`) pins every shipped schema.
- **`user_context` created a blank prompt section** (QW-3): the section carried
  a trailing `"\n\n"` and the joiner added another — exactly the D1
  blank-section bloat the sweep exists to catch; its fixture just never set
  `user_context`. Now covered both ways.
- **Default model hardcoded in two places** (QW-2): now a single framework
  constant `xubb_agents.DEFAULT_MODEL` (value unchanged: `gpt-4o-mini`;
  changing the value is a separate, eval-gated decision).
- `docs/prompt_engineering_guide.md` wrongly said the transcript is sent as
  separate user/assistant messages; it is one `### TRANSCRIPT:` user message.

### Fixed (carried from post-2.4.0 unreleased)

- **Contract-gate CI was red** (so the "every contract is CI-gated" claim was fragile).
  The repo root *is* the `xubb_agents` package, and pytest names it after the checkout
  directory; GitHub's default `xubb-agents` (hyphen) checkout is not a valid module name,
  so collection failed with "attempted relative import with no known parent package".
  CI now checks out into `xubb_agents` (`actions/checkout` `path:` + a job
  `working-directory`); the dir-name requirement is documented in CONTRIBUTING and the
  pytest config. Local `git clone` + `pytest` needs the same dir name.
- `tools/debugger.html`: fixed a malformed tag — a stylesheet `<link>` was closed with
  `</script>` (introduced with the SRI pinning).
- `SECURITY.md` supported-versions table still listed `2.3.x` after the 2.4.0 bump;
  corrected to `2.4.x`. Also dropped a stale "(v2.3+)" qualifier from a spec heading.

---

## [2.4.0] - 2026-07-05

Public-release hardening. One additive API (`unregister_agent`); no breaking changes.

### Added

- **`AgentEngine.unregister_agent(agent_id) -> bool`** — remove a single agent by id,
  symmetric with `register_agent`. It was missing entirely although a host relied on it
  (the Prompt Studio "test agent" cleanup called it, hitting `AttributeError`). Rebinds
  the registry under the lock and recomputes indices. Contract:
  `AGENT-REGISTRY-MUTATORS-CONSISTENT`.
- `SECURITY.md` — a private vulnerability-disclosure policy, a supported-versions table,
  and the security model (the Jinja2 template-source trust boundary, and the rule that
  agent output is untrusted and must be escaped by the host).
- `docs/README.md` — an index for the documentation tree.
- README badges (contract-gate, license, Python), a one-line pitch, and a **no-key
  offline Quickstart** variant. Both README code blocks are drift-locked by
  `tests/test_readme_quickstart.py`, which executes them in CI.
- `pyproject.toml` Changelog / Bug Tracker / Security URLs, plus discovery keywords and
  classifiers (`Framework :: AsyncIO`, AI topic).
- `CONTRIBUTING.md` (promoted from the README section) and a
  `.github/PULL_REQUEST_TEMPLATE.md` with a contract-checklist.

### Changed

- Copyright and package author set to `genriq` (LICENSE + `pyproject.toml`).
- Minimum Python raised to **3.11**; dropped the untested 3.8–3.10 classifiers so the
  metadata matches what CI actually exercises.
- `AgentContext.blackboard` is now typed `Optional[Blackboard]` (was `Optional[Any]`)
  via a `TYPE_CHECKING` forward reference, restoring static checking on the hottest field.
- Added missing return annotations (`register_agent`/`update_api_key -> None`,
  `check_keyword_triggers -> List[Tuple[BaseAgent, str]]`).
- Softened the `[2.1.0]` security note: "SSTI vulnerability eliminated" → sandboxing as
  defense-in-depth, with untrusted template source called out as a trust boundary.
- Removed self-referential "12/10 Architecture" comments from `library/dynamic.py`.
- Trimmed `docs/EXECUTIVE_SUMMARY.md` to a developer-facing Overview: kept the
  architecture, concepts, and use-case content; dropped the pitch-deck framing.
- Moved the README table of contents to the top and expanded it to cover all major
  sections (anchors verified).

### Removed

- `docs/PUBLIC_RELEASE_READINESS.md` — an internal pre-launch audit artifact, not
  documentation for the public tree.

### Fixed

- **`register_agent` now mutates the registry lock-safely.** It appended/assigned in
  place while `replace_agents` (called from the host's config-reload thread) rebinds
  under a lock, so the two could race. `register_agent` now uses the same
  rebind-under-lock discipline; a lock-free reader always sees a complete registry.
- **Legacy memory path no longer aliases live agent state.** The default-format memory
  update assigned the live `self.private_state` dict into the response by reference, so a
  tracer capturing the response (or the next turn's mutation) altered already-emitted
  data. It now emits a copy.
- **Background LLM-client close no longer fire-and-forgets.** `update_api_key`'s async
  client close is now referenced (not GC'd mid-flight) and its failures are logged.
- **README Quickstart crashed on its last line.** It iterated `response.insights` as
  dicts (`insight['type']`) but they are `AgentInsight` objects — a `TypeError` on the
  first code a newcomer runs. Now uses attribute access, drift-locked in CI.

### Security

- **Jinja2 sandbox floor raised to `>=3.1.6`.** Prompt templates render through
  `SandboxedEnvironment`; the sandbox is only as strong as the installed patch level.
  The old `>=3.1.0` floor permitted versions with published sandbox escapes
  (CVE-2024-56201, CVE-2024-56326 — fixed in 3.1.5; CVE-2025-27516 — fixed in 3.1.6).
- **`tools/debugger.html` hardened against DOM XSS.** The metadata pane rendered
  LLM-emitted, transcript-derived content through a `v-html` sink without escaping.
  Values are now HTML-escaped before syntax highlighting.
- **`StructuredLogTracer` privacy documented.** Its docstring now warns that the trace
  includes full transcript history / shared state / raw agent output (potential PII) and
  is emitted at INFO — attach it behind a dedicated, access-controlled logger rather than
  general INFO aggregation. "Production-ready" warranty wording dropped.
- **`tools/debugger.html` CDN assets pinned + SRI.** Vue and Font Awesome are now
  version-pinned with `integrity` hashes; Tailwind (play CDN) is documented as
  unhashable and dev-only.

---

## [2.3.0] - 2026-07-04

### Added

- **`AgentEngine.replace_agents(agents)`** — atomic full-registry swap for hot
  reloads. Rebuilds the registry and rebinds it LAST, so a concurrent turn never
  observes a half-cleared registry (the unsafe `clear()` + register-loop pattern
  this replaces could drop every agent mid-turn). Contract:
  `AGENT-REGISTRY-ATOMIC-SWAP`.
- **Contract gate (`tools/check_contracts.py`)** — the contract-accuracy gate
  (see `docs/PROCESS.md`). Reads `docs/CONTRACTS.yaml` and hard-fails the
  build for any `covered` contract whose named test is missing, skipped, or failing, and
  for any malformed registry entry; `to_verify`/`uncovered` are reported as debt (not a
  red build) so the framework is not blocked before the bijection back-fill. `--strict`
  additionally requires a passing test for every entry (the full-coverage release gate).
  Production-grade behavior: **fails closed** (`GateError`) when the suite did not run /
  the JUnit report is absent, empty, or unparseable — never a silent pass; a **debt
  ratchet** (`debt_baseline`) fails the build if debt grows, so it can shrink but never
  silently accrete; **node-level bijection** is required for `covered` (file-level refs
  rejected); parametrized tests are aggregated (all-pass → pass, any-fail → fail).
  Decision logic is a pure `evaluate()` over a `{test_ref: outcome}` map for fast,
  deterministic unit tests; the CLI accepts `--junit PATH` so CI runs the suite once.
- **CI workflow (`.github/workflows/contract-gate.yml`)** — runs the suite once (JUnit)
  and feeds the gate via `--junit`, making the Contract Registry an enforced gate rather
  than an advisory doc, with no double execution.
- Four self-covering registry entries (`REGISTRY-WELLFORMED`, `GATE-INFRASTRUCTURE`,
  `CONTRACT-BIJECTION`, `RELEASE-GATE-CI`); the gate guards its own contracts.
- `pyyaml` dev dependency; black/mypy clean under the tool versions pinned at authoring time.

### Fixed

- **Interval trigger mode was inoperative** — `trigger_config.trigger_interval`
  was never parsed into `AgentConfig.trigger_interval`, so an interval-mode
  agent defined via host config could never fire (hosts gate on
  `if interval and ...`). Now parsed and int-coerced; non-numeric or
  non-positive values are warned and treated as absent. Migration note:
  interval-mode configs that previously did nothing WILL start firing.
  Contract: `INTERVAL-CONFIG-PARSED`.
- **Unknown condition `mode` fails closed (C-4)** — an unrecognized mode string
  ("and", "or", "ALL") in `trigger_conditions` fell through to `return True`,
  silently un-gating the agent. It now warns and returns `False`, matching the
  unknown-operator behavior (C-1). Contract: `CONDITIONS-FAIL-CLOSED`.

### Tests / registry

- Contract registry certified to **24/24 covered, debt 0** (blackboard,
  engine/tracing, config-parsing, fail-closed evaluation, and bounded-cascade
  contracts all name passing, rule-asserting tests). Two previously-tested
  behaviors gained registry entries: `CONDITIONS-FAIL-CLOSED` and
  `CASCADE-SINGLE-HOP`. Packaging drift-locks added (`tests/test_packaging.py`).

### Packaging

- **Built wheels now include `library/schemas/*.json`** — the old package-data
  glob was non-recursive, so pip-installed copies shipped without the schemas
  and silently degraded every v2 output format to the emergency fallback
  schema. Explicit `"xubb_agents.library" = ["schemas/*.json"]` package-data
  plus a drift-lock test.
- Version bumped to **2.3.0** (new public API ⇒ minor bump). The `v2.2.0` tag
  is cut retroactively at the 2026-06-08 release commit.

---

## [2.2.0] - 2026-06-08

Production-hardening release driven by the v2.2 comprehensive audit: 1 critical contract bug,
4 high-severity gaps, 13 medium fixes, an additive memory-persistence fix (MR-1), plus
test-infra, hygiene, and a full documentation refresh. Suite 105 → 224, zero warnings.
See [SPEC_V2_2_HARDENING.md](docs/SPEC_V2_2_HARDENING.md).

### Bug Fixes

- **F-1** (CRITICAL): Fact conflict resolution now honors agent **priority** (INV-9).
  `Blackboard.add_fact` previously resolved `(type, key)` collisions by confidence only,
  silently inverting the documented "higher priority wins" rule (SPEC_V2 §6.5.4) — a
  high-priority extractor could be overruled by a lower-priority/higher-confidence agent.
  Added `Fact.priority` (engine-stamped); `add_fact` now resolves by
  `(priority, confidence)` with later registration breaking full ties.
  **Migration:** consumers relying on the buggy confidence-only behavior may see a
  different fact win — verify agent `priority` reflects intended extraction authority.
  Guarded permanently by `PROBE-F1` (`tests/qa_probes/`).
- **C-1**: condition evaluation now fails **closed** on an unknown/typo'd operator
  (was fail-open → fired every turn).
- **C-2**: `in`/`not_in` membership operators guard on `expected is None` instead of
  truthiness, so a legitimately-falsy expected (`0`, `""`) runs a real membership test.
- **C-3**: `mod` operator handles `expected == 0` locally (returns False, no
  `ZeroDivisionError` leak).
- **S-1**: `DynamicAgent` now parses `expiry`/`action_label` from LLM output and passes
  them through to `AgentInsight` (previously requested by schemas but silently dropped).
- **A-2** (INV-13): `Event`/`Fact` timestamps emitted by `DynamicAgent` are now
  session-relative (derived from the conversation window) instead of wall-clock epoch.
- **A-3**: model-supplied `confidence` is coerced to float and clamped to [0,1] before
  building the insight (a bad value no longer turns a good insight into an ERROR).
- **E-2**: `sys.*` keys are excluded when syncing blackboard variables to the v1
  `shared_state` (no longer trips the reserved-key warning on v1 round-trip).
- **E-3**: legacy `state_updates` `memory_` writes are applied even when
  `variable_updates` is also present (hybrid v1/v2 responses no longer drop them).
- **M-1** (INV-8'): `set_memory`/`update_memory` deep-copy on write, closing the
  write-side aliasing gap (memory is now copied in both directions).

- **R-1** (INV-10): the LLM call site (`core/llm.py`) is now resilient — explicit
  request timeout, bounded retries with backoff (429/5xx/timeout), `max_tokens` cap, and
  typed exception handling that logs a distinct failure category (timeout / rate_limit /
  auth / server / malformed) via `last_error_category`. The never-raise / return-`None`
  contract is preserved (callers unaffected).
- **A-1** (INV-11): gate-less + rootless schemas now default to **silence** (a schema must
  opt in via `speak_without_gate: true` to speak on content alone); a load-time warning
  fires when a schema's instruction references a gate field but the mapping omits
  `check_field`. Shipped schemas (all gated or root-keyed) are unaffected.
- **E-1** (INV-12): the Phase-2 execution block now restores `context.trigger_type` and
  `context.phase` via `try/finally`, so a Phase-2 exception can no longer leave the
  host-reused context corrupted as `EVENT`/`phase=2`.

- **MR-1** (INV-14, Amendment 1): cross-turn agent memory now survives even when the host
  re-instantiates agents per turn. Memory is stored on the blackboard but `DynamicAgent`
  reads it from `shared_state["memory_<id>"]`; `_sync_state_to_legacy` now populates those
  keys from `blackboard.memory` (deep-copied) before agents run. **Migration:** hosts that
  manually wrote `shared_state["memory_<id>"]` should write via `blackboard.update_memory`.
- **E-6**: misconfigured event-subscriber warning is now emitted once per agent, not every turn.
- **DBG-1**: `tools/debugger.html` now renders per-step `state_updates` as a dict (was a
  no-op `.length` guard) and displays the v2 trace fields (`variable_updates`,
  `events_emitted`, `facts_count`, `queue_pushes`, `memory_updates_keys`).

### Changed

- **S-2**: removed the dead `is_state_at_root` key from all schemas (never read by the parser).
- **S-3**: v2 schemas (`v2_raw`, `ui_control`, `widget_control`) route state through
  `variable_updates_field` for consistency with `default_v2`.
- **E-4**: `update_api_key` closes the previous LLM client's session and documents the
  no-concurrent-`process_turn` precondition.
- **E-7**: `max_phases` now only accepts `1` or `2`; other values are clamped with a warning.
- **G-1**: migrated the deprecated class-based Pydantic `Config` to `ConfigDict` on
  `Blackboard`/`AgentContext` — eliminates the `PydanticDeprecatedSince20` warnings (suite
  now runs with **zero warnings**).
- **G-2**: removed unused imports (`AgentInsight`/`InsightType` in `core/engine.py`); the
  tracked `__pycache__` bytecode is now untracked.
- **E-8**: documented that `check_keyword_triggers` uses case-insensitive substring matching.

### Performance

- **E-5**: `_merge_responses` resolves agent priority via an O(1) `_agent_meta` lookup
  instead of an O(agents × responses) linear scan; unresolvable agent ids log a warning.

### Tests & tooling

- **T-1**: first coverage for `DynamicAgent` (incl. spec-mandated auto-add-`EVENT` and
  prompt-no-leading-whitespace) and the tracer; resilience tests for `core/llm.py`.
- **T-2**: added `[tool.pytest.ini_options]` (`asyncio_mode`, registered markers, `pythonpath`)
  and a repo-root `conftest.py` so the suite is importable independent of the checkout
  directory name (previously the green suite depended on the dir being named `xubb_agents`).
- **T-3**: strengthened the atomic-discard test (INV-6) — a failed agent now attempts an
  observable write that must not persist (was tautological).
- **T-4**: cooldown tests use a frozen clock for deterministic elapsed time (no wall-clock flakiness).
- Suite 105 → **224**, zero warnings.

### Documentation

- **DOC-1**: documented OpenAI / OpenAI-compatible as the intended provider (Anthropic adapter
  out of scope); removed "Claude library" ambiguity.
- **DOC-2**: version → 2.2.0 across README, EXECUTIVE_SUMMARY, technical spec, prompt guide,
  `pyproject.toml`, `__init__.py`.
- **DOC-3**: withdrew the stale NP16 `_sync_state_from_legacy` reference in SPEC_V2_1_HARDENING.
- **DOC-4**: removed the stale `xubb_v6` install path from the README.
- **DOC-5**: replaced the aspirational tracer-schema example with the actual emitted shape.
- Full accuracy sweep of README + docs against the v2.2 code (Fact `priority`, MR-1/M-1
  memory, R-1 resilience, A-1 silence gate, condition fail-closed, session-relative timestamps).

---

## [2.1.1] - 2026-03-19

Bugfix release: 4 bug fixes, 3 defense-in-depth improvements, 1 test correction.

See [SPEC_V2_1_1_BUGFIX.md](docs/archive/SPEC_V2_1_1_BUGFIX.md) for full details.

### Bug Fixes

- **B1**: `get_event_subscribers()` now validates `TriggerType.EVENT` — agents with `subscribed_events` but missing `EVENT` trigger type are excluded with a warning
- **B2**: `_sync_state_to_legacy()` runs before Phase 2 — v1 agents in Phase 2 now see correct `shared_state`
- **B4**: Added `memory_updates_by_agent` field on `AgentResponse` — per-agent keyed memory available on aggregated responses (additive, `memory_updates` unchanged)
- **B5**: `process_turn` wrapped for `on_chain_error` — callback now fires on unhandled exceptions

### Improvements

- **D1**: Prompt whitespace elimination in `DynamicAgent` — no blank sections when optional context is absent
- **D2**: Class-level `SandboxedEnvironment` in `DynamicAgent` — single Jinja2 env instance instead of per-call allocation
- **D3**: v2 fields added to `StructuredLogTracer` — traces now include events, facts, queues, variables, memory

### Convenience

- `DynamicAgent` auto-adds `TriggerType.EVENT` when `subscribed_events` is set

### Test Fixes

- **T1**: Fixed false-positive subscriber test — subscriber agent now correctly uses `TriggerType.EVENT` with `cooldown=0`

---

## [2.1.0] - 2026-03-18

Hardening release: no new features, only bug fixes and production-grade improvements.

See [SPEC_V2_1_HARDENING.md](docs/archive/SPEC_V2_1_HARDENING.md) for full details.

### Security

- Jinja2 templates now render through `SandboxedEnvironment`, mitigating SSTI. The sandbox
  is defense-in-depth, not a guarantee: untrusted template *source* remains a trust boundary
  and its safety depends on the installed Jinja2 patch level (floored at `>=3.1.6`).

### Bug Fixes

- `source_agent_id` field on `AgentResponse` — reliable agent identity (no more insight-based inference)
- `get_memory()` returns deep copy — snapshot isolation enforced
- `to_dict()` returns deep copies — no mutable reference leaks
- Callbacks fire exactly once per agent (previously fired 2x due to engine + agent duplication)
- Cooldown enforced after errors — prevents runaway retries on persistent failures

### Additions

- `on_phase_start`, `on_phase_end`, `on_agent_skipped` callbacks added
- `AgentCallbackHandler` is no longer `ABC` — subclasses don't need to implement anything
- `sys.*` write protection on Blackboard — warns on non-engine writes to reserved keys

---

## [2.0.0] - 2026-01-27

Major release: structured Blackboard, event-driven agent coordination, multi-phase execution.

See [SPEC_V2.md](docs/archive/SPEC_V2.md) for full details.

### Added

- Structured Blackboard with 5 typed containers (Variables, Events, Queues, Facts, Memory)
- Event-driven pub/sub agent coordination
- Blackboard-aware trigger conditions with 14 operators
- Multi-phase execution (Phase 1: normal agents, Phase 2: event-triggered agents)
- `TriggerType.EVENT` for agent-to-agent coordination
- `DynamicAgent` with Jinja2 templating and pluggable output schemas
- `ConditionEvaluator` for trigger preconditions
- Priority-based merge ordering (ascending, last-write-wins)

### Removed

- Response caching (replaced by cooldowns + trigger conditions)

### Compatibility

- 100% backward compatible with v1.0 agents
- `shared_state` auto-mapped to `blackboard.variables`
- `state_updates` auto-mapped to `variable_updates`

---

## [1.0.0] - 2025

Initial release: parallel agent execution with flat shared state.

[Unreleased]: https://github.com/genriq/xubb-agents/compare/v2.7.0...HEAD
[2.7.0]: https://github.com/genriq/xubb-agents/compare/v2.6.0...v2.7.0
[2.6.0]: https://github.com/genriq/xubb-agents/compare/v2.5.0...v2.6.0
[2.5.0]: https://github.com/genriq/xubb-agents/compare/v2.4.0...v2.5.0
[2.4.0]: https://github.com/genriq/xubb-agents/compare/v2.3.0...v2.4.0
[2.3.0]: https://github.com/genriq/xubb-agents/compare/v2.2.0...v2.3.0
[2.2.0]: https://github.com/genriq/xubb-agents/releases/tag/v2.2.0
[2.1.1]: https://github.com/genriq/xubb-agents/blob/main/CHANGELOG.md
[2.1.0]: https://github.com/genriq/xubb-agents/blob/main/CHANGELOG.md
[2.0.0]: https://github.com/genriq/xubb-agents/blob/main/CHANGELOG.md
[1.0.0]: https://github.com/genriq/xubb-agents/blob/main/CHANGELOG.md
