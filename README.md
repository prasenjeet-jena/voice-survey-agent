# Voice Survey Agent

## Overview

This project is a real-time conversational voice survey agent designed to conduct interactive, voice-first surveys. It reads a declarative survey definition and acts as an empathetic, natural-sounding host that guides users through the survey, asking questions one-by-one, clarifying intent, and capturing structured answers. 

Key features:
- **Swappable Voice Engine**: Supports both **Gemini Live** and **OpenAI Realtime** native speech-to-speech APIs, selectable directly from the developer UI.
- **Real-Time Responsiveness**: Utilizes native voice APIs for ultra-low latency, complete with a per-turn Time-to-First-Byte (TTFB) latency display in the UI.
- **Intelligent Flow Control**: Deduces answers dynamically. If a user provides a broad answer that covers multiple questions, the agent intelligently infers those answers and skips the redundant questions automatically.
- **Structured Answer Capture**: Leverages function-calling tools to map free-form conversational answers to strict multiple-choice or open-ended schemas.

---

## Architecture

The system is built on an event-driven, real-time pipeline orchestrated by **Pipecat** and exposes an **RTVI (Real-Time Voice AI)** client-server split. 

```text
+-----------------------+      WebRTC / RTVI      +---------------------------------+
|   Developer Test UI   | <=====================> |        Python Backend           |
|  (localhost:7860)     |                         |                                 |
| - Connect/Disconnect  |                         |  +---------------------------+  |
| - Engine Selector     |                         |  |   Pipecat Orchestration   |  |
| - TTFB Latency Display|                         |  | (VAD, WebRTC, turn-taking)|  |
| - Live Transcripts    |                         |  +---------------------------+  |
+-----------------------+                         |               |                 |
                                                  |  +---------------------------+  |
                                                  |  |    voice_engine.py        |  |
                                                  |  | (Gemini / OpenAI factory) |  |
                                                  |  +---------------------------+  |
                                                  |               |                 |
+-----------------------+                         |  +---------------------------+  |
|     survey.json       | ----------------------> |  |        Survey Brain       |  |
| (Questions, schema)   |                         |  | - flow.py (System Prompt) |  |
+-----------------------+                         |  | - tools.py (Function Calls)| |
                                                  |  +---------------------------+  |
                                                  +---------------------------------+
```

- **Pipecat (Orchestration)**: Handles the hard real-time plumbing—WebRTC streaming, Voice Activity Detection (VAD), interruption handling, and turn-taking orchestration.
- **Voice Engine Factory (`voice_engine.py`)**: A swappable layer that boots up either `GeminiLiveLLMService` or `OpenAIRealtimeLLMService`.
- **Survey Brain (`flow.py` & `tools.py`)**: 
  - `flow.py`: Dynamically builds the system prompt from the `survey.json` definition and the current conversational state.
  - `tools.py`: Contains 7 function-call tools used by the LLM to record answers, defer questions, flag off-topic chatter, and manage the survey state (`SurveyState`).
- **Developer Test Client**: A local web interface used purely as a test harness for the backend. *Note: In production, the real survey UI would be a separate RTVI frontend built on modern web frameworks, communicating with this same backend.*

---

## Why These Choices?

- **Pipecat**: Solves the incredibly difficult plumbing of real-time voice (WebRTC buffers, VAD, network jitter) right out of the box. It supports the open RTVI standard and makes it trivial to swap AI providers.
- **Native Speech-to-Speech APIs**: We opted for Gemini Live and OpenAI Realtime rather than a cascaded STT → LLM → TTS pipeline. A single audio-in/audio-out model dramatically reduces latency, handles interruptions gracefully, and preserves emotional prosody.
- **Gemini Live (Default)**: Chosen as the primary engine for its cost-efficiency and near-zero audio latency. 
- **OpenAI Realtime (Alternative)**: Provided as a swappable fallback specifically because of its robust recognition of heavily accented English, which proved to be a pain point during testing.
- **Function-Calling Tools**: Enables the agent to engage in natural, meandering conversation while still strictly enforcing structured data capture (e.g., mapping "I usually go for Cadbury" to a recorded JSON answer payload).

---

## Setup & How to Run

### Prerequisites
- Python 3.12+
- `uv` or `pip` for package management

### 1. Environment Variables
You will need API keys for the voice engines. Create a `.env` file in the root directory (this file is `.gitignore`d to protect your keys):
```env
GOOGLE_API_KEY=your_gemini_key_here
OPENAI_API_KEY=your_openai_key_here
```

