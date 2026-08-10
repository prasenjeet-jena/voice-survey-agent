"""
Voice Survey Agent — Entry Point

Starts a Pipecat bot using the official runner pattern (PipelineWorker +
WorkerRunner). Supports multiple transports (WebSocket, Daily, WebRTC)
via the `pipecat.runner.run.main()` CLI.

Usage (local dev — WebSocket transport, default):
    python -m app.main

Usage (select transport explicitly):
    python -m app.main -t websocket          # FastAPI WebSocket
    python -m app.main -t daily              # Daily WebRTC (needs DAILY_API_KEY)

Docs reference:
    https://github.com/pipecat-ai/pipecat/blob/main/examples/realtime/realtime-gemini-live.py
    (pipecat-ai/pipecat main branch, as of Aug 2026)
"""

from __future__ import annotations

import os
import certifi

# Fix for macOS missing-root-certificates issue (OpenAI Realtime API)
os.environ["SSL_CERT_FILE"] = certifi.where()
os.environ["WEBSOCKET_CLIENT_CA_BUNDLE"] = certifi.where()

import asyncio

from dotenv import load_dotenv
from loguru import logger
from aiortc.mediastreams import MediaStreamError

from pipecat.transports.smallwebrtc.transport import SmallWebRTCClient


from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.audio.vad.vad_analyzer import VADParams
from pipecat.frames.frames import LLMRunFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.worker import PipelineParams, PipelineWorker
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    AssistantTurnStoppedMessage,
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
    UserTurnMessageAddedMessage,
)
from pipecat.runner.types import RunnerArguments
from pipecat.runner.utils import create_transport
from pipecat.transports.base_transport import BaseTransport, TransportParams
from pipecat.transports.websocket.fastapi import FastAPIWebsocketParams
from pipecat.workers.runner import WorkerRunner
from pipecat.turns.user_turn_strategies import UserTurnStrategies
from pipecat.turns.user_start import VADUserTurnStartStrategy
from pipecat.turns.user_stop import SpeechTimeoutUserTurnStopStrategy

from app.config import get_settings
from app.survey.flow import build_survey_prompt, load_survey_metadata
from app.survey.tools import build_survey_tools
from app.voice_engine import build_voice_pipeline

load_dotenv(override=True)

# Load config once at module level
settings = get_settings()

# ---------------------------------------------------------------------------
# Load survey once at module level — shared across all connections.
# The SurveyState is per-connection (created in run_bot).
# ---------------------------------------------------------------------------
SURVEY_META = load_survey_metadata("survey.json")
logger.info(
    "Loaded survey: {} ({} questions, {} required)",
    SURVEY_META.title,
    len(SURVEY_META.questions),
    sum(1 for q in SURVEY_META.questions if q.required),
)

# ---------------------------------------------------------------------------
# Transport parameter map (lambdas defer creation until transport is chosen).
# The Pipecat runner selects one at runtime based on the -t flag.
# ---------------------------------------------------------------------------
transport_params = {
    "websocket": lambda: FastAPIWebsocketParams(
        audio_in_enabled=True,
        audio_out_enabled=True,
    ),
    "webrtc": lambda: TransportParams(
        audio_in_enabled=True,
        audio_out_enabled=True,
    ),
}


# ---------------------------------------------------------------------------
# Bot entrypoint — called by the Pipecat runner for each new connection.
# ---------------------------------------------------------------------------
async def run_bot(transport: BaseTransport, runner_args: RunnerArguments) -> None:
    logger.info("Starting bot — engine={}, model={}", settings.voice_engine, settings.gemini_model)

    # --- Survey brain -------------------------------------------------------
    # Build per-session tools + state, and render the system prompt.
    tools_schema, survey_state = build_survey_tools(SURVEY_META.questions)
    system_prompt = build_survey_prompt(SURVEY_META, survey_state)

    logger.info(
        "Survey brain ready — {} tools, prompt length={} chars",
        len(tools_schema.standard_tools),
        len(system_prompt),
    )

    # --- Voice engine -------------------------------------------------------
    voice_stages = build_voice_pipeline(
        engine=settings.voice_engine,
        config=settings,
        system_prompt=system_prompt,
        tools=tools_schema,
    )

    # Normalise to a list so the cascade engine (which returns [stt, llm, tts])
    # works without any special handling in the pipeline wiring.
    if not isinstance(voice_stages, list):
        voice_stages = [voice_stages]

    # --- Context aggregation ------------------------------------------------
    context = LLMContext()
    user_aggregator, assistant_aggregator = LLMContextAggregatorPair(
        context,
        user_params=LLMUserAggregatorParams(
            vad_analyzer=SileroVADAnalyzer(params=VADParams(
                stop_secs=1.5,
                start_secs=0.3,
                confidence=0.85,
                min_volume=0.8
            )),
            user_turn_strategies=UserTurnStrategies(
                start=[VADUserTurnStartStrategy()],
                stop=[SpeechTimeoutUserTurnStopStrategy(user_speech_timeout=0.0)]
            )
        ),
    )

    @user_aggregator.event_handler("on_user_turn_message_added")
    async def on_user_turn_message_added(aggregator, message: UserTurnMessageAddedMessage):
        timestamp = f"[{message.timestamp}] " if message.timestamp else ""
        logger.info("Transcript User: {}{}", timestamp, message.content)

    @assistant_aggregator.event_handler("on_assistant_turn_stopped")
    async def on_assistant_turn_stopped(aggregator, message: AssistantTurnStoppedMessage):
        timestamp = f"[{message.timestamp}] " if message.timestamp else ""
        logger.info("Transcript Assistant: {}{}", timestamp, message.content)

    from app.ttfb_processor import TTFBProcessor
    ttfb_processor = TTFBProcessor()

    pipeline = Pipeline(
        [
            transport.input(),
            user_aggregator,
            *voice_stages,
            ttfb_processor,
            transport.output(),
            assistant_aggregator,
        ]
    )

    worker = PipelineWorker(
        pipeline,
        params=PipelineParams(
            enable_metrics=True,
            enable_usage_metrics=True,
        ),
        idle_timeout_secs=runner_args.pipeline_idle_timeout_secs,
        app_resources={
            "survey_state": survey_state,
            "survey_questions": SURVEY_META.questions,
        },
    )

    # --- Transport event handlers -------------------------------------------
    @transport.event_handler("on_client_connected")
    async def on_client_connected(transport, client):
        logger.info("Client connected")
        # Kick off the conversation — the model will greet the user
        # following the system prompt's GREETING instructions.
        context.add_message(
            {"role": "user", "content": "Please introduce yourself to the user, ask if they are ready to jump in, and WAIT for their response before proceeding."}
        )
        await worker.queue_frames([LLMRunFrame()])

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport, client):
        logger.info("Client disconnected")
        await worker.cancel()

    # --- Run ----------------------------------------------------------------
    runner = WorkerRunner(handle_sigint=runner_args.handle_sigint)
    await runner.add_workers(worker)
    await runner.run()


# ---------------------------------------------------------------------------
# Pipecat Cloud / runner compatibility
# ---------------------------------------------------------------------------
async def bot(runner_args: RunnerArguments) -> None:
    """Main bot entry point compatible with Pipecat Cloud."""
    transport = await create_transport(runner_args, transport_params)
    await run_bot(transport, runner_args)


# ---------------------------------------------------------------------------
# Local dev runner
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    from pipecat.runner.run import main

    main()
