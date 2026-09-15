# The Playbook has moved

The Playbook was written against a v2.2 code analysis and had grown to 355 KB. Its doctrine was
good and its recipes had aged; a single superseded banner on a document that long does not stop
a reader landing halfway down and following an instruction that no longer works.

So it is split rather than patched, on the 2026-09-15 design review's direction:

| What you wanted from it | Now |
|---|---|
| The design doctrine — restraint, specialized observers, ownership | [**DESIGN_GUIDE.md**](DESIGN_GUIDE.md) |
| How to write an agent | [guides/authoring-agents.md](guides/authoring-agents.md) |
| Coordinating several agents | [guides/orchestration.md](guides/orchestration.md) |
| Wiring it into a host | [guides/host-integration.md](guides/host-integration.md) |
| Long-form generation | [guides/long-form-content.md](guides/long-form-content.md) |
| A class, method or field | [API_REFERENCE.md](API_REFERENCE.md) |
| A diagnostic code | [DIAGNOSTICS.md](DIAGNOSTICS.md) |

Every runnable example in those guides is executed in CI, so a recipe labelled current is one
that ran.

## The original

Preserved unchanged at [**archive/PLAYBOOK_v2.2.md**](archive/PLAYBOOK_v2.2.md). It remains a
useful record of the thinking, and its worked examples are still instructive if you read them as
history. It is **not** current instruction: it predates the single insight contract (3.0.0), the
output-format consolidation (3.1.0) and everything after.

This stub exists so links to `docs/PLAYBOOK.md` keep working. It will not be removed without a
deprecation note in the changelog.