### 2. Installation
```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 3. Running the Server
You can start the server and dictate which voice engine to use via the `VOICE_ENGINE` environment variable (`gemini` or `openai`).
```bash
VOICE_ENGINE=gemini python -m app.main
```

### 4. Testing
Once the server is running, open your browser to:
[http://localhost:7860](http://localhost:7860)

Click **Connect** to start the voice session.

---

## Production Cost Estimation

We have prepared a detailed breakdown of the token consumption, audio billing, and infrastructural costs associated with running this survey at scale (from 1,000 to 100,000 users). 

- **OpenAI Realtime (`gpt-4o-mini`)**: ~$0.21 per survey session.
- **Gemini Live (`gemini-2.5-flash`)**: ~$0.02 per survey session.

For the full mathematical breakdown, please read the [COST_ESTIMATE.md](./COST_ESTIMATE.md) file.

---

## Project Structure

### Application Core
- **`app/main.py`**
  The entry point of the application. It spins up a FastAPI/Uvicorn server and manages the Pipecat WebRTC transport lifecycle. It configures the Voice Activity Detection (VAD) via `SileroVADAnalyzer`, manages client connections, and orchestrates the primary `PipelineWorker` loop.
- **`app/config.py`**
  Handles environment variable validation and loading. It ensures required API keys (Google, OpenAI) are present before booting the server.
- **`app/voice_engine.py`**
  A swappable factory layer that provisions the active LLM voice engine based on the `VOICE_ENGINE` environment variable. It sets up either the `GeminiLiveLLMService` (with a monkeypatch to strictly enforce US English transcription) or the `OpenAIRealtimeLLMService`.
- **`app/ttfb_processor.py`**
  A custom Pipecat `FrameProcessor`. It sits in the pipeline, intercepts TTFB (Time-To-First-Byte) latency metrics generated by the voice engines, and securely pushes them down the WebRTC data channel to be rendered on the developer UI.

### Survey Brain & Logic
- **`app/survey/flow.py`**
  The dynamic system prompt generator. It evaluates the current `SurveyState` against the master list of questions and continuously rebuilds the prompt. It enforces strict conversational boundaries and contains the "Multi-Question Inference" logic, allowing the AI to skip questions dynamically.
- **`app/survey/tools.py`**
  Implements the 7 essential Pipecat function-call tools (`record_answer`, `skip_question`, `defer_question`, etc.) that the LLM uses to capture structured data. It also defines the JSON-serializable `SurveyState` dataclass that powers analytics and state-tracking.

### Configuration & Docs
- **`survey.json`**
  The declarative schema for the active survey. Defines the title, description, and an array of questions (with their respective `single_choice`, `multi_choice`, or `open` parameters).
- **`BRAIN_SPEC.md`**
  The master specification document detailing the intended AI persona, behavioral constraints, and validation logic.
- **`requirements.txt`**
  The list of required Python dependencies (including `pipecat-ai`, `fastapi`, and `uvicorn`).

---

## Challenges & Solutions

Building a stable real-time voice pipeline revealed several edge cases. Here are the core issues we encountered and resolved during development:

- **Dead Model Strings Crashing the Pipeline**
  - *Problem*: The application failed to connect to Gemini initially.
  - *Cause*: A retired preview model string was hardcoded in the codebase.
  - *Fix*: Updated to the current production Live model (`models/gemini-2.5-flash-native-audio-preview-12-2025`).

- **One-Way Audio & Missing Configs**
  - *Problem*: The pipeline connected, but the agent wouldn't speak.
  - *Cause*: Missing parameters in the `GeminiLiveLLMService` setup.
  - *Fix*: Configured the engine with the proper modal setup, wiring audio inputs/outputs explicitly.

- **Prebuilt-Frontend Package Mismatch**
  - *Problem*: The UI assets wouldn't load on localhost.
  - *Cause*: A mismatch in the Pipecat prebuilt frontend dependencies.
  - *Fix*: Verified and installed the correct `pipecat-ai-prebuilt` Python module.

- **Session Dropping Mid-Call**
  - *Problem*: The server would crash and drop the call ungracefully.
  - *Cause*: A stale `RNNoiseFilter` import in the transport params was throwing a `NameError` as soon as the WebRTC stream started. 
  - *Fix*: Removed the broken filter call from the transport initialization in `main.py`.

- **Double VAD Adding Severe Latency**
  - *Problem*: Long awkward pauses before the bot responded.
  - *Cause*: Both the client (browser) and the server were running VAD simultaneously, causing frame buffering delays.
  - *Fix*: Tuned the server-side `SileroVADAnalyzer` natively (`stop_secs=1.5`, `min_volume=0.8`) and let it drive the turn-taking.

- **Language Misclassification (Accented English)**
  - *Problem*: Gemini was transcribing Indian-accented English as Hindi/Sinhala script, which completely broke the prompt's instructions and caused massive 6–12s latency spikes.
  - *Fix*: Implemented a monkeypatch in `voice_engine.py` to forcibly inject `language_codes = ["en-US"]` into the Pipecat `InputAudioTranscriptionConfig`. As a fallback, we added the OpenAI Realtime engine for better baseline handling of heavy accents.

- **macOS SSL Verification Failures**
  - *Problem*: The OpenAI Realtime engine failed to connect on macOS with `[SSL: CERTIFICATE_VERIFY_FAILED]`.
  - *Cause*: OpenAI's websockets use the system's Python CA trust store, which is unpopulated by default on macOS.
  - *Fix*: Imported `certifi` and manually mapped the `SSL_CERT_FILE` environment variable in `main.py` at boot.

- **Greeting Race Condition**
  - *Problem*: The agent would say its greeting and immediately ask Question 1 without letting the user confirm they were ready.
  - *Cause*: The system prompt allowed it to merge the greeting and the first question in a single turn.
  - *Fix*: Updated `flow.py` to strictly enforce a two-step "Greet then Wait" logic.

---

## Known Limitations / Next Steps

- **Accent Sensitivity**: While forced to English, extreme accents may still experience occasional hallucinated transcriptions depending on the engine. OpenAI is generally more forgiving of heavy accents than Gemini.
- **Network Dependency**: As a true real-time streaming architecture, latency (TTFB) is highly dependent on the host network speed and geographical proximity to Google/OpenAI edge servers.
- **Stage 4 Implementation**: The final stage—persisting the captured `SurveyState` out to flat files (`responses.json`, `analytics.json`, and `.xlsx`) upon survey completion—is architected but not yet implemented.
- **Production UI**: The current UI is a developer test harness. The next phase involves spinning up a dedicated Next.js/React frontend utilizing the RTVI client SDK to communicate with this backend.
