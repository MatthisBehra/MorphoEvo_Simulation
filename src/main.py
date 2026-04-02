import pygame

from physics.environment import Environment
from entities.creature import Creature
from ui.config_screen import ConfigScreen
from ui.camera import Camera
from ui.summary_screen import draw_summary_overlay
from evolution.genetics import breed_next_generation, compute_diversity, count_segments
from utils.csv_export import init_csv, append_row


# ─── Constants ────────────────────────────────────────────────────────────────
SCREEN_WIDTH        = 1080
SCREEN_HEIGHT       = 720
HALF_H              = SCREEN_HEIGHT // 2
FPS                 = 60
TIME_STEP           = 1.0 / FPS
GENERATION_DURATION = 15.0    # default; overridden by ConfigScreen slider
SHOWCASE_DURATION   = 3.0     # seconds to display winners before next gen
GROUND_Y            = 5       # Y coordinate of ground in Pymunk world space
GROUND_COLOR_A      = (0, 100, 0)

# Env A: friction zones (grass / glace / sable cycling every ZONE_WIDTH units)
ZONE_WIDTH          = 800

SPAWN_X             = 300
SPAWN_Y             = GROUND_Y + 200
CSV_PATH            = "evolution_data.csv"

# ─── Game states ──────────────────────────────────────────────────────────────
STATE_SIMULATING = "simulating"
STATE_SHOWCASE   = "showcase"


# ─── Helpers ──────────────────────────────────────────────────────────────────

def create_population(space, n, dnas=None):
    """
    Spawn n creatures at (SPAWN_X, SPAWN_Y), optionally from a list of DNA dicts.
    All creatures start with 2 segments (random_dna default) unless DNA is provided.
    Resets Creature._group_counter so collision bits are always in range [0, 29].
    """
    Creature._group_counter = 1
    creatures = []
    for i in range(n):
        dna = dnas[i] if dnas is not None else None
        creatures.append(Creature(space, (SPAWN_X, SPAWN_Y), dna=dna))
    return creatures


def setup_env_b(env_b, total_x, ground_y):
    """
    Clear and regenerate procedural terrain for Env B.
    Returns [(shape, color), …] for rendering.
    """
    env_b.clear_terrain()
    return env_b.generate_terrain(total_x, ground_y)


def find_leader(creatures, start_x):
    """Return (index, fitness) of the creature with highest Env A fitness."""
    best_i, best_f = 0, float("-inf")
    for i, c in enumerate(creatures):
        f = c.get_fitness(start_x)
        if f > best_f:
            best_f = f
            best_i = i
    return best_i, best_f


def draw_hud(surface, font, env_label, best_dist, gen_num, state):
    bg = pygame.Surface((270, 76), pygame.SRCALPHA)
    bg.fill((255, 255, 255, 160))
    surface.blit(bg, (8, 8))
    status = "SHOWCASING" if state == STATE_SHOWCASE else f"Gen {gen_num}"
    lines = [
        env_label,
        f"Best : {best_dist:.1f} px",
        status,
    ]
    for i, line in enumerate(lines):
        surf = font.render(line, True, (30, 30, 30))
        surface.blit(surf, (14, 14 + i * 22))


