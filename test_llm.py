import asyncio
import os
from dotenv import load_dotenv

from pipecat.services.google.gemini_live.llm import GeminiLiveLLMService, GeminiVADParams
from app.config import get_settings
from app.survey.flow import build_survey_prompt, load_survey_metadata
from app.survey.tools import build_survey_tools
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.task import PipelineTask
from pipecat.pipeline.worker import PipelineWorker, PipelineParams
from pipecat.frames.frames import LLMRunFrame
from pipecat.processors.aggregators.llm_context import LLMContext

async def main():
    load_dotenv(override=True)
    settings = get_settings()
    
    meta = load_survey_metadata("survey.json")
    tools_schema, state = build_survey_tools(meta.questions)
    prompt = build_survey_prompt(meta, state)
    
    print(f"System prompt length: {len(prompt)}")
    print(f"Number of tools: {len(tools_schema.standard_tools)}")
    
    llm = GeminiLiveLLMService(
        api_key=settings.google_api_key,
        settings=GeminiLiveLLMService.Settings(
            model=settings.gemini_model,
            system_instruction=prompt,
            voice="Aoede",
            vad=GeminiVADParams(disabled=True),
        ),
        tools=tools_schema,
    )
    
    context = LLMContext()
    context.add_message({"role": "user", "content": "Please introduce yourself."})
    
    pipeline = Pipeline([llm])
    worker = PipelineWorker(
        pipeline,
        params=PipelineParams(enable_metrics=False),
        app_resources={"survey_state": state, "survey_questions": meta.questions}
    )
    
    task = PipelineTask(pipeline)
    
    print("Starting pipeline task...")
    
    @task.on_events("on_task_started")
    async def on_task_started():
        print("Task started, queueing LLMRunFrame...")
        await task.queue_frames([LLMRunFrame()])
        await asyncio.sleep(5)
        print("Cancelling task after 5 seconds...")
        await task.cancel()

    try:
        await task.run()
    except Exception as e:
        print(f"Exception during run: {e}")

if __name__ == "__main__":
    asyncio.run(main())
