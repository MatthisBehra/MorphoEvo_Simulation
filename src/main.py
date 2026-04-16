"""
MorphoEvo — entry point.

Usage:
    python src/main.py                  # headless (default, max speed, no pygame)
    python src/main.py --gui            # graphical mode (pygame window + ConfigScreen)
    python src/main.py --multi-run      # K paired runs + A×A / B×B / A×B analysis

Headless options:
    --pop N          Population size (default 30)
    --duration S     Generation duration in sim-seconds (default 15)
    --generations N  Number of generations (default: infinite)

Multi-run options:
    --runs K         Number of paired runs (default 4)
    --workers W      Parallel worker processes (default: cpu_count)
"""

import os
import sys
import argparse

# Ensure src/ is on the path for multiprocessing child processes (Windows spawn)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def main():
    parser = argparse.ArgumentParser(
        description="MorphoEvo — Morphological Evolution Simulation",
    )
    parser.add_argument("--gui", action="store_true",
                        help="Launch with graphical interface (pygame)")
    parser.add_argument("--multi-run", action="store_true",
                        help="K paired runs (A+B) with multiprocessing + graphs")
    parser.add_argument("--pop", type=int, default=30,
                        help="Population size (default: 30)")
    parser.add_argument("--duration", type=float, default=15.0,
                        help="Generation duration in seconds (default: 15)")
    parser.add_argument("--generations", type=int, default=None,
                        help="Number of generations (default: infinite)")
    parser.add_argument("--runs", type=int, default=4,
                        help="Number of paired runs for --multi-run (default: 4)")
    parser.add_argument("--workers", type=int, default=None,
                        help="Worker processes for --multi-run (default: cpu_count)")
    args = parser.parse_args()

    if args.multi_run:
        _run_multi(args)
    elif args.gui:
        _run_gui()
    else:
        _run_headless(args)


# ─── Multi-run mode ──────────────────────────────────────────────────────────

def _run_multi(args):
    from evolution.run_manager import RunManager

    manager = RunManager(
        k_runs=args.runs,
        n_generations=args.generations,   # None = infinite, Ctrl+C to stop
        pop_size=args.pop,
        gen_duration=args.duration,
        n_workers=args.workers,
    )
    manager.run_all()


# ─── Headless mode (default) ─────────────────────────────────────────────────

def _run_headless(args):
    from simulation import run_headless

    run_headless(
        n_creatures=args.pop,
        gen_duration=args.duration,
        n_generations=args.generations,
    )


# ─── Graphical mode (pygame) ─────────────────────────────────────────────────

