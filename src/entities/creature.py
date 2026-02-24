import pymunk
import pygame
import math
import random


# ─── DNA Helpers ──────────────────────────────────────────────────────────────

def random_segment_gene():
    """
    Generates a random gene dict for a single segment node.
    Each segment has its own size, attachment angle, rotation limits, and muscle params.
    """
    return {
        "width":          random.uniform(20, 55),    # Length of this segment
        "height":         random.uniform(6, 18),     # Thickness of this segment
        "attach_angle":   random.uniform(-math.pi / 2, math.pi / 2),  # Angle relative to parent
        "rot_min":        random.uniform(-1.2, -0.2),  # Rotary joint lower limit (rad)
        "rot_max":        random.uniform(0.2, 1.2),    # Rotary joint upper limit (rad)
        "motor_force":    random.uniform(50_000, 500_000),  # Max force of this joint's motor
        "motor_speed":    random.uniform(1.5, 8.0),    # Amplitude of angular velocity
        "motor_phase":    random.uniform(0, 2 * math.pi),  # Phase offset in the sine wave
        "friction":       random.uniform(0.3, 1.8),
        "children":       [],  # List of child segment genes (branching)
    }


def random_dna(n_segments):
    """
    Builds a tree-shaped DNA structure.
    - 1 root (torso) node
    - n_segments-1 additional nodes distributed across the tree
    """
    root = random_segment_gene()
    root["attach_angle"] = 0.0   # Root always faces forward
    root["width"] = random.uniform(35, 60)
    root["height"] = random.uniform(12, 22)

    all_nodes = [root]

    for _ in range(n_segments - 1):
        child = random_segment_gene()
        # Attach to a random existing node (creates the branching tree)
        parent = random.choice(all_nodes)
        parent["children"].append(child)
        all_nodes.append(child)

    return root


def mutate_dna(dna, mutation_rate=0.15, mutation_strength=0.25):
    """
    Recursively mutates each gene value by a small random amount.
    Used by the genetic algorithm for offspring generation.
    """
    scalar_keys = ["width", "height", "attach_angle", "rot_min", "rot_max",
                   "motor_force", "motor_speed", "motor_phase", "friction"]
    for key in scalar_keys:
        if random.random() < mutation_rate:
            delta = dna[key] * mutation_strength * random.uniform(-1, 1)
            dna[key] += delta

    # Ensure rotation limits stay coherent
    if dna["rot_min"] > dna["rot_max"]:
        dna["rot_min"], dna["rot_max"] = dna["rot_max"], dna["rot_min"]

    for child in dna["children"]:
        mutate_dna(child, mutation_rate, mutation_strength)

    return dna


def crossover_dna(dna_a, dna_b):
    """
    Produces a child DNA by randomly blending two parent DNAs node-by-node.
    Each scalar gene is picked from either parent with 50/50 chance.
    """
    scalar_keys = ["width", "height", "attach_angle", "rot_min", "rot_max",
                   "motor_force", "motor_speed", "motor_phase", "friction"]
    child = {}
    for key in scalar_keys:
        child[key] = dna_a[key] if random.random() < 0.5 else dna_b[key]

    # Recurse into children lists (zip truncates to shortest parent)
    child["children"] = [
        crossover_dna(ca, cb)
        for ca, cb in zip(dna_a["children"], dna_b["children"])
    ]

    # If one parent has more children, randomly inherit the extras
    longer = dna_a["children"] if len(dna_a["children"]) > len(dna_b["children"]) else dna_b["children"]
    for extra in longer[len(child["children"]):]:
        if random.random() < 0.5:
            child["children"].append(dict(extra))

    return child


# ─── Creature ─────────────────────────────────────────────────────────────────

