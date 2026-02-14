import pymunk

class Environment:
    def __init__(self, gravity=(0, -981)): 
        """
        Initializes the Pymunk physics world.
        :param gravity: A tuple (x, y). Default is Earth-like gravity (downward).
        """
        # The 'Space' is the simulation container where all physics happens
        self.space = pymunk.Space()
        self.space.gravity = gravity

    def add_static_segment(self, start, end, thickness=1.0):
        """
        Creates an immovable line segment, usually used for floors or walls.
        :param start: (x, y) starting coordinates.
        :param end: (x, y) ending coordinates.
        :param thickness: The 'radius' or width of the line.
        """
        # STATIC bodies do not move and are not affected by gravity or collisions
        body = pymunk.Body(body_type=pymunk.Body.STATIC)
        shape = pymunk.Segment(body, start, end, thickness)
        
        # Static shapes need a high friction by default to allow creatures to push off them
        shape.friction = 1.0 
        
        self.space.add(body, shape)
        return shape

    def step(self, dt):
        """
        Advances the physics simulation by a small time delta.
        :param dt: The time step (usually 1/60 for 60FPS).
        """
        # Moving the 'clock' of the physics engine forward
        self.space.step(dt)