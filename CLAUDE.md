# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Run the simulation (graphical, with ConfigScreen)
python src/main.py

# Run multi-run headless mode (K=3 runs, rapport de convergence)
python src/main.py --multi-run

# Install dependencies (venv must be activated first)
pip install -r requirements.txt
```

There is no test suite and no linter configured.

> Note: `neat-python` is listed in requirements but neuro-evolution (NEAT) is **strictly forbidden**. Do not use it.

## Outils
Toujours préfixer les commandes bash avec `rtk` (ex: `rtk git diff`, `rtk git status`).

---

## Architecture

### Entry point & simulation loop

`src/main.py` is the sole entry point. It:
1. Shows `ConfigScreen` to collect `gen_duration`, `n_creatures`, `showcase_duration`, and `speed_mode` from the user.
2. Creates two `Environment`s: Env A (friction zones) and Env B (procedural terrain).
3. Spawns `n_creatures` `Creature` objects in each environment.
4. Runs the pygame main loop at 60 FPS, executing `SPEED_FACTOR` physics sub-steps per frame.

**Timing model — two clocks:**
- `sim_time` advances by `TIME_STEP` per physics sub-step (decoupled from wall clock). Used for the sine oscillator in `act()` and for generation/end-of-gen timers.
- `now_wall = pygame.time.get_ticks() / 1000.0` is used **only** for the showcase countdown — because `sim_time` is paused during `STATE_SHOWCASE` (no physics runs then).

**State machine:** `STATE_SIMULATING` → `STATE_SHOWCASE` → back to `STATE_SIMULATING`. Breeding happens at the `SHOWCASE → SIMULATING` transition.

### Creature & DNA tree (`src/entities/creature.py`)

DNA is a **nested dict tree** where each node represents one physical segment:
- Root node = torso; child nodes = limbs and sub-limbs.
- `random_dna()` builds a minimal 2-segment tree (torso + 1 child). Complexity emerges via `mutate_structure()`.
- `mutate_dna` mutates scalar parameters recursively; `mutate_structure` adds/removes segments once per creature per generation (add 12%, remove 5%, cap 12 segments).
- `crossover_dna` blends two parent DNAs node-by-node; extra children from the longer parent are kept with 50% probability.
- Morphology is **asymmetric** — no mirroring, each branch is independent.
- `Creature._build_node()` recursively instantiates each gene as a `pymunk.Body` + `pymunk.Poly`, connected to its parent via `PivotJoint + SimpleMotor + RotaryLimitJoint + DampedRotarySpring`.
- Segment mass is proportional to area (`width × height × MASS_SCALE`).
- Fitness includes a **complexity penalty**: `−0.5 × n_segments` in both environments.

**Clock (sine oscillator):** `Creature.act(sim_time, dt)` drives every `SimpleMotor` with `ω = motor_speed × sin(t×10 + motor_phase)`. All creatures share the same global `sim_time` — only morphology differs, never the oscillator formula.

**ShapeFilter (collision isolation):** Each creature gets a unique bit (`_category = 1 << (group-1) % 30`). Its mask is `ALL_MASKS ^ ALL_CREATURE_BITS`, so segments collide with the static ground but never with other creatures. Do not break this pattern.

**Colors:** stored as `creature.colors: dict[id(shape) → RGB]`, keyed by `id(shape)`. The camera reads this dict when drawing.

### Evolution (`src/evolution/genetics.py`)

`breed_next_generation` pipeline:
1. **Elitism** — top 2 individuals (raw fitness) copied intact.
2. **Fitness sharing** — raw fitness divided by niche size (morphological distance = |Δ segments|, σ=3) to discourage convergence on a single body plan.
3. **Tournament selection** (k=3) on shared fitness → `crossover_dna` → `mutate_dna` → `mutate_structure`.

Diversity metric: stddev of segment counts across the population.

### Coordinate system

Pymunk uses Y-up; Pygame uses Y-down. All conversions go through `Camera.world_to_screen(world_x, world_y)`:
```
screen_x = world_x - camera.x_offset
screen_y = (screen_h - ground_margin + ground_y_world) - world_y
```
Never invert Y manually outside of this method.

### Key files

| File | Responsibility |
|------|---------------|
| `src/main.py` | Game loop, HUD, leader tracking, state machine |
| `src/entities/creature.py` | DNA helpers, physics tree construction, `act()`, fitness |
| `src/physics/environment.py` | Pymunk `Space`, friction zones (Env A), procedural terrain (Env B), velocity cap |
| `src/ui/camera.py` | Smooth horizontal scroll, coordinate transform, creature/ground drawing |
| `src/ui/config_screen.py` | Pre-simulation config UI — returns `(gen_duration, n_creatures, showcase_duration, speed_mode)` |
| `src/ui/summary_screen.py` | Semi-transparent inter-generation overlay banner |
| `src/evolution/genetics.py` | Selection, crossover, niching, `breed_next_generation` |
| `src/evolution/run_manager.py` | Multi-run headless manager — K runs, genotype distance, convergence report |
| `src/utils/csv_export.py` | Per-generation CSV stats export to `evolution_data.csv` |

---

## Invariants — never violate

1. **No neuro-evolution.** No neural networks, no NEAT, no learning algorithms. Only morphological evolution via the sine clock.
2. **ShapeFilter per creature.** Every new `Creature` must allocate its own `_category` bit and set the mask to exclude all creature bits.
3. **Clock formula is universal.** `motor_speed × sin(t×10 + motor_phase)` — only per-gene parameters vary, never the formula itself.
4. **`sim_time` for physics; `now_wall` for showcase only.** Never use wall clock to drive physics or fitness comparisons.
5. **Velocity cap in `Environment.step()`.** Bodies are capped at 3000 u/s linear and 50 rad/s angular after each step. Do not remove this — high `motor_force` values evolved over generations will cause physics explosions without it.
6. **`src/main.py` stays at that path.** Do not move it.
7. **Never modify `venv/` or `.remember/`.**

---

## Implemented features

- Split-screen: Environment A (Plain, top) vs Environment B (Terrain, bottom)
- Generational loop with configurable showcase delay (0–3 s) between generations
- `SPEED_FACTOR` constant in `main.py` — number of physics sub-steps per rendered frame (default 4 → 4× faster wall-clock evolution)
- Fitness: Env A = distance − energy − complexity; Env B = distance + stability + terrain bonus − complexity
- Env B procedural terrain: inclined segments [−25°, +25°] + soft zones, regenerated each generation
- Auto-export to `evolution_data.csv` (fitness, diversity, complexity per generation)
- Asymmetric emergent morphology (2 segments initial, cap 12)
- Complexity penalty (−0.5 × n_segments)
- Population size configurable 1–100
- **Speed mode selector** in ConfigScreen: `1x`, `4x`, `8x`, `HEADLESS`
- **Headless mode** (`HEADLESS` flag): no graphical rendering, no FPS cap, SPEED_FACTOR=8
- **Multi-run mode** (`--multi-run` CLI flag): K=3 independent headless runs, genotype distance matrix, convergence report in `runs/report.json`
- Run Manager (`src/evolution/run_manager.py`): saves best genome per run in `runs/run_{k}.json`

## Référence scientifique
En cas de doute sur les définitions de recherche (fitness, diversité morphologique), consulter `/docs`.