class Creature:
    """
    A physics creature built as a tree of rigid segments connected by motorized joints.

    Morphology is encoded in a nested DNA dict (see random_dna / random_segment_gene).
    Each node in the tree becomes one physical body; each parent→child edge becomes
    a PivotJoint + SimpleMotor + RotaryLimitJoint.

    The root segment is the "torso". Children are limbs; grandchildren are sub-limbs, etc.
    """

    # Each creature gets a unique bit in the category mask (up to 32 creatures)
    # category = its own bit  →  mask = ground (cat 0xFFFF) but NOT other creatures
    _group_counter = 1

    def __init__(self, space, pos, n_segments=4, dna=None):
        """
        :param space:       Pymunk physics space.
        :param pos:         (x, y) spawn position of the torso.
        :param n_segments:  Total number of segments (used only when dna is None).
        :param dna:         Pre-built DNA dict. If None, random DNA is generated.
        """
        self.space = space
        self.bodies  = []   # All pymunk Body objects
        self.shapes  = []   # All pymunk Shape objects
        self.joints  = []   # All constraint objects (joints, motors, limits)
        self.motors  = []   # Only SimpleMotor objects, for act()
        self.motor_genes = []  # Parallel list: gene dict for each motor
        self.colors = {}     # shape -> (r,g,b) plain tuple, avoids pymunk Color issues

        # Each creature occupies one bit in a 32-bit category field.
        # Its own segments share that category (group=_group → no self-collision).
        # The mask excludes all creature bits → creatures never collide with each other,
        # but still collide with the static ground (category 0x0, always matched).
        self._group    = Creature._group_counter
        self._category = 1 << ((Creature._group_counter - 1) % 30)  # bits 0-29
        Creature._group_counter += 1

        self.dna = dna if dna is not None else random_dna(n_segments)

        # Build the physical tree starting from root
        self._build_node(
            gene=self.dna,
            parent_body=None,
            parent_tip=(pos[0], pos[1]),   # World position of the attachment point
            inherited_angle=0.0
        )

    # ── Tree Builder ──────────────────────────────────────────────────────────

    def _build_node(self, gene, parent_body, parent_tip, inherited_angle):
        """
        Recursively creates one segment and all its children.

        :param gene:            The gene dict for this segment.
        :param parent_body:     The pymunk Body of the parent segment (None for root).
        :param parent_tip:      World (x, y) of the point where this segment attaches.
        :param inherited_angle: Cumulative angle from root to this node (radians).
        """
        # Absolute world angle of this segment = parent angle + local attach angle
        world_angle = inherited_angle + gene["attach_angle"]

        w = gene["width"]
        h = gene["height"]

        # The segment's center is offset from the attachment point along its axis
        cx = parent_tip[0] + math.cos(world_angle) * w / 2
        cy = parent_tip[1] + math.sin(world_angle) * w / 2

        # ── Physical body ─────────────────────────────────────────────────────
        moment = pymunk.moment_for_box(1, (w, h))
        body = pymunk.Body(1, moment)
        body.position = (cx, cy)
        body.angle = world_angle

        shape = pymunk.Poly.create_box(body, (w, h))
        shape.friction = gene["friction"]
        # group      → segments of THIS creature ignore each other
        # categories → this creature's bit
        # mask       → collide with everything EXCEPT other creature bits (0x3FFFFFFF covers all 30 bits)
        ALL_CREATURE_BITS = (1 << 30) - 1
        shape.filter = pymunk.ShapeFilter(
            group=self._group,
            categories=self._category,
            mask=pymunk.ShapeFilter.ALL_MASKS() ^ ALL_CREATURE_BITS  # ground only
        )

        # Color encodes motor speed — stored in self.colors to avoid pymunk Color type issues
        hue = int(gene["motor_speed"] * 28) % 255
        self.colors[id(shape)] = (hue, 120, max(0, 220 - hue))

        self.space.add(body, shape)
        self.bodies.append(body)
        self.shapes.append(shape)

        # ── Joint to parent ───────────────────────────────────────────────────
        if parent_body is not None:
            pivot = pymunk.PivotJoint(parent_body, body, parent_tip)

            motor = pymunk.SimpleMotor(parent_body, body, 0)
            motor.max_force = gene["motor_force"]

            limit = pymunk.RotaryLimitJoint(parent_body, body,
                                            gene["rot_min"], gene["rot_max"])

            self.space.add(pivot, motor, limit)
            self.joints.extend([pivot, motor, limit])
            self.motors.append(motor)
            self.motor_genes.append(gene)

        # ── Tip position for children ─────────────────────────────────────────
        tip_x = parent_tip[0] + math.cos(world_angle) * w
        tip_y = parent_tip[1] + math.sin(world_angle) * w

        # ── Recurse into children ─────────────────────────────────────────────
        for child_gene in gene["children"]:
            self._build_node(
                gene=child_gene,
                parent_body=body,
                parent_tip=(tip_x, tip_y),
                inherited_angle=world_angle
            )

    # ── Behaviour ─────────────────────────────────────────────────────────────

    def act(self, time):
        """
        Drives each motor with a sine wave parameterised by its own gene.

        Directional bias: if the torso is moving left (vx < -5 px/s dead zone),
        we flip the sign of every motor to reverse the gait rightward.
        """
        vx = self.bodies[0].velocity.x
        direction_bias = -1.0 if vx < -5 else 1.0

        for motor, gene in zip(self.motors, self.motor_genes):
            rate = gene["motor_speed"] * math.sin(time * 10 + gene["motor_phase"])
            motor.rate = direction_bias * rate

    # ── Metrics ───────────────────────────────────────────────────────────────

    def get_position(self):
        """X-coordinate of the root (torso) body."""
        return self.bodies[0].position.x

    def get_fitness(self, start_x=100):
        """Horizontal distance traveled from spawn. Used by the genetic algorithm."""
        return self.get_position() - start_x

    # ── Rendering ─────────────────────────────────────────────────────────────

    def draw(self, screen, screen_height):
        """Renders all segments as filled polygons with a black outline."""
        for shape in self.shapes:
            verts = []
            for v in shape.get_vertices():
                world_v = v.rotated(shape.body.angle) + shape.body.position
                verts.append((world_v.x, screen_height - world_v.y))

            color = getattr(shape, "color", (120, 120, 120))
            pygame.draw.polygon(screen, color, verts)
            pygame.draw.polygon(screen, (0, 0, 0), verts, 2)

    # ── Cleanup ───────────────────────────────────────────────────────────────

    def remove(self):
        """
        Removes all physics objects from the space.
        Call this before discarding a creature (e.g. between generations).
        """
        for obj in self.joints:
            self.space.remove(obj)
        for body, shape in zip(self.bodies, self.shapes):
            self.space.remove(shape, body)
        self.bodies.clear()
        self.shapes.clear()
        self.joints.clear()
        self.motors.clear()
        self.motor_genes.clear()