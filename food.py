import random
from config import WORLD_WIDTH, WORLD_HEIGHT

class Food:
    def __init__(self):
        self.x = random.randint(0, WORLD_WIDTH)
        self.y = random.randint(0, WORLD_HEIGHT)
        self.hue = random.randint(0, 360)
        self.value = 1

    def to_dict(self):
        return {"x": self.x, "y": self.y, "hue": self.hue, "value": self.value}