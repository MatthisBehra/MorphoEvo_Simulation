import pymunk
import math
import random
import copy


# ─── Constants ────────────────────────────────────────────────────────────────
MASS_SCALE     = 0.002   # body mass = width × height × MASS_SCALE
ENERGY_PENALTY = 1e-6    # fitness penalty per unit of energy spent (tunable)


# ─── DNA Helpers ──────────────────────────────────────────────────────────────

def random_segment_gene():
    """
    Generates a random gene dict for a single segment node.
    Each segment has its own size, attachment angle, rotation limits, muscle params,
    and joint damping.  Asymmetric by design — no mirroring flag.
    """
    return {
        "width":          random.uniform(20, 55),
        "height":         random.uniform(6, 18),
        "attach_angle":   random.uniform(-math.pi / 2, math.pi / 2),
        "rot_min":        random.uniform(-1.2, -0.2),
        "rot_max":        random.uniform(0.2, 1.2),
        "motor_force":    random.uniform(50_000, 500_000),
        "motor_speed":    random.uniform(1.5, 8.0),
        "motor_phase":    random.uniform(0, 2 * math.pi),
        "friction":       random.uniform(0.3, 1.8),
        "joint_damping":  random.uniform(50, 500),   # Ns/rad — simulates muscle resistance
        "children":       [],
    }


def random_dna():
    """
    Builds a minimal 2-segment DNA: 1 root (torso) + 1 child.
    Morphological complexity emerges through additive mutations over generations.
    """
    root = random_segment_gene()
    root["attach_angle"] = 0.0
    root["width"]  = random.uniform(35, 60)
    root["height"] = random.uniform(12, 22)

    child = random_segment_gene()
    root["children"].append(child)

    return root


# ─── Tree utilities ──────────────────────────────────────────────────────────

def count_segments(dna):
    """Recursive count of all nodes in a DNA tree."""
    return 1 + sum(count_segments(child) for child in dna["children"])


SCALAR_GENE_KEYS = [
    "width", "height", "attach_angle", "rot_min", "rot_max",
    "motor_force", "motor_speed", "motor_phase", "friction", "joint_damping",
]


# Hard bounds applied after every mutation to prevent unbounded drift.
# Slightly wider than the random_segment_gene ranges so evolution still has room.
GENE_BOUNDS = {
    "width":         (5.0,        100.0),
    "height":        (3.0,         40.0),
    "attach_angle":  (-math.pi,    math.pi),
    "rot_min":       (-2.0,        -0.05),
    "rot_max":       (0.05,         2.0),
    "motor_force":   (10_000.0,    2_000_000.0),
    "motor_speed":   (0.3,         15.0),
    "motor_phase":   (0.0,         2 * math.pi),
    "friction":      (0.0,         5.0),
    "joint_damping": (10.0,        2_000.0),
}


def tree_depth(dna):
    """Depth of the DNA tree. Root alone = 0."""
    if not dna["children"]:
        return 0
    return 1 + max(tree_depth(child) for child in dna["children"])


def avg_branching(dna):
    """Average number of children across all non-leaf nodes. Returns 0 if leaf-only."""
    total_children = 0
    n_internal = 0
    stack = [dna]
    while stack:
        node = stack.pop()
        if node["children"]:
            total_children += len(node["children"])
            n_internal += 1
            stack.extend(node["children"])
    return total_children / n_internal if n_internal else 0.0


def iter_genes(dna):
    """Yield every gene node (root + descendants) in the DNA tree."""
    stack = [dna]
    while stack:
        node = stack.pop()
        yield node
        stack.extend(node["children"])


def dna_total_area(dna):
    """Sum of width × height over every segment."""
    return sum(g["width"] * g["height"] for g in iter_genes(dna))


def _collect_all_nodes(dna, parent=None, result=None):
    """Return a flat list of (node, parent) tuples for every node in the tree."""
    if result is None:
        result = []
    result.append((dna, parent))
    for child in dna["children"]:
        _collect_all_nodes(child, parent=dna, result=result)
    return result


def mutate_structure(dna, add_rate=0.12, remove_rate=0.05, max_segments=12):
    """
    Per-creature-per-generation structural mutation (called once, not recursively).

    - add_rate  : probability of adding one random child to a random node.
    - remove_rate : probability of removing one random leaf (non-root).
    - max_segments : hard cap on total segment count.
    """
    # ── Add a segment ─────────────────────────────────────────────────────────
    if random.random() < add_rate and count_segments(dna) < max_segments:
        nodes = _collect_all_nodes(dna)
        target, _ = random.choice(nodes)
        target["children"].append(random_segment_gene())

    # ── Remove a leaf segment ─────────────────────────────────────────────────
    if random.random() < remove_rate:
        nodes = _collect_all_nodes(dna)
        leaves = [(node, parent) for node, parent in nodes
                  if not node["children"] and parent is not None]
        if leaves:
            leaf, parent = random.choice(leaves)
            parent["children"].remove(leaf)

    return dna


