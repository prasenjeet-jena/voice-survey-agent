# Production Cost Estimation

This document outlines the estimated costs of running the Voice Survey Agent in a production environment at scale, comparing the **OpenAI Realtime** and **Gemini Live** engines.

## 1. Base Assumptions (Per Session)
- **Survey Length**: 20 questions.
- **Average Conversational Turns**: ~25 turns per user (factoring in greetings, off-topic handling, and multi-question inference).
- **Total Session Duration**: ~5 minutes.
  - **User Speaking Time**: ~2 minutes (120 seconds).
  - **Agent Speaking Time**: ~3 minutes (180 seconds).
- **System Prompt & Tool Context**: ~1,500 tokens (which grows cumulatively with conversation history).

---

## 2. OpenAI Realtime (`gpt-4o-mini-realtime`)

OpenAI charges distinct, premium rates for native Audio tokens compared to standard text tokens.
- **Audio Input Rate**: $10.00 per 1M tokens (~40 tokens per second).
- **Audio Output Rate**: $20.00 per 1M tokens (~40 tokens per second).
- **Text Input Rate**: $0.60 per 1M tokens.

### Per-Survey Calculation:
1. **Audio Input (User)**: 2 minutes = ~4,800 tokens = **$0.048**
2. **Audio Output (Agent)**: 3 minutes = ~7,200 tokens = **$0.144**
3. **Text Context & Tool Calling**: Cumulative context across 25 turns = ~30,000 input text tokens + ~1,000 output text tokens = **~$0.020**

**Estimated Cost per Survey**: **~$0.21**

### Production Scale (OpenAI):
- **1,000 users**: $210
- **10,000 users**: $2,100
- **100,000 users**: $21,000

---

## 3. Gemini Live (`gemini-2.5-flash-native-audio-preview`)

Google's Gemini Flash tier is heavily optimized for cost-efficiency, processing multimodal audio inputs at a fraction of the cost of standard text-to-speech pipelines.
- **Multimodal Input Rate**: ~$0.075 per 1M tokens (Audio tokenizes at ~25 tokens per second).
- **Audio Output Rate**: Gemini Native Audio output is generally significantly cheaper than GPT-4o-mini, heavily subsidized for the Flash tier. 

### Per-Survey Calculation:
1. **Audio Input (User)**: 2 minutes = ~ 3,000 tokens = **~$0.0002**
2. **Audio Output (Agent)**: 3 minutes = **~$0.015** (Estimated native audio generation rate)
3. **Text Context & Tool Calling**: **~$0.005**

**Estimated Cost per Survey**: **~$0.02**

### Production Scale (Gemini):
- **1,000 users**: $20
- **10,000 users**: $200
- **100,000 users**: $2,000

---

## 4. Other Production Costs to Consider

Beyond the core LLM API costs, running this at scale will incur infrastructure costs:

1. **WebRTC Server (Backend)**: 
   - A standard Kubernetes cluster or auto-scaling VM group (e.g., AWS EC2, GCP Compute Engine).
   - Real-time voice processing requires decent CPU bandwidth. Expect to run multiple instances to handle concurrent WebSocket/WebRTC connections.
   - *Est. Cost: $50 - $200/month depending on traffic spikes.*
2. **Bandwidth / Egress**:
   - Streaming bidirectional audio (16kHz - 24kHz PCM) consumes roughly 0.5 MB per minute per user.
   - 10,000 surveys * 5 mins = ~25 GB of egress traffic, which is negligible (usually under $5/month).
3. **Database / Storage**:
   - Storing the final `responses.json`, analytics metadata, and potentially the raw audio logs (if compliance allows) in an S3 bucket or PostgreSQL database.
   - *Est. Cost: $10 - $30/month.*

## Conclusion
For an initial POC or low-volume testing (under 1,000 users), **OpenAI Realtime** provides exceptional accent comprehension at a manageable cost (~$210). However, for mass-market production scale (100k+ surveys), **Gemini Live** is the financially viable choice, reducing API costs by nearly 10x while maintaining excellent conversational flow.
