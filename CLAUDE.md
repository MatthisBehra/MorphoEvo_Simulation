# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Run the simulation
python src/main.py

# Install dependencies (venv must be activated first)
pip install -r requirements.txt
```

There is no test suite and no linter configured.

> Note: `neat-python` but neuro-evolution (NEAT) is **strictly forbidden** in this project. Do not use it.

## Architecture

### Entry point & simulation loop

`src/main.py` is the sole entry point. It:
1. Shows `ConfigScreen` to collect `gen_duration` and `n_creatures` from the user.
2. Creates two `Environment`s: Env A (friction zones) and Env B (procedural terrain).
3. Spawns `n_creatures` `Creature` objects in each environment.
4. Runs the pygame main loop: `env.step()` → `creature.act(time)` → `Camera.draw_creature()`.

The generational loop is implemented: simulation → showcase → breed → next generation.

### Creature & DNA tree (`src/entities/creature.py`)

DNA is a **nested dict tree** where each node represents one physical segment:
- Root node = torso; child nodes = limbs and sub-limbs.
- `random_dna()` builds a minimal 2-segment tree (torso + 1 child). Complexity emerges via `mutate_structure()`.
- `mutate_dna` mutates scalar parameters recursively; `mutate_structure` adds/removes segments once per creature per generation (add 12%, remove 5%, cap 12 segments).
- `crossover_dna` blends two parent DNAs node-by-node.
- Morphology is **asymmetric** — no mirroring, each branch is independent.
- `Creature._build_node()` recursively instantiates each gene as a `pymunk.Body` + `pymunk.Poly`, connected to its parent via `PivotJoint + SimpleMotor + RotaryLimitJoint`.
- Fitness includes a **complexity penalty**: `−0.5 × n_segments` in both environments.

**Clock (sine oscillator):** `Creature.act(time)` drives every `SimpleMotor` with `ω = motor_speed × sin(t×10 + motor_phase)`. All creatures share the same global clock — only morphology differs, never the oscillator formula.

**ShapeFilter (collision isolation):** Each creature gets a unique bit (`_category = 1 << (group-1) % 30`). Its mask is `ALL_MASKS ^ ALL_CREATURE_BITS`, so segments collide with the static ground but never with other creatures. Do not break this pattern.

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
| `src/main.py` | Game loop, HUD, leader tracking |
| `src/entities/creature.py` | DNA helpers, physics tree construction, `act()`, fitness |
| `src/physics/environment.py` | Pymunk `Space`, friction zones (Env A), procedural terrain (Env B) |
| `src/physics/renderer.py` | Standalone helper to draw a static pymunk `Segment` (used for debug/ground drawing) |
| `src/ui/camera.py` | Smooth horizontal scroll, coordinate transform, creature/ground drawing |
| `src/ui/config_screen.py` | Pre-simulation config UI (generation duration + population sliders) |
| `src/evolution/genetics.py` | Selection, crossover, niching, breed_next_generation |
| `src/utils/csv_export.py` | Per-generation CSV stats export |

## Invariants — never violate

1. **No neuro-evolution.** No neural networks, no NEAT, no learning algorithms. Only morphological evolution via the sine clock.
2. **ShapeFilter per creature.** Every new `Creature` must allocate its own `_category` bit and set the mask to exclude all creature bits.
3. **Clock formula is universal.** `motor_speed × sin(t×10 + motor_phase)` — only per-gene parameters vary, never the formula itself.
4. **`src/main.py` stays at that path.** Do not move it.
5. **Never modify `venv/` or `.remember/`.**

## Implemented features

- Split-screen: Environment A (Plain, top) vs Environment B (Terrain, bottom)
- Generational loop with showcase delay between generations
- Fitness: Env A = distance − energy − complexity; Env B = distance + stability + terrain bonus − complexity
- Env B procedural terrain: inclined segments [−25°, +25°] + soft zones, regenerated each generation
- Auto-export to `evolution_data.csv` (fitness, diversity, complexity per generation)
- Asymmetric emergent morphology (2 segments initial, cap 12)
- Complexity penalty (−0.5 × n_segments)

## Référence scientifique
En cas de doute sur les définitions de recherche (fitness, diversité morphologique),
consulter `/docs`.


## Outils
Toujours préfixer les commandes bash avec `rtk` (ex: `rtk git diff`, `rtk git status`).