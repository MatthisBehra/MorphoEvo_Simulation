"""
Run Manager — K paired runs across Env A + Env B with multiprocessing.

Each run starts from the **same initial population** for both environments,
so morphological divergence is driven solely by selective pressure differences.

K runs × 2 envs = 2K worker processes (optimised for 8-core CPUs).

Usage:
    python src/main.py --multi-run
    python src/main.py --multi-run --runs 4 --workers 8 --pop 30 --generations 20
"""

import json
import math
import os
import random
import copy
import sys
import time as _time
from datetime import datetime
from typing import Any
from multiprocessing import Pool, Event

# Ensure src/ is importable (needed by child processes on Windows spawn)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from physics.environment import Environment
from entities.creature import (
    Creature, random_dna, count_segments, tree_depth, dna_total_area,
    iter_genes, SCALAR_GENE_KEYS, GENE_BOUNDS,
)
from evolution.genetics import breed_next_generation


# ─── Constants ──────────────────────────────────────────────────────────────

TIME_STEP: float = 1 / 60
GROUND_Y:  int   = 5
SPAWN_X:   float = 300.0
SPAWN_Y:   float = GROUND_Y + 200

_SCALAR_KEYS: list[str] = SCALAR_GENE_KEYS  # re-exported for back-compat

_MAX_SEGMENTS_REF: int = 12  # cap used by mutate_structure


# ─── DNA utilities ──────────────────────────────────────────────────────────

def _normalised_scalar_vector(dna: dict) -> list[float]:
    """
    Flatten DNA and min-max normalise each gene against GENE_BOUNDS so that
    every dimension contributes in [0, 1]. Prevents motor_force
    (scale 10k-2M) from dominating the distance.
    """
    values: list[float] = []
    for key in _SCALAR_KEYS:
        lo, hi = GENE_BOUNDS[key]
        rng = max(hi - lo, 1e-9)
        values.append((float(dna.get(key, lo)) - lo) / rng)
    for child in dna.get("children", []):
        values.extend(_normalised_scalar_vector(child))
    return values


def genotype_distance(dna_a: dict, dna_b: dict) -> float:
    """
    Composite genotype distance in [0, ~2] that separates *structure* from
    *parameter drift*, both normalised so neither dominates:

        d = sqrt( structural² + scalar² )

    where
        structural = |Δ n_segments| / MAX_SEGMENTS_REF  ∈ [0, 1]
        scalar     = RMS(|Δ gene_i|)  over shared segments, after min-max
                     normalisation by GENE_BOUNDS  ∈ [0, √M]

    This replaces the previous raw Euclidean distance, which was dominated
    by `motor_force` (scale ~1e6) and inflated by zero-padding when segment
    counts differed. See commit history for rationale.
    """
    # Structural component
    n_a = count_segments(dna_a)
    n_b = count_segments(dna_b)
    structural = abs(n_a - n_b) / max(_MAX_SEGMENTS_REF, 1)

    # Scalar component: pad the shorter vector with the mean of the longer
    # one so "missing" segments don't create a spurious max-range delta.
    vec_a = _normalised_scalar_vector(dna_a)
    vec_b = _normalised_scalar_vector(dna_b)
    if len(vec_a) < len(vec_b):
        vec_a.extend([0.5] * (len(vec_b) - len(vec_a)))
    elif len(vec_b) < len(vec_a):
        vec_b.extend([0.5] * (len(vec_a) - len(vec_b)))

    if not vec_a:
        return structural
    diffs = [a - b for a, b in zip(vec_a, vec_b)]
    scalar = math.sqrt(sum(d * d for d in diffs) / len(diffs))

    return math.sqrt(structural * structural + scalar * scalar)


# ─── Population morphology stats (logged per generation) ────────────────────

def _dna_morph_vector(dna: dict) -> dict[str, float]:
    """Per-creature morphology summary used for population-level logging."""
    genes = list(iter_genes(dna))
    n = len(genes)
    out: dict[str, float] = {
        "n_segments": float(n),
        "depth":      float(tree_depth(dna)),
        "total_area": float(dna_total_area(dna)),
    }
    for key in SCALAR_GENE_KEYS:
        out[key] = float(sum(g[key] for g in genes) / n) if n else 0.0
    return out


