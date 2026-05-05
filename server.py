"""
Agar.io Autoritativni Python Server
=====================================
Pokretanje: python server.py
Zahteva: pip install websockets==16.0
"""

import asyncio
import json
import math
import random
import time
import uuid
import websockets
from dataclasses import dataclass, field
from typing import Dict, List, Optional

# ─── KONSTANTE ───────────────────────────────────────────────────────────────
WORLD_SIZE        = 4000
TICK_RATE         = 25          # tika u sekundi
TICK_DELTA        = 1.0 / TICK_RATE
FOOD_COUNT        = 600
VIRUS_COUNT       = 18
BOT_COUNT         = 20
MERGE_TIME        = 10.0        # sekundi pre spajanja split ćelija
DECAY_THRESHOLD   = 200.0
DECAY_RATE        = 0.0035      # % gubitka mase po tiku
EJECT_COST        = 18.0
EJECT_MASS        = 14.0
SPLIT_MIN_MASS    = 36.0
MAX_SPLITS        = 16
VIRUS_SPLIT_MASS  = 133.0
VIRUS_FEED_COUNT  = 7           # koliko peleta virus mora da pojede da se podeli
GRID_CELL_SIZE    = 250         # velicina spatial grid celije
VIEWPORT_W        = 1800.0      # sirma viewporta u world jedinicama
VIEWPORT_H        = 1400.0
LEADERBOARD_EVERY = 1.0         # sekundi

BOT_NAMES = [
    "Moose","Panda","Rex","Nova","Ace","Zara","Kira","Bolt",
    "Finn","Pixel","Echo","Storm","Blaze","Cleo","Rift","Axel",
    "Dusk","Ember","Fang","Ghost"
]

# ─── UTILITY FUNKCIJE ────────────────────────────────────────────────────────
def rnd(a: float, b: float) -> float:
    return random.uniform(a, b)

def mass_to_radius(mass: float) -> float:
    return math.sqrt(mass / math.pi) * 4.0

def dist2(ax, ay, bx, by) -> float:
    return math.hypot(ax - bx, ay - by)

def clamp(v, lo, hi):
    return max(lo, min(hi, v))

def new_id() -> str:
    return uuid.uuid4().hex[:12]

# ─── DATACLASS-OVI ───────────────────────────────────────────────────────────
@dataclass
class Cell:
    id: str
    owner_id: str
    x: float
    y: float
    mass: float
    vx: float = 0.0
    vy: float = 0.0
    merge_timer: float = 0.0   # sekundi pre nego sto moze da se spoji

    @property
    def radius(self) -> float:
        return mass_to_radius(self.mass)

    @property
    def speed(self) -> float:
        return 8 / (math.log10(max(self.mass-50, 1.0))+1)

@dataclass
class FoodPellet:
    id: str
    x: float
    y: float
    mass: float
    hue: int
    vx: float = 0.0
    vy: float = 0.0
    ejected: bool = False

@dataclass
class Virus:
    id: str
    x: float
    y: float
    mass: float = 100.0
    fed_count: int = 0

    @property
    def radius(self) -> float:
        return mass_to_radius(self.mass)

@dataclass
class Player:
    player_id: str
    session_id: str
    name: str
    hue: int
    cells: List[Cell] = field(default_factory=list)
    is_bot: bool = False
    dead: bool = False
    # Input state
    target_x: float = WORLD_SIZE / 2.0
    target_y: float = WORLD_SIZE / 2.0
    wants_split: bool = False
    wants_eject: bool = False
    # Bot AI state
    think_timer: float = 0.0
    bot_tx: float = WORLD_SIZE / 2.0
    bot_ty: float = WORLD_SIZE / 2.0

    @property
    def total_mass(self) -> float:
        return sum(c.mass for c in self.cells)

    @property
    def cx(self) -> float:
        tm = self.total_mass
        if tm == 0:
            return WORLD_SIZE / 2.0
        return sum(c.x * c.mass for c in self.cells) / tm

    @property
    def cy(self) -> float:
        tm = self.total_mass
        if tm == 0:
            return WORLD_SIZE / 2.0
        return sum(c.y * c.mass for c in self.cells) / tm

# ─── GAME WORLD ──────────────────────────────────────────────────────────────
class GameWorld:
    def __init__(self):
        self.players: Dict[str, Player] = {}
        self.food: Dict[str, FoodPellet] = {}
        self.viruses: Dict[str, Virus] = {}
        self._spawn_initial_food()
        self._spawn_viruses()

    def _spawn_initial_food(self):
        while len(self.food) < FOOD_COUNT:
            self._add_food_pellet()

    def _add_food_pellet(self, x=None, y=None, mass=None, hue=None,
                          vx=0.0, vy=0.0, ejected=False):
        fid = new_id()
        r = random.random()
        if mass is None:
            mass = 1.0 if r < 0.6 else (3.0 if r < 0.9 else 5.0)
        self.food[fid] = FoodPellet(
            id=fid,
            x=x if x is not None else rnd(20, WORLD_SIZE - 20),
            y=y if y is not None else rnd(20, WORLD_SIZE - 20),
            mass=mass,
            hue=hue if hue is not None else random.randint(0, 359),
            vx=vx, vy=vy, ejected=ejected
        )
        return fid

    def _spawn_viruses(self):
        for _ in range(VIRUS_COUNT):
            self._add_virus()

    def _add_virus(self, x=None, y=None):
        vid = new_id()
        self.viruses[vid] = Virus(
            id=vid,
            x=x if x is not None else rnd(100, WORLD_SIZE - 100),
            y=y if y is not None else rnd(100, WORLD_SIZE - 100),
        )

    def add_player(self, session_id: str, name: str, is_bot=False) -> Player:
        pid = new_id()
        hue = random.randint(0, 359)
        start_x = rnd(200, WORLD_SIZE - 200)
        start_y = rnd(200, WORLD_SIZE - 200)
        cell = Cell(id=new_id(), owner_id=pid,
                    x=start_x, y=start_y, mass=50.0)
        player = Player(
            player_id=pid, session_id=session_id,
            name=name, hue=hue, cells=[cell], is_bot=is_bot
        )
        player.target_x = start_x
        player.target_y = start_y
        player.bot_tx = rnd(0, WORLD_SIZE)
        player.bot_ty = rnd(0, WORLD_SIZE)
        self.players[pid] = player
        return player

    def remove_player(self, player_id: str):
        self.players.pop(player_id, None)

    def refill_food(self):
        while len(self.food) < FOOD_COUNT:
            self._add_food_pellet()

    def refill_viruses(self):
        while len(self.viruses) < VIRUS_COUNT:
            self._add_virus()

# ─── SPATIAL GRID ────────────────────────────────────────────────────────────
def build_food_grid(world: GameWorld) -> dict:
    grid = {}
    for fid, f in world.food.items():
        key = (int(f.x // GRID_CELL_SIZE), int(f.y // GRID_CELL_SIZE))
        grid.setdefault(key, []).append(fid)
    return grid

def nearby_food_ids(grid: dict, cx: float, cy: float, radius: float):
    bx = int(cx // GRID_CELL_SIZE)
    by = int(cy // GRID_CELL_SIZE)
    span = int(radius // GRID_CELL_SIZE) + 1
    result = []
    for dx in range(-span, span + 1):
        for dy in range(-span, span + 1):
            result.extend(grid.get((bx + dx, by + dy), []))
    return result

# ─── FIZIKA ──────────────────────────────────────────────────────────────────
def move_cell(cell: Cell, tx: float, ty: float, dt: float):
    dx = tx - cell.x
    dy = ty - cell.y
    d = math.hypot(dx, dy) or 1.0
    sp = cell.speed * 60.0 * dt
    nx, ny = dx / d, dy / d
    cell.vx = cell.vx * 0.85 + nx * sp * 0.5
    cell.vy = cell.vy * 0.85 + ny * sp * 0.5
    max_sp = cell.speed * 2.0
    spd = math.hypot(cell.vx, cell.vy)
    if spd > max_sp:
        cell.vx *= max_sp / spd
        cell.vy *= max_sp / spd
    r = cell.radius
    cell.x = clamp(cell.x + cell.vx, r, WORLD_SIZE - r)
    cell.y = clamp(cell.y + cell.vy, r, WORLD_SIZE - r)

def apply_decay(cell: Cell, dt: float):
    if cell.mass > DECAY_THRESHOLD:
        cell.mass -= cell.mass * DECAY_RATE * dt
        if cell.mass < DECAY_THRESHOLD:
            cell.mass = DECAY_THRESHOLD

def update_merge_timer(cell: Cell, dt: float):
    if cell.merge_timer > 0:
        cell.merge_timer = max(0.0, cell.merge_timer - dt)

def update_ejected_food(world: GameWorld, dt: float):
    to_remove = []
    for fid, f in world.food.items():
        if not f.ejected:
            continue
        f.x += f.vx
        f.y += f.vy
        f.vx *= 0.88
        f.vy *= 0.88
        f.x = clamp(f.x, 0, WORLD_SIZE)
        f.y = clamp(f.y, 0, WORLD_SIZE)
        # Da li peleta udara u virus
        for vid, v in list(world.viruses.items()):
            if dist2(f.x, f.y, v.x, v.y) < v.radius + mass_to_radius(f.mass):
                f.ejected = False
                f.mass = 1.0
                v.fed_count += 1
                if v.fed_count >= VIRUS_FEED_COUNT:
                    v.fed_count = 0
                    # Virus se deli i ispaljivuje novi
                    if len(world.viruses) < VIRUS_COUNT + 5:
                        world._add_virus(v.x + rnd(-30, 30), v.y + rnd(-30, 30))
                break
    return to_remove

# ─── MERGE ĆELIJA ────────────────────────────────────────────────────────────
def try_merge_cells(player: Player):
    cells = player.cells
    i = 0
    while i < len(cells):
        j = i + 1
        while j < len(cells):
            a, b = cells[i], cells[j]
            if a.merge_timer > 0 or b.merge_timer > 0:
                j += 1
                continue
            d = dist2(a.x, a.y, b.x, b.y)
            overlap = a.radius + b.radius - min(a.radius, b.radius) * 0.5
            if d < overlap:
                a.mass += b.mass
                cells.pop(j)
            else:
                j += 1
        i += 1

# ─── SPLIT ───────────────────────────────────────────────────────────────────
def do_split(player: Player):
    if len(player.cells) >= MAX_SPLITS:
        return
    new_cells = []
    for cell in list(player.cells):
        if cell.mass < SPLIT_MIN_MASS * 2:
            continue
        if len(player.cells) + len(new_cells) >= MAX_SPLITS:
            break
        dx = player.target_x - cell.x
        dy = player.target_y - cell.y
        d = math.hypot(dx, dy) or 1.0
        half = cell.mass / 2.0
        cell.mass = half
        child = Cell(id=new_id(), owner_id=player.player_id,
                     x=cell.x, y=cell.y, mass=half)
        child.vx = (dx / d) * child.speed * 12.0
        child.vy = (dy / d) * child.speed * 12.0
        child.merge_timer = MERGE_TIME
        cell.merge_timer = MERGE_TIME
        new_cells.append(child)
    player.cells.extend(new_cells)

# ─── EJECT ───────────────────────────────────────────────────────────────────
def do_eject(player: Player, world: GameWorld):
    for cell in player.cells:
        if cell.mass < EJECT_COST + 20:
            continue
        dx = player.target_x - cell.x
        dy = player.target_y - cell.y
        d = math.hypot(dx, dy) or 1.0
        cell.mass -= EJECT_COST
        ex = cell.x + (dx / d) * (cell.radius + 5)
        ey = cell.y + (dy / d) * (cell.radius + 5)
        world._add_food_pellet(
            x=ex, y=ey, mass=EJECT_MASS,
            hue=player.hue,
            vx=(dx / d) * 9.0,
            vy=(dy / d) * 9.0,
            ejected=True
        )

# ─── VIRUS POP ───────────────────────────────────────────────────────────────
def pop_cell(cell: Cell, player: Player):
    pops = min(8, MAX_SPLITS - len(player.cells) + 1)
    if pops <= 0:
        return
    new_cells = []
    for i in range(pops):
        angle = (i / pops) * math.pi * 2
        child = Cell(id=new_id(), owner_id=player.player_id,
                     x=cell.x, y=cell.y,
                     mass=cell.mass / (pops + 1))
        child.vx = math.cos(angle) * child.speed * 8.0
        child.vy = math.sin(angle) * child.speed * 8.0
        child.merge_timer = MERGE_TIME
        new_cells.append(child)
    cell.mass /= (pops + 1)
    cell.merge_timer = MERGE_TIME
    player.cells.extend(new_cells)

# ─── KOLIZIJE ────────────────────────────────────────────────────────────────
def resolve_collisions(world: GameWorld):
    food_grid = build_food_grid(world)
    eaten_food = set()
    dead_cells = set()
    dead_players = set()

    all_players = list(world.players.values())

    for player in all_players:
        if player.dead:
            continue
        for cell in player.cells:
            # Jedenje hrane
            for fid in nearby_food_ids(food_grid, cell.x, cell.y, cell.radius + 10):
                if fid in eaten_food:
                    continue
                f = world.food.get(fid)
                if f is None:
                    continue
                if dist2(cell.x, cell.y, f.x, f.y) < cell.radius:
                    cell.mass += f.mass
                    eaten_food.add(fid)

            # Interakcija sa virusima
            for vid, v in list(world.viruses.items()):
                if cell.mass > VIRUS_SPLIT_MASS:
                    if dist2(cell.x, cell.y, v.x, v.y) < cell.radius:
                        if not player.is_bot:
                            if len(player.cells) < MAX_SPLITS:
                                pop_cell(cell, player)
                        else:
                            cell.mass *= 0.7
                        break

    # Brisanje pojedene hrane
    for fid in eaten_food:
        world.food.pop(fid, None)

    # Igrač jede igrača
    for i, pred_player in enumerate(all_players):
        if pred_player.dead:
            continue
        for pred_cell in list(pred_player.cells):
            for j, prey_player in enumerate(all_players):
                if i == j or prey_player.dead:
                    continue
                for k in range(len(prey_player.cells) - 1, -1, -1):
                    prey_cell = prey_player.cells[k]
                    if pred_cell.mass > prey_cell.mass * 1.15:
                        d = dist2(pred_cell.x, pred_cell.y, prey_cell.x, prey_cell.y)
                        if d < pred_cell.radius - prey_cell.radius * 0.3:
                            pred_cell.mass += prey_cell.mass
                            dead_cells.add(prey_cell.id)
                            prey_player.cells.pop(k)
                if len(prey_player.cells) == 0:
                    dead_players.add(prey_player.player_id)

    return dead_players, dead_cells

# ─── BOT AI ──────────────────────────────────────────────────────────────────
def update_bot_ai(bot: Player, world: GameWorld, dt: float):
    bot.think_timer -= dt
    if bot.think_timer > 0:
        return

    bot.think_timer = rnd(0.3, 0.9)
    best_target = None
    best_score = float('inf')

    # Traži obližnju hranu
    for f in world.food.values():
        d = dist2(bot.cx, bot.cy, f.x, f.y)
        if d < best_score:
            best_score = d
            best_target = (f.x, f.y)

    # Juri manje igrače
    bot_mass = bot.total_mass
    for other in world.players.values():
        if other.player_id == bot.player_id or other.dead:
            continue
        if other.total_mass * 1.2 < bot_mass:
            d = dist2(bot.cx, bot.cy, other.cx, other.cy)
            if d < best_score * 0.6:
                best_score = d
                best_target = (other.cx, other.cy)

    # Beži od većih igrača
    for other in world.players.values():
        if other.player_id == bot.player_id or other.dead:
            continue
        if other.total_mass * 1.2 > bot_mass:
            d = dist2(bot.cx, bot.cy, other.cx, other.cy)
            if d < 400:
                # Pobegni u suprotnom smeru
                flee_x = bot.cx * 2 - other.cx
                flee_y = bot.cy * 2 - other.cy
                bot.bot_tx = clamp(flee_x, 0, WORLD_SIZE)
                bot.bot_ty = clamp(flee_y, 0, WORLD_SIZE)
                bot.target_x = bot.bot_tx
                bot.target_y = bot.bot_ty
                return

    if best_target:
        bot.bot_tx = best_target[0]
        bot.bot_ty = best_target[1]
    else:
        bot.bot_tx = rnd(0, WORLD_SIZE)
        bot.bot_ty = rnd(0, WORLD_SIZE)

    bot.target_x = bot.bot_tx
    bot.target_y = bot.bot_ty

# ─── VIEWPORT FILTRIRANJE ────────────────────────────────────────────────────
def viewport_for_player(player: Player) -> tuple:
    """Vraca (min_x, min_y, max_x, max_y) vidljivog dela sveta."""
    tm = player.total_mass
    zoom = min(1.5, max(0.15, 64.0 / math.sqrt(max(tm, 1.0))))
    half_w = (VIEWPORT_W / zoom) / 2.0
    half_h = (VIEWPORT_H / zoom) / 2.0
    cx, cy = player.cx, player.cy
    return (cx - half_w, cy - half_h, cx + half_w, cy + half_h)

def build_tick_payload(world: GameWorld, player: Player) -> dict:
    vp = viewport_for_player(player)
    min_x, min_y, max_x, max_y = vp

    cells_out = []
    for p in world.players.values():
        if p.dead:
            continue
        for c in p.cells:
            # Uvek uključi sopstvene ćelije
            if p.player_id == player.player_id:
                cells_out.append({
                    "id": c.id, "pid": p.player_id,
                    "name": p.name, "hue": p.hue,
                    "x": round(c.x, 1), "y": round(c.y, 1),
                    "mass": round(c.mass, 1), "mine": True
                })
            elif (min_x - 100 < c.x < max_x + 100 and
                  min_y - 100 < c.y < max_y + 100):
                cells_out.append({
                    "id": c.id, "pid": p.player_id,
                    "name": p.name, "hue": p.hue,
                    "x": round(c.x, 1), "y": round(c.y, 1),
                    "mass": round(c.mass, 1), "mine": False
                })

    food_out = []
    for f in world.food.values():
        if min_x < f.x < max_x and min_y < f.y < max_y:
            food_out.append({
                "id": f.id,
                "x": round(f.x, 1), "y": round(f.y, 1),
                "hue": f.hue, "mass": f.mass
            })

    viruses_out = []
    for v in world.viruses.values():
        if min_x < v.x < max_x and min_y < v.y < max_y:
            viruses_out.append({
                "id": v.id,
                "x": round(v.x, 1), "y": round(v.y, 1)
            })

    return {
        "type": "tick",
        "t": round(time.monotonic(), 3),
        "cells": cells_out,
        "food": food_out,
        "viruses": viruses_out,
        "my_mass": round(player.total_mass, 0)
    }

def build_leaderboard(world: GameWorld) -> list:
    entries = []
    for p in world.players.values():
        if p.dead or p.is_bot and p.total_mass == 0:
            continue
        entries.append({"name": p.name, "mass": int(p.total_mass),
                         "player_id": p.player_id})
    entries.sort(key=lambda e: e["mass"], reverse=True)
    return entries[:10]

# ─── SESSION MANAGEMENT ──────────────────────────────────────────────────────
@dataclass
class Session:
    session_id: str
    websocket: object
    player_id: Optional[str] = None

sessions: Dict[str, Session] = {}   # session_id -> Session
world = GameWorld()

async def safe_send(ws, data: dict):
    try:
        await ws.send(json.dumps(data, separators=(',', ':')))
    except Exception:
        pass

async def broadcast_ticks():
    """Broadcastuje tick svim konektovanim igračima."""
    tasks = []
    for sid, session in list(sessions.items()):
        if session.player_id is None:
            continue
        player = world.players.get(session.player_id)
        if player is None or player.dead:
            continue
        payload = build_tick_payload(world, player)
        tasks.append(safe_send(session.websocket, payload))
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)

async def broadcast_leaderboard():
    """Broadcastuje leaderboard svim igračima."""
    lb = build_leaderboard(world)
    payload = json.dumps({"type": "leaderboard", "entries": lb},
                          separators=(',', ':'))
    tasks = []
    for sid, session in list(sessions.items()):
        tasks.append(safe_send(session.websocket, {"type": "leaderboard", "entries": lb}))
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)

# ─── GAME LOOP ───────────────────────────────────────────────────────────────
async def game_loop():
    last_time = time.monotonic()
    last_leaderboard = time.monotonic()
    lb_counter = 0

    # Dodaj botove
    for _ in range(BOT_COUNT):
        name = random.choice(BOT_NAMES)
        world.add_player(session_id=f"bot_{new_id()}", name=name, is_bot=True)

    print(f"[Game] Loop pokrenut @ {TICK_RATE} TPS")

    while True:
        loop_start = time.monotonic()
        dt = loop_start - last_time
        last_time = loop_start

        # ── 1. Primeni inpute i fiziku igrača ──
        for player in list(world.players.values()):
            if player.dead:
                continue

            # Bot AI
            if player.is_bot:
                update_bot_ai(player, world, dt)

            # Split i eject
            if player.wants_split:
                do_split(player)
                player.wants_split = False
            if player.wants_eject:
                do_eject(player, world)
                player.wants_eject = False

            # Pomeri ćelije
            for cell in player.cells:
                move_cell(cell, player.target_x, player.target_y, dt)
                apply_decay(cell, dt)
                update_merge_timer(cell, dt)

            # Spoji ćelije ako je moguće
            if len(player.cells) > 1:
                try_merge_cells(player)

        # ── 2. Ejected food fizika ──
        update_ejected_food(world, dt)

        # ── 3. Kolizije ──
        dead_players, dead_cells = resolve_collisions(world)

        # ── 4. Obradi mrtve igrače ──
        for pid in dead_players:
            player = world.players.get(pid)
            if player is None:
                continue
            player.dead = True
            if not player.is_bot:
                # Obavesti klijenta
                session = next(
                    (s for s in sessions.values() if s.player_id == pid), None
                )
                if session:
                    await safe_send(session.websocket, {
                        "type": "died",
                        "final_mass": int(player.total_mass)
                    })
            world.remove_player(pid)

        # ── 5. Respawn botova ──
        bots = [p for p in world.players.values() if p.is_bot and not p.dead]
        while len(bots) < BOT_COUNT:
            name = random.choice(BOT_NAMES)
            world.add_player(session_id=f"bot_{new_id()}", name=name, is_bot=True)
            bots = [p for p in world.players.values() if p.is_bot and not p.dead]

        # ── 6. Dopuni hranu i viruse ──
        world.refill_food()
        world.refill_viruses()

        # ── 7. Broadcast tick ──
        await broadcast_ticks()

        # ── 8. Leaderboard svakih ~1s ──
        lb_counter += 1
        if time.monotonic() - last_leaderboard >= LEADERBOARD_EVERY:
            await broadcast_leaderboard()
            last_leaderboard = time.monotonic()

        # ── Precizno čekanje do sledećeg tika ──
        elapsed = time.monotonic() - loop_start
        sleep_for = max(0.0, TICK_DELTA - elapsed)
        await asyncio.sleep(sleep_for)

# ─── WEBSOCKET HANDLER ───────────────────────────────────────────────────────
async def handle_client(websocket):
    session_id = None
    player_id = None

    try:
        # ── Handshake ──
        raw = await asyncio.wait_for(websocket.recv(), timeout=15.0)
        hello = json.loads(raw)

        if hello.get("type") != "hello" or "session_id" not in hello:
            await safe_send(websocket, {"type": "error", "msg": "Neispravan handshake."})
            return

        session_id = hello["session_id"]

        # Ako je isti tab reconnektovan
        if session_id in sessions:
            old_session = sessions[session_id]
            try:
                await old_session.websocket.close()
            except Exception:
                pass
            # Zadrzavamo player_id ako igrač nije mrtav
            if old_session.player_id and old_session.player_id in world.players:
                player_id = old_session.player_id

        session = Session(session_id=session_id, websocket=websocket,
                          player_id=player_id)
        sessions[session_id] = session

        await safe_send(websocket, {
            "type": "welcome",
            "session_id": session_id,
            "world_size": WORLD_SIZE
        })
        print(f"[+] Klijent {session_id[:8]}... povezan. Ukupno: {len(sessions)}")

        # ── Glavna petlja poruka ──
        async for message in websocket:
            try:
                data = json.loads(message)
                msg_type = data.get("type")

                if msg_type == "join":
                    name = str(data.get("name", "Igrač"))[:16].strip() or "Igrač"
                    # Ako igrač već postoji (reconnect), ne kreiraj novog
                    if player_id and player_id in world.players:
                        pass
                    else:
                        player = world.add_player(session_id=session_id, name=name)
                        player_id = player.player_id
                        session.player_id = player_id
                    p = world.players[player_id]
                    await safe_send(websocket, {
                        "type": "init",
                        "player_id": player_id,
                        "hue": p.hue,
                        "name": p.name,
                        "world_size": WORLD_SIZE
                    })
                    print(f"  [{session_id[:8]}] Ušao kao '{p.name}'")

                elif msg_type == "input":
                    if player_id and player_id in world.players:
                        p = world.players[player_id]
                        p.target_x = float(data.get("tx", p.target_x))
                        p.target_y = float(data.get("ty", p.target_y))
                        if data.get("split"):
                            p.wants_split = True
                        if data.get("eject"):
                            p.wants_eject = True

                elif msg_type == "respawn":
                    if player_id:
                        world.remove_player(player_id)
                    name = str(data.get("name", "Igrač"))[:16].strip() or "Igrač"
                    player = world.add_player(session_id=session_id, name=name)
                    player_id = player.player_id
                    session.player_id = player_id
                    p = world.players[player_id]
                    await safe_send(websocket, {
                        "type": "init",
                        "player_id": player_id,
                        "hue": p.hue,
                        "name": p.name,
                        "world_size": WORLD_SIZE
                    })

            except (json.JSONDecodeError, KeyError, ValueError) as e:
                pass

    except asyncio.TimeoutError:
        print(f"[!] Timeout za {session_id}")
    except websockets.ConnectionClosed:
        pass
    except Exception as e:
        print(f"[!] Greška: {e}")
    finally:
        if session_id and session_id in sessions:
            # Ukloni samo ako je ovo aktuelna sesija (ne reconnect)
            if sessions[session_id].websocket is websocket:
                del sessions[session_id]
                if player_id:
                    world.remove_player(player_id)
                print(f"[-] Klijent {(session_id or '?')[:8]}... otišao. Ukupno: {len(sessions)}")

# ─── MAIN ────────────────────────────────────────────────────────────────────
async def main():
    print("=" * 50)
    print("  Agar.io Autoritativni Server")
    print("  Adresa: ws://localhost:8765")
    print(f"  Tick rate: {TICK_RATE} TPS")
    print(f"  Svet: {WORLD_SIZE}x{WORLD_SIZE}")
    print(f"  Botovi: {BOT_COUNT}")
    print("=" * 50)

    # Pokreni game loop i websocket server paralelno
    async with websockets.serve(handle_client, "localhost", 8765):
        await game_loop()

if __name__ == "__main__":
    asyncio.run(main())