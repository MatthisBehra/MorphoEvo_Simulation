# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Headless mode (default — zero pygame, max speed)
python src/main.py
python src/main.py --pop 30 --duration 15 --generations 50

# Graphical mode (pygame window + ConfigScreen)
python src/main.py --gui

# Multi-run (K=4 paired runs, 8 workers, graphs + report)
python src/main.py --multi-run
python src/main.py --multi-run --runs 4 --workers 8 --pop 30 --generations 20

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

`src/main.py` is the sole entry point. It uses `argparse` to dispatch:
- **Default (no flag):** headless mode via `src/simulation.py` — zero pygame, runs as fast as CPU allows.
- **`--gui`:** graphical mode — imports pygame, shows `ConfigScreen`, split-screen rendering at 60 FPS.
- **`--multi-run`:** K independent headless runs via `RunManager`.

`src/simulation.py` contains the pure headless loop and shared helpers (`create_population`, `setup_env_b`) imported by both paths.

**Timing model — two clocks:**
- `sim_time` advances by `TIME_STEP` per physics sub-step (decoupled from wall clock). Used for the sine oscillator in `act()` and for generation/end-of-gen timers.
- `now_wall = pygame.time.get_ticks() / 1000.0` is used **only** in GUI mode for the showcase countdown — because `sim_time` is paused during `STATE_SHOWCASE` (no physics runs then). In headless mode, `time.perf_counter()` is used for wall-clock timing.

**State machine (GUI only):** `STATE_SIMULATING` → `STATE_SHOWCASE` → back to `STATE_SIMULATING`. Breeding happens at the `SHOWCASE → SIMULATING` transition. In headless mode there is no showcase — breeding happens immediately after fitness evaluation.

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
| `src/main.py` | CLI dispatcher (argparse), GUI game loop when `--gui` |
| `src/simulation.py` | Pure headless simulation loop (zero pygame), shared helpers |
| `src/entities/creature.py` | DNA helpers, physics tree construction, `act()`, fitness |
| `src/physics/environment.py` | Pymunk `Space`, friction zones (Env A), procedural terrain (Env B), velocity cap |
| `src/ui/camera.py` | Smooth horizontal scroll, coordinate transform, creature/ground drawing |
| `src/ui/config_screen.py` | Pre-simulation config UI — returns `(gen_duration, n_creatures, showcase_duration, speed_mode)` |
| `src/ui/summary_screen.py` | Semi-transparent inter-generation overlay banner |
| `src/evolution/genetics.py` | Selection, crossover, niching, `breed_next_generation` |
| `src/evolution/run_manager.py` | Multi-run manager — K paired runs (A+B), multiprocessing, distance matrices, matplotlib graphs |
| `src/utils/data_store.py` | Per-session `stats.csv` + `lineage.jsonl` + `session.json` writer |

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
- Per-session output in `data/session_YYYY-MM-DD_HHMMSS/` — `stats.csv` (52-col schema: fitness distribution, morphology, physical, gene averages, A↔B divergence), `lineage.jsonl` (best DNA/gen), `session.json` (parameters)
- Asymmetric emergent morphology (2 segments initial, cap 12)
- Complexity penalty (−0.5 × n_segments)
- Population size configurable 1–100
- **Speed mode selector** in ConfigScreen (GUI only): `1x`, `4x`, `8x`, `HEADLESS`
- **Headless mode** (default, no `--gui`): zero pygame dependency, no FPS cap, max speed. CLI args: `--pop`, `--duration`, `--generations`, `--speed`
- **GUI mode** (`--gui`): full pygame window with ConfigScreen, split-screen rendering, showcase banners
- **Multi-run mode** (`--multi-run`): K paired runs (same initial pop for A+B), multiprocessing (2K workers). Generates distance matrices A×A / B×B / A×B, convergence report, and matplotlib graphs in `runs/`
- Run Manager (`src/evolution/run_manager.py`): multiprocessing.Pool, saves `run_{k}_{A|B}.json` + `report.json` + 3 PNG figures
- CLI args: `--runs K` (default 4), `--workers W` (default cpu_count), `--pop`, `--duration`, `--generations`

## Référence scientifique
En cas de doute sur les définitions de recherche (fitness, diversité morphologique), consulter `/docs`.
