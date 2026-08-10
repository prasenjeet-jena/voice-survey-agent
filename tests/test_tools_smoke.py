"""
Smoke test for app.survey.tools — verifies all 7 tool handlers, SurveyState,
validation, and JSON serialization round-trip.

Run: python tests/test_tools_smoke.py
"""

import asyncio
import json
import sys
from dataclasses import dataclass
from typing import Any
from collections.abc import Mapping

# ---------------------------------------------------------------------------
# Minimal mock of FunctionCallParams (avoids importing the full Pipecat stack
# just for a smoke test)
# ---------------------------------------------------------------------------

@dataclass
class MockFunctionCallParams:
    """Mimics pipecat.services.llm_service.FunctionCallParams for testing."""
    function_name: str = ""
    tool_call_id: str = "test-001"
    arguments: Mapping[str, Any] = None
    llm: Any = None
    pipeline_worker: Any = None
    context: Any = None
    result_callback: Any = None
    app_resources: Any = None

    def __post_init__(self):
        if self.arguments is None:
            self.arguments = {}


class ResultCapture:
    """Captures the result_callback invocation."""
    def __init__(self):
        self.result = None

    async def __call__(self, result):
        self.result = result


# ---------------------------------------------------------------------------
# Import the module under test
# ---------------------------------------------------------------------------

sys.path.insert(0, ".")
from app.survey.tools import (
    build_survey_tools,
    load_survey,
    validate_answer,
    SurveyState,
    Question,
    record_answer,
    skip_question,
    defer_question,
    note_clarification,
    flag_offtopic,
    end_survey,
    resume_survey,
)


def make_params(state: SurveyState) -> tuple[MockFunctionCallParams, ResultCapture]:
    """Create a mock FunctionCallParams with the given state."""
    capture = ResultCapture()
    params = MockFunctionCallParams(
        app_resources={"survey_state": state},
        result_callback=capture,
    )
    return params, capture


