import asyncio
import websockets
import json
from engine import Engine

# session_id -> websocket
clients = {}
# session_id -> poslednja komanda
move_commands = {}

engine = Engine()

TICK_RATE = 20  # 20 puta u sekundi
TICK_INTERVAL = 1 / TICK_RATE

async def handle_client(websocket):
    session_id = None
    try:
        # Prva poruka mora biti session_id
        raw = await websocket.recv()
        hello = json.loads(raw)
        if hello.get("type") != "hello" or "session_id" not in hello:
            await websocket.close()
            return
        session_id = hello["session_id"]
        # Samo jedna konekcija po session_id
        if session_id in clients:
            await websocket.send(json.dumps({"type": "error", "msg": "Already connected in another tab."}))
            await websocket.close()
            return
        clients[session_id] = websocket
        engine.add_player(session_id)
        print(f"[+] Klijent {session_id} se povezao. Ukupno: {len(clients)}")
        await websocket.send(json.dumps({"type": "welcome", "session_id": session_id}))

        async for message in websocket:
            try:
                data = json.loads(message)
                if data.get("type") == "move" and "dx" in data and "dy" in data:
                    move_commands[session_id] = (data["dx"], data["dy"])
            except Exception as e:
                print(f"[!] Error handling message: {e}")
    except websockets.ConnectionClosed:
        pass
    finally:
        if session_id and session_id in clients and clients[session_id] == websocket:
            del clients[session_id]
            engine.remove_player(session_id)
            if session_id in move_commands:
                del move_commands[session_id]
            print(f"[-] Klijent {session_id} se odspojio. Ukupno: {len(clients)}")

async def tick_loop():
    while True:
        # Obrada svih komandi
        for session_id, (dx, dy) in list(move_commands.items()):
            engine.move_player(session_id, dx, dy)
        # Šalji stanje svim klijentima
        state = engine.get_state()
        msg = json.dumps({"type": "state", "state": state})
        to_remove = []
        for sid, ws in list(clients.items()):
            try:
                await ws.send(msg)
            except Exception:
                to_remove.append(sid)
        for sid in to_remove:
            if sid in clients:
                del clients[sid]
            engine.remove_player(sid)
            if sid in move_commands:
                del move_commands[sid]
        await asyncio.sleep(TICK_INTERVAL)

async def main():
    print("Server sluša na ws://localhost:8765")
    async with websockets.serve(handle_client, "localhost", 8765):
        await tick_loop()

asyncio.run(main())