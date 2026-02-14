import pymunk
import pygame
import math
import random

class Creature:
    def __init__(self, space, pos, n_segments=3, dna=None):
        """
        Initializes a multi-segmented physics creature.
        :param space: The Pymunk physics space.
        :param pos: Initial (x, y) spawn position.
        :param n_segments: Number of rectangular bodies linked together.
        :param dna: Dictionary of genetic traits. If None, random traits are generated.
        """
        self.space = space
        self.n_segments = n_segments
        self.bodies = []
        self.shapes = []
        self.motors = []
        
        # Collision group to prevent segments of the same creature from colliding with each other
        CREATURE_GROUP = 1

        # --- DNA / Genetic Traits ---
        if dna is None:
            self.dna = {
                "width": random.uniform(30, 50),          # Length of each segment
                "height": random.uniform(8, 15),          # Thickness of each segment
                "friction": random.uniform(0.1, 1.5),     # How well it grips the ground
                "speed_multiplier": random.uniform(2.0, 8.0), # Maximum angular velocity
                "phase_offset": random.uniform(0.2, 1.0)  # Timing difference between segments
            }
        else:
            self.dna = dna

        last_body = None
        
        # --- Physical Construction ---
        for i in range(self.n_segments):
            mass = 1
            size = (self.dna["width"], self.dna["height"])
            
            # Calculate moment of inertia for a rectangle
            moment = pymunk.moment_for_box(mass, size)
            body = pymunk.Body(mass, moment)
            
            # Position segments side-by-side horizontally
            body.position = (pos[0] + i * self.dna["width"], pos[1])
            shape = pymunk.Poly.create_box(body, size)
            shape.friction = self.dna["friction"]

            # Filter prevents self-collision (collision with same group = ignored)
            shape.filter = pymunk.ShapeFilter(group=CREATURE_GROUP)
            
            # Procedural color based on the speed trait
            shape.color = (int(self.dna["speed_multiplier"] * 30) % 255, 100, 200)
            
            self.space.add(body, shape)
            self.bodies.append(body)
            self.shapes.append(shape)

            # --- Jointing System ---
            if last_body:
                # 1. PivotJoint: Acts as a hinge between the current and previous segment
                pivot_pos = (body.position.x - self.dna["width"]/2, body.position.y)
                joint = pymunk.PivotJoint(last_body, body, pivot_pos)
                
                # 2. SimpleMotor: Provides the "muscle" force to rotate the segments
                motor = pymunk.SimpleMotor(last_body, body, 0)
                motor.max_force = 1000000 # High force to ensure movement
                
                # 3. RotaryLimitJoint: Prevents the creature from folding onto itself (spine limits)
                limit = pymunk.RotaryLimitJoint(last_body, body, -0.7, 0.7)
                
                self.space.add(joint, motor, limit)
                self.motors.append(motor)

            last_body = body

    def act(self, time):
        """
        Calculates and applies motor movement based on a sine wave.
        This creates the undulating movement pattern.
        """
        for i, motor in enumerate(self.motors):
            # Phase offset creates a 'traveling wave' through the segments
            # motor.rate is the target angular velocity
            motor.rate = self.dna["speed_multiplier"] * math.sin(time * 10 + i * self.dna["phase_offset"])

    def get_position(self):
        """Returns the X-coordinate of the head segment for distance tracking."""
        return self.bodies[0].position.x

    def draw(self, screen, screen_height):
        """
        Manually renders the Pymunk shapes using Pygame polygons.
        Handles coordinate conversion (Pymunk Y-up to Pygame Y-down).
        """
        for shape in self.shapes:
            points = []
            # Get the world-space coordinates of the box vertices
            for v in shape.get_vertices():
                # Rotate and translate vertex based on body state
                pos = v.rotated(shape.body.angle) + shape.body.position
                # Flip Y-axis for Pygame (0,0 is top-left)
                points.append((pos.x, screen_height - pos.y))
            
            color = getattr(shape, 'color', (100, 100, 100))
            pygame.draw.polygon(screen, color, points)
            pygame.draw.polygon(screen, (0, 0, 0), points, 2) # Black outline