def _population_stats(dnas: list[dict]) -> dict[str, dict[str, float]]:
    """
    Aggregate morphology over the entire population for a generation.
    Returns {metric: {mean, std, median, min, max}} — enables per-gen
    population-level analysis (not just the best individual).
    """
    if not dnas:
        return {}
    rows = [_dna_morph_vector(d) for d in dnas]
    keys = list(rows[0].keys())
    import statistics
    out: dict[str, dict[str, float]] = {}
    for k in keys:
        vals = [r[k] for r in rows]
        out[k] = {
            "mean":   float(sum(vals) / len(vals)),
            "std":    float(statistics.pstdev(vals)) if len(vals) > 1 else 0.0,
            "median": float(statistics.median(vals)),
            "min":    float(min(vals)),
            "max":    float(max(vals)),
        }
    return out


# ─── Worker stop signal (shared across processes) ───────────────────────────

_stop_event = None


def _init_worker(event):
    """Pool initializer: stores the shared stop Event and ignores SIGINT.

    Only the parent process handles Ctrl+C — workers check the stop event
    between generations and exit gracefully with their partial results.
    """
    import signal
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    global _stop_event
    _stop_event = event


# ─── Worker function (module-level for pickling) ────────────────────────────

def _run_single_env(task: dict) -> dict:
    """
    Worker: run a full evolution loop for one (run_id, env_type) pair.

    Must be a top-level function so multiprocessing can pickle it.
    """
    run_id:       int   = task["run_id"]
    env_type:     str   = task["env_type"]
    initial_dnas: list  = task["initial_dnas"]
    n_generations: int  = task["n_generations"]
    pop_size:     int   = task["pop_size"]
    gen_duration: float = task["gen_duration"]
    lineage_path: str   = task["lineage_path"]

    dnas = [copy.deepcopy(d) for d in initial_dnas]

    fitness_history:    list[float] = []
    complexity_history: list[float] = []
    best_fitness_overall: float = float("-inf")
    best_dna_overall: dict = {}

    gen = 0
    gen_label = str(n_generations) if n_generations else "inf"

    lineage_f = open(lineage_path, "w", encoding="utf-8")

    while True:
        # Stop conditions
        if n_generations is not None and gen >= n_generations:
            break
        if _stop_event is not None and _stop_event.is_set():
            break

        # Fresh environment each generation (Env B terrain must be regenerated)
        env = Environment(gravity=(0, -900))
        total_x = 216_000

        if env_type == "A":
            env.add_friction_zones(total_x=total_x, ground_y=GROUND_Y,
                                   zone_width=800, thickness=5.0)
        else:
            env.generate_terrain(total_x=total_x, ground_y=GROUND_Y)

        Creature._group_counter = 1
        creatures: list[Creature] = []
        for dna in dnas:
            creatures.append(
                Creature(env.space, (SPAWN_X, SPAWN_Y), dna=copy.deepcopy(dna))
            )

        # Simulate
        n_steps = int(gen_duration / TIME_STEP)
        sim_time = 0.0
        for _ in range(n_steps):
            env.step(TIME_STEP)
            for creature in creatures:
                creature.act(sim_time, TIME_STEP)
                creature.record_stability()
            sim_time += TIME_STEP

        # Fitness
        if env_type == "A":
            fitnesses = [c.get_fitness(SPAWN_X) for c in creatures]
        else:
            fitnesses = [c.get_fitness_b(SPAWN_X, env.terrain_zones)
                         for c in creatures]

        gen_best_idx = max(range(len(fitnesses)), key=lambda i: fitnesses[i])
        gen_best_fitness = fitnesses[gen_best_idx]
        fitness_history.append(gen_best_fitness)

        avg_segs = sum(count_segments(d) for d in dnas) / len(dnas)
        complexity_history.append(avg_segs)

        if gen_best_fitness > best_fitness_overall:
            best_fitness_overall = gen_best_fitness
            best_dna_overall = copy.deepcopy(dnas[gen_best_idx])

        lineage_f.write(json.dumps({
            "gen":          gen + 1,
            "best_fitness": gen_best_fitness,
            "n_segments":   count_segments(dnas[gen_best_idx]),
            "best_dna":     dnas[gen_best_idx],
            "fitness_pop": {
                "mean":   float(sum(fitnesses) / len(fitnesses)),
                "std":    float(
                    (sum((f - sum(fitnesses) / len(fitnesses)) ** 2
                         for f in fitnesses) / len(fitnesses)) ** 0.5
                ),
                "min":    float(min(fitnesses)),
                "max":    float(max(fitnesses)),
            },
            "pop_stats":   _population_stats(dnas),
        }, ensure_ascii=False) + "\n")
        lineage_f.flush()

        print(
            f"  [{env_type}-{run_id}] Gen {gen + 1:>3}/{gen_label}"
            f"  best={gen_best_fitness:>8.1f}",
            flush=True,
        )

        # Cleanup
        for creature in creatures:
            creature.remove()

        # Breed
        dnas = breed_next_generation(dnas, fitnesses, pop_size)
        gen += 1

    lineage_f.close()

    return {
        "run_id":             run_id,
        "env_type":           env_type,
        "best_fitness":       best_fitness_overall,
        "best_dna":           best_dna_overall,
        "fitness_history":    fitness_history,
        "complexity_history": complexity_history,
        "final_segments":     count_segments(best_dna_overall),
    }


