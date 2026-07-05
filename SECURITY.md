# Security Policy

## Reporting a vulnerability

Please report suspected vulnerabilities **privately** — do not open a public issue.

Use GitHub's **[Report a vulnerability](https://github.com/genriq/xubb-agents/security/advisories/new)**
(the repository's Security tab → "Report a vulnerability"). You will receive an
acknowledgment within a few business days, and a fix or mitigation plan once the report
is triaged.

## Supported versions

| Version | Supported |
|---------|-----------|
| 2.4.x   | ✅ |
| < 2.4   | ❌ |

## Security model and trust boundaries

xubb-agents is a **library embedded in a host application**. It has no network surface
of its own — no server, no telemetry, no phone-home; the only egress is the OpenAI
client the host configures. Its security therefore depends on how the host feeds it
data. Two boundaries matter.

### 1. Prompt template *data* is untrusted; template *source* is a trust boundary

Agent prompts render through Jinja2's `SandboxedEnvironment`. Interpolated **data**
(transcripts, blackboard values) is safe to pass as render context. The template
**source** — the prompt text itself — is a trust boundary: a malicious template is
contained only by the Jinja2 sandbox, and the sandbox is only as strong as the installed
patch level. This project floors Jinja2 at `>=3.1.6`; older versions have published
sandbox escapes.

**If your host lets untrusted parties author prompt template source, treat that as a
code-execution boundary** — vet the authors, or restrict/disable Jinja rendering for
untrusted templates.

### 2. Agent output is untrusted

Agents run over **untrusted transcript input**, and their output (insight content and
metadata, event payloads, facts, variable updates) is LLM-generated from that input.
The framework passes this through to the host verbatim; it does **not** sanitize it.

**Hosts must treat all agent output as untrusted** and escape or sanitize it before
rendering into any UI. (The bundled `tools/debugger.html` is a developer tool; it
HTML-escapes agent metadata for exactly this reason.)

## What the framework guarantees

- The OpenAI API key is never logged, never placed in exception messages, and never
  written to traces or `debug_info`.
- No telemetry, analytics, or network egress beyond the host-configured OpenAI client.
- Every LLM call is time-bounded and never raises into a turn.
