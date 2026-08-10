"""
Pipecat function-call tools for survey actions.

Implements the 7 tools from BRAIN_SPEC.md §4 as Pipecat DirectFunctions,
backed by a JSON-serializable SurveyState object.

State sharing: SurveyState is passed via PipelineWorker(app_resources=...)
and accessed in each handler via params.app_resources["survey_state"].

Usage (Stage 2 — main.py / voice_engine.py will wire this):
    from app.survey.tools import build_survey_tools, load_survey

    questions = load_survey("survey.json")
    tools_schema, survey_state = build_survey_tools(questions)
    # Pass tools_schema to GeminiLiveLLMService(tools=tools_schema)
    # Pass survey_state via PipelineWorker(app_resources={"survey_state": state, ...})
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from loguru import logger

from pipecat.adapters.schemas.tools_schema import ToolsSchema
from pipecat.services.llm_service import FunctionCallParams


# ---------------------------------------------------------------------------
# Survey data model
# ---------------------------------------------------------------------------

@dataclass
class Question:
    """A single survey question loaded from survey.json."""
    id: str
    text: str
    type: str               # "single_choice" | "multi_choice" | "open"
    options: list[str]
    required: bool
    note: str = ""


def load_survey(path: str | Path) -> list[Question]:
    """Load questions from a survey.json file.

    Args:
        path: Path to the survey JSON file.

    Returns:
        Ordered list of Question objects.
    """
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    questions: list[Question] = []
    for q in raw["questions"]:
        questions.append(Question(
            id=q["id"],
            text=q["text"],
            type=q["type"],
            options=q.get("options", []),
            required=q.get("required", False),
            note=q.get("note", ""),
        ))
    return questions


# ---------------------------------------------------------------------------
# Survey state — JSON-serializable, tracks everything for analytics
# ---------------------------------------------------------------------------

@dataclass
class AnswerRecord:
    """A single captured answer."""
    question_id: str
    value: str | list[str]
    timestamp: str           # ISO 8601


@dataclass
class SurveyState:
    """Mutable state for one survey session.

    Tracks answers, skips, deferrals, clarifications, off-topic counts,
    and per-question timestamps — enough to produce the outputs in
    BRAIN_SPEC.md §8.
    """

    # The ordered question list (not serialized — passed separately)
    questions: list[Question] = field(default_factory=list, repr=False)

    # Core tracking
    answers: dict[str, AnswerRecord] = field(default_factory=dict)
    skipped: set[str] = field(default_factory=set)
    deferred: list[str] = field(default_factory=list)  # ordered

    # Analytics counters
    clarifications: dict[str, int] = field(default_factory=dict)
    offtopic_counts: dict[str, int] = field(
        default_factory=lambda: {"chitchat": 0, "blocked": 0}
    )

    # Session metadata
    current_question_index: int = 0
    started_at: str | None = None
    ended_at: str | None = None
    end_reason: str | None = None   # "completed" | "user_requested"
    is_active: bool = True

    # Per-question timestamps  {qid: {"asked_at": ..., "answered_at": ...}}
    question_timestamps: dict[str, dict[str, str]] = field(default_factory=dict)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def get_question(self, question_id: str) -> Question | None:
        """Look up a question by ID."""
        for q in self.questions:
            if q.id == question_id:
                return q
        return None

    def next_unanswered_index(self) -> int | None:
        """Return the index of the next question that hasn't been answered or skipped."""
        for i in range(len(self.questions)):
            qid = self.questions[i].id
            if qid not in self.answers and qid not in self.skipped:
                return i
        return None

    def _advance(self) -> str | None:
        """Advance current_question_index to the next unanswered question.

        Returns the next question_id, or None if all done.
        """
        idx = self.next_unanswered_index()
        if idx is not None:
            self.current_question_index = idx
            return self.questions[idx].id
        return None

    def missing_required(self) -> list[str]:
        """Return IDs of required questions that are still unanswered."""
        return [
            q.id for q in self.questions
            if q.required and q.id not in self.answers
        ]

    def progress(self) -> dict[str, int]:
        """Return a quick progress summary."""
        total = len(self.questions)
        answered = len(self.answers)
        return {"answered": answered, "total": total, "remaining": total - answered}

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-safe dictionary (excludes questions list)."""
        return {
            "answers": {
                qid: {"question_id": r.question_id, "value": r.value, "timestamp": r.timestamp}
                for qid, r in self.answers.items()
            },
            "skipped": sorted(self.skipped),
            "deferred": list(self.deferred),
            "clarifications": dict(self.clarifications),
            "offtopic_counts": dict(self.offtopic_counts),
            "current_question_index": self.current_question_index,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "end_reason": self.end_reason,
            "is_active": self.is_active,
            "question_timestamps": dict(self.question_timestamps),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any], questions: list[Question]) -> SurveyState:
        """Restore from a serialized dict (for session resume)."""
        state = cls(questions=questions)
        for qid, rec in d.get("answers", {}).items():
            state.answers[qid] = AnswerRecord(
                question_id=rec["question_id"],
                value=rec["value"],
                timestamp=rec["timestamp"],
            )
        state.skipped = set(d.get("skipped", []))
        state.deferred = list(d.get("deferred", []))
        state.clarifications = dict(d.get("clarifications", {}))
        state.offtopic_counts = dict(d.get("offtopic_counts", {"chitchat": 0, "blocked": 0}))
        state.current_question_index = d.get("current_question_index", 0)
        state.started_at = d.get("started_at")
        state.ended_at = d.get("ended_at")
        state.end_reason = d.get("end_reason")
        state.is_active = d.get("is_active", True)
        state.question_timestamps = dict(d.get("question_timestamps", {}))
        return state


# ---------------------------------------------------------------------------
# Answer validation (light schema check — BRAIN_SPEC.md §7)
# ---------------------------------------------------------------------------

def _normalize(s: str) -> str:
    """Lowercase + strip for fuzzy matching."""
    return s.strip().lower()


def _parse_multi_value(raw: str) -> list[str]:
    """Parse a multi-choice value.

    Accepts either:
      - A JSON array string: '["Chocolate", "Soft drinks"]'
      - A comma-separated string: "Chocolate, Soft drinks"
    """
    raw = raw.strip()
    if raw.startswith("["):
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                return [str(v).strip() for v in parsed if str(v).strip()]
        except (json.JSONDecodeError, TypeError):
            pass
    # Fall back to comma-split
    return [v.strip() for v in raw.split(",") if v.strip()]


def validate_answer(question: Question, value: str) -> tuple[bool, str, str | list[str]]:
    """Validate an answer against the question schema.

    Returns:
        (is_valid, message, normalized_value)
    """
    if question.type == "single_choice":
        norm_options = {_normalize(o): o for o in question.options}
        norm_val = _normalize(value)
        if norm_val in norm_options:
            return True, "ok", norm_options[norm_val]
        # Try substring / partial match (e.g. "milk" matches "Milk")
        for norm_o, original_o in norm_options.items():
            if norm_val in norm_o or norm_o in norm_val:
                return True, "ok", original_o
        return (
            False,
            f"That doesn't seem to match the options: {', '.join(question.options)}. "
            f"Could you pick one of those?",
            value,
        )

    elif question.type == "multi_choice":
        items = _parse_multi_value(value)
        if not items:
            return False, "I didn't catch any selections. Could you try again?", value
        norm_options = {_normalize(o): o for o in question.options}
        matched: list[str] = []
        unmatched: list[str] = []
        for item in items:
            norm_item = _normalize(item)
            found = False
            for norm_o, original_o in norm_options.items():
                if norm_item == norm_o or norm_item in norm_o or norm_o in norm_item:
                    matched.append(original_o)
                    found = True
                    break
            if not found:
                unmatched.append(item)
        if unmatched:
            return (
                False,
                f"I couldn't match these: {', '.join(unmatched)}. "
                f"The options are: {', '.join(question.options)}.",
                value,
            )
        return True, "ok", matched

    elif question.type == "open":
        stripped = value.strip()
        if not stripped:
            return False, "Could you say a bit more? Even a short answer is fine.", value
        return True, "ok", stripped

    # Unknown type — accept anything
    return True, "ok", value


# ---------------------------------------------------------------------------
# Tool handlers (Pipecat DirectFunction pattern)
# ---------------------------------------------------------------------------

async def record_answer(params: FunctionCallParams, question_id: str, value: str):
    """Record a validated answer for a survey question and advance to the next one.

    Args:
        question_id: The ID of the question being answered (e.g. "q1").
        value: The user's answer. For single-choice, the selected option.
            For multi-choice, a comma-separated list or JSON array of selections.
            For open-ended, the free-text response.
    """
    state: SurveyState = params.app_resources["survey_state"]
    question = state.get_question(question_id)

    if question is None:
        logger.warning(f"record_answer: unknown question_id={question_id}")
        await params.result_callback({"status": "error", "message": f"Unknown question: {question_id}"})
        return

    # Light validation (§7)
    is_valid, message, normalized = validate_answer(question, value)
    if not is_valid:
        logger.info(f"record_answer: validation failed for {question_id}: {message}")
        await params.result_callback({
            "status": "validation_failed",
            "question_id": question_id,
            "message": message,
        })
        return

    # Store
    now = state._now()
    state.answers[question_id] = AnswerRecord(
        question_id=question_id,
        value=normalized,
        timestamp=now,
    )
    # Remove from deferred if it was there
    if question_id in state.deferred:
        state.deferred.remove(question_id)
    # Remove from skipped if re-answered
    state.skipped.discard(question_id)
    # Update per-question timestamp
    ts = state.question_timestamps.setdefault(question_id, {})
    ts["answered_at"] = now

    # Advance
    next_qid = state._advance()
    progress = state.progress()

    logger.info(f"record_answer: {question_id}={normalized!r} → next={next_qid} ({progress})")
    await params.result_callback({
        "status": "recorded",
        "question_id": question_id,
        "next_question_id": next_qid,
        "progress": progress,
    })


async def skip_question(params: FunctionCallParams, question_id: str):
    """Skip an optional survey question the user declined to answer.

    Args:
        question_id: The ID of the question being skipped (e.g. "q4").
    """
    state: SurveyState = params.app_resources["survey_state"]
    question = state.get_question(question_id)

    if question is None:
        await params.result_callback({"status": "error", "message": f"Unknown question: {question_id}"})
        return

    state.skipped.add(question_id)
    now = state._now()
    ts = state.question_timestamps.setdefault(question_id, {})
    ts["skipped_at"] = now

    next_qid = state._advance()
    logger.info(f"skip_question: {question_id} → next={next_qid}")
    await params.result_callback({
        "status": "skipped",
        "question_id": question_id,
        "next_question_id": next_qid,
    })


async def defer_question(params: FunctionCallParams, question_id: str):
    """Park a required question to revisit later before ending the survey.

    Args:
        question_id: The ID of the question being deferred (e.g. "q5").
    """
    state: SurveyState = params.app_resources["survey_state"]
    question = state.get_question(question_id)

    if question is None:
        await params.result_callback({"status": "error", "message": f"Unknown question: {question_id}"})
        return

    if question_id not in state.deferred:
        state.deferred.append(question_id)
    now = state._now()
    ts = state.question_timestamps.setdefault(question_id, {})
    ts["deferred_at"] = now

    next_qid = state._advance()
    logger.info(f"defer_question: {question_id} → next={next_qid}")
    await params.result_callback({
        "status": "deferred",
        "question_id": question_id,
        "next_question_id": next_qid,
    })


async def note_clarification(params: FunctionCallParams, question_id: str):
    """Log that the user asked for clarification on a question.

    Args:
        question_id: The ID of the question the user needs clarified (e.g. "q3").
    """
    state: SurveyState = params.app_resources["survey_state"]
    count = state.clarifications.get(question_id, 0) + 1
    state.clarifications[question_id] = count

    logger.info(f"note_clarification: {question_id} (count={count})")
    await params.result_callback({
        "status": "noted",
        "question_id": question_id,
        "count": count,
    })


async def flag_offtopic(params: FunctionCallParams, kind: str):
    """Flag an off-topic user turn for analytics.

    Args:
        kind: The category of off-topic turn — either "chitchat" for social/meta
            questions, or "blocked" for external facts, opinions, or suggestions.
    """
    state: SurveyState = params.app_resources["survey_state"]
    if kind not in ("chitchat", "blocked"):
        kind = "blocked"  # default to the stricter category
    state.offtopic_counts[kind] = state.offtopic_counts.get(kind, 0) + 1

    logger.info(f"flag_offtopic: {kind} (total={state.offtopic_counts[kind]})")
    await params.result_callback({
        "status": "flagged",
        "kind": kind,
        "total": state.offtopic_counts[kind],
    })


async def end_survey(params: FunctionCallParams, reason: str):
    """End the survey session.

    Args:
        reason: Why the survey is ending — either "completed" when all questions
            are done, or "user_requested" when the user wants to stop early.
    """
    state: SurveyState = params.app_resources["survey_state"]
    now = state._now()
    state.ended_at = now
    state.end_reason = reason if reason in ("completed", "user_requested") else "user_requested"
    state.is_active = False

    missing = state.missing_required()
    logger.info(f"end_survey: reason={reason}, missing_required={missing}")
    await params.result_callback({
        "status": "ended",
        "reason": state.end_reason,
        "missing_required": missing,
        "progress": state.progress(),
    })


async def resume_survey(params: FunctionCallParams):
    """Resume the survey after the user changed their mind about stopping.

    Picks up at the first unanswered or deferred question.
    """
    state: SurveyState = params.app_resources["survey_state"]
    state.is_active = True
    state.ended_at = None
    state.end_reason = None

    next_qid = state._advance()
    logger.info(f"resume_survey: next={next_qid}")
    await params.result_callback({
        "status": "resumed",
        "next_question_id": next_qid,
        "progress": state.progress(),
    })


# ---------------------------------------------------------------------------
# Factory — builds ToolsSchema + initial SurveyState
# ---------------------------------------------------------------------------

def build_survey_tools(questions: list[Question]) -> tuple[ToolsSchema, SurveyState]:
    """Create the Pipecat ToolsSchema and initial SurveyState for a survey.

    Args:
        questions: Ordered list of Question objects from load_survey().

    Returns:
        A tuple of (ToolsSchema, SurveyState). Pass the ToolsSchema to the
        LLM service via ``tools=``, and the SurveyState into
        ``PipelineWorker(app_resources={"survey_state": state})``.
    """
    state = SurveyState(
        questions=questions,
        started_at=datetime.now(timezone.utc).isoformat(),
    )

    tools = ToolsSchema(
        standard_tools=[
            record_answer,
            skip_question,
            defer_question,
            note_clarification,
            flag_offtopic,
            end_survey,
            resume_survey,
        ]
    )

    return tools, state
