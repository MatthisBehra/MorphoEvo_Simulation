"""
Pure headless simulation loop — zero pygame dependency.
Runs the dual-environment morphological evolution as fast as the CPU allows.
"""

import time

from physics.environment import Environment
from entities.creature import Creature, count_segments
from evolution.genetics import breed_next_generation, compute_diversity
from utils.data_store import DataStore


# ─── Constants (shared with GUI via imports) ─────────────────────────────────
GROUND_Y   = 5
SPAWN_X    = 300
SPAWN_Y    = GROUND_Y + 200
TIME_STEP  = 1.0 / 60
ZONE_WIDTH = 800


# ─── Helpers (used by both headless and GUI paths) ───────────────────────────

def create_population(space, n, dnas=None):
    """
    Spawn n creatures at (SPAWN_X, SPAWN_Y), optionally from a list of DNA dicts.
    Resets Creature._group_counter so collision bits stay in range [0, 29].
    """
    Creature._group_counter = 1
    creatures = []
    for i in range(n):
        dna = dnas[i] if dnas is not None else None
        creatures.append(Creature(space, (SPAWN_X, SPAWN_Y), dna=dna))
    return creatures


def setup_env_b(env_b, total_x, ground_y):
    """Clear and regenerate procedural terrain for Env B."""
    env_b.clear_terrain()
    return env_b.generate_terrain(total_x, ground_y)


# ─── Headless simulation ─────────────────────────────────────────────────────

def run_headless(n_creatures, gen_duration, n_generations=None):
    """
    Run the full dual-environment evolution without any graphical dependency.

    :param n_creatures:   Population size per environment.
    :param gen_duration:  Simulated seconds per generation.
    :param n_generations: Total generations (None = infinite, stop with Ctrl+C).
    """
    store = DataStore()
    store.save_metadata(
        n_creatures=n_creatures,
        gen_duration=gen_duration,
        speed_mode="headless",
    )

    env_a = Environment(gravity=(0, -900))
    env_b = Environment(gravity=(0, -900))

    total_ground = 1080 * 200
    env_a.add_friction_zones(
        total_x=total_ground, ground_y=GROUND_Y,
        zone_width=ZONE_WIDTH, thickness=5.0,
    )
    setup_env_b(env_b, total_ground, GROUND_Y)

    creatures_a = create_population(env_a.space, n_creatures)
    creatures_b = create_population(env_b.space, n_creatures)

    gen_num  = 1
    sim_time = 0.0

    print(f"MorphoEvo headless — pop={n_creatures}, gen_dur={gen_duration}s")
    print(f"Data -> {store.session_dir}\n")

    try:
        while n_generations is None or gen_num <= n_generations:
            wall_start = time.perf_counter()

            # ── Simulate one generation ───────────────────────────────────────
            steps = int(gen_duration / TIME_STEP)
            for _ in range(steps):
                sim_time += TIME_STEP
                env_a.step(TIME_STEP)
                env_b.step(TIME_STEP)
                for c in creatures_a:
                    c.act(sim_time, TIME_STEP)
                    c.record_stability()
                for c in creatures_b:
                    c.act(sim_time, TIME_STEP)
                    c.record_stability()

            # ── Fitness & stats ───────────────────────────────────────────────
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

            wall_elapsed = time.perf_counter() - wall_start
            print(
                f"Gen {gen_num:>4d} | "
                f"A best={max(fits_a):>8.1f}  avg={sum(fits_a)/len(fits_a):>8.1f} | "
                f"B best={max(fits_b):>8.1f}  avg={sum(fits_b)/len(fits_b):>8.1f} | "
                f"{wall_elapsed:.2f}s"
            )

            # ── Breed ─────────────────────────────────────────────────────────
            new_dnas_a = breed_next_generation(dnas_a, fits_a, n_creatures)
            new_dnas_b = breed_next_generation(dnas_b, fits_b, n_creatures)

            for c in creatures_a:
                c.remove()
            for c in creatures_b:
                c.remove()

            setup_env_b(env_b, total_ground, GROUND_Y)

            creatures_a = create_population(env_a.space, n_creatures, new_dnas_a)
            creatures_b = create_population(env_b.space, n_creatures, new_dnas_b)

            gen_num += 1

    except KeyboardInterrupt:
        print(f"\nStopped at generation {gen_num}.")

    print(f"Data saved in {store.session_dir}")