# ─── Graph generation ───────────────────────────────────────────────────────

def _generate_figures(results_a, results_b, dist_aa, dist_bb, dist_ab,
                      output_dir):
    """Generate analysis figures with matplotlib and save as PNG."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import numpy as np
    except ImportError:
        print("matplotlib/numpy not installed — skipping graph generation")
        return

    # Runs may have different lengths if stopped via Ctrl+C
    # ── Figure 1: Fitness + Complexity curves (2×2) ──────────────────────
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    fig.suptitle("MorphoEvo — Multi-Run Analysis", fontsize=16,
                 fontweight="bold")

    for col, (results, env_label) in enumerate([
        (results_a, "Env A — Plaine"),
        (results_b, "Env B — Terrain"),
    ]):
        # Fitness
        ax = axes[0][col]
        for r in results:
            gens = list(range(1, len(r["fitness_history"]) + 1))
            ax.plot(gens, r["fitness_history"], alpha=0.7,
                    label=f"Run {r['run_id']}")
        ax.set_title(f"{env_label} — Best Fitness")
        ax.set_xlabel("Generation")
        ax.set_ylabel("Fitness")
        ax.legend(fontsize=8)
        ax.grid(True, alpha=0.3)

        # Complexity
        ax = axes[1][col]
        for r in results:
            gens = list(range(1, len(r["complexity_history"]) + 1))
            ax.plot(gens, r["complexity_history"], alpha=0.7,
                    label=f"Run {r['run_id']}")
        ax.set_title(f"{env_label} — Avg Segments")
        ax.set_xlabel("Generation")
        ax.set_ylabel("Segments")
        ax.legend(fontsize=8)
        ax.grid(True, alpha=0.3)

    plt.tight_layout()
    fig.savefig(os.path.join(output_dir, "fitness_complexity.png"), dpi=150)
    plt.close(fig)

    # ── Figure 2: Distance heatmaps (1×3) ───────────────────────────────
    fig, axes = plt.subplots(1, 3, figsize=(18, 6))
    fig.suptitle("Genotype Distance Matrices", fontsize=16,
                 fontweight="bold")

    configs = [
        (axes[0], dist_aa, "A × A (intra-plaine)", "Run A", "Run A"),
        (axes[1], dist_bb, "B × B (intra-terrain)", "Run B", "Run B"),
        (axes[2], dist_ab, "A × B (inter-env)", "Run B", "Run A"),
    ]
    for ax, matrix, title, xlabel, ylabel in configs:
        arr = np.array(matrix, dtype=float)
        im = ax.imshow(arr, cmap="YlOrRd", aspect="auto")
        ax.set_title(title)
        ax.set_xlabel(xlabel)
        ax.set_ylabel(ylabel)
        ax.set_xticks(range(arr.shape[1]))
        ax.set_yticks(range(arr.shape[0]))
        for i in range(arr.shape[0]):
            for j in range(arr.shape[1]):
                ax.text(j, i, f"{arr[i, j]:.0f}",
                        ha="center", va="center", fontsize=8)
        plt.colorbar(im, ax=ax, shrink=0.8)

    plt.tight_layout()
    fig.savefig(os.path.join(output_dir, "distance_matrices.png"), dpi=150)
    plt.close(fig)

    # ── Figure 3: Divergence summary bar chart ───────────────────────────
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    fig.suptitle("Morphological Divergence Summary", fontsize=16,
                 fontweight="bold")

    # Final segment counts
    ax = axes[0]
    segs_a = [r["final_segments"] for r in results_a]
    segs_b = [r["final_segments"] for r in results_b]
    x = range(len(results_a))
    w = 0.35
    ax.bar([i - w / 2 for i in x], segs_a, w, label="Env A", color="#4a90d9")
    ax.bar([i + w / 2 for i in x], segs_b, w, label="Env B", color="#d94a4a")
    ax.set_title("Best Creature — Segment Count")
    ax.set_xlabel("Run")
    ax.set_ylabel("Segments")
    ax.set_xticks(list(x))
    ax.legend()
    ax.grid(True, alpha=0.3, axis="y")

    # Final fitness
    ax = axes[1]
    fit_a = [r["best_fitness"] for r in results_a]
    fit_b = [r["best_fitness"] for r in results_b]
    ax.bar([i - w / 2 for i in x], fit_a, w, label="Env A", color="#4a90d9")
    ax.bar([i + w / 2 for i in x], fit_b, w, label="Env B", color="#d94a4a")
    ax.set_title("Best Fitness")
    ax.set_xlabel("Run")
    ax.set_ylabel("Fitness")
    ax.set_xticks(list(x))
    ax.legend()
    ax.grid(True, alpha=0.3, axis="y")

    plt.tight_layout()
    fig.savefig(os.path.join(output_dir, "divergence_summary.png"), dpi=150)
    plt.close(fig)

    print(f"  Figures saved -> {output_dir}/")


# ─── RunManager ─────────────────────────────────────────────────────────────

class RunManager:
    """
    Launches K paired evolution runs across Env A and Env B.

    Each pair shares the same initial population so morphological divergence
    is driven purely by environmental selective pressure.
    Uses multiprocessing.Pool to run 2K tasks in parallel.
    """

    def __init__(
        self,
        k_runs:        int        = 4,
        n_generations: int | None = None,
        pop_size:      int        = 30,
        gen_duration:  float      = 15.0,
        n_workers:     int | None = None,
    ) -> None:
        self.k_runs        = k_runs
        self.n_generations = n_generations   # None = infinite (Ctrl+C to stop)
        self.pop_size      = pop_size
        self.gen_duration  = gen_duration
        self.n_workers     = n_workers or min(os.cpu_count() or 4, k_runs * 2)

    # ── Distance matrices ────────────────────────────────────────────────

    @staticmethod
    def _distance_matrix(dnas: list[dict]) -> list[list[float]]:
        """Symmetric K×K distance matrix."""
        k = len(dnas)
        m = [[0.0] * k for _ in range(k)]
        for i in range(k):
            for j in range(i + 1, k):
                d = genotype_distance(dnas[i], dnas[j])
                m[i][j] = round(d, 2)
                m[j][i] = round(d, 2)
        return m

    @staticmethod
    def _cross_distance_matrix(dnas_a: list[dict],
                               dnas_b: list[dict]) -> list[list[float]]:
        """A×B distance matrix (rows=A, cols=B)."""
        return [
            [round(genotype_distance(da, db), 2) for db in dnas_b]
            for da in dnas_a
        ]

    @staticmethod
    def _check_convergence(dist_matrix: list[list[float]]) -> bool:
        k = len(dist_matrix)
        if k < 2:
            return True
        max_d = max(
            dist_matrix[i][j] for i in range(k) for j in range(i + 1, k)
        )
        threshold = 0.1 * max_d if max_d > 0 else 0
        return all(
            dist_matrix[i][j] < threshold
            for i in range(k) for j in range(i + 1, k)
        )

    # ── Main entry ───────────────────────────────────────────────────────

    def run_all(self, output_dir: str = None) -> dict[str, Any]:
        """
        Launch K paired runs in parallel, save results + report + graphs.

        Each invocation creates a fresh timestamped folder under ``runs/``
        (``runs/multirun_YYYY-MM-DD_HHMMSS``) so previous runs are never
        overwritten. Pass ``output_dir`` explicitly to override.
        """
        if output_dir is None:
            # Default to project root / runs (not src/runs)
            project_root = os.path.dirname(os.path.dirname(
                os.path.dirname(os.path.abspath(__file__))
            ))
            timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
            output_dir = os.path.join(
                project_root, "runs", f"multirun_{timestamp}"
            )
        os.makedirs(output_dir, exist_ok=True)

        # 1. Generate K shared initial populations
        initial_pops: list[list[dict]] = []
        for k in range(self.k_runs):
            random.seed(k)
            initial_pops.append([random_dna() for _ in range(self.pop_size)])

        # 2. Build 2K tasks (one per env per run)
        tasks: list[dict] = []
        for k in range(self.k_runs):
            for env_type in ("A", "B"):
                tasks.append({
                    "run_id":       k,
                    "env_type":     env_type,
                    "initial_dnas": copy.deepcopy(initial_pops[k]),
                    "n_generations": self.n_generations,
                    "pop_size":     self.pop_size,
                    "gen_duration": self.gen_duration,
                    "lineage_path": os.path.join(
                        output_dir, f"run_{k}_{env_type}_lineage.jsonl"
                    ),
                })

        # 3. Run in parallel with shared stop event
        n_tasks = len(tasks)
        gen_label = str(self.n_generations) if self.n_generations else "infinite (Ctrl+C to stop)"
        print(
            f"MorphoEvo multi-run -- {self.k_runs} runs x 2 envs = "
            f"{n_tasks} tasks on {self.n_workers} workers"
            f"\nGenerations: {gen_label}\n"
        )
        wall_start = _time.perf_counter()

        stop = Event()
        pool = Pool(processes=self.n_workers,
                     initializer=_init_worker, initargs=(stop,))
        try:
            async_results = [pool.apply_async(_run_single_env, (t,))
                             for t in tasks]
            # Wait for completion (sleep loop allows KeyboardInterrupt)
            while not all(ar.ready() for ar in async_results):
                _time.sleep(0.3)
        except KeyboardInterrupt:
            print("\n\nStopping... waiting for current generation to finish")
            stop.set()
        finally:
            pool.close()
            pool.join()

        results: list[dict] = []
        for ar in async_results:
            try:
                results.append(ar.get(timeout=5))
            except Exception:
                pass  # worker may not have finished if terminated early

        wall_elapsed = _time.perf_counter() - wall_start
        print(f"\nAll runs completed in {wall_elapsed:.1f}s")

        # 4. Split results by env
        results_a = sorted(
            [r for r in results if r["env_type"] == "A"],
            key=lambda r: r["run_id"],
        )
        results_b = sorted(
            [r for r in results if r["env_type"] == "B"],
            key=lambda r: r["run_id"],
        )

        # 5. Distance matrices
        dnas_a = [r["best_dna"] for r in results_a]
        dnas_b = [r["best_dna"] for r in results_b]

        dist_aa = self._distance_matrix(dnas_a)
        dist_bb = self._distance_matrix(dnas_b)
        dist_ab = self._cross_distance_matrix(dnas_a, dnas_b)

        # 6. Convergence & divergence
        conv_a = self._check_convergence(dist_aa)
        conv_b = self._check_convergence(dist_bb)

        # Mean A×B distance = morphological divergence between environments
        flat_ab = [dist_ab[i][j]
                   for i in range(len(dist_ab))
                   for j in range(len(dist_ab[0]))]
        mean_div = sum(flat_ab) / len(flat_ab) if flat_ab else 0.0

        # 7. Build report (exclude raw DNA for readability)
        def _summary(r):
            return {k: v for k, v in r.items() if k != "best_dna"}

        report: dict[str, Any] = {
            "k_runs":               self.k_runs,
            "n_generations":        self.n_generations,
            "pop_size":             self.pop_size,
            "gen_duration":         self.gen_duration,
            "n_workers":            self.n_workers,
            "wall_time_s":          round(wall_elapsed, 1),
            "results_a":            [_summary(r) for r in results_a],
            "results_b":            [_summary(r) for r in results_b],
            "distance_matrix_aa":   dist_aa,
            "distance_matrix_bb":   dist_bb,
            "distance_matrix_ab":   dist_ab,
            "convergence_a":        conv_a,
            "convergence_b":        conv_b,
            "mean_divergence_ab":   round(mean_div, 2),
        }

        # 8. Save individual run results (with DNA)
        for r in results:
            path = os.path.join(
                output_dir, f"run_{r['run_id']}_{r['env_type']}.json"
            )
            with open(path, "w", encoding="utf-8") as f:
                json.dump(r, f, indent=2, ensure_ascii=False)

        # 9. Save report
        report_path = os.path.join(output_dir, "report.json")
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)

        # 10. Generate graphs
        _generate_figures(results_a, results_b, dist_aa, dist_bb, dist_ab,
                          output_dir)

        # 11. Print summary
        print(f"\n{'=' * 60}")
        print(f"  Convergence Env A : {conv_a}")
        print(f"  Convergence Env B : {conv_b}")
        print(f"  Mean A×B divergence: {mean_div:.0f}")
        print(f"  Report -> {report_path}")
        print(f"{'=' * 60}")

        return report


# ─── Direct entry point ─────────────────────────────────────────────────────

if __name__ == "__main__":
    manager = RunManager(k_runs=4, n_generations=10, pop_size=20,
                         gen_duration=10.0)
    manager.run_all()
