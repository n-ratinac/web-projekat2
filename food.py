import random
class Food:
    def __init__(self,WORLD_WIDTH,WORLD_HEIGHT):
        self.x = random.randint(0,WORLD_WIDTH)
        self.y = random.randint(0,WORLD_HEIGHT)
        self.color = random.choice(['red','blue','green','yellow'])
        self.value = 1