def _run_gui():
    """Full graphical mode — ConfigScreen + split-screen rendering."""
    import pygame
    from physics.environment import Environment
    from entities.creature import Creature
    from ui.config_screen import ConfigScreen
    from ui.camera import Camera
    from ui.summary_screen import draw_summary_overlay
    from evolution.genetics import breed_next_generation, compute_diversity, count_segments
    from utils.data_store import DataStore
    from simulation import create_population, setup_env_b, GROUND_Y, SPAWN_X, ZONE_WIDTH

    # ─── Constants ────────────────────────────────────────────────────────────
    SCREEN_WIDTH  = 1080
    SCREEN_HEIGHT = 720
    HALF_H        = SCREEN_HEIGHT // 2
    FPS           = 60
    TIME_STEP     = 1.0 / 60

    STATE_SIMULATING = "simulating"
    STATE_SHOWCASE   = "showcase"

    # ─── Local helpers ────────────────────────────────────────────────────────

    def find_leader(creatures, start_x):
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
        for i, line in enumerate([env_label, f"Best : {best_dist:.1f} px", status]):
            surf = font.render(line, True, (30, 30, 30))
            surface.blit(surf, (14, 14 + i * 22))

    def render_env(surface, camera, ground_zones,
                   creatures, leader_idx, font_hud, bg_color=(220, 235, 255)):
        surface.fill(bg_color)
        for shape, color in ground_zones:
            camera.draw_ground(surface, shape, color)
        for i, c in enumerate(creatures):
            camera.draw_creature(surface, c, is_best=(i == leader_idx))
        lx, ly = camera.world_to_screen(
            creatures[leader_idx].get_position(),
            creatures[leader_idx].bodies[0].position.y + 35,
        )
        label = font_hud.render("* BEST", True, (200, 50, 50))
        surface.blit(label, (lx - label.get_width() // 2, ly))

    # ─── Init pygame ──────────────────────────────────────────────────────────
    pygame.init()
    screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
    pygame.display.set_caption("MorphoEvo — Split-Screen Evolution")
    clock = pygame.time.Clock()

    font_hud = pygame.font.SysFont("Courier New", 16, bold=True)
    font_lg  = pygame.font.SysFont("Courier New", 22, bold=True)
    font_sm  = pygame.font.SysFont("Courier New", 15)

    gen_duration, n_creatures, showcase_duration, speed_mode = ConfigScreen(
        screen, clock, SCREEN_WIDTH, SCREEN_HEIGHT
    ).run()

    # ── Speed mode branching ──────────────────────────────────────────────────
    HEADLESS     = False
    SPEED_FACTOR = 4
    if speed_mode == "headless":
        HEADLESS       = True
        SPEED_FACTOR   = 8
        showcase_duration = 0
        screen = pygame.display.set_mode((1, 1))
    elif speed_mode == "1x":
        SPEED_FACTOR = 1
    elif speed_mode == "8x":
        SPEED_FACTOR = 8

    # ─── DataStore ────────────────────────────────────────────────────────────
    store = DataStore()
    store.save_metadata(
        n_creatures=n_creatures,
        gen_duration=gen_duration,
        showcase_duration=showcase_duration,
        speed_mode=speed_mode,
        headless=HEADLESS,
        speed_factor=SPEED_FACTOR,
    )

    # ─── Environments ─────────────────────────────────────────────────────────
    env_a = Environment(gravity=(0, -900))
    env_b = Environment(gravity=(0, -900))

    total_ground = SCREEN_WIDTH * 200
    ground_zones_a = env_a.add_friction_zones(
        total_x=total_ground, ground_y=GROUND_Y,
        zone_width=ZONE_WIDTH, thickness=5.0,
    )
    ground_zones_b = setup_env_b(env_b, total_ground, GROUND_Y)

    # ─── Populations ──────────────────────────────────────────────────────────
    creatures_a = create_population(env_a.space, n_creatures)
    creatures_b = create_population(env_b.space, n_creatures)

    if not HEADLESS:
        camera_a = Camera(SCREEN_WIDTH, HALF_H)
        camera_b = Camera(SCREEN_WIDTH, HALF_H, ground_margin=100)
        surf_a   = pygame.Surface((SCREEN_WIDTH, HALF_H))
        surf_b   = pygame.Surface((SCREEN_WIDTH, HALF_H))

    # ─── Simulation state ─────────────────────────────────────────────────────
    gen_num        = 1
    state          = STATE_SIMULATING
    sim_time       = 0.0
    gen_start      = 0.0
    showcase_start = 0.0
    showcase_stats = {"best_a": 0.0, "best_b": 0.0}

    running = True
    while running:
        now_wall = pygame.time.get_ticks() / 1000.0

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

        # ── State machine ─────────────────────────────────────────────────────
        if state == STATE_SIMULATING:
            for _ in range(SPEED_FACTOR):
                sim_time += TIME_STEP
                env_a.step(TIME_STEP)
                env_b.step(TIME_STEP)

                for c in creatures_a:
                    c.act(sim_time, TIME_STEP)
                    c.record_stability()
                for c in creatures_b:
                    c.act(sim_time, TIME_STEP)
                    c.record_stability()

            if sim_time - gen_start >= gen_duration:
                lead_a_idx, best_a = find_leader(creatures_a, SPAWN_X)
                lead_b_idx, best_b = find_leader(creatures_b, SPAWN_X)
                showcase_stats = {"best_a": best_a, "best_b": best_b}
                showcase_start = now_wall
                state = STATE_SHOWCASE

        elif state == STATE_SHOWCASE:
            if now_wall - showcase_start >= showcase_duration:
                fits_a = [c.get_fitness(SPAWN_X) for c in creatures_a]
                fits_b = [c.get_fitness_b(SPAWN_X, env_b.terrain_zones)
                          for c in creatures_b]

                dnas_a = [c.dna for c in creatures_a]
                dnas_b = [c.dna for c in creatures_b]

                div_a = compute_diversity(dnas_a)
                div_b = compute_diversity(dnas_b)
                store.append_generation(
                    gen_num, fits_a, fits_b, dnas_a, dnas_b,
                    div_a, div_b, count_segments,
                )

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
                gen_start  = sim_time
                state      = STATE_SIMULATING

        # ── Rendering (skip if headless) ──────────────────────────────────────
        if not HEADLESS:
            lead_a_idx, lead_a_fit = find_leader(creatures_a, SPAWN_X)
            lead_b_idx, lead_b_fit = find_leader(creatures_b, SPAWN_X)

            camera_a.follow(creatures_a[lead_a_idx].get_position())
            camera_b.follow(creatures_b[lead_b_idx].get_position())

            render_env(surf_a, camera_a, ground_zones_a,
                       creatures_a, lead_a_idx, font_hud)
            render_env(surf_b, camera_b, ground_zones_b,
                       creatures_b, lead_b_idx, font_hud,
                       bg_color=(255, 248, 225))

            draw_hud(surf_a, font_hud, "ENV A — PLAINE",  lead_a_fit, gen_num, state)
            draw_hud(surf_b, font_hud, "ENV B — TERRAIN", lead_b_fit, gen_num, state)

            screen.blit(surf_a, (0, 0))
            screen.blit(surf_b, (0, HALF_H))
            pygame.draw.line(screen, (30, 30, 30),
                             (0, HALF_H), (SCREEN_WIDTH, HALF_H), 3)

            if state == STATE_SHOWCASE and showcase_duration > 0:
                remaining = showcase_duration - (now_wall - showcase_start)
                draw_summary_overlay(
                    screen, font_lg, font_sm, gen_num,
                    showcase_stats["best_a"], showcase_stats["best_b"],
                    remaining,
                )

            pygame.display.flip()

        clock.tick(0 if HEADLESS else FPS)

    pygame.quit()


# ─── Entry point ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    main()
