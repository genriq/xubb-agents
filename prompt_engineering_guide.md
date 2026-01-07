# Xubb Agent Prompt Engineering Guide (v2.1)

> **"Silence is Golden. Insight is Diamond."**

Writing prompts for real-time Xubb Agents is fundamentally different from writing for chatbots. Your agent is not a conversation partner; it is a **whisper in the ear**. It must be fast, precise, and invisible until it is absolutely necessary.

This guide defines the best practices for creating high-performance agents for the Xubb HUD v2.1.

---

## 1. The Core Philosophy

### The "95% Silence" Rule
A Xubb Agent watches a live conversation. If it interrupts every 10 seconds, the user will turn it off.
*   **Bad Agent:** Comments on everything. ("Good greeting!", "Nice question!", "You are listening well.")
*   **Good Agent:** Only speaks when the user *needs* help. ("Missed objection: Price.", "Opportunity: Upsell now.")

**Technique:** Explicitly instruct the LLM to default to silence.
> "If the user is handling the situation well, or if the transcript is ambiguous, return `{ "has_insight": false }`. Do not chat. Do not praise unless exceptional."

### Short > Smart
The user is cognitive loaded (talking to a human). They cannot read a paragraph.
*   **Zone A (Flash):** Max 3-5 words. ("Stop! Compliance Risk.")
*   **Zone C (Stream):** Max 1 sentence. ("Ask about their timeline.")

---

## 2. Targeting the HUD Zones

You must decide *where* your insight belongs before you write the prompt.

### Zone A: The "Flash" (High Urgency)
*   **Use Case:** Critical warnings or massive opportunities. Immediate action required.
*   **Insight Type:** `warning` (Red), `opportunity` (Green).
*   **Prompt Instruction:** "Output a WARNING only if the user is about to make a fatal mistake. Output an OPPORTUNITY only if the client explicitly signals a buying intent."

### Zone B: The "Blackboard" (Persistent State)
*   **Use Case:** Facts that should remain visible (Budget, Timeline, Risk Level).
*   **Insight Type:** N/A (Uses `state_snapshot`).
*   **Prompt Instruction:** "Extract key facts. If the client mentions a budget, update the 'budget' field in state_snapshot. Do not output an insight text for this."

### Zone C: The "Stream" (Passive Guidance)
*   **Use Case:** Coaching tips, suggestions, relevant facts.
*   **Insight Type:** `suggestion`, `fact`.
*   **Prompt Instruction:** "If you see a way to improve the user's argument, provide a SUGGESTION. Be polite but direct."

---

## 3. The "Raw Mode" Template

To unlock full control over the HUD, use `output_format: "v2_raw"`. Use this skeleton for your system prompts:

```text
You are a [ROLE, e.g., Compliance Monitor] supporting [USER].

GOAL: Protect the user from [SPECIFIC RISK].

INPUT DATA:
- You will receive a transcript of the last ~6 turns.
- You have access to shared memory.

OUTPUT FORMAT (JSON ONLY):
You must output a JSON object with this exact structure:
{
  "insight": {
    "type": "warning" | "opportunity" | "suggestion",
    "content": "Max 5 words for warnings, 1 sentence for suggestions.",
    "confidence": 0.0 to 1.0,
    "metadata": { "zone": "A" } // Optional hints
  },
  "state_snapshot": {
    "risk_level": "low" | "medium" | "high" // Updates for Zone B
  }
}

RULES:
1. If no risk is detected, return null or empty insight.
2. WARNINGS must be reserved for [LIST CRITICAL ERRORS].
3. Do not hallucinate risks.
```

---

## 4. Advanced Techniques

### Cognitive Anchoring
The framework injects a `user_context` string. Use it to ground your agent.
> "You are supporting {{user_context}}. Adapt your advice to their expertise level."

### State-Awareness (Memory & Jinja2)
Agents have short-term memory (RAM) and long-term memory (Blackboard).

*   **Accessing State (New in v2.1):** Use Jinja2 syntax to read state directly in your prompt.
    > "Current Phase: {{ state.phase }}. If phase is 'Closing', be aggressive."
*   **Counting:** "Track how many times the client said 'No'. If > 3, trigger a Warning."
    *   *Implementation:* Read `private_state['no_count']`, increment, and return in `memory_updates`.

### Widget Control (The "Hands")
To control UI widgets, use `output_format: "widget_control"`. The Backend injects the specific widget schema, but you should structure your prompt to output actions.

> "If the user agrees to the date, output: { 'ui_actions': [{ 'target_widget': 'calendar', 'action': 'update', 'payload': { 'date': '...' } }] }"

### Latency Optimization (Chain of Thought)
For complex logic, asking the LLM to "think" before answering improves accuracy but adds latency.
*   **Fast (Direct):** "Return JSON immediately." -> ~400ms.
*   **Smart (CoT):** "Think about the objection type, then return JSON." -> ~1.2s.

**Recommendation:** Use Direct prompts for Zone A (Flash). Use CoT for Zone C (Stream) where 1s delay is acceptable.

---

## 5. Checklist: Is Your Agent Ready?

1.  [ ] **The Silence Test:** Run it on a normal conversation. Does it stay quiet?
2.  [ ] **The Zone Test:** Does it use `warning` for urgencies and `suggestion` for tips?
3.  [ ] **The Blink Test:** Can you read the Zone A output in 0.5 seconds? (If it's > 5 words, it fails).
4.  [ ] **The JSON Test:** Does it reliably output valid JSON in `v2_raw` mode?

---

## 6. Example: The "Sales Sniper" (Zone A Agent)

**Configuration:**
```json
{
  "id": "sales_sniper",
  "output_format": "v2_raw",
  "trigger_config": { "mode": "keyword", "keywords": ["price", "cost"] }
}
```

**System Prompt:**
```text
You are the Sales Sniper. You watch for BUYING SIGNALS.

TRIGGER: You were woken up by a price discussion.

INSTRUCTIONS:
1. Analyze the client's tone. 
2. If they are complaining about price, do nothing (Sales Coach handles that).
3. If they ask "How much for X?", this is a Buying Signal.

OUTPUT:
{
  "insight": {
    "type": "opportunity",
    "content": "BUYING SIGNAL DETECTED",
    "metadata": { "color": "green", "flash": true }
  }
}
```
