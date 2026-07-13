"""
Tests for v2.6 VL-1 + EN-1 (SPEC_LLM_MODERN_MODELS).

VL-1 / INV-19: load-time cross-validation at registration — a model matching
the reasoning heuristic without an explicit reasoning_effort HARD-FAILS
registration (D-1 ruling; warns under strict_reasoning_config=False). The
heuristic table is payload-advisory: it never alters outbound kwargs.

EN-1 / INV-18: engine-level LLM configuration (timeout / retries / token cap /
base_url / wire knob) survives update_api_key — key rotation never resets the
client to module defaults.

Fixtures local to this file; no network (fake key, mocked/absent calls).
"""

import logging

import pytest

from xubb_agents import AgentEngine, AgentConfigurationError, BaseAgent, AgentConfig


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

class _NoopAgent(BaseAgent):
    async def evaluate(self, context):
        return None


def make_agent(agent_id="a1", model="gpt-4o-mini", **cfg):
    return _NoopAgent(AgentConfig(name=agent_id, id=agent_id, model=model, **cfg))


@pytest.fixture
def engine():
    return AgentEngine(api_key="test_key")


# --------------------------------------------------------------------------- #
# VL-1 rule 1 — reasoning-heuristic model without effort (D-1 hard-fail)
# --------------------------------------------------------------------------- #

class TestRule1HardFail:
    def test_reasoning_model_without_effort_hard_fails(self, engine):
        agent = make_agent(model="gpt-5.6-luna")
        with pytest.raises(AgentConfigurationError) as exc:
            engine.register_agent(agent)
        # Copy-pasteable fix in the message.
        assert "reasoning_effort" in str(exc.value)

    def test_hard_fail_leaves_registry_and_agent_untouched(self, engine):
        """Validate-before-mutate: no registry entry, no llm injection."""
        agent = make_agent(model="gpt-5.6-luna")
        with pytest.raises(AgentConfigurationError):
            engine.register_agent(agent)
        assert engine.agents == []
        assert agent.llm is None

    def test_reasoning_model_with_effort_registers(self, engine):
        agent = make_agent(model="gpt-5.6-luna", reasoning_effort="none")
        engine.register_agent(agent)
        assert engine.agents == [agent]

    def test_strict_false_downgrades_to_warning(self, caplog):
        engine = AgentEngine(api_key="test_key", strict_reasoning_config=False)
        agent = make_agent(model="gpt-5.6-luna")
        with caplog.at_level(logging.WARNING, logger="AgentEngine"):
            engine.register_agent(agent)
        assert engine.agents == [agent]
        assert "reasoning_effort" in caplog.text

    def test_non_reasoning_model_registers_silently(self, engine, caplog):
        with caplog.at_level(logging.WARNING, logger="AgentEngine"):
            engine.register_agent(make_agent(model="gpt-4o-mini"))
        assert len(engine.agents) == 1
        assert caplog.text == ""

    @pytest.mark.parametrize("model", [
        "gpt-5-chat-latest",   # chat-tuned: rejects reasoning_effort
        "gpt-5-search-api",    # search variant
        "o1-mini",             # exact-name denylist
        "gpt-5.4-pro",         # pro tier (restricted efforts, Responses-only)
    ])
    def test_deny_shapes_do_not_hard_fail(self, engine, model):
        """Heuristic exclusions: these match the raw prefix but are known to
        reject/restrict the parameter — rule 1 must not fire."""
        engine.register_agent(make_agent(agent_id=f"a-{model}", model=model))


# --------------------------------------------------------------------------- #
# VL-1 rules 2–4 — warnings
# --------------------------------------------------------------------------- #

class TestWarnRules:
    def test_rule2_effort_on_non_reasoning_shape_warns(self, engine, caplog):
        agent = make_agent(model="gpt-5-chat-latest", reasoning_effort="low")
        with caplog.at_level(logging.WARNING, logger="AgentEngine"):
            engine.register_agent(agent)
        assert "reasoning-capable" in caplog.text or "reject" in caplog.text

    def test_rule3_deep_effort_with_default_budgets_warns(self, engine, caplog):
        agent = make_agent(model="gpt-5.6-terra", reasoning_effort="high")
        with caplog.at_level(logging.WARNING, logger="AgentEngine"):
            engine.register_agent(agent)
        assert "starve" in caplog.text or "time out" in caplog.text

    def test_rule3_low_efforts_do_not_warn(self, engine, caplog):
        for i, effort in enumerate(("none", "minimal", "low")):
            agent = make_agent(agent_id=f"low-{i}", model="gpt-5.6-luna",
                               reasoning_effort=effort)
            with caplog.at_level(logging.WARNING, logger="AgentEngine"):
                engine.register_agent(agent)
        assert "starve" not in caplog.text and "time out" not in caplog.text

    def test_rule3_satisfied_budgets_do_not_warn(self, engine, caplog):
        agent = make_agent(model="gpt-5.6-terra", reasoning_effort="high",
                           timeout=30.0, max_tokens=25000)
        with caplog.at_level(logging.WARNING, logger="AgentEngine"):
            engine.register_agent(agent)
        assert "starve" not in caplog.text and "time out" not in caplog.text

    def test_rule4_temperature_on_reasoning_model_warns(self, engine, caplog):
        agent = make_agent(model="gpt-5.6-luna", reasoning_effort="none",
                           model_params={"temperature": 0})
        with caplog.at_level(logging.WARNING, logger="AgentEngine"):
            engine.register_agent(agent)
        assert "temperature" in caplog.text

    def test_warn_once_across_vault_reloads(self, caplog):
        """A vault reload re-registering the same misconfigured id must not
        re-warn every few minutes (E-6 discipline)."""
        engine = AgentEngine(api_key="test_key", strict_reasoning_config=False)
        with caplog.at_level(logging.WARNING, logger="AgentEngine"):
            engine.replace_agents([make_agent(agent_id="same", model="gpt-5.6-luna")])
            first = caplog.text.count("looks reasoning-capable")
            engine.replace_agents([make_agent(agent_id="same", model="gpt-5.6-luna")])
            second = caplog.text.count("looks reasoning-capable")
        assert first == 1 and second == 1