def render_env(surface, camera, ground_zones,
               creatures, leader_idx, font_hud, bg_color=(220, 235, 255)):
    """
    Full render pass for one environment into its surface.

    :param ground_zones: List of (shape, color) tuples — supports multi-zone grounds.
    :param bg_color:     Background fill colour.
    """
    surface.fill(bg_color)

    for shape, color in ground_zones:
        camera.draw_ground(surface, shape, color)

    for i, c in enumerate(creatures):
        camera.draw_creature(surface, c, is_best=(i == leader_idx))

    # Label above leader
    lx, ly = camera.world_to_screen(
        creatures[leader_idx].get_position(),
        creatures[leader_idx].bodies[0].position.y + 35,
    )
    label = font_hud.render("* BEST", True, (200, 50, 50))
    surface.blit(label, (lx - label.get_width() // 2, ly))


# ─── Entry point ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    pygame.init()
    screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
    pygame.display.set_caption("MorphoEvo — Split-Screen Evolution")
    clock = pygame.time.Clock()

    _font_cache = {
        "hud": pygame.font.SysFont("Courier New", 16, bold=True),
        "lg":  pygame.font.SysFont("Courier New", 22, bold=True),
        "sm":  pygame.font.SysFont("Courier New", 15),
    }
    font_hud = _font_cache["hud"]
    font_lg  = _font_cache["lg"]
    font_sm  = _font_cache["sm"]

    gen_duration, n_creatures = ConfigScreen(screen, clock, SCREEN_WIDTH, SCREEN_HEIGHT).run()

    # ── Environments ─────────────────────────────────────────────────────────
    env_a = Environment(gravity=(0, -900))
    env_b = Environment(gravity=(0, -900))

    # Env A: alternating friction zones (grass / glace / sable)
    total_ground = SCREEN_WIDTH * 200
    ground_zones_a = env_a.add_friction_zones(
        total_x=total_ground,
        ground_y=GROUND_Y,
        zone_width=ZONE_WIDTH,
        thickness=5.0,
    )

    # Env B: procedural terrain (inclined segments + soft zones), regenerated each gen
    ground_zones_b = setup_env_b(env_b, total_ground, GROUND_Y)

    # ── Populations ───────────────────────────────────────────────────────────
    creatures_a = create_population(env_a.space, n_creatures)
    creatures_b = create_population(env_b.space, n_creatures)

    # ── Cameras & render surfaces ─────────────────────────────────────────────
    camera_a = Camera(SCREEN_WIDTH, HALF_H)
    camera_b = Camera(SCREEN_WIDTH, HALF_H, ground_margin=100)
    surf_a   = pygame.Surface((SCREEN_WIDTH, HALF_H))
    surf_b   = pygame.Surface((SCREEN_WIDTH, HALF_H))

    # ── Simulation state ──────────────────────────────────────────────────────
    init_csv(CSV_PATH)
    gen_num        = 1
    state          = STATE_SIMULATING
    gen_start      = pygame.time.get_ticks() / 1000.0
    showcase_start = 0.0
    showcase_stats = {"best_a": 0.0, "best_b": 0.0}

    running = True
    while running:
        now = pygame.time.get_ticks() / 1000.0

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

        # ── State machine ─────────────────────────────────────────────────────
        if state == STATE_SIMULATING:
            env_a.step(TIME_STEP)
            env_b.step(TIME_STEP)

            for c in creatures_a:
                c.act(now, TIME_STEP)
                c.record_stability()
            for c in creatures_b:
                c.act(now, TIME_STEP)
                c.record_stability()

            if now - gen_start >= gen_duration:
                lead_a_idx, best_a = find_leader(creatures_a, SPAWN_X)
                lead_b_idx, best_b = find_leader(creatures_b, SPAWN_X)
                showcase_stats = {"best_a": best_a, "best_b": best_b}
                showcase_start = now
                state = STATE_SHOWCASE

        elif state == STATE_SHOWCASE:
            if now - showcase_start >= SHOWCASE_DURATION:
                # ── End of generation ─────────────────────────────────────────
                fits_a = [c.get_fitness(SPAWN_X) for c in creatures_a]
                fits_b = [c.get_fitness_b(SPAWN_X, env_b.terrain_zones)
                          for c in creatures_b]

                dnas_a = [c.dna for c in creatures_a]
                dnas_b = [c.dna for c in creatures_b]

                div_a   = compute_diversity(dnas_a)
                div_b   = compute_diversity(dnas_b)
                cmplx_a = sum(count_segments(d) for d in dnas_a) / len(dnas_a)
                cmplx_b = sum(count_segments(d) for d in dnas_b) / len(dnas_b)

                append_row(CSV_PATH, gen_num,
                           max(fits_a), sum(fits_a) / len(fits_a),
                           max(fits_b), sum(fits_b) / len(fits_b),
                           div_a, div_b, cmplx_a, cmplx_b)

                new_dnas_a = breed_next_generation(dnas_a, fits_a, n_creatures)
                new_dnas_b = breed_next_generation(dnas_b, fits_b, n_creatures)

                for c in creatures_a:
                    c.remove()
                for c in creatures_b:
                    c.remove()

                ground_zones_b = setup_env_b(env_b, total_ground, GROUND_Y)

                creatures_a = create_population(env_a.space, n_creatures, new_dnas_a)
                creatures_b = create_population(env_b.space, n_creatures, new_dnas_b)

                gen_num   += 1
                gen_start  = now
                state      = STATE_SIMULATING

        # ── Leaders ───────────────────────────────────────────────────────────
        lead_a_idx, lead_a_fit = find_leader(creatures_a, SPAWN_X)
        lead_b_idx, lead_b_fit = find_leader(creatures_b, SPAWN_X)

        camera_a.follow(creatures_a[lead_a_idx].get_position())
        camera_b.follow(creatures_b[lead_b_idx].get_position())

        # ── Render ────────────────────────────────────────────────────────────
        render_env(surf_a, camera_a, ground_zones_a,
                   creatures_a, lead_a_idx, font_hud)
        render_env(surf_b, camera_b, ground_zones_b,
                   creatures_b, lead_b_idx, font_hud,
                   bg_color=(255, 248, 225))

        draw_hud(surf_a, font_hud, "ENV A — PLAINE",  lead_a_fit, gen_num, state)
        draw_hud(surf_b, font_hud, "ENV B — TERRAIN", lead_b_fit, gen_num, state)

        screen.blit(surf_a, (0, 0))
        screen.blit(surf_b, (0, HALF_H))
        pygame.draw.line(screen, (30, 30, 30), (0, HALF_H), (SCREEN_WIDTH, HALF_H), 3)

        if state == STATE_SHOWCASE:
            remaining = SHOWCASE_DURATION - (now - showcase_start)
            draw_summary_overlay(
                screen, font_lg, font_sm, gen_num,
                showcase_stats["best_a"], showcase_stats["best_b"],
                remaining,
            )

        pygame.display.flip()
        clock.tick(FPS)

    pygame.quit()