# ─── Genetic operators ────────────────────────────────────────────────────────

def mutate_dna(dna, mutation_rate=0.15, mutation_strength=0.25):
    """
    Recursively mutates each scalar gene value by a small random amount.
    Structural mutations (add/remove segments) are handled separately by mutate_structure().
    """
    for key in SCALAR_GENE_KEYS:
        if random.random() < mutation_rate:
            delta = dna[key] * mutation_strength * random.uniform(-1, 1)
            dna[key] += delta
        lo, hi = GENE_BOUNDS[key]
        if dna[key] < lo:
            dna[key] = lo
        elif dna[key] > hi:
            dna[key] = hi

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
                   "motor_force", "motor_speed", "motor_phase", "friction",
                   "joint_damping"]
    child = {}
    for key in scalar_keys:
        child[key] = dna_a[key] if random.random() < 0.5 else dna_b[key]

    child["children"] = [
        crossover_dna(ca, cb)
        for ca, cb in zip(dna_a["children"], dna_b["children"])
    ]

    longer = dna_a["children"] if len(dna_a["children"]) > len(dna_b["children"]) else dna_b["children"]
    for extra in longer[len(child["children"]):]:
        if random.random() < 0.5:
            child["children"].append(copy.deepcopy(extra))

    return child


# ─── Creature ─────────────────────────────────────────────────────────────────

