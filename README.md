# Voice Survey Agent

A real-time conversational voice agent built with [Pipecat](https://github.com/pipecat-ai/pipecat) and **Google Gemini Live** (native speech-to-speech). The architecture is designed so the voice engine is swappable — Gemini Live is the default, with planned support for OpenAI Realtime and a cascade (STT → LLM → TTS) approach.

> **Status:** Skeleton / scaffolding only. The survey logic will be added in a later phase.

## Project Structure

```
app/
├── main.py          # Entry point — Pipecat pipeline + FastAPI WebSocket server
├── config.py        # Loads settings from .env via python-dotenv
├── voice_engine.py  # Swappable voice engine factory
└── survey/
    ├── flow.py      # (TODO) Survey conversation state machine
    └── tools.py     # (TODO) Function-call tools for survey actions
```

## How to Run Locally

### 1. Clone and set up a virtual environment

```bash
git clone <repo-url> voice-survey-agent
cd voice-survey-agent
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure your API key

Copy the example env file and add your Google API key:

```bash
cp .env.example .env
# Edit .env and set GOOGLE_API_KEY=your_key_here
```

Get a key from [Google AI Studio](https://aistudio.google.com/).

### 4. Start the server

```bash
python -m app.main
```

The WebSocket server will start on `ws://localhost:8765/ws`. Connect a browser client to begin a voice conversation.

## Architecture Notes

- **Gemini Multimodal Live** handles the full audio loop natively (no separate STT/TTS).
- The voice engine factory (`voice_engine.py`) isolates engine-specific code — survey logic never imports engine classes directly.
- The pipeline is intentionally minimal right now: `transport.input() → voice stage → transport.output()`.
- Survey flow, question definitions (`survey.json`), and function-call tools will be layered in without changing the core pipeline wiring.
