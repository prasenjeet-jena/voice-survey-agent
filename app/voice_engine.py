"""Swappable voice engine factory.

Provides `build_voice_pipeline()` which returns the Pipecat service stage(s)
for the selected voice engine. The survey brain (prompt + tools) is built
once by main.py and passed in — this factory never imports survey modules.

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

from pipecat.adapters.schemas.tools_schema import ToolsSchema
from pipecat.processors.frame_processor import FrameProcessor
from pipecat.services.google.gemini_live.llm import GeminiLiveLLMService, GeminiVADParams

if TYPE_CHECKING:
    from app.config import Settings


def build_voice_pipeline(
    engine: str,
    config: "Settings",
    *,
    system_prompt: str,
    tools: ToolsSchema | None = None,
) -> FrameProcessor | list[FrameProcessor]:
    """
    Build and return the voice-engine stage(s) for the Pipecat pipeline.

    Parameters
    ----------
    engine : str
        Which engine to use: "gemini", "openai", or "cascade".
    config : Settings
        Application settings (API keys, model name, etc.).
    system_prompt : str
        The full system instruction (rendered by flow.build_survey_prompt).
    tools : ToolsSchema | None
        The survey function-calling tools (built by tools.build_survey_tools).

    Returns
    -------
    FrameProcessor | list[FrameProcessor]
        A single Pipecat processor (gemini, openai) or a list of processors
        (cascade: [stt, llm, tts]) to splice into the Pipeline.
        The caller should handle both cases — see main.py.
    """

    # ------------------------------------------------------------------
    # ENGINE: Google Gemini Live (native speech-to-speech)
    # ------------------------------------------------------------------
    if engine == "gemini":
        from pipecat.services.google.gemini_live.llm import GeminiLiveLLMService

        # Monkeypatch _connection_task_handler to lock audio transcription to en-US.
        # Pipecat 1.7 hardcodes AudioTranscriptionConfig() without languageCodes.
        original_handler = GeminiLiveLLMService._connection_task_handler

        async def patched_connection_task_handler(self, config):
            if hasattr(config, "input_audio_transcription") and config.input_audio_transcription is not None:
                config.input_audio_transcription.language_codes = ["en-US"]
            if hasattr(config, "output_audio_transcription") and config.output_audio_transcription is not None:
                config.output_audio_transcription.language_codes = ["en-US"]
            return await original_handler(self, config)

        GeminiLiveLLMService._connection_task_handler = patched_connection_task_handler

        llm = GeminiLiveLLMService(
            api_key=config.google_api_key,
            settings=GeminiLiveLLMService.Settings(
                model=config.gemini_model,
                system_instruction=system_prompt,
                voice="Aoede",  # Options: Puck, Charon, Kore, Fenrir, Aoede
                language="en-US", # Locks text generation and TTS to en-US
            ),
            tools=tools,
        )
        return llm

    # ------------------------------------------------------------------
    # ENGINE: OpenAI Realtime API  [TODO]
    # ------------------------------------------------------------------
    elif engine == "openai":
        from pipecat.services.openai.realtime.llm import OpenAIRealtimeLLMService
        from pipecat.services.openai.realtime.events import (
            SessionProperties,
            AudioConfiguration,
            AudioInput,
            AudioOutput,
            InputAudioTranscription
        )

        if not config.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY must be set to use the openai engine.")

        llm = OpenAIRealtimeLLMService(
            api_key=config.openai_api_key,
            settings=OpenAIRealtimeLLMService.Settings(
                model="gpt-realtime-2.1-mini",
                system_instruction=system_prompt,
                session_properties=SessionProperties(
                    audio=AudioConfiguration(
                        input=AudioInput(
                            transcription=InputAudioTranscription(language="en"),
                            turn_detection=False  # Disable server VAD to prevent duplicates with our local VAD
                        ),
                        output=AudioOutput(voice="alloy"),
                    )
                )
            ),
            tools=tools,
        )
        return llm

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
