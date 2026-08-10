import asyncio
import os

async def main():
    api_key = os.environ["OPENAI_API_KEY"]
    model = "gpt-realtime-2.1-mini"
    
    # Let's just use pipecat's websocket client to be sure
    from pipecat.transports.network.websocket_client import WebsocketClientTransport
    print("This would test it.")

asyncio.run(main())
