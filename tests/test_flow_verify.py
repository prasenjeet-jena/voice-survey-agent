"""
Verification script for app.survey.flow — checks import, marker presence,
and rendered prompt correctness.

Run: python tests/test_flow_verify.py
"""

import sys
sys.path.insert(0, ".")

from app.survey.flow import build_survey_prompt, load_survey_metadata
from app.survey.tools import SurveyState, AnswerRecord


def main():
    print("=" * 60)
    print("VERIFICATION: app.survey.flow")
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
    # 1. Import & load
    # ------------------------------------------------------------------
    print("\n--- Import & Load ---")
    meta = load_survey_metadata("survey.json")
    check("load_survey_metadata works", meta is not None)
    check("title loaded", meta.title == "NielsenIQ Consumer Panel — Chocolate & Beverages")
    check("20 questions loaded", len(meta.questions) == 20)

    # ------------------------------------------------------------------
    # 2. Fresh session prompt
    # ------------------------------------------------------------------
    print("\n--- Fresh Session Prompt ---")
    state = SurveyState(questions=meta.questions, started_at="2026-08-09T10:00:00Z")
    prompt = build_survey_prompt(meta, state)

    # Computed counts (not hardcoded)
    required_count = sum(1 for q in meta.questions if q.required)
    optional_count = len(meta.questions) - required_count
    check("computed required count in prompt",
          f"{required_count} required" in prompt,
          f"expected '{required_count} required' in prompt")
    check("computed optional count in prompt",
          f"{optional_count} optional" in prompt,
          f"expected '{optional_count} optional' in prompt")

    # All 20 question IDs present
    print("\n--- All 20 Question IDs ---")
    all_qids_present = True
    for i in range(1, 21):
        qid = f"q{i}"
        if qid not in prompt:
            check(f"{qid} present", False, "missing")
            all_qids_present = False
    if all_qids_present:
        check("all 20 question IDs (q1–q20) present", True)

    # Key markers
    print("\n--- Key Markers ---")

    # Exact blocked-deflection line
    deflection = "That's outside what I can help with here — a search engine like Google or Bing, or another AI tool, would answer that well. Anyway, back to where we were…"
    check("exact blocked-deflection line present",
          deflection in prompt,
          "deflection line not found verbatim")

    # Screener note on q1
    check("q1 screener note present",
          "SCREENER" in prompt and "None of these" in prompt)

    # Tool names
    for tool in ["record_answer", "skip_question", "defer_question",
                 "note_clarification", "flag_offtopic", "end_survey", "resume_survey"]:
        check(f"tool '{tool}' referenced", tool in prompt)

    # Defer script
    check("defer script present",
          "I'll park this one and we can circle back" in prompt)

    # Resume script
    check("resume script present",
          "pick up where we left off" in prompt or "pick right back up" in prompt)

    # Wind-down one gentle attempt
    check("wind-down gentle attempt present",
          "Before you go, there's just one I really need" in prompt)

    # Multi-choice gathering rule (new)
    check("multi-choice gather-all rule present",
          "do NOT record after the first option" in prompt)
    check("multi-choice 'Any others' prompt present",
          "Any others, or is that it?" in prompt)

    # Open-question reflect-back rule (new)
    check("open reflect-back rule present",
          "reflect back what you heard before recording" in prompt)
    check("open reflect-back example present",
          "Lindt and Cadbury" in prompt)

    # Fresh state
    check("fresh session state",
          "fresh session" in prompt.lower() and "Start from q1" in prompt)

    # ------------------------------------------------------------------
    # 3. Resumed session prompt
    # ------------------------------------------------------------------
    print("\n--- Resumed Session Prompt ---")
    state2 = SurveyState(questions=meta.questions, started_at="2026-08-09T10:00:00Z")
    state2.answers["q1"] = AnswerRecord("q1", ["Chocolate", "Soft drinks"], "2026-08-09T10:01:00Z")
    state2.answers["q2"] = AnswerRecord("q2", "Rarely", "2026-08-09T10:02:00Z")
    state2.answers["q3"] = AnswerRecord("q3", "Dark", "2026-08-09T10:03:00Z")
    state2.skipped.add("q4")
    state2.deferred.append("q5")
    state2.current_question_index = 5  # q6

    prompt2 = build_survey_prompt(meta, state2)

    check("resumed prompt has answered list",
          "q1" in prompt2 and "q2" in prompt2 and "q3" in prompt2
          and "already answered" in prompt2.lower())
    check("resumed prompt has skipped list",
          "q4" in prompt2 and "skipped" in prompt2.lower())
    check("resumed prompt has deferred list",
          "q5" in prompt2 and "deferred" in prompt2.lower())
    check("resumed prompt shows progress",
          "3 of 20 answered" in prompt2)
    check("resumed prompt does NOT say 'fresh session'",
          "fresh session" not in prompt2.lower())

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
        print("🎉 All checks passed!")
    print("=" * 60)


if __name__ == "__main__":
    main()