class Creature:
    """
    A physics creature built as a tree of rigid segments connected by motorized joints.

    Morphology is encoded in a nested DNA dict (see random_dna / random_segment_gene).
    Each node in the tree becomes one physical body; each parent→child edge becomes a
    PivotJoint + SimpleMotor + RotaryLimitJoint + DampedRotarySpring.

    The root segment is the 'torso'. Children are limbs; grandchildren are sub-limbs, etc.

    Physical improvements:
    - Mass is proportional to segment area (width × height × MASS_SCALE).
    - Joint damping (DampedRotarySpring) simulates muscle resistance/fatigue.
    - Energy expenditure is accumulated each step; penalties are subtracted from fitness.
    - Morphology is asymmetric — no mirroring.
    - Rotation limits vary by depth: hip (large ROM) > knee (medium) > ankle (restricted).
    """

    _group_counter = 1

    def __init__(self, space, pos, dna=None):
        self.space = space
        self.bodies      = []
        self.shapes      = []
        self.joints      = []
        self.motors      = []
        self.motor_genes = []
        self.colors      = {}

        self._group    = Creature._group_counter
        self._category = 1 << ((Creature._group_counter - 1) % 30)
        Creature._group_counter += 1

        self.dna = dna if dna is not None else random_dna()

        self._angle_samples = []
        self._energy_spent  = 0.0   # J — cumulative metabolic cost

        self._build_node(
            gene=self.dna,
            parent_body=None,
            parent_tip=(pos[0], pos[1]),
            inherited_angle=0.0,
            depth=0,
        )

    # ── Tree Builder ──────────────────────────────────────────────────────────

    def _build_node(self, gene, parent_body, parent_tip, inherited_angle, depth):
        world_angle = inherited_angle + gene["attach_angle"]

        w = gene["width"]
        h = gene["height"]

        cx = parent_tip[0] + math.cos(world_angle) * w / 2
        cy = parent_tip[1] + math.sin(world_angle) * w / 2

        # Variable mass: proportional to segment area
        mass   = max(0.1, w * h * MASS_SCALE)
        moment = pymunk.moment_for_box(mass, (w, h))
        body   = pymunk.Body(mass, moment)
        body.position = (cx, cy)
        body.angle    = world_angle

        shape = pymunk.Poly.create_box(body, (w, h))
        shape.friction = gene["friction"]

        ALL_CREATURE_BITS = (1 << 30) - 1
        shape.filter = pymunk.ShapeFilter(
            group=self._group,
            categories=self._category,
            mask=pymunk.ShapeFilter.ALL_MASKS() ^ ALL_CREATURE_BITS
        )

        hue = int(gene["motor_speed"] * 28) % 255
        self.colors[id(shape)] = (hue, 120, max(0, 220 - hue))

        self.space.add(body, shape)
        self.bodies.append(body)
        self.shapes.append(shape)

        if parent_body is not None:
            pivot = pymunk.PivotJoint(parent_body, body, parent_tip)

            # Articulation différenciée par profondeur
            # depth=1 → hanche (grande amplitude)
            # depth=2 → genou  (amplitude standard)
            # depth≥3 → cheville/extrémité (amplitude réduite)
            if depth == 1:
                rot_min = gene["rot_min"] * 1.3
                rot_max = gene["rot_max"] * 1.3
            elif depth == 2:
                rot_min = gene["rot_min"]
                rot_max = gene["rot_max"]
            else:
                rot_min = max(gene["rot_min"], -0.4)
                rot_max = min(gene["rot_max"],  0.4)

            motor  = pymunk.SimpleMotor(parent_body, body, 0)
            motor.max_force = gene["motor_force"]
            limit  = pymunk.RotaryLimitJoint(parent_body, body, rot_min, rot_max)

            # Amortissement angulaire : simule la résistance musculaire
            # stiffness=0 → pur amortissement sans rappel vers un angle cible
            spring = pymunk.DampedRotarySpring(
                parent_body, body,
                rest_angle=0,
                stiffness=0,
                damping=gene["joint_damping"],
            )

            self.space.add(pivot, motor, limit, spring)
            self.joints.extend([pivot, motor, limit, spring])
            self.motors.append(motor)
            self.motor_genes.append(gene)

        tip_x = parent_tip[0] + math.cos(world_angle) * w
        tip_y = parent_tip[1] + math.sin(world_angle) * w

        for child_gene in gene["children"]:
            self._build_node(child_gene, body, (tip_x, tip_y), world_angle, depth + 1)

    # ── Behaviour ─────────────────────────────────────────────────────────────

    def act(self, time, dt=1 / 60):
        """
        Drives each motor with a sine wave parameterised by its own gene.
        Accumulates energy expenditure (force × |rate| × dt) each call.

        Directional bias: if the torso is moving left (vx < -5 px/s dead zone),
        we flip the sign of every motor to reverse the gait rightward.
        """
        vx = self.bodies[0].velocity.x
        direction_bias = -1.0 if vx < -5 else 1.0

        for motor, gene in zip(self.motors, self.motor_genes):
            rate = gene["motor_speed"] * math.sin(time * 10 + gene["motor_phase"])
            motor.rate = direction_bias * rate
            # Metabolic cost: power = torque × angular speed
            self._energy_spent += abs(motor.rate) * gene["motor_force"] * dt

    # ── Stability tracking ────────────────────────────────────────────────────

    def record_stability(self):
        if self.bodies:
            self._angle_samples.append(self.bodies[0].angle)

    def get_trunk_stability(self):
        """
        Returns a score in (0, 1] where 1 = perfectly stable torso.
        Formula: 1 / (1 + std(torso_angles))
        """
        n = len(self._angle_samples)
        if n < 2:
            return 1.0
        mean     = sum(self._angle_samples) / n
        variance = sum((a - mean) ** 2 for a in self._angle_samples) / n
        return 1.0 / (1.0 + variance ** 0.5)

    # ── Metrics ───────────────────────────────────────────────────────────────

    def get_position(self):
        x = self.bodies[0].position.x
        return x if math.isfinite(x) else 0.0

    def get_fitness(self, start_x=100):
        """Env A fitness: horizontal distance minus metabolic energy and complexity penalties."""
        distance = self.get_position() - start_x
        raw = distance - ENERGY_PENALTY * self._energy_spent
        return raw - 0.5 * count_segments(self.dna)

    def get_fitness_b(self, start_x, terrain_zones, ground_y=5,
                      w_dist=0.7, w_stab=1.0, w_terrain=2.0, w_elev=0.5):
        """
        Env B fitness: distance + trunk stability + inclined-terrain bonus + elevation,
        with complexity REWARDED (opposite pressure from Env A).

        terrain_zones: [(shape, color, x_start, x_end, angle_rad), …]

        Key design choices to maximise morphological divergence vs Env A:
        - w_dist reduced: raw distance is less decisive than in Env A.
        - w_stab increased: a tipping creature fails on steep slopes.
        - w_terrain greatly increased: steep-slope traversal is the primary pressure.
        - w_elev: bonus for the torso being physically higher (actual climbing).
        - complexity_bonus: offsets the −0.5×n_segments from get_fitness and adds
          a net +0.2 per extra segment, so Env B favours complex multi-limbed
          creatures while Env A still penalises them.
        """
        base_fitness = self.get_fitness(start_x)   # includes -0.5 × n_segments
        stability    = self.get_trunk_stability()

        x_pos = self.get_position()
        terrain_bonus = 0.0
        for _shape, _color, x_start, x_end, angle in terrain_zones:
            if x_start >= x_pos:
                break
            covered = min(x_pos, x_end) - max(start_x, x_start)
            if covered > 0:
                terrain_bonus += covered * abs(math.sin(angle))

        # Elevation: how high the torso currently sits above the base ground level
        elevation = max(0.0, self.bodies[0].position.y - ground_y) if self.bodies else 0.0

        # Net +0.2 per segment (cancels the -0.5 penalty then adds a small reward)
        complexity_bonus = 0.7 * count_segments(self.dna)

        return (w_dist * base_fitness
                + w_stab * stability
                + w_terrain * terrain_bonus
                + w_elev * elevation
                + complexity_bonus)

    # ── Cleanup ───────────────────────────────────────────────────────────────

    def remove(self):
        for obj in self.joints:
            self.space.remove(obj)
        for body, shape in zip(self.bodies, self.shapes):
            self.space.remove(shape, body)
        self.bodies.clear()
        self.shapes.clear()
        self.joints.clear()
        self.motors.clear()
        self.motor_genes.clear()
