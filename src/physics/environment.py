import pymunk

class Environment:
    def __init__(self, gravity=(0, -981)): 
        self.space = pymunk.Space()
        self.space.gravity = gravity

    def add_static_segment(self, start, end, thickness=1.0):
        body = pymunk.Body(body_type=pymunk.Body.STATIC)
        shape = pymunk.Segment(body, start, end, thickness)
        self.space.add(body, shape)
        return shape

    def step(self, dt):
        self.space.step(dt)