"""
Pipecat function-call tools for survey actions.

TODO: This module will contain tool definitions that the LLM can invoke
during a survey conversation. Each tool is a Python function registered
with the Pipecat service via its `tools=` parameter.

Planned tools:
  - record_answer(question_id: str, answer: str)
      Save the user's response for a given question.

  - next_question()
      Advance the survey to the next question and update the system prompt.

  - end_survey(reason: str)
      Mark the survey as complete (or abandoned) and trigger wrap-up.

  - validate_response(question_id: str, answer: str) -> bool
      Optional: check that an answer meets constraints (e.g. numeric range,
      valid selection from a list) before recording it.
"""

# TODO: Implement tool functions and register them with the voice engine.
# See voice_engine.py for the integration point (tools= parameter).
