# Host conformance kit — 1.2.0

## Scope

This kit tests a named host adapter; it does not automatically certify Xubb or another host. Parent requirements and unique leaf scopes are in CONTRACT_OWNERSHIP.json. An actual run needs a host name, version, immutable build digest, and an adapter driving that build.

`host_conformance_kit.py` declares the adapter interface and eight deterministic cases. `sample_host_adapter.py` is an inert, in-memory self-test, not the desktop UI. No actual adopting host is exercised by the packaged report. The negative self-test exports only a preview; the runner must detect the loss of the full body.

## Run

```bash
python host_conformance_kit.py --adapter your_host_adapter:create_adapter --output host-results.json
```

For the reference self-test only:

```bash
python host_conformance_kit.py --adapter sample_host_adapter:create_adapter --output synthetic-host-results.json
```

The adapter implements identity/reset/command/inspect/metrics/export/answers. Commands must drive the real host. Inspection must observe actual stored body, UI state and instrumented generation/network/action events. Returning expected fixture values without operating the host is not conformance evidence.

## Cases and required evidence

| Case | Operation | Required observation |
|---|---|---|
| HC-01 draft | Ingest a reply without sending it | Draft distinction visible; no external send/narration action |
| HC-02 correction | Apply a replacement of a prior insight | Original body retained historically; target superseded; replacement linked |
| HC-03 input | Submit the same correlated answer twice | One logical answer; same principal/question; conflicting ID rejected in extended cases |
| HC-04 reading | Open, scroll, focus, expire notification | Full body and current reading state remain; highlight may expire |
| HC-05 preservation | Open and export a previewed response | Canonical body unchanged; one logical insight |
| HC-06 rendering | Render active-content-like text and remote-image syntax | Inert/sanitized output; no execution or implicit resource request |
| HC-07 expand | Open an already accepted body twice | Generation counter unchanged |
| HC-08 confidence | Display a numeric placeholder with provided=false | No numeric model-confidence estimate shown |

## Required extended/manual procedure

Record browser/desktop platform and accessibility mode. Retain logs, screenshots or accessibility-tree captures tied to case/build identifiers. Observe actual focus/scroll while live updates arrive; test keyboard navigation and screen-reader access. Test correction withdrawal as well as replacement. Test answer dismissal, closed question, wrong principal, cross-session target, replayed event IDs and conflicting payloads. A dismissal must not be treated as consent.

Exercise Markdown through the actual renderer with escaping, links, HTML, fenced code and remote-resource attempts; a stub counter proves nothing about a real renderer. Verify preview fidelity with a reviewer: it must retain material caveats and not turn a hypothesis into a fact. Test security/retention deletion with an explicit unavailable state, not silent body replacement.

For isolated detail generation, use an installed Xubb build and real host task instrumentation: induce a slow content request, process live turns concurrently, cancel the content request, and confirm no live lock retention, state writes, trace contamination or post-close publication. Confirm provider-concurrency admission preserves the declared live allocation. This is end-to-end testing, not a headless host self-test.

## Reporting

The runner records observed adapter assertions and identity, with runtime_or_host_certified=false. Attach the extended procedure evidence and owner sign-off to make a release claim. A synthetic adapter passing is evidence about the kit interface only. Framework registry entries cannot claim a adopting host's behavior from that run.
