# Long-form content

**Applies to runtime:** 3.1.5 · Part of the [design guide](../DESIGN_GUIDE.md) set.

Most insights are one or two sentences. Sometimes you want a paragraph, a draft, a summary —
and that is a different risk profile: longer generations cost more, take longer, and can fail
halfway. The content contract exists so that risk is negotiated up front rather than discovered
in production.

## It is negotiated, not requested

Three parties have to agree before a single token is generated:

- the **agent** declares a content block — which depths it offers and their budgets;
- the **host** declares which contracts and formats it can present, and its ceilings;
- the **operator** sets absolute limits on the engine (a required byte ceiling, live-lane caps).

Admission runs **before** any model call. A request that cannot be honoured costs nothing —
no tokens, no latency, no bill. That is the whole point of doing it this way rather than
truncating afterwards.

If any party is missing its half, the request is refused with a diagnostic rather than
silently downgraded: `content_contract_unavailable`, `invalid_content_policy`,
`unsupported_depth`, `content_extension_not_enabled`.

## Nothing is shortened and accepted

If the body exceeds the effective character ceiling, the result is **rejected**
(`content_too_large`). It is not trimmed to fit.

The same applies to the preview: a `preview` never salvages a rejected body
(`preview_too_large`), and it must be a faithful summary or excerpt of the same body — it may
not add a claim or hide a caveat.

If generation stops on length, that is `incomplete_generation`: the result is incomplete,
already billed, and never salvaged. If the provider reports no trustworthy completion status,
that is `completion_unknown` — fail-closed, because an unknown completion is not a good one.

This is deliberate and it will occasionally frustrate you. The alternative is a product that
silently shows half a paragraph as though it were whole.

## Two lanes

**Live turn.** The agent produces long-form output during the normal turn. Bounded hard by the
operator's live-lane caps, because a slow generation here delays the turn for everyone.

**Isolated task.** `AgentEngine.start_content_request` runs the generation *outside* the turn,
as an engine-owned task on a frozen snapshot:

```python
handle = engine.start_content_request(context, "summariser",
                                      InsightContentRequest(depth="detailed"))
result = await handle.result()          # returns only after the slot is released
```

The isolation is structural, not declarative. The task runs on a **fresh agent instance** with
no shared private state, against a frozen snapshot of the conversation; it cannot touch the live
blackboard, the turn counter or another agent's memory. It is **result-only**: it may not emit
events, facts, state or actions, and a request that tries is refused
(`content_execution_not_allowed`).

A host cannot declare itself into this lane. The isolated path is admitted only on a declaration
the **engine** issued for a task it owns — a boolean supplied by a caller will not do.

`handle.cancel()` revokes publication; closing the session revokes any outstanding tasks.
Concurrency is bounded by the operator's limit, so a burst of requests queues rather than
stampeding the provider.

## Reading the result

A negotiated insight carries fields that appear **only** on this path: `preview`,
`content_format`, `response_depth`, `content_request_id` and `source_snapshot_id`. On ordinary
insights they are absent — that is how you can tell the two apart without tracking the request
yourself.

`ContentResult.status` is the outcome; `diagnostics` says why when it is not accepted; `usage`
carries the token cost, which on this path is worth recording.

## When to reach for it

Use the isolated lane when the output is genuinely long and the user is waiting for *it*, not
for the conversation — a call summary, a drafted reply, a written recommendation.

Do not use it to make ordinary insights longer. A long insight in a live HUD is usually a
design error, not a capability gap: the scarce resource is still attention.

## Common mistakes

- **Expecting truncation.** Over-length output is rejected, not trimmed.
- **Declaring the isolated path from the host.** Only the engine can issue that declaration.
- **Emitting state from an isolated task.** It is result-only by construction.
- **Treating a preview as a teaser.** It must be faithful to the body it previews.
