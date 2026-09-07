"""Clean-wheel smoke: exercise the INSTALLED xubb-agents package from outside the
source checkout (no PYTHONPATH, no editable install, cwd ≠ repository).

Run by the CI job ``wheel-smoke`` after ``pip wheel`` + a fresh venv install, and
by tests/test_wheel_smoke_script.py against the current environment (which only
proves the script itself; the clean-wheel evidence is the CI job). Exits non-zero
on any deviation. No model provider is called: an in-process fake stands in for
the transport, so this is distribution evidence, not provider acceptance.
"""
import asyncio
import json
import os
import sys


def main() -> int:
    import xubb_agents
    from xubb_agents import AgentEngine, AgentContext, Blackboard, DynamicAgent, HostInsightCapabilities
    from xubb_agents.core.agent import AgentConfig, BaseAgent
    from xubb_agents.core.llm import LLMResult
    from xubb_agents.core.models import (
        AgentResponse, InsightType, InsightConfig, TranscriptSegment, TriggerType, InsightContentRequest,
        ContentExecutionContext, ContentResult,
    )

    # 1. the import must resolve to site-packages, never to a source tree
    #    (--allow-source only for the in-repo script test against an editable install)
    location = os.path.abspath(os.path.dirname(xubb_agents.__file__))
    if "site-packages" not in location.replace("\\", "/") and "--allow-source" not in sys.argv[1:]:
        print(f"FAIL: xubb_agents imported from {location}, not an installed distribution")
        return 2

    class Fake:
        def __init__(self, body):
            self.body, self.calls = body, []

        async def generate(self, model=None, messages=None, **kw):
            self.calls.append(kw)
            return LLMResult(parsed=self.body, finish_reason="stop", transport="json_object",
                             raw_bytes=len(json.dumps(self.body).encode()), usage={"prompt_tokens": 1, "completion_tokens": 2})

    # 2. packaged schemas + contract artifacts load from the wheel
    dyn = DynamicAgent({"id": "d", "name": "d", "text": "t", "output_format": "insight_v1", "trigger_config": {"cooldown": 0},
                        "insight_config": {"allowed_types": ["warning", "suggestion"], "content": {
                            "contract": "long_form_v1", "default_depth": "brief", "formats": ["plain_text", "markdown"],
                            "max_preview_chars": 280,
                            "profiles": {"brief": {"max_content_chars": 1200, "max_output_tokens": 1000, "llm_timeout_seconds": 10},
                                         "standard": {"max_content_chars": 8000, "max_output_tokens": 3500, "llm_timeout_seconds": 20},
                                         "detailed": {"max_content_chars": 40000, "max_output_tokens": 16000, "llm_timeout_seconds": 60}}}}})
    dyn.llm = Fake({"has_insight": True, "insight": {"type": "warning", "content": "Budget risk ahead.", "confidence": 0.7, "urgency": "now"}})

    class Custom(BaseAgent):
        def __init__(self):
            super().__init__(AgentConfig(name="custom", cooldown=0, trigger_types=[TriggerType.TURN_BASED],
                                         insight_config=InsightConfig(allowed_types=["question"], allow_question=True)))

        async def evaluate(self, context):
            return AgentResponse(insights=[self.create_insight("Who approves?", type=InsightType.QUESTION)],
                                 variable_updates={"leak": 1})

    engine = AgentEngine(api_key="not-a-real-key", insight_contract="typed_v1", structured_outputs="json_object",
                         content_limits={"max_response_bytes": 262144, "live_max_output_tokens": 1000,
                                         "live_max_timeout_seconds": 10, "max_concurrent_content_tasks": 1})
    fake = dyn.llm
    engine.register_agent(dyn)      # injects the real client; restore the fake
    dyn.llm = fake
    engine.register_agent(Custom())
    caps = HostInsightCapabilities(supported_types=["warning", "suggestion", "question"], text_questions=True,
                                   content_contracts=["long_form_v1"], content_formats=["plain_text", "markdown"],
                                   expanded_reading=True, max_content_chars=40000, max_preview_chars=280)
    ctx = AgentContext(session_id="s", turn_count=1, blackboard=Blackboard(), principal_id="p", insight_capabilities=caps,
                       recent_segments=[TranscriptSegment(speaker="CLIENT", text="Can we keep the date?", timestamp=1.0)],
                       content_execution_context=ContentExecutionContext(session_mode="active", execution_path="live_turn"))

    # 3. live turn: typed acceptance, engine-minted identity, custom-agent rejection at the boundary
    final = asyncio.run(engine.process_turn(ctx))
    types = [i.type for i in final.insights]
    if types != [InsightType.WARNING] or not final.insights[0].id or final.insights[0].contract_version != "typed_v1":
        print(f"FAIL: live turn produced {types}")
        return 3
    if final.acceptance_by_agent.get("custom") != "rejected" or ctx.blackboard.get_var("leak") is not None:
        print("FAIL: custom-agent boundary did not hold")
        return 4

    # 4. isolated content task: admission, fresh instance, result-only
    long_body = " ".join(["scope"] * 3000)
    dyn.llm = Fake({"has_insight": True, "insight": {"type": "suggestion", "content": long_body, "confidence": 0.8,
                                                    "urgency": "soon", "preview": "Short.", "content_format": "markdown"}})

    async def content():
        return await engine.start_content_request(ctx, "d", InsightContentRequest(depth="detailed", request_id="r1")).result()
    result = asyncio.run(content())
    if not isinstance(result, ContentResult) or result.status != "accepted" or result.insight.content != long_body \
            or result.insight.content_request_id != "r1":
        print(f"FAIL: content task {result.status} {[d.code for d in result.diagnostics]}")
        return 5
    if ctx.blackboard.get_var("sys.turn_count") != 1:
        print("FAIL: content task touched the live board")
        return 6
    print(f"wheel smoke OK — xubb_agents {getattr(xubb_agents, '__version__', '?')} from {location}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