# --------------------------------------------------------------------------- #
# VL-1 rule 5 — model_params collisions for custom agents (registration path)
# --------------------------------------------------------------------------- #

class TestRule5Collisions:
    def test_custom_agent_collision_rejected_at_registration(self, engine):
        agent = make_agent(model="gpt-4o-mini",
                           model_params={"max_completion_tokens": 9})
        with pytest.raises(AgentConfigurationError) as exc:
            engine.register_agent(agent)
        assert "framework-owned" in str(exc.value)


# --------------------------------------------------------------------------- #
# VL-1 — replace_agents is all-or-nothing
# --------------------------------------------------------------------------- #

class TestReplaceAllOrNothing:
    def test_one_bad_config_rejects_whole_reload_old_registry_serves(self, engine):
        old = make_agent(agent_id="old", model="gpt-4o-mini")
        engine.register_agent(old)

        good = make_agent(agent_id="good", model="gpt-5.6-luna", reasoning_effort="none")
        bad = make_agent(agent_id="bad", model="gpt-5.6-sol")  # no effort

        with pytest.raises(AgentConfigurationError) as exc:
            engine.replace_agents([good, bad])

        # Old registry still fully live; incoming agents untouched.
        assert engine.agents == [old]
        assert good.llm is None and bad.llm is None
        assert "bad" in str(exc.value)

    def test_all_violations_reported_together(self, engine):
        bad1 = make_agent(agent_id="bad1", model="gpt-5.6-sol")
        bad2 = make_agent(agent_id="bad2", model="o3")
        with pytest.raises(AgentConfigurationError) as exc:
            engine.replace_agents([bad1, bad2])
        msg = str(exc.value)
        assert "bad1" in msg and "bad2" in msg


# --------------------------------------------------------------------------- #
# VL-1 — the heuristic is payload-advisory (INV-15)
# --------------------------------------------------------------------------- #

class TestPayloadAdvisory:
    @pytest.mark.asyncio
    async def test_registration_never_mutates_config_or_payload(self, engine):
        """The table drives load-time signals ONLY: after registering a
        heuristic-matching agent, its config is exactly what the operator
        wrote — nothing injected for the wire to pick up."""
        agent = make_agent(model="gpt-5.6-luna", reasoning_effort="low")
        before = (agent.config.model, agent.config.reasoning_effort,
                  agent.config.timeout, agent.config.max_tokens,
                  dict(agent.config.model_params))
        engine.register_agent(agent)
        after = (agent.config.model, agent.config.reasoning_effort,
                 agent.config.timeout, agent.config.max_tokens,
                 dict(agent.config.model_params))
        assert before == after

    def test_emptied_table_changes_no_payload_surface(self, monkeypatch, engine):
        """With the heuristic emptied, the same agent registers with zero
        signals — proving the table's only effect is validation messaging."""
        import xubb_agents.core.engine as engine_mod
        monkeypatch.setattr(engine_mod, "REASONING_MODEL_PREFIXES", ())
        agent = make_agent(model="gpt-5.6-sol")  # would hard-fail with table on
        engine.register_agent(agent)
        assert engine.agents == [agent]
        assert agent.config.reasoning_effort is None  # still nothing injected


# --------------------------------------------------------------------------- #
# EN-1 — engine LLM knobs + rotation persistence (INV-18)
# --------------------------------------------------------------------------- #

class TestEN1EngineKnobs:
    KNOBS = dict(llm_timeout=4.0, llm_max_retries=5, llm_max_tokens=512,
                 llm_base_url="http://proxy.local:8080/v1",
                 llm_wire_max_tokens_param="max_tokens")

    def _assert_client_carries(self, client):
        assert client.timeout == 4.0
        assert client.max_retries == 5
        assert client.max_tokens == 512
        assert client.base_url == "http://proxy.local:8080/v1"
        assert client.wire_max_tokens_param == "max_tokens"

    def test_ctor_knobs_reach_llm_client(self):
        engine = AgentEngine(api_key="test_key", **self.KNOBS)
        self._assert_client_carries(engine.llm_client)

    def test_rotation_persists_engine_llm_config(self):
        """INV-18 repro (fails on baseline: rotation rebuilt with module
        defaults, silently resetting base_url/timeouts mid-session)."""
        engine = AgentEngine(api_key="test_key", **self.KNOBS)
        engine.update_api_key("rotated_key")
        self._assert_client_carries(engine.llm_client)

    def test_default_engine_keeps_client_defaults(self):
        engine = AgentEngine(api_key="test_key")
        assert engine.llm_client.timeout == 10.0
        assert engine.llm_client.max_retries == 2
        assert engine.llm_client.max_tokens == 1024
        assert engine.llm_client.wire_max_tokens_param == "max_completion_tokens"
        assert engine._llm_config == {}

    def test_rotation_reinjects_into_agents(self):
        engine = AgentEngine(api_key="test_key", **self.KNOBS)
        agent = make_agent(model="gpt-4o-mini")
        engine.register_agent(agent)
        engine.update_api_key("rotated_key")
        assert agent.llm is engine.llm_client
        self._assert_client_carries(agent.llm)
