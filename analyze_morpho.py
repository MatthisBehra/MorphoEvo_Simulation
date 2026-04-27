# -*- coding: utf-8 -*-
"""
MorphoEvo - Multi-Run Morphological Analysis

Reads lineage.jsonl files from a `runs/multirun_*/` directory and produces:

  1. Per-run morphology trajectories            -> individual/run_{k}_{env}.png
  2. Interval-binned distributions (100-wide)   -> intervals/interval_{metric}_{env}.png
  3. Cross-correlation heatmaps (A-A, B-B, A-B) -> correlation/corr_{pair}.png
  4. Aggregated overlays across all runs        -> aggregate/overlay_{metric}.png
  5. Skeleton snapshots every N gens (+ gen 1)  -> skeletons/run_{k}_{env}/gen_*.png
  6. Paired A↔B comparison per interval         -> paired/paired_{metric}.png
  7. Divergence trajectory (Cohen's d)          -> divergence/divergence_trajectory.png
  8. PCA 2D of morphologies                     -> pca/pca_final.png, pca/pca_intervals.png
  9. Skeleton grid K×N per env                  -> skeletons_grid/grid_{env}.png
 10. Intra vs inter-env divergence (null test)  -> divergence/intra_vs_inter.png

Stats tests use PER-RUN AGGREGATES (K values per env) — not pooled per-gen
values — to avoid pseudo-replication. Multiple comparisons are corrected with
Holm-Bonferroni across metrics × intervals.

Usage:
    python analyze_morpho.py                       # latest multirun, PNG
    python analyze_morpho.py --multirun <dir>
    python analyze_morpho.py --format pdf
    python analyze_morpho.py --interval 100 --max-gen 1000
"""

import argparse
import glob
import json
import math
import os
import sys
from typing import Any

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

# Reuse morphology helpers from the sim package
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))
from entities.creature import (  # noqa: E402
    count_segments, tree_depth, dna_total_area, iter_genes, SCALAR_GENE_KEYS,
)

# Skeleton renderer lives at project root
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import morphology as morphology_renderer  # noqa: E402


# ── Config ──────────────────────────────────────────────────────────────────

ENV_COLORS = {"A": "#2196F3", "B": "#FF9800"}

# Metrics we track across generations. Each: (key, label, unit)
METRICS = [
    ("n_segments",     "Segments",        "count"),
    ("depth",          "Tree depth",      "levels"),
    ("total_area",     "Total area",      "u²"),
    ("motor_force",    "Motor force",     "N·m"),
    ("motor_speed",    "Motor speed",     "rad/s"),
    ("friction",       "Friction",        "µ"),
    ("joint_damping",  "Joint damping",   "N·s/rad"),
    ("width",          "Segment width",   "u"),
    ("height",         "Segment height",  "u"),
]


# ── CLI ─────────────────────────────────────────────────────────────────────

def parse_args():
    p = argparse.ArgumentParser(description="Multi-run morphological analysis.")
    p.add_argument("--multirun", default=None,
                   help="Path to runs/multirun_* dir (default: latest).")
    p.add_argument("--runs-dir", default="runs",
                   help="Root directory containing multirun_* folders.")
    p.add_argument("--out", default=None,
                   help="Output dir (default: <multirun>/morpho_analysis).")
    p.add_argument("--format", choices=["png", "pdf"], default="png")
    p.add_argument("--interval", type=int, default=100,
                   help="Interval width in generations (default 100).")
    p.add_argument("--max-gen", type=int, default=None,
                   help="Truncate at this generation (default: all).")
    p.add_argument("--skel-step", type=int, default=100,
                   help="Stride for skeleton snapshots (default 100). "
                        "Gen 1 and the final gen are always included.")
    p.add_argument("--no-skeletons", action="store_true",
                   help="Skip skeleton snapshot generation.")
    return p.parse_args()


def resolve_multirun(args) -> str:
    if args.multirun:
        return args.multirun
    pattern = os.path.join(args.runs_dir, "multirun_*")
    matches = sorted(glob.glob(pattern))
    if not matches:
        sys.exit(f"[error] No multirun found under {pattern}")
    return matches[-1]


# ── Data loading ────────────────────────────────────────────────────────────

def extract_metrics(dna: dict) -> dict[str, float]:
    """Compute morphology metrics for a single DNA tree."""
    genes = list(iter_genes(dna))
    n = len(genes)
    out = {
        "n_segments": float(n),
        "depth":      float(tree_depth(dna)),
        "total_area": float(dna_total_area(dna)),
    }
    for key in SCALAR_GENE_KEYS:
        out[key] = float(sum(g[key] for g in genes) / n) if n else 0.0
    return out


def load_run(lineage_path: str, max_gen: int | None) -> dict[str, Any]:
    """
    Return {metric: array[gens], 'gen', 'fitness', 'source'} for one run.

    Prefers `pop_stats.<metric>.mean` (population-level) when present,
    falls back to metrics computed on `best_dna` for legacy lineages.
    """
    gens:    list[int]   = []
    fitness: list[float] = []
    per_metric: dict[str, list[float]] = {k: [] for k, *_ in METRICS}
    source = "best"  # will flip to "population" if pop_stats detected

    with open(lineage_path, encoding="utf-8") as f:
        for line in f:
            rec = json.loads(line)
            if max_gen is not None and rec["gen"] > max_gen:
                break
            gens.append(rec["gen"])
            fitness.append(rec["best_fitness"])

            pop_stats = rec.get("pop_stats")
            if pop_stats:
                source = "population"
                for key, *_ in METRICS:
                    per_metric[key].append(float(pop_stats[key]["mean"]))
            else:
                m = extract_metrics(rec["best_dna"])
                for key, *_ in METRICS:
                    per_metric[key].append(m[key])

    data: dict[str, Any] = {
        "gen":     np.array(gens),
        "fitness": np.array(fitness),
        "source":  source,
    }
    data.update({k: np.array(v) for k, v in per_metric.items()})
    return data


def discover_runs(multirun_dir: str, max_gen: int | None):
    """Return {'A': {run_id: data}, 'B': {run_id: data}}."""
    out: dict[str, dict[int, dict]] = {"A": {}, "B": {}}
    pattern = os.path.join(multirun_dir, "run_*_lineage.jsonl")
    for path in sorted(glob.glob(pattern)):
        name = os.path.basename(path)
        # run_{k}_{env}_lineage.jsonl
        parts = name.replace("_lineage.jsonl", "").split("_")
        run_id = int(parts[1])
        env = parts[2]
        if env not in out:
            continue
        out[env][run_id] = load_run(path, max_gen)
    return out


