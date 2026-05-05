class Player:
    def __init__(self, x=0, y=0):
        self.x = x
        self.y = y
    def move(self, dx, dy):
        self.x += dx
        self.y += dy
    def to_dict(self):
        return {"x": self.x, "y": self.y}