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
        # Procedural terrain (Env B): [(shape, color, x_start, x_end, angle_rad)]
        self.terrain_zones = []

    # ── Env A — friction zones ────────────────────────────────────────────────

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

    # ── Env B — procedural terrain ────────────────────────────────────────────

    # Terrain colours
    _TERRAIN_NORMAL = (100, 70, 30)    # brown
    _TERRAIN_SOFT   = (70, 100, 60)    # muddy green

    def generate_terrain(self, total_x, ground_y=5, seg_length=150,
                         max_angle_deg=40, soft_zone_prob=0.35,
                         thickness=5.0, flat_start=150):
        """
        Generate procedural terrain made of chained inclined segments.

        - First *flat_start* units are flat (spawning area).
        - Each subsequent segment has a random slope ∈ [−max_angle_deg, +max_angle_deg].
        - ~35 % of segments past the flat zone are "soft" (high friction, zero restitution).
        - Y is clamped to [ground_y − 60, ground_y + 120] to allow more extreme relief.

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
            end_y = max(ground_y - 60, min(ground_y + 120, end_y))
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
