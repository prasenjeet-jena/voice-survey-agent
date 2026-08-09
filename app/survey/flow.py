"""
Survey conversation flow engine.

TODO: This module will contain:
  - SurveyFlow class that manages question progression
  - State machine for survey states (greeting → questions → closing)
  - Integration with survey.json question definitions
  - Hooks into the voice engine's system prompt (dynamically rewritten
    as the survey advances through questions)
  - Callbacks for when the model invokes function-call tools
    (e.g. record_answer, next_question, end_survey)
"""


class SurveyFlow:
    """
    Manages the survey conversation state.

    TODO: Implement this class. It should:
      1. Load question definitions from a survey.json file.
      2. Track which question we're on + collected answers.
      3. Generate the system prompt for the current survey state.
      4. Provide hooks that main.py can register with the pipeline.
    """

    def __init__(self, survey_path: str = "survey.json") -> None:
        self.survey_path = survey_path
        # TODO: Load and parse survey definition
        raise NotImplementedError("SurveyFlow is not yet implemented")
