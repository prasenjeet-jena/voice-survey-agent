"""
Swappable voice engine factory.

Provides `build_voice_pipeline()` which returns the Pipecat service stage(s)
for the selected voice engine. The survey code imports only this factory —
never engine-specific classes directly.

Supported engines:
  - "gemini"  : Google Gemini Live (native speech-to-speech) [DEFAULT]
  - "openai"  : OpenAI Realtime API [TODO]
  - "cascade" : STT → LLM → TTS pipeline [TODO]

Docs reference:
  https://github.com/pipecat-ai/pipecat/blob/main/examples/realtime/realtime-gemini-live.py
  (pipecat-ai/pipecat main branch, as of Aug 2026)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pipecat.processors.frame_processor import FrameProcessor
from pipecat.services.google.gemini_live.llm import GeminiLiveLLMService, GeminiVADParams

if TYPE_CHECKING:
    from app.config import Settings

# ---------------------------------------------------------------------------
# Default system prompt — used only during scaffolding / smoke-testing.
# --- SURVEY INTEGRATION POINT ---
# When the survey brain is wired in, this prompt will be replaced by
# survey.flow.SurveyFlow, which dynamically builds the system prompt
# based on the current question from survey.json.
# ---------------------------------------------------------------------------
DEFAULT_SYSTEM_PROMPT = (
    "You are a friendly assistant. "
    "Greet the user warmly and have a short conversation."
)


def build_voice_pipeline(
    engine: str,
    config: "Settings",
    *,
    system_prompt: str | None = None,
) -> FrameProcessor | list[FrameProcessor]:
    """
    Build and return the voice-engine stage(s) for the Pipecat pipeline.

    Parameters
    ----------
    engine : str
        Which engine to use: "gemini", "openai", or "cascade".
    config : Settings
        Application settings (API keys, model name, etc.).
    system_prompt : str | None
        Override the default system prompt. When the survey brain is active,
        it will pass its own prompt here.

    Returns
    -------
    FrameProcessor | list[FrameProcessor]
        A single Pipecat processor (gemini, openai) or a list of processors
        (cascade: [stt, llm, tts]) to splice into the Pipeline.
        The caller should handle both cases — see main.py.
    """
    prompt = system_prompt or DEFAULT_SYSTEM_PROMPT

    # ------------------------------------------------------------------
    # ENGINE: Google Gemini Live (native speech-to-speech)
    # ------------------------------------------------------------------
    if engine == "gemini":
        llm = GeminiLiveLLMService(
            api_key=config.google_api_key,
            settings=GeminiLiveLLMService.Settings(
                model=config.gemini_model,
                system_instruction=prompt,
                voice="Aoede",  # Options: Puck, Charon, Kore, Fenrir, Aoede
                vad=GeminiVADParams(disabled=True),
            ),
            # --- SURVEY INTEGRATION POINT ---
            # When function-call tools are added (survey.tools), pass them
            # via the `tools=` parameter here. Example:
            #   tools=survey_tools,
        )
        return llm

    # ------------------------------------------------------------------
    # ENGINE: OpenAI Realtime API  [TODO]
    # ------------------------------------------------------------------
    elif engine == "openai":
        # TODO: Implement OpenAI Realtime voice engine.
        # Expected import:
        #   from pipecat.services.openai_realtime import OpenAIRealtimeService
        # Similar pattern: instantiate with api_key, model, system_prompt.
        raise NotImplementedError(
            "OpenAI Realtime engine is not yet implemented. "
            "Contributions welcome — see voice_engine.py for the pattern."
        )

    # ------------------------------------------------------------------
    # ENGINE: Cascade (separate STT → LLM → TTS)  [TODO]
    # ------------------------------------------------------------------
    elif engine == "cascade":
        # TODO: Implement cascade pipeline with separate services.
        # This would return a list of stages, e.g.:
        #   return [stt_service, llm_service, tts_service]
        # The caller (main.py) unpacks them into the Pipeline via:
        #   stages = build_voice_pipeline(...)
        #   pipeline_list = [transport.input(), *stages, transport.output()]
        raise NotImplementedError(
            "Cascade (STT → LLM → TTS) engine is not yet implemented. "
            "Contributions welcome — see voice_engine.py for the pattern."
        )

    else:
        raise ValueError(
            f"Unknown voice engine: {engine!r}. "
            f"Supported: 'gemini', 'openai', 'cascade'."
        )