async def run_tests():
    print("=" * 60)
    print("SMOKE TEST: app.survey.tools")
    print("=" * 60)
    passed = 0
    failed = 0

    def check(name, condition, detail=""):
        nonlocal passed, failed
        if condition:
            print(f"  ✅ {name}")
            passed += 1
        else:
            print(f"  ❌ {name} — {detail}")
            failed += 1

    # ------------------------------------------------------------------
    # 1. load_survey
    # ------------------------------------------------------------------
    print("\n--- load_survey ---")
    questions = load_survey("survey.json")
    check("loads 20 questions", len(questions) == 20, f"got {len(questions)}")
    check("q1 is multi_choice", questions[0].type == "multi_choice")
    check("q1 is required", questions[0].required is True)
    check("q4 is open", questions[3].type == "open")
    check("q4 is optional", questions[3].required is False)

    # ------------------------------------------------------------------
    # 2. build_survey_tools
    # ------------------------------------------------------------------
    print("\n--- build_survey_tools ---")
    tools_schema, state = build_survey_tools(questions)
    check("returns ToolsSchema", type(tools_schema).__name__ == "ToolsSchema")
    check("returns SurveyState", isinstance(state, SurveyState))
    check("7 standard tools", len(tools_schema.standard_tools) == 7,
          f"got {len(tools_schema.standard_tools)}")
    tool_names = [t.name for t in tools_schema.standard_tools]
    expected_names = [
        "record_answer", "skip_question", "defer_question",
        "note_clarification", "flag_offtopic", "end_survey", "resume_survey",
    ]
    check("correct tool names", tool_names == expected_names, f"got {tool_names}")
    check("state.started_at is set", state.started_at is not None)
    check("state.is_active is True", state.is_active is True)

    # Inspect generated schemas
    for tool in tools_schema.standard_tools:
        schema = tool.to_default_dict()
        check(f"  {tool.name} has description", bool(schema.get("description")),
              f"schema={schema}")

    # ------------------------------------------------------------------
    # 3. validate_answer
    # ------------------------------------------------------------------
    print("\n--- validate_answer ---")
    q_single = questions[1]  # q2, single_choice
    ok, msg, val = validate_answer(q_single, "Weekly or more")
    check("single_choice exact match", ok and val == "Weekly or more")

    ok, msg, val = validate_answer(q_single, "weekly or more")
    check("single_choice case-insensitive", ok and val == "Weekly or more")

    ok, msg, val = validate_answer(q_single, "nonsense answer")
    check("single_choice rejects invalid", not ok)

    q_multi = questions[0]  # q1, multi_choice
    ok, msg, val = validate_answer(q_multi, "Chocolate, Soft drinks")
    check("multi_choice comma-separated", ok and isinstance(val, list) and len(val) == 2,
          f"val={val}")

    ok, msg, val = validate_answer(q_multi, '["Juices", "Tea or coffee"]')
    check("multi_choice JSON array", ok and isinstance(val, list) and len(val) == 2,
          f"val={val}")

    ok, msg, val = validate_answer(q_multi, "bogus item")
    check("multi_choice rejects invalid", not ok)

    q_open = questions[3]  # q4, open
    ok, msg, val = validate_answer(q_open, "Lindt and Ghirardelli")
    check("open accepts text", ok and val == "Lindt and Ghirardelli")

    ok, msg, val = validate_answer(q_open, "   ")
    check("open rejects blank", not ok)

    # ------------------------------------------------------------------
    # 4. record_answer
    # ------------------------------------------------------------------
    print("\n--- record_answer ---")
    params, capture = make_params(state)
    await record_answer(params, question_id="q1", value="Chocolate, Soft drinks")
    check("recorded q1", capture.result["status"] == "recorded")
    check("q1 in state.answers", "q1" in state.answers)
    check("next_question_id is q2", capture.result["next_question_id"] == "q2")

    # Invalid answer
    params, capture = make_params(state)
    await record_answer(params, question_id="q2", value="every day")
    check("invalid q2 fails validation", capture.result["status"] == "validation_failed")
    check("q2 NOT in answers yet", "q2" not in state.answers)

    # Valid answer for q2
    params, capture = make_params(state)
    await record_answer(params, question_id="q2", value="Rarely")
    check("recorded q2", capture.result["status"] == "recorded")

    # ------------------------------------------------------------------
    # 5. skip_question
    # ------------------------------------------------------------------
    print("\n--- skip_question ---")
    params, capture = make_params(state)
    await skip_question(params, question_id="q4")
    check("skipped q4", capture.result["status"] == "skipped")
    check("q4 in state.skipped", "q4" in state.skipped)

    # ------------------------------------------------------------------
    # 6. defer_question
    # ------------------------------------------------------------------
    print("\n--- defer_question ---")
    params, capture = make_params(state)
    await defer_question(params, question_id="q5")
    check("deferred q5", capture.result["status"] == "deferred")
    check("q5 in state.deferred", "q5" in state.deferred)

    # ------------------------------------------------------------------
    # 7. note_clarification
    # ------------------------------------------------------------------
    print("\n--- note_clarification ---")
    params, capture = make_params(state)
    await note_clarification(params, question_id="q3")
    check("noted clarification q3", capture.result["status"] == "noted")
    check("clarification count=1", capture.result["count"] == 1)

    params, capture = make_params(state)
    await note_clarification(params, question_id="q3")
    check("second clarification count=2", capture.result["count"] == 2)

    # ------------------------------------------------------------------
    # 8. flag_offtopic
    # ------------------------------------------------------------------
    print("\n--- flag_offtopic ---")
    params, capture = make_params(state)
    await flag_offtopic(params, kind="chitchat")
    check("flagged chitchat", capture.result["status"] == "flagged")
    check("chitchat total=1", state.offtopic_counts["chitchat"] == 1)

    params, capture = make_params(state)
    await flag_offtopic(params, kind="blocked")
    check("flagged blocked", capture.result["status"] == "flagged")

    # ------------------------------------------------------------------
    # 9. end_survey
    # ------------------------------------------------------------------
    print("\n--- end_survey ---")
    params, capture = make_params(state)
    await end_survey(params, reason="user_requested")
    check("ended", capture.result["status"] == "ended")
    check("is_active=False", state.is_active is False)
    check("missing_required present", isinstance(capture.result["missing_required"], list))
    check("ended_at set", state.ended_at is not None)

    # ------------------------------------------------------------------
    # 10. resume_survey
    # ------------------------------------------------------------------
    print("\n--- resume_survey ---")
    params, capture = make_params(state)
    await resume_survey(params)
    check("resumed", capture.result["status"] == "resumed")
    check("is_active=True", state.is_active is True)
    check("next_question_id set", capture.result["next_question_id"] is not None)

    # ------------------------------------------------------------------
    # 11. Serialization round-trip
    # ------------------------------------------------------------------
    print("\n--- Serialization round-trip ---")
    d = state.to_dict()
    json_str = json.dumps(d, indent=2)
    check("to_dict is JSON-serializable", isinstance(json.loads(json_str), dict))

    restored = SurveyState.from_dict(json.loads(json_str), questions)
    check("from_dict restores answers", set(restored.answers.keys()) == set(state.answers.keys()))
    check("from_dict restores skipped", restored.skipped == state.skipped)
    check("from_dict restores deferred", restored.deferred == state.deferred)
    check("from_dict restores clarifications", restored.clarifications == state.clarifications)
    check("from_dict restores offtopic", restored.offtopic_counts == state.offtopic_counts)

    # Re-serialize and compare
    d2 = restored.to_dict()
    check("round-trip stable", d == d2, f"diff keys: {set(d.keys()) ^ set(d2.keys())}")

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    print("\n" + "=" * 60)
    total = passed + failed
    print(f"RESULTS: {passed}/{total} passed, {failed} failed")
    if failed:
        print("⚠️  Some tests failed!")
        sys.exit(1)
    else:
        print("🎉 All tests passed!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(run_tests())
