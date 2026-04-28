import asyncio
import websockets
import json

# session_id -> websocket
clients = {}

async def handle_client(websocket):
    session_id = None
    try:
        # First message must be session_id
        raw = await websocket.recv()
        hello = json.loads(raw)
        if hello.get("type") != "hello" or "session_id" not in hello:
            await websocket.close()
            return
        session_id = hello["session_id"]
        # Only one connection per session_id
        if session_id in clients:
            await websocket.send(json.dumps({"type": "error", "msg": "Already connected in another tab."}))
            await websocket.close()
            return
        clients[session_id] = websocket
        print(f"[+] Klijent {session_id} se povezao. Ukupno: {len(clients)}")
        await websocket.send(json.dumps({"type": "welcome", "session_id": session_id}))

        async for message in websocket:
            try:
                data = json.loads(message)
                if data.get("type") == "msg" and "text" in data:
                    # Broadcast to all except sender
                    for sid, ws in clients.items():
                        if ws != websocket:
                            await ws.send(json.dumps({"type": "msg", "from": session_id, "text": data["text"]}))
            except Exception as e:
                print(f"[!] Error handling message: {e}")
    except websockets.ConnectionClosed:
        pass
    finally:
        if session_id and session_id in clients and clients[session_id] == websocket:
            del clients[session_id]
            print(f"[-] Klijent {session_id} se odspojio. Ukupno: {len(clients)})")

async def main():
    print("Server sluša na ws://localhost:8765")
    async with websockets.serve(handle_client, "localhost", 8765):
        await asyncio.Future()

asyncio.run(main())