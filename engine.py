from config import WORLD_WIDTH, WORLD_HEIGHT
import random
from player import Player
from food import Food
class Engine:
    def __init__(self, width=WORLD_WIDTH, height=WORLD_HEIGHT):
        self.width = width
        self.height = height
        self.players = {}  # session_id -> player data
        self.food = self.init_food(60)
    
    def init_food(self,i):
        return [Food() for x in range (i) ]

    def add_player(self, session_id):
        self.players[session_id] = Player(x=random.randint(0, self.width), y=random.randint(0, self.height))

    def remove_player(self, session_id):
        if session_id in self.players:
            del self.players[session_id]

    def move_player(self, session_id, dx, dy):
        if session_id in self.players:
            player = self.players[session_id]
            player.move(dx, dy)


    def get_state(self):
        return {"players": {sid: p.to_dict() for sid, p in self.players.items()}}