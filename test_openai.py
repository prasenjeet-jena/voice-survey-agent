import asyncio
from pipecat.transports.network.websocket_client import WebsocketClientTransport, WebsocketClientParams
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineTask
from pipecat.services.openai.realtime.llm import OpenAIRealtimeLLMService
from pipecat.processors.aggregators.llm_response import LLMUserResponseAggregator, LLMAssistantResponseAggregator
from loguru import logger
import os

# ensure loguru shows DEBUG
import sys
logger.remove()
logger.add(sys.stderr, level="DEBUG")

# We just want to see if OpenAIRealtimeLLMService connects and emits anything.
async def main():
    logger.info("Starting test")
    llm = OpenAIRealtimeLLMService(api_key=os.environ.get("OPENAI_API_KEY", "dummy"))
    logger.info("Done")

asyncio.run(main())
