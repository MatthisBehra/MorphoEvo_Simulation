import random
import math
import pymunk


# Friction zone definitions for Env A: (friction_coefficient, render_color)
# Cycles: grass → ice → sand → grass → …
_FRICTION_ZONES = [
    (1.0,  (34, 139,  34)),   # grass — friction normale
    (0.2,  (180, 220, 240)),  # glace  — très glissant
    (2.2,  (210, 170, 110)),  # sable  — très collant
]


class Environment:
    def __init__(self, gravity=(0, -981)):
        """
        Initializes the Pymunk physics world.
        :param gravity: A tuple (x, y). Default is Earth-like gravity (downward).
        """
        self.space = pymunk.Space()
        self.space.gravity = gravity
        # Static obstacles: [(shape, x, y_bottom, w, h)]
        self.obstacles = []
        # Kinematic (dynamic) obstacles: [dict]
        self.dynamic_obstacles = []
        # Procedural terrain: [(shape, color, x_start, x_end, angle_rad)]
        self.terrain_zones = []

    # ── Static geometry ───────────────────────────────────────────────────────

    def add_static_segment(self, start, end, thickness=1.0, friction=1.0):
        """
        Creates an immovable line segment (floor or wall).
        :param start:     (x, y) starting coordinates.
        :param end:       (x, y) ending coordinates.
        :param thickness: Radius of the line.
        :param friction:  Surface friction coefficient.
        """
        body  = pymunk.Body(body_type=pymunk.Body.STATIC)
        shape = pymunk.Segment(body, start, end, thickness)
        shape.friction = friction
        self.space.add(body, shape)
        return shape

    def add_friction_zones(self, total_x, ground_y=5,
                           zone_width=800, thickness=5.0):
        """
        Replace a single flat ground with alternating friction zones
        (grass / glace / sable), each zone_width units wide.

        Returns [(shape, color), ...] for rendering with per-zone colours.
        """
        zones = []
        x = 0
        zone_idx = 0
        while x < total_x:
            end_x            = min(x + zone_width, total_x)
            friction, color  = _FRICTION_ZONES[zone_idx % len(_FRICTION_ZONES)]
            body  = pymunk.Body(body_type=pymunk.Body.STATIC)
            seg   = pymunk.Segment(body, (x, ground_y), (end_x, ground_y), thickness)
            seg.friction = friction
            self.space.add(body, seg)
            zones.append((seg, color))
            x = end_x
            zone_idx += 1
        return zones

    def add_static_box(self, x, y_bottom, w, h):
        """
        Creates an immovable filled rectangle (obstacle).
        :param x:        Left edge X in world space.
        :param y_bottom: Bottom edge Y in world space (Pymunk Y-up).
        :param w:        Width.
        :param h:        Height.
        :return:         The pymunk Shape.
        """
        body  = pymunk.Body(body_type=pymunk.Body.STATIC)
        body.position = (x + w / 2, y_bottom + h / 2)
        shape = pymunk.Poly.create_box(body, (w, h))
        shape.friction = 1.0
        self.space.add(body, shape)
        return shape

    # ── Obstacle management ───────────────────────────────────────────────────

    def generate_obstacles(self, count, x_start=500, spacing=280,
                           min_h=10, max_h=40, w=20, ground_y=5):
        """
        Place *count* random-height static box obstacles along the X axis.
        """
        for i in range(count):
            x     = x_start + i * spacing
            h     = random.uniform(min_h, max_h)
            shape = self.add_static_box(x, ground_y, w, h)
            self.obstacles.append((shape, x, ground_y, w, h))

    def generate_dynamic_obstacles(self, count, x_start=500, spacing=280,
                                    ground_y=5, w=20, h_range=(15, 35),
                                    oscillation_amp=20, base_freq=0.4):
        """
        Place *count* kinematic obstacles that oscillate vertically.
        They rise and fall continuously, making them harder to time and cross.

        :param oscillation_amp: Max vertical displacement in world units.
        :param base_freq:       Oscillation frequency in Hz (randomised ±30%).
        """
        for i in range(count):
            x    = x_start + i * spacing
            h    = random.uniform(*h_range)
            body = pymunk.Body(body_type=pymunk.Body.KINEMATIC)
            body.position = (x + w / 2, ground_y + h / 2)
            shape = pymunk.Poly.create_box(body, (w, h))
            shape.friction = 1.0
            self.space.add(body, shape)
            self.dynamic_obstacles.append({
                "body":     body,
                "shape":    shape,
                "base_y":   ground_y + h / 2,
                "amp":      oscillation_amp,
                "freq":     base_freq * random.uniform(0.7, 1.3),
                "phase":    random.uniform(0, 2 * math.pi),
                "x":        x,
                "ground_y": ground_y,
                "w":        w,
                "h":        h,
            })

    def update_obstacles(self, time):
        """
        Move all kinematic obstacles according to their oscillation parameters.
        Call once per simulation step (before or after space.step).
        """
        for d in self.dynamic_obstacles:
            new_y = d["base_y"] + d["amp"] * math.sin(
                2 * math.pi * d["freq"] * time + d["phase"]
            )
            d["body"].position = (d["body"].position.x, new_y)

    @property
    def all_obstacles(self):
        """
        Return static + dynamic obstacles as (shape, x, y_bottom, w, h) tuples.
        Dynamic positions are read from the kinematic body's current location.
        """
        result = list(self.obstacles)
        for d in self.dynamic_obstacles:
            cx, cy = d["body"].position
            ox = cx - d["w"] / 2
            oy = cy - d["h"] / 2
            result.append((d["shape"], ox, oy, d["w"], d["h"]))
        return result

    def clear_obstacles(self):
        """Remove all obstacle bodies and shapes from the space."""
        for shape, *_ in self.obstacles:
            self.space.remove(shape.body, shape)
        self.obstacles.clear()
        for d in self.dynamic_obstacles:
            self.space.remove(d["body"], d["shape"])
        self.dynamic_obstacles.clear()

    # ── Procedural terrain ────────────────────────────────────────────────────

    # Terrain colours
    _TERRAIN_NORMAL = (100, 70, 30)    # brown
    _TERRAIN_SOFT   = (70, 100, 60)    # muddy green

    def generate_terrain(self, total_x, ground_y=5, seg_length=200,
                         max_angle_deg=25, soft_zone_prob=0.25,
                         thickness=5.0, flat_start=400):
        """
        Generate procedural terrain made of chained inclined segments.

        - First *flat_start* units are flat (spawning area).
        - Each subsequent segment has a random slope ∈ [−max_angle_deg, +max_angle_deg].
        - ~25 % of segments past the flat zone are "soft" (high friction, zero restitution).
        - Y is clamped to [ground_y − 40, ground_y + 80] to keep terrain walkable.

        Stores full data in self.terrain_zones for fitness calculation.
        Returns [(shape, color), …] for rendering (same format as add_friction_zones).
        """
        self.terrain_zones = []

        x = 0.0
        y = float(ground_y)

        while x < total_x:
            if x < flat_start:
                angle_rad = 0.0
            else:
                angle_rad = math.radians(random.uniform(-max_angle_deg, max_angle_deg))

            end_x = x + seg_length
            end_y = y + math.tan(angle_rad) * seg_length

            # Clamp Y then recompute actual angle
            end_y = max(ground_y - 40, min(ground_y + 80, end_y))
            angle_rad = math.atan2(end_y - y, end_x - x)

            is_soft = x >= flat_start and random.random() < soft_zone_prob

            friction    = random.uniform(1.5, 2.0) if is_soft else 0.7
            restitution = 0.0                      if is_soft else 0.3
            color       = self._TERRAIN_SOFT        if is_soft else self._TERRAIN_NORMAL

            body  = pymunk.Body(body_type=pymunk.Body.STATIC)
            shape = pymunk.Segment(body, (x, y), (end_x, end_y), thickness)
            shape.friction   = friction
            shape.elasticity = restitution
            self.space.add(body, shape)

            self.terrain_zones.append((shape, color, x, end_x, angle_rad))

            x = end_x
            y = end_y

        return [(s, c) for s, c, *_ in self.terrain_zones]

    def clear_terrain(self):
        """Remove all procedural terrain segments from the space."""
        for shape, *_ in self.terrain_zones:
            self.space.remove(shape.body, shape)
        self.terrain_zones.clear()

    # ── Simulation ────────────────────────────────────────────────────────────

    _MAX_LINEAR_VEL  = 3000.0   # world units/s — prevents physics explosion
    _MAX_ANGULAR_VEL =   50.0   # rad/s

    def step(self, dt):
        """Advance the physics simulation by dt seconds."""
        self.space.step(dt)
        for body in self.space.bodies:
            if body.body_type != pymunk.Body.DYNAMIC:
                continue
            spd = body.velocity.length
            if spd > self._MAX_LINEAR_VEL:
                body.velocity = body.velocity * (self._MAX_LINEAR_VEL / spd)
            av = abs(body.angular_velocity)
            if av > self._MAX_ANGULAR_VEL:
                body.angular_velocity *= self._MAX_ANGULAR_VEL / av
