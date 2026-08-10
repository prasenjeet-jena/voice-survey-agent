import asyncio
import sys
import websockets
import json

async def run_client():
    uri = "ws://localhost:8000/ws"  # Or whatever the endpoint is.
    print(f"Connecting to {uri}")
    try:
        async with websockets.connect(uri) as websocket:
            print("Connected. Sending client-ready")
            await websocket.send(json.dumps({
                "type": "action",
                "action": "client-ready",
                "version": "2.1.0"
            }))
            while True:
                msg = await websocket.recv()
                print(f"Received: {msg[:200]}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(run_client())