# ── Interval binning ────────────────────────────────────────────────────────

def bin_by_interval(gens: np.ndarray, values: np.ndarray, interval: int,
                    max_gen: int) -> list[tuple[int, int, np.ndarray]]:
    """Return list of (lo, hi, values_in_bin). lo inclusive, hi inclusive."""
    bins = []
    for lo in range(1, max_gen + 1, interval):
        hi = min(lo + interval - 1, max_gen)
        mask = (gens >= lo) & (gens <= hi)
        bins.append((lo, hi, values[mask]))
    return bins


# ── Plot 1: Individual per-run morphology ───────────────────────────────────

def plot_individual(env: str, run_id: int, data: dict,
                    interval: int, out_dir: str, fmt: str):
    max_gen = int(data["gen"].max()) if len(data["gen"]) else 0
    fig, axes = plt.subplots(3, 3, figsize=(15, 11))
    fig.suptitle(f"Env {env} · Run {run_id} · Morphology over {max_gen} gens",
                 fontsize=14, fontweight="bold")
    color = ENV_COLORS[env]

    for (key, label, unit), ax in zip(METRICS, axes.flatten()):
        y = data[key]
        ax.plot(data["gen"], y, color=color, lw=0.8, alpha=0.5)

        # Per-interval mean as step line
        bins = bin_by_interval(data["gen"], y, interval, max_gen)
        xs, ms, stds = [], [], []
        for lo, hi, vals in bins:
            if len(vals) == 0:
                continue
            xs.append((lo + hi) / 2)
            ms.append(vals.mean())
            stds.append(vals.std())
        xs, ms, stds = np.array(xs), np.array(ms), np.array(stds)
        ax.fill_between(xs, ms - stds, ms + stds, color=color, alpha=0.15)
        ax.plot(xs, ms, color=color, lw=2.0, marker="o", ms=4,
                label=f"mean ±σ (bin={interval})")

        ax.set_title(f"{label}")
        ax.set_xlabel("Generation")
        ax.set_ylabel(unit)
        ax.grid(True, alpha=0.3)
        ax.legend(fontsize=7)

    fig.tight_layout()
    path = os.path.join(out_dir, f"run_{run_id}_{env}.{fmt}")
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path


# ── Plot 2: Interval distributions (box/violin per bin, all runs combined) ──

def plot_interval_distributions(env: str, runs: dict[int, dict],
                                interval: int, out_dir: str, fmt: str):
    if not runs:
        return []
    max_gen = max(int(r["gen"].max()) for r in runs.values())
    color = ENV_COLORS[env]
    paths = []

    for key, label, unit in METRICS:
        fig, ax = plt.subplots(figsize=(12, 5))

        # Collect pooled values per bin (all runs together)
        all_bins: list[np.ndarray] = []
        bin_labels: list[str] = []
        for lo in range(1, max_gen + 1, interval):
            hi = min(lo + interval - 1, max_gen)
            pooled = []
            for r in runs.values():
                mask = (r["gen"] >= lo) & (r["gen"] <= hi)
                pooled.extend(r[key][mask].tolist())
            if pooled:
                all_bins.append(np.array(pooled))
                bin_labels.append(f"{lo}-{hi}")

        if not all_bins:
            plt.close(fig)
            continue

        bp = ax.boxplot(all_bins, tick_labels=bin_labels, showfliers=False,
                        patch_artist=True)
        for patch in bp["boxes"]:
            patch.set_facecolor(color)
            patch.set_alpha(0.55)
        for median in bp["medians"]:
            median.set_color("black")

        ax.set_title(f"Env {env} · {label} — distribution per interval "
                     f"(all {len(runs)} runs pooled)", fontweight="bold")
        ax.set_xlabel(f"Generation interval (width={interval})")
        ax.set_ylabel(f"{label} ({unit})")
        ax.grid(True, alpha=0.3, axis="y")
        plt.setp(ax.get_xticklabels(), rotation=35, ha="right")

        fig.tight_layout()
        path = os.path.join(out_dir, f"interval_{key}_{env}.{fmt}")
        fig.savefig(path, dpi=150)
        plt.close(fig)
        paths.append(path)

    return paths


# ── Plot 3: Cross-correlation heatmaps ──────────────────────────────────────

def _align(x: np.ndarray, y: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    n = min(len(x), len(y))
    return x[:n], y[:n]


def _pearson(x: np.ndarray, y: np.ndarray) -> float:
    x, y = _align(x, y)
    if len(x) < 2:
        return np.nan
    if x.std() == 0 or y.std() == 0:
        return np.nan
    return float(np.corrcoef(x, y)[0, 1])


def _correlation_matrix(runs_row: dict[int, dict],
                        runs_col: dict[int, dict],
                        key: str) -> tuple[np.ndarray, list[int], list[int]]:
    row_ids = sorted(runs_row)
    col_ids = sorted(runs_col)
    mat = np.full((len(row_ids), len(col_ids)), np.nan)
    for i, ri in enumerate(row_ids):
        for j, cj in enumerate(col_ids):
            mat[i, j] = _pearson(runs_row[ri][key], runs_col[cj][key])
    return mat, row_ids, col_ids


def plot_correlation(runs_a: dict[int, dict], runs_b: dict[int, dict],
                     out_dir: str, fmt: str):
    configs = [
        ("A_vs_A", runs_a, runs_a, "A × A (intra-plaine)",     "Run A", "Run A"),
        ("B_vs_B", runs_b, runs_b, "B × B (intra-terrain)",    "Run B", "Run B"),
        ("A_vs_B", runs_a, runs_b, "A × B (inter-environnement)", "Run B", "Run A"),
    ]
    paths = []
    n_metrics = len(METRICS)
    ncols = 3
    nrows = (n_metrics + ncols - 1) // ncols

    for tag, rr, rc, title, xlbl, ylbl, in [(c[0], c[1], c[2], c[3], c[4], c[5]) for c in configs]:
        if not rr or not rc:
            continue
        fig, axes = plt.subplots(nrows, ncols, figsize=(4 * ncols, 3.4 * nrows))
        fig.suptitle(f"Cross-correlation (Pearson) — {title}",
                     fontsize=14, fontweight="bold")
        axes = np.array(axes).flatten()

        for ax, (key, label, _unit) in zip(axes, METRICS):
            mat, rids, cids = _correlation_matrix(rr, rc, key)
            im = ax.imshow(mat, cmap="RdBu_r", vmin=-1, vmax=1, aspect="auto")
            ax.set_title(label, fontsize=10)
            ax.set_xticks(range(len(cids)))
            ax.set_yticks(range(len(rids)))
            ax.set_xticklabels(cids)
            ax.set_yticklabels(rids)
            ax.set_xlabel(xlbl, fontsize=8)
            ax.set_ylabel(ylbl, fontsize=8)
            for i in range(mat.shape[0]):
                for j in range(mat.shape[1]):
                    v = mat[i, j]
                    if np.isnan(v):
                        txt = "—"
                    else:
                        txt = f"{v:.2f}"
                    ax.text(j, i, txt, ha="center", va="center", fontsize=8,
                            color="white" if abs(v) > 0.6 else "black")
            plt.colorbar(im, ax=ax, shrink=0.75)

        # Blank out unused axes
        for ax in axes[n_metrics:]:
            ax.axis("off")

        fig.tight_layout()
        path = os.path.join(out_dir, f"corr_{tag}.{fmt}")
        fig.savefig(path, dpi=150)
        plt.close(fig)
        paths.append(path)

    return paths


# ── Plot 4: Aggregated overlays (all runs + mean±σ band per env) ────────────

def plot_aggregate(runs_a: dict[int, dict], runs_b: dict[int, dict],
                   out_dir: str, fmt: str):
    """One figure per metric, 2 panels (A / B). Shows every run + mean band."""
    paths = []
    for key, label, unit in METRICS:
        fig, axes = plt.subplots(1, 2, figsize=(14, 4.5))
        fig.suptitle(f"Aggregate — {label}", fontsize=14, fontweight="bold")

        for ax, env, runs in [(axes[0], "A", runs_a), (axes[1], "B", runs_b)]:
            color = ENV_COLORS[env]
            if not runs:
                ax.set_title(f"Env {env} (no data)")
                continue

            # Individual runs (faded)
            max_len = max(len(r["gen"]) for r in runs.values())
            gen_axis = np.arange(1, max_len + 1)
            stacked = np.full((len(runs), max_len), np.nan)
            for i, r in enumerate(sorted(runs.values(), key=lambda x: x["gen"][0] if len(x["gen"]) else 0)):
                n = len(r[key])
                stacked[i, :n] = r[key]
                ax.plot(r["gen"], r[key], color=color, lw=0.8, alpha=0.3,
                        label=None)

            # Mean ± std band (ignoring NaNs)
            with np.errstate(all="ignore"):
                m = np.nanmean(stacked, axis=0)
                s = np.nanstd(stacked, axis=0)
            ax.fill_between(gen_axis, m - s, m + s, color=color, alpha=0.25,
                            label="mean ±σ")
            ax.plot(gen_axis, m, color=color, lw=2.2, label="mean")

            ax.set_title(f"Env {env} · {len(runs)} runs")
            ax.set_xlabel("Generation")
            ax.set_ylabel(f"{label} ({unit})")
            ax.grid(True, alpha=0.3)
            ax.legend(fontsize=8, loc="best")

        fig.tight_layout()
        path = os.path.join(out_dir, f"overlay_{key}.{fmt}")
        fig.savefig(path, dpi=150)
        plt.close(fig)
        paths.append(path)

    return paths


# ── Statistical helpers (numpy-only) ────────────────────────────────────────

def _mann_whitney_u(a: np.ndarray, b: np.ndarray) -> tuple[float, float]:
    """
    Two-sided Mann-Whitney U test with normal approximation (ties-corrected).
    Returns (U, p_value). Requires n1+n2 large enough for the z-approx (>~20).
    """
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    n1, n2 = len(a), len(b)
    if n1 == 0 or n2 == 0:
        return float("nan"), float("nan")

    combined = np.concatenate([a, b])
    # Average ranks (handles ties)
    order = np.argsort(combined, kind="mergesort")
    ranks = np.empty_like(order, dtype=float)
    ranks[order] = np.arange(1, len(combined) + 1, dtype=float)
    # Tie correction: average ranks within tied blocks
    _, inv, counts = np.unique(combined, return_inverse=True, return_counts=True)
    if np.any(counts > 1):
        sums = np.zeros(len(counts))
        np.add.at(sums, inv, ranks)
        avg = sums / counts
        ranks = avg[inv]

    r1 = ranks[:n1].sum()
    u1 = r1 - n1 * (n1 + 1) / 2
    u2 = n1 * n2 - u1
    u  = min(u1, u2)

    mu    = n1 * n2 / 2
    # Tie correction for sigma
    t_sum = ((counts ** 3) - counts).sum()
    n     = n1 + n2
    sigma2 = n1 * n2 / 12 * ((n + 1) - t_sum / (n * (n - 1))) if n > 1 else 0.0
    if sigma2 <= 0:
        return float(u), float("nan")
    z = (u - mu) / math.sqrt(sigma2)
    # Two-sided p-value from normal CDF
    p = 2 * (1 - 0.5 * (1 + math.erf(abs(z) / math.sqrt(2))))
    return float(u), float(p)


def _holm_bonferroni(p_values: list[float], alpha: float = 0.05) -> np.ndarray:
    """
    Return boolean array: True where the null is rejected after Holm correction.
    NaNs are treated as non-significant.
    """
    p = np.asarray(p_values, dtype=float)
    n = len(p)
    reject = np.zeros(n, dtype=bool)
    # Sort by p ascending, ignore NaNs
    valid = np.where(np.isfinite(p))[0]
    order = valid[np.argsort(p[valid])]
    m = len(order)
    for rank, idx in enumerate(order, start=1):
        threshold = alpha / (m - rank + 1)
        if p[idx] <= threshold:
            reject[idx] = True
        else:
            break  # Holm: stop at first non-reject
    return reject


def _cohens_d(a: np.ndarray, b: np.ndarray) -> float:
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    n1, n2 = len(a), len(b)
    if n1 < 2 or n2 < 2:
        return float("nan")
    var_a, var_b = a.var(ddof=1), b.var(ddof=1)
    pooled = math.sqrt(((n1 - 1) * var_a + (n2 - 1) * var_b) / (n1 + n2 - 2))
    if pooled == 0:
        return float("nan")
    return float((a.mean() - b.mean()) / pooled)


# ── Per-run interval aggregator ─────────────────────────────────────────────

def _per_run_means(runs: dict[int, dict], key: str, lo: int, hi: int) -> np.ndarray:
    """Return array [K] of per-run means of `key` over gens [lo, hi]."""
    out = []
    for r in runs.values():
        mask = (r["gen"] >= lo) & (r["gen"] <= hi)
        if mask.any():
            out.append(float(r[key][mask].mean()))
    return np.array(out, dtype=float)


# ── Plot 5: Paired A↔B comparison per interval ──────────────────────────────

def plot_paired_comparison(runs_a: dict[int, dict], runs_b: dict[int, dict],
                           interval: int, out_dir: str, fmt: str):
    """
    Boxplot Env A vs Env B per interval.
    Statistical test uses PER-RUN means as independent units (K vs K),
    not pooled per-gen values. Holm-Bonferroni correction applied across
    all (metric × interval) tests → ~90 tests at once.
    """
    if not runs_a or not runs_b:
        return []
    max_gen = max(
        max(int(r["gen"].max()) for r in runs_a.values()),
        max(int(r["gen"].max()) for r in runs_b.values()),
    )
    paths = []

    # Pre-compute per-run means for every (metric, interval) for global Holm
    all_pvals_flat: list[float] = []
    all_keys_flat:  list[tuple[str, int]] = []
    stats_cache: dict[tuple[str, int], dict] = {}

    for key, *_ in METRICS:
        for idx, lo in enumerate(range(1, max_gen + 1, interval)):
            hi = min(lo + interval - 1, max_gen)
            a_means = _per_run_means(runs_a, key, lo, hi)
            b_means = _per_run_means(runs_b, key, lo, hi)
            d = _cohens_d(a_means, b_means)
            _, p = _mann_whitney_u(a_means, b_means)
            stats_cache[(key, idx)] = {
                "lo": lo, "hi": hi,
                "a_means": a_means, "b_means": b_means,
                "d": d, "p": p,
            }
            all_pvals_flat.append(p)
            all_keys_flat.append((key, idx))

    reject_flat = _holm_bonferroni(all_pvals_flat, alpha=0.05)
    reject_map = dict(zip(all_keys_flat, reject_flat))
    n_total_tests = sum(1 for p in all_pvals_flat if np.isfinite(p))

    for key, label, unit in METRICS:
        fig, axes = plt.subplots(2, 1, figsize=(13, 7),
                                 gridspec_kw={"height_ratios": [3, 1]})
        ax_box, ax_tab = axes
        positions_a, positions_b, labels = [], [], []
        data_a, data_b = [], []
        d_values, p_values, rejects = [], [], []

        for idx, lo in enumerate(range(1, max_gen + 1, interval)):
            s = stats_cache[(key, idx)]
            hi = s["hi"]
            data_a.append(s["a_means"])
            data_b.append(s["b_means"])
            positions_a.append(idx * 3)
            positions_b.append(idx * 3 + 1)
            labels.append(f"{lo}-{hi}")
            d_values.append(s["d"])
            p_values.append(s["p"])
            rejects.append(reject_map.get((key, idx), False))

        # Boxplots over K per-run means (tiny samples → small boxes, by design)
        bp_a = ax_box.boxplot(data_a, positions=positions_a, widths=0.8,
                              showfliers=True, patch_artist=True)
        bp_b = ax_box.boxplot(data_b, positions=positions_b, widths=0.8,
                              showfliers=True, patch_artist=True)
        for patch in bp_a["boxes"]:
            patch.set_facecolor(ENV_COLORS["A"]); patch.set_alpha(0.6)
        for patch in bp_b["boxes"]:
            patch.set_facecolor(ENV_COLORS["B"]); patch.set_alpha(0.6)
        for med in bp_a["medians"] + bp_b["medians"]:
            med.set_color("black")

        # Overlay individual per-run points
        for pos, arr, color in (
            *[(p, a, ENV_COLORS["A"]) for p, a in zip(positions_a, data_a)],
            *[(p, b, ENV_COLORS["B"]) for p, b in zip(positions_b, data_b)],
        ):
            jitter = np.random.normal(0, 0.05, size=len(arr))
            ax_box.scatter(pos + jitter, arr, color=color, s=18,
                           edgecolors="black", linewidths=0.4, zorder=3)

        centers = [(a + b) / 2 for a, b in zip(positions_a, positions_b)]
        ax_box.set_xticks(centers)
        ax_box.set_xticklabels(labels, rotation=35, ha="right")
        ax_box.set_ylabel(f"{label} ({unit})")
        k_a = len(next(iter(runs_a.values()))["gen"]) and len(runs_a)
        k_b = len(runs_b)
        ax_box.set_title(
            f"Paired A vs B — {label} · test on per-run means "
            f"(K_A={k_a}, K_B={k_b}) · Holm-corrected across {n_total_tests} tests",
            fontweight="bold", fontsize=11)
        ax_box.grid(True, alpha=0.3, axis="y")
        ax_box.legend([bp_a["boxes"][0], bp_b["boxes"][0]],
                      ["Env A (plaine)", "Env B (terrain)"], loc="best")

        # Stats table beneath
        ax_tab.axis("off")
        cell_text = [
            [f"{d:+.2f}" if np.isfinite(d) else "—" for d in d_values],
            [f"{p:.3g}" if (p is not None and np.isfinite(p)) else "—"
             for p in p_values],
            ["✓" if rj else "·" for rj in rejects],
        ]
        tbl = ax_tab.table(cellText=cell_text,
                           rowLabels=["Cohen's d", "MW p (raw)", "Holm sig."],
                           colLabels=labels, loc="center", cellLoc="center")
        tbl.auto_set_font_size(False)
        tbl.set_fontsize(8)
        tbl.scale(1, 1.3)
        for col_idx, (d, rj) in enumerate(zip(d_values, rejects)):
            if np.isfinite(d):
                abs_d = min(abs(d), 2.0)
                shade = (1.0, max(0, 1 - abs_d / 2), max(0, 1 - abs_d / 2))
                tbl[(1, col_idx)].set_facecolor(shade)
            if rj:
                tbl[(3, col_idx)].set_facecolor((0.75, 1.0, 0.75))

        fig.tight_layout()
        path = os.path.join(out_dir, f"paired_{key}.{fmt}")
        fig.savefig(path, dpi=150)
        plt.close(fig)
        paths.append(path)

    return paths


# ── Plot 6: Divergence trajectory (Cohen's d per interval, all metrics) ─────

def plot_divergence_trajectory(runs_a: dict[int, dict], runs_b: dict[int, dict],
                               interval: int, out_dir: str, fmt: str):
    """
    Cohen's d per interval, computed on PER-RUN means (n=K vs K).
    Holm-Bonferroni applied globally across (metric × interval) tests.
    Filled marker = significant after Holm correction.
    """
    if not runs_a or not runs_b:
        return None
    max_gen = max(
        max(int(r["gen"].max()) for r in runs_a.values()),
        max(int(r["gen"].max()) for r in runs_b.values()),
    )
    bin_centers = []
    d_matrix: dict[str, list[float]] = {k: [] for k, *_ in METRICS}
    p_matrix: dict[str, list[float]] = {k: [] for k, *_ in METRICS}
    pvals_flat: list[float] = []
    pvals_keys: list[tuple[str, int]] = []

    for bi, lo in enumerate(range(1, max_gen + 1, interval)):
        hi = min(lo + interval - 1, max_gen)
        bin_centers.append((lo + hi) / 2)
        for key, *_ in METRICS:
            a_means = _per_run_means(runs_a, key, lo, hi)
            b_means = _per_run_means(runs_b, key, lo, hi)
            d = _cohens_d(a_means, b_means)
            _, p = _mann_whitney_u(a_means, b_means)
            d_matrix[key].append(d)
            p_matrix[key].append(p)
            pvals_flat.append(p)
            pvals_keys.append((key, bi))

    reject_flat = _holm_bonferroni(pvals_flat, alpha=0.05)
    reject_map  = dict(zip(pvals_keys, reject_flat))

    n_metrics = len(METRICS)
    ncols = 3
    nrows = (n_metrics + ncols - 1) // ncols
    fig, axes = plt.subplots(nrows, ncols, figsize=(5 * ncols, 3.3 * nrows))
    k_a, k_b = len(runs_a), len(runs_b)
    fig.suptitle(
        f"Divergence A-B — Cohen's d per interval of {interval} gens · "
        f"per-run means (K_A={k_a}, K_B={k_b}) · filled=Holm-sig. at α=0.05",
        fontsize=13, fontweight="bold")
    axes = np.array(axes).flatten()

    for ax, (key, label, _unit) in zip(axes, METRICS):
        d = np.array(d_matrix[key])
        ax.axhline(0, color="gray", lw=0.8)
        ax.axhspan(-0.2, 0.2, color="#E8F5E9", alpha=0.3)
        ax.axhspan(0.5, 2.5, color="#FFECB3", alpha=0.2)
        ax.axhspan(-2.5, -0.5, color="#FFECB3", alpha=0.2)
        ax.axhspan(0.8, 2.5, color="#FFCDD2", alpha=0.2)
        ax.axhspan(-2.5, -0.8, color="#FFCDD2", alpha=0.2)

        sig = np.array([reject_map.get((key, bi), False)
                        for bi in range(len(bin_centers))])

        ax.plot(bin_centers, d, color="#4A148C", lw=1.8, zorder=3)
        ax.scatter(np.array(bin_centers)[sig], d[sig],
                   color="#4A148C", s=55, zorder=4, label="Holm sig.")
        ax.scatter(np.array(bin_centers)[~sig], d[~sig],
                   facecolors="none", edgecolors="#4A148C", s=55, zorder=4,
                   label="ns")
        ax.set_title(label, fontsize=11)
        ax.set_xlabel("Generation (interval center)")
        ax.set_ylabel("Cohen's d  (A − B)")
        ax.grid(True, alpha=0.3)
        ax.legend(fontsize=7, loc="best")

    for ax in axes[n_metrics:]:
        ax.axis("off")

    fig.tight_layout()
    path = os.path.join(out_dir, f"divergence_trajectory.{fmt}")
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path


# ── Plot 6b: Intra vs inter-env divergence (null baseline) ──────────────────

def _feature_matrix(runs: dict[int, dict], gen_idx: int) -> np.ndarray:
    """Return matrix [K × M] of normalised features for one generation index."""
    keys = [k for k, *_ in METRICS]
    rows = []
    for r in runs.values():
        if gen_idx < len(r["gen"]):
            rows.append([float(r[k][gen_idx]) for k in keys])
    return np.array(rows, dtype=float)


def _pairwise_distances(A: np.ndarray, B: np.ndarray) -> np.ndarray:
    """All pairwise Euclidean distances between rows of A and B."""
    if len(A) == 0 or len(B) == 0:
        return np.array([])
    diff = A[:, None, :] - B[None, :, :]
    return np.linalg.norm(diff, axis=-1).flatten()


def _intra_distances(A: np.ndarray) -> np.ndarray:
    """Upper-triangular pairwise distances (no self-pairs, no duplicates)."""
    if len(A) < 2:
        return np.array([])
    diff = A[:, None, :] - A[None, :, :]
    d = np.linalg.norm(diff, axis=-1)
    i, j = np.triu_indices(len(A), k=1)
    return d[i, j]


def plot_intra_vs_inter(runs_a: dict[int, dict], runs_b: dict[int, dict],
                        interval: int, out_dir: str, fmt: str):
    """
    Null-test: if environmental pressure drives divergence, pairwise feature
    distances between A and B runs should exceed intra-env distances.

    Features are z-scored across all (run × gen) samples so every metric
    contributes equally.
    """
    if not runs_a or not runs_b:
        return None

    keys = [k for k, *_ in METRICS]
    max_gen = max(
        max(int(r["gen"].max()) for r in runs_a.values()),
        max(int(r["gen"].max()) for r in runs_b.values()),
    )
    n_gens = max_gen  # assume gen 1..max_gen present in each run

    # Build a global matrix [env, run, gen, metric] → for z-scoring
    all_vectors = []
    for r in list(runs_a.values()) + list(runs_b.values()):
        v = np.stack([r[k] for k in keys], axis=1)  # [gens × M]
        all_vectors.append(v)
    stacked = np.concatenate(all_vectors, axis=0)  # [total_gens × M]
    mu    = stacked.mean(axis=0)
    sigma = stacked.std(axis=0)
    sigma[sigma == 0] = 1.0

    # Normalise each run's per-gen vector
    A_norm = {rid: (np.stack([r[k] for k in keys], axis=1) - mu) / sigma
              for rid, r in runs_a.items()}
    B_norm = {rid: (np.stack([r[k] for k in keys], axis=1) - mu) / sigma
              for rid, r in runs_b.items()}

    intra_a_curve = []
    intra_b_curve = []
    inter_curve   = []
    for gi in range(n_gens):
        A_mat = np.stack([A_norm[rid][gi] for rid in A_norm
                          if gi < len(A_norm[rid])], axis=0)
        B_mat = np.stack([B_norm[rid][gi] for rid in B_norm
                          if gi < len(B_norm[rid])], axis=0)
        intra_a_curve.append(_intra_distances(A_mat).mean()
                             if len(A_mat) >= 2 else np.nan)
        intra_b_curve.append(_intra_distances(B_mat).mean()
                             if len(B_mat) >= 2 else np.nan)
        inter_curve.append(_pairwise_distances(A_mat, B_mat).mean()
                           if len(A_mat) and len(B_mat) else np.nan)

    intra_a_curve = np.array(intra_a_curve)
    intra_b_curve = np.array(intra_b_curve)
    inter_curve   = np.array(inter_curve)
    gens = np.arange(1, n_gens + 1)

    # Per-interval test: is inter > max(intra_a, intra_b)?
    # Use per-run-mean features per interval, then compute intra / inter.
    bin_centers = []
    bin_intra_a: list[float] = []
    bin_intra_b: list[float] = []
    bin_inter:   list[float] = []
    pvals: list[float] = []

    for lo in range(1, n_gens + 1, interval):
        hi = min(lo + interval - 1, n_gens)
        bin_centers.append((lo + hi) / 2)
        mask_idx = slice(lo - 1, hi)

        A_feat = np.stack([A_norm[rid][mask_idx].mean(axis=0)
                           for rid in A_norm], axis=0)
        B_feat = np.stack([B_norm[rid][mask_idx].mean(axis=0)
                           for rid in B_norm], axis=0)
        intra_a = _intra_distances(A_feat)
        intra_b = _intra_distances(B_feat)
        inter   = _pairwise_distances(A_feat, B_feat)
        bin_intra_a.append(intra_a.mean() if len(intra_a) else np.nan)
        bin_intra_b.append(intra_b.mean() if len(intra_b) else np.nan)
        bin_inter.append(inter.mean() if len(inter) else np.nan)
        # MW: inter vs pooled intra. One-sided conceptually; we use two-sided.
        pooled_intra = np.concatenate([intra_a, intra_b])
        if len(inter) and len(pooled_intra):
            _, p = _mann_whitney_u(inter, pooled_intra)
        else:
            p = float("nan")
        pvals.append(p)

    reject = _holm_bonferroni(pvals, alpha=0.05)

    # ── Plot ────────────────────────────────────────────────────────────────
    fig, axes = plt.subplots(2, 1, figsize=(13, 8),
                             gridspec_kw={"height_ratios": [2.2, 1]})
    ax_curve, ax_bar = axes

    # Smoothed per-gen curves
    def smooth(x, w=25):
        if len(x) < w:
            return x
        c = np.convolve(np.nan_to_num(x, nan=np.nanmean(x)),
                        np.ones(w) / w, mode="same")
        return c

    ax_curve.plot(gens, smooth(intra_a_curve), color=ENV_COLORS["A"], lw=1.8,
                  label=f"intra-A  (mean over K={len(runs_a)} runs, smoothed)")
    ax_curve.plot(gens, smooth(intra_b_curve), color=ENV_COLORS["B"], lw=1.8,
                  label=f"intra-B  (mean over K={len(runs_b)} runs, smoothed)")
    ax_curve.plot(gens, smooth(inter_curve), color="#4A148C", lw=2.2,
                  label="inter-A-B (K_A × K_B pairs, smoothed)")
    ax_curve.set_xlabel("Generation")
    ax_curve.set_ylabel("Mean pairwise distance in z-scored feature space")
    ax_curve.set_title(
        "Intra-env vs inter-env morphological distance · null baseline = intra\n"
        "Divergence is real only if inter > max(intra_A, intra_B)",
        fontweight="bold")
    ax_curve.legend(loc="best")
    ax_curve.grid(True, alpha=0.3)

    # Bar chart per interval: inter vs pooled intra, with Holm significance
    idx = np.arange(len(bin_centers))
    w = 0.28
    ax_bar.bar(idx - w, bin_intra_a, w, color=ENV_COLORS["A"], alpha=0.7,
               label="intra-A")
    ax_bar.bar(idx,     bin_intra_b, w, color=ENV_COLORS["B"], alpha=0.7,
               label="intra-B")
    ax_bar.bar(idx + w, bin_inter,   w, color="#4A148C", alpha=0.85,
               label="inter-A-B")
    ax_bar.set_xticks(idx)
    ax_bar.set_xticklabels([f"{int(c - interval / 2 + 1)}-{int(c + interval / 2)}"
                            for c in bin_centers], rotation=35, ha="right")
    ax_bar.set_ylabel("Mean distance")
    ax_bar.set_title(
        f"Per-interval distance (Holm-corrected across {len(pvals)} tests) · "
        "marker ✱ = inter > intra significantly",
        fontweight="bold", fontsize=11)
    for i, rj in enumerate(reject):
        if rj and np.isfinite(bin_inter[i]):
            ymax = max(filter(np.isfinite,
                              [bin_intra_a[i], bin_intra_b[i], bin_inter[i]]))
            ax_bar.text(i + w, ymax * 1.05, "✱", ha="center", fontsize=16,
                        color="#4A148C", fontweight="bold")
    ax_bar.legend()
    ax_bar.grid(True, alpha=0.3, axis="y")

    fig.tight_layout()
    path = os.path.join(out_dir, f"intra_vs_inter.{fmt}")
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path


# ── Plot 7: PCA 2D of morphologies ──────────────────────────────────────────

def _pca_2d(X: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Return (projection, explained_variance_ratio). X shape (n_samples, n_features)."""
    mu = X.mean(axis=0)
    sigma = X.std(axis=0)
    sigma[sigma == 0] = 1.0
    Xc = (X - mu) / sigma
    _U, S, Vt = np.linalg.svd(Xc, full_matrices=False)
    proj = Xc @ Vt.T[:, :2]
    total_var = (S ** 2).sum()
    ratios = (S ** 2) / total_var if total_var > 0 else S ** 2
    return proj, ratios[:2]


def _dna_feature_vector(metrics: dict[str, float]) -> list[float]:
    return [metrics[k] for k, *_ in METRICS]


def plot_pca(runs_a: dict[int, dict], runs_b: dict[int, dict],
             interval: int, multirun_dir: str, max_gen_cap: int | None,
             out_dir: str, fmt: str):
    paths = []

    # ── 7a. PCA on FINAL gen (one point per run per env) ────────────────────
    final_points = []
    for env, runs in (("A", runs_a), ("B", runs_b)):
        for rid, r in runs.items():
            vec = [r[k][-1] for k, *_ in METRICS]
            final_points.append((env, rid, vec))

    if len(final_points) >= 3:
        X = np.array([p[2] for p in final_points], dtype=float)
        proj, var_ratio = _pca_2d(X)
        fig, ax = plt.subplots(figsize=(8, 6))
        for (env, rid, _), xy in zip(final_points, proj):
            ax.scatter(xy[0], xy[1], color=ENV_COLORS[env], s=140,
                       edgecolors="black", lw=1.2, zorder=3)
            ax.annotate(f"{env}{rid}", (xy[0], xy[1]),
                        textcoords="offset points", xytext=(6, 6), fontsize=9)
        ax.set_xlabel(f"PC1 ({var_ratio[0] * 100:.1f}%)")
        ax.set_ylabel(f"PC2 ({var_ratio[1] * 100:.1f}%)")
        ax.set_title("PCA — morphologies finales (1 point par run)",
                     fontweight="bold")
        ax.grid(True, alpha=0.3)
        ax.legend(handles=[
            plt.Line2D([0], [0], marker='o', color='w', label='Env A',
                       markerfacecolor=ENV_COLORS["A"], markersize=11,
                       markeredgecolor='black'),
            plt.Line2D([0], [0], marker='o', color='w', label='Env B',
                       markerfacecolor=ENV_COLORS["B"], markersize=11,
                       markeredgecolor='black'),
        ])
        fig.tight_layout()
        path = os.path.join(out_dir, f"pca_final.{fmt}")
        fig.savefig(path, dpi=150)
        plt.close(fig)
        paths.append(path)

    # ── 7b. PCA on per-interval centroids (trajectory in morpho space) ──────
    max_gen = max(
        max(int(r["gen"].max()) for r in runs_a.values()) if runs_a else 0,
        max(int(r["gen"].max()) for r in runs_b.values()) if runs_b else 0,
    )
    traj_points = []  # (env, run_id, bin_idx, vec)
    for env, runs in (("A", runs_a), ("B", runs_b)):
        for rid, r in runs.items():
            for bin_idx, lo in enumerate(range(1, max_gen + 1, interval)):
                hi = min(lo + interval - 1, max_gen)
                mask = (r["gen"] >= lo) & (r["gen"] <= hi)
                if not mask.any():
                    continue
                vec = [r[k][mask].mean() for k, *_ in METRICS]
                traj_points.append((env, rid, bin_idx, vec))

    if len(traj_points) >= 3:
        X = np.array([p[3] for p in traj_points], dtype=float)
        proj, var_ratio = _pca_2d(X)
        n_bins = max(p[2] for p in traj_points) + 1

        fig, ax = plt.subplots(figsize=(10, 7))
        # Draw trajectory per run (connect bins in order)
        by_key: dict[tuple[str, int], list] = {}
        for (env, rid, bi, _), xy in zip(traj_points, proj):
            by_key.setdefault((env, rid), []).append((bi, xy))
        for (env, rid), pts in by_key.items():
            pts.sort()
            xs = [p[1][0] for p in pts]
            ys = [p[1][1] for p in pts]
            ax.plot(xs, ys, color=ENV_COLORS[env], lw=1.2, alpha=0.4)
            # Start (circle) and end (triangle)
            ax.scatter(xs[0], ys[0], color=ENV_COLORS[env], marker="o",
                       s=55, edgecolors="black", lw=0.8, zorder=3)
            ax.scatter(xs[-1], ys[-1], color=ENV_COLORS[env], marker="^",
                       s=120, edgecolors="black", lw=1.0, zorder=4)
            ax.annotate(f"{env}{rid}", (xs[-1], ys[-1]),
                        textcoords="offset points", xytext=(7, 5), fontsize=9)
        # Size-coded dots for all points
        for (env, rid, bi, _), xy in zip(traj_points, proj):
            size = 25 + 25 * (bi / max(1, n_bins - 1))
            ax.scatter(xy[0], xy[1], color=ENV_COLORS[env], s=size,
                       alpha=0.7, edgecolors="none", zorder=2)

        ax.set_xlabel(f"PC1 ({var_ratio[0] * 100:.1f}%)")
        ax.set_ylabel(f"PC2 ({var_ratio[1] * 100:.1f}%)")
        ax.set_title(
            f"PCA — trajectoires morphologiques (1 point par run par intervalle de {interval} gens)\n"
            f"○ = intervalle 1   ▲ = intervalle final",
            fontweight="bold")
        ax.grid(True, alpha=0.3)
        ax.legend(handles=[
            plt.Line2D([0], [0], marker='o', color='w', label='Env A',
                       markerfacecolor=ENV_COLORS["A"], markersize=11,
                       markeredgecolor='black'),
            plt.Line2D([0], [0], marker='o', color='w', label='Env B',
                       markerfacecolor=ENV_COLORS["B"], markersize=11,
                       markeredgecolor='black'),
        ])
        fig.tight_layout()
        path = os.path.join(out_dir, f"pca_intervals.{fmt}")
        fig.savefig(path, dpi=150)
        plt.close(fig)
        paths.append(path)

    return paths


# ── Plot 8: Skeleton grid K runs × N intervals per env ──────────────────────

def _load_lineage_raw(path: str) -> list[dict]:
    out = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def plot_skeleton_grid(multirun_dir: str, interval: int, max_gen_cap: int | None,
                       out_dir: str, fmt: str):
    paths = []
    for env in ("A", "B"):
        run_files = sorted(glob.glob(
            os.path.join(multirun_dir, f"run_*_{env}_lineage.jsonl")))
        if not run_files:
            continue

        # Load all lineages, find global max_gen respecting cap
        lineages = {}
        global_max = 0
        for fp in run_files:
            name = os.path.basename(fp)
            rid = int(name.split("_")[1])
            entries = _load_lineage_raw(fp)
            if max_gen_cap is not None:
                entries = [e for e in entries if e["gen"] <= max_gen_cap]
            if entries:
                lineages[rid] = {e["gen"]: e for e in entries}
                global_max = max(global_max, entries[-1]["gen"])

        if not lineages:
            continue

        # Gen grid: interval boundaries (use hi of each bin)
        gens_to_show = []
        for lo in range(1, global_max + 1, interval):
            hi = min(lo + interval - 1, global_max)
            gens_to_show.append(hi)

        run_ids = sorted(lineages.keys())
        n_rows = len(run_ids)
        n_cols = len(gens_to_show)

        fig, axes = plt.subplots(n_rows, n_cols,
                                 figsize=(2.2 * n_cols, 2.6 * n_rows),
                                 squeeze=False)
        fig.suptitle(
            f"Env {env} — Skeleton grid · {n_rows} runs × {n_cols} intervals "
            f"(gen {interval}..{global_max})",
            fontsize=15, fontweight="bold", color=ENV_COLORS[env])

        for r, rid in enumerate(run_ids):
            by_gen = lineages[rid]
            for c, g in enumerate(gens_to_show):
                ax = axes[r][c]
                # Find nearest available gen ≤ g
                chosen = max((gg for gg in by_gen if gg <= g), default=None)
                if chosen is None:
                    ax.axis("off")
                    continue
                entry = by_gen[chosen]
                morphology_renderer.draw_skeleton(ax, entry["best_dna"], env)
                ax.set_title(
                    f"gen {chosen} · fit={entry['best_fitness']:.0f} · "
                    f"{entry['n_segments']}seg",
                    fontsize=8)
                ax.tick_params(labelsize=6)
                if c == 0:
                    ax.set_ylabel(f"Run {rid}", fontsize=10, fontweight="bold")

        fig.tight_layout()
        path = os.path.join(out_dir, f"grid_{env}.{fmt}")
        fig.savefig(path, dpi=120)  # lower DPI — large figure
        plt.close(fig)
        paths.append(path)

    return paths


# ── Main ────────────────────────────────────────────────────────────────────

def main():
    args = parse_args()
    multirun_dir = resolve_multirun(args)
    out_root = args.out or os.path.join(multirun_dir, "morpho_analysis")

    subdirs = {
        "individual":     os.path.join(out_root, "individual"),
        "intervals":      os.path.join(out_root, "intervals"),
        "correlation":    os.path.join(out_root, "correlation"),
        "aggregate":      os.path.join(out_root, "aggregate"),
        "skeletons":      os.path.join(out_root, "skeletons"),
        "paired":         os.path.join(out_root, "paired"),
        "divergence":     os.path.join(out_root, "divergence"),
        "pca":            os.path.join(out_root, "pca"),
        "skeletons_grid": os.path.join(out_root, "skeletons_grid"),
    }
    for d in subdirs.values():
        os.makedirs(d, exist_ok=True)

    print(f"Loading multirun: {multirun_dir}")
    runs = discover_runs(multirun_dir, args.max_gen)
    n_a, n_b = len(runs["A"]), len(runs["B"])
    print(f"  Env A: {n_a} runs  |  Env B: {n_b} runs")
    if n_a == 0 and n_b == 0:
        sys.exit("[error] No lineage files found.")

    sample = next(iter((runs["A"] or runs["B"]).values()))
    print(f"  Generations per run (first): {len(sample['gen'])}")
    src = sample.get("source", "best")
    if src == "population":
        print("  Source: population-level means (pop_stats present)")
    else:
        print("  Source: BEST individual only (legacy lineage - "
              "re-run multirun to get pop-level stats)")
    print()

    # 1. Individual per-run morphology
    print("[1/10] Individual per-run plots")
    for env in ("A", "B"):
        for rid, data in sorted(runs[env].items()):
            p = plot_individual(env, rid, data, args.interval,
                                subdirs["individual"], args.format)
            print(f"   -> {p}")

    # 2. Interval distributions
    print("[2/10] Interval-binned distributions")
    for env in ("A", "B"):
        paths = plot_interval_distributions(env, runs[env], args.interval,
                                            subdirs["intervals"], args.format)
        for p in paths:
            print(f"   -> {p}")

    # 3. Cross-correlation
    print("[3/10] Cross-correlation heatmaps")
    paths = plot_correlation(runs["A"], runs["B"],
                             subdirs["correlation"], args.format)
    for p in paths:
        print(f"   -> {p}")

    # 4. Aggregated overlays
    print("[4/10] Aggregated overlays")
    paths = plot_aggregate(runs["A"], runs["B"],
                           subdirs["aggregate"], args.format)
    for p in paths:
        print(f"   -> {p}")

    # 5. Skeleton snapshots every N gens per run
    if args.no_skeletons:
        print("[5/10] Skeletons: skipped (--no-skeletons)")
    else:
        print(f"[5/10] Skeleton snapshots (step={args.skel_step})")
        morphology_renderer.process_runs_dir(
            runs_dir=multirun_dir,
            step=args.skel_step,
            out_root=subdirs["skeletons"],
        )

    # 6. Paired A↔B comparison
    print("[6/10] Paired A<->B boxplots per interval (Mann-Whitney + Cohen's d)")
    paths = plot_paired_comparison(runs["A"], runs["B"], args.interval,
                                   subdirs["paired"], args.format)
    for p in paths:
        print(f"   -> {p}")

    # 7. Divergence trajectory
    print("[7/10] Divergence trajectory (per-run Cohen's d + Holm)")
    p = plot_divergence_trajectory(runs["A"], runs["B"], args.interval,
                                   subdirs["divergence"], args.format)
    if p:
        print(f"   -> {p}")

    # 7b. Intra vs inter-env null test
    print("[7b/10] Intra-env vs inter-env divergence (null baseline)")
    p = plot_intra_vs_inter(runs["A"], runs["B"], args.interval,
                            subdirs["divergence"], args.format)
    if p:
        print(f"   -> {p}")

    # 8. PCA 2D
    print("[8/10] PCA 2D (final + trajectory)")
    paths = plot_pca(runs["A"], runs["B"], args.interval, multirun_dir,
                     args.max_gen, subdirs["pca"], args.format)
    for p in paths:
        print(f"   -> {p}")

    # 9. Skeleton grid per env
    if args.no_skeletons:
        print("[9/10] Skeleton grids: skipped (--no-skeletons)")
    else:
        print(f"[9/10] Skeleton grid K runs × N intervals (step={args.interval})")
        paths = plot_skeleton_grid(multirun_dir, args.interval, args.max_gen,
                                   subdirs["skeletons_grid"], args.format)
        for p in paths:
            print(f"   -> {p}")

    print(f"\nDone. Output: {out_root}")


if __name__ == "__main__":
    main()
