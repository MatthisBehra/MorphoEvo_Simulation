# -*- coding: utf-8 -*-
"""
MorphoEvo - Evolution Data Analysis
Usage: python analyze.py [--csv evolution_data.csv] [--out plots/]
"""

import argparse
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from matplotlib.patches import Patch
import numpy as np
import pandas as pd


# ── CLI ──────────────────────────────────────────────────────────────────────

def parse_args():
    p = argparse.ArgumentParser(description="Plot MorphoEvo evolution stats.")
    p.add_argument("--csv", default="evolution_data.csv")
    p.add_argument("--out", default="plots/")
    return p.parse_args()


# ── Constants ─────────────────────────────────────────────────────────────────

ENV_COLORS        = {"A": "#2196F3", "B": "#FF9800"}   # blue / orange
ALPHA_RUN         = 0.25
EXPLOSION_THRESHOLD = 1e6   # fitness above this = physics explosion


# ── Data loading ─────────────────────────────────────────────────────────────

def load_runs(csv_path):
    """Split CSV into individual runs (each run starts at generation == 1).
    Runs where the best fitness ever exceeds EXPLOSION_THRESHOLD are flagged.
    """
    df = pd.read_csv(csv_path)

    boundaries = df.index[df["generation"] == 1].tolist()
    boundaries.append(len(df))

    runs = []
    for i, start in enumerate(boundaries[:-1]):
        end    = boundaries[i + 1]
        run_df = df.iloc[start:end].copy().reset_index(drop=True)
        run_df["run"] = i + 1
        peak   = run_df[["best_fitness_a", "best_fitness_b"]].max().max()
        run_df["exploded"] = bool(peak > EXPLOSION_THRESHOLD)
        runs.append(run_df)

    return runs


def summary_table(runs):
    rows = []
    for run in runs:
        rows.append({
            "run":           run["run"].iloc[0],
            "n_gen":         len(run),
            "exploded":      run["exploded"].iloc[0],
            "peak_fit_a":    run["best_fitness_a"].clip(upper=EXPLOSION_THRESHOLD).max(),
            "peak_fit_b":    run["best_fitness_b"].clip(upper=EXPLOSION_THRESHOLD).max(),
            "final_avg_a":   run["avg_fitness_a"].iloc[-1],
            "final_avg_b":   run["avg_fitness_b"].iloc[-1],
            "final_div_a":   run["diversity_a"].iloc[-1],
            "final_div_b":   run["diversity_b"].iloc[-1],
            "final_cmplx_a": run["avg_complexity_a"].iloc[-1],
            "final_cmplx_b": run["avg_complexity_b"].iloc[-1],
        })
    return pd.DataFrame(rows)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _runs_mean(runs, col, skip_exploded=True):
    """Return (gens, mean, std) on a common generation grid.
    Exploded runs are excluded from the mean by default.
    """
    valid = [r for r in runs if not (skip_exploded and r["exploded"].iloc[0])]
    if not valid:
        valid = runs
    max_gen = max(len(r) for r in valid)
    matrix  = np.full((len(valid), max_gen), np.nan)
    for i, r in enumerate(valid):
        vals = np.clip(r[col].values.astype(float), None, EXPLOSION_THRESHOLD)
        matrix[i, :len(vals)] = vals
    return np.arange(1, max_gen + 1), np.nanmean(matrix, axis=0), np.nanstd(matrix, axis=0)


def _plot_metric_both_envs(ax, runs, col_a, col_b, ylabel, title,
                            label_a="Env A (Plain)", label_b="Env B (Terrain)"):
    for r in runs:
        gens     = r["generation"].values
        exploded = r["exploded"].iloc[0]
        style    = dict(alpha=0.10, lw=0.6, linestyle="--") if exploded \
                   else dict(alpha=ALPHA_RUN, lw=0.8)
        ax.plot(gens, np.clip(r[col_a].values, None, EXPLOSION_THRESHOLD),
                color=ENV_COLORS["A"], **style)
        ax.plot(gens, np.clip(r[col_b].values, None, EXPLOSION_THRESHOLD),
                color=ENV_COLORS["B"], **style)

    g_a, m_a, s_a = _runs_mean(runs, col_a)
    g_b, m_b, s_b = _runs_mean(runs, col_b)

    ax.plot(g_a, m_a, color=ENV_COLORS["A"], lw=2.0, label=label_a)
    ax.fill_between(g_a, m_a - s_a, m_a + s_a, color=ENV_COLORS["A"], alpha=0.15)
    ax.plot(g_b, m_b, color=ENV_COLORS["B"], lw=2.0, label=label_b)
    ax.fill_between(g_b, m_b - s_b, m_b + s_b, color=ENV_COLORS["B"], alpha=0.15)

    ax.set_xlabel("Generation")
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3)


# ── Plot 1 : Fitness (best + avg) ─────────────────────────────────────────────

def plot_fitness(runs, out_dir):
    fig, axes = plt.subplots(2, 1, figsize=(12, 8), sharex=True)
    fig.suptitle("Evolution de la fitness", fontsize=14, fontweight="bold")

    _plot_metric_both_envs(
        axes[0], runs,
        "best_fitness_a", "best_fitness_b",
        "Meilleure fitness", "Meilleure fitness par generation"
    )
    _plot_metric_both_envs(
        axes[1], runs,
        "avg_fitness_a", "avg_fitness_b",
        "Fitness moyenne", "Fitness moyenne par generation"
    )

    axes[0].set_xlabel("")
    fig.tight_layout()
    path = os.path.join(out_dir, "01_fitness.png")
    fig.savefig(path, dpi=150)
    plt.close(fig)
    print("  -> " + path)


# ── Plot 2 : Diversity ────────────────────────────────────────────────────────

def plot_diversity(runs, out_dir):
    fig, ax = plt.subplots(figsize=(10, 5))
    fig.suptitle("Diversite morphologique (ecart-type du nombre de segments)", fontsize=13)

    _plot_metric_both_envs(
        ax, runs,
        "diversity_a", "diversity_b",
        "Diversite (sigma segments)", "Diversite au fil des generations"
    )

    g, m, _ = _runs_mean(runs, "diversity_a")
    collapse = np.where(m < 0.1)[0]
    if len(collapse):
        first = int(collapse[0]) + 1
        ax.axvline(first, color=ENV_COLORS["A"], linestyle="--", alpha=0.6,
                   label="Collapse Env A ~ gen " + str(first))
        ax.legend(fontsize=8)

    fig.tight_layout()
    path = os.path.join(out_dir, "02_diversity.png")
    fig.savefig(path, dpi=150)
    plt.close(fig)
    print("  -> " + path)


# ── Plot 3 : Complexity ───────────────────────────────────────────────────────

def plot_complexity(runs, out_dir):
    fig, ax = plt.subplots(figsize=(10, 5))
    fig.suptitle("Complexite morphologique (nb moyen de segments)", fontsize=13)

    _plot_metric_both_envs(
        ax, runs,
        "avg_complexity_a", "avg_complexity_b",
        "Segments moyens", "Complexite au fil des generations"
    )

    fig.tight_layout()
    path = os.path.join(out_dir, "03_complexity.png")
    fig.savefig(path, dpi=150)
    plt.close(fig)
    print("  -> " + path)


# ── Plot 4 : Inter-run comparison (bar chart) ─────────────────────────────────

def plot_run_comparison(runs, out_dir):
    smry = summary_table(runs)
    n  = len(smry)
    x  = np.arange(n)
    w  = 0.35

    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    fig.suptitle("Comparaison des runs - Peak fitness & complexite finale", fontsize=13)

    # Peak fitness (clipped)
    ax = axes[0]
    bars_a = ax.bar(x - w/2, smry["peak_fit_a"], w, label="Env A", color=ENV_COLORS["A"])
    bars_b = ax.bar(x + w/2, smry["peak_fit_b"], w, label="Env B", color=ENV_COLORS["B"])
    # Mark exploded runs with a hatching
    for idx, row in smry.iterrows():
        if row["exploded"]:
            bars_a[idx].set_hatch("//")
            bars_b[idx].set_hatch("//")
    ax.set_xticks(x)
    ax.set_xticklabels(["Run " + str(r) for r in smry["run"]], rotation=45, ha="right", fontsize=8)
    ax.set_ylabel("Fitness maximale (clippee a 1e6)")
    ax.set_title("Pic de fitness par run")
    ax.legend()
    ax.grid(True, axis="y", alpha=0.3)

    # Final complexity
    ax = axes[1]
    ax.bar(x - w/2, smry["final_cmplx_a"], w, label="Env A", color=ENV_COLORS["A"])
    ax.bar(x + w/2, smry["final_cmplx_b"], w, label="Env B", color=ENV_COLORS["B"])
    ax.set_xticks(x)
    ax.set_xticklabels(["Run " + str(r) for r in smry["run"]], rotation=45, ha="right", fontsize=8)
    ax.set_ylabel("Segments moyens (derniere gen)")
    ax.set_title("Complexite finale par run")
    ax.legend()
    ax.grid(True, axis="y", alpha=0.3)

    fig.tight_layout()
    path = os.path.join(out_dir, "04_run_comparison.png")
    fig.savefig(path, dpi=150)
    plt.close(fig)
    print("  -> " + path)


# ── Plot 5 : Dashboard (2x3) ─────────────────────────────────────────────────

def plot_dashboard(runs, out_dir):
    fig = plt.figure(figsize=(18, 10))
    fig.suptitle("MorphoEvo - Dashboard d'analyse evolutive", fontsize=15, fontweight="bold")
    gs  = gridspec.GridSpec(2, 3, figure=fig, hspace=0.45, wspace=0.35)

    ax_best  = fig.add_subplot(gs[0, 0])
    ax_avg   = fig.add_subplot(gs[0, 1])
    ax_div   = fig.add_subplot(gs[0, 2])
    ax_cmplx = fig.add_subplot(gs[1, 0])
    ax_corr  = fig.add_subplot(gs[1, 1])
    ax_box   = fig.add_subplot(gs[1, 2])

    _plot_metric_both_envs(ax_best, runs, "best_fitness_a", "best_fitness_b",
                           "Fitness", "Meilleure fitness")
    _plot_metric_both_envs(ax_avg,  runs, "avg_fitness_a",  "avg_fitness_b",
                           "Fitness", "Fitness moyenne")
    _plot_metric_both_envs(ax_div,  runs, "diversity_a",    "diversity_b",
                           "sigma segments", "Diversite")
    _plot_metric_both_envs(ax_cmplx, runs, "avg_complexity_a", "avg_complexity_b",
                           "Segments", "Complexite moyenne")

    # Scatter: complexity vs best fitness (valid runs only)
    valid_runs = [r for r in runs if not r["exploded"].iloc[0]]
    all_data   = pd.concat(valid_runs, ignore_index=True) if valid_runs else pd.concat(runs)
    ax_corr.scatter(all_data["avg_complexity_a"], all_data["best_fitness_a"],
                    color=ENV_COLORS["A"], alpha=0.3, s=10, label="Env A")
    ax_corr.scatter(all_data["avg_complexity_b"], all_data["best_fitness_b"],
                    color=ENV_COLORS["B"], alpha=0.3, s=10, label="Env B")
    for col_x, col_y, col in [
        ("avg_complexity_a", "best_fitness_a", ENV_COLORS["A"]),
        ("avg_complexity_b", "best_fitness_b", ENV_COLORS["B"]),
    ]:
        xv   = all_data[col_x].values
        yv   = all_data[col_y].values
        mask = np.isfinite(xv) & np.isfinite(yv)
        if mask.sum() > 2:
            coef = np.polyfit(xv[mask], yv[mask], 1)
            xr   = np.linspace(xv[mask].min(), xv[mask].max(), 100)
            ax_corr.plot(xr, np.polyval(coef, xr), color=col, lw=1.5)
    ax_corr.set_xlabel("Complexite moyenne")
    ax_corr.set_ylabel("Meilleure fitness")
    ax_corr.set_title("Complexite vs Fitness")
    ax_corr.legend(fontsize=7)
    ax_corr.grid(True, alpha=0.3)

    # Box: best fitness distribution per run (clipped)
    smry        = summary_table(runs)
    run_ids     = smry["run"].values
    data_a      = [np.clip(r["best_fitness_a"].values, None, EXPLOSION_THRESHOLD) for r in runs]
    data_b      = [np.clip(r["best_fitness_b"].values, None, EXPLOSION_THRESHOLD) for r in runs]
    positions_a = np.arange(len(runs)) * 2
    positions_b = positions_a + 0.8

    ax_box.boxplot(data_a, positions=positions_a, widths=0.6,
                   patch_artist=True, boxprops=dict(facecolor=ENV_COLORS["A"], alpha=0.6),
                   medianprops=dict(color="white", lw=2),
                   whiskerprops=dict(color=ENV_COLORS["A"]),
                   capprops=dict(color=ENV_COLORS["A"]),
                   flierprops=dict(marker=".", color=ENV_COLORS["A"], alpha=0.4))
    ax_box.boxplot(data_b, positions=positions_b, widths=0.6,
                   patch_artist=True, boxprops=dict(facecolor=ENV_COLORS["B"], alpha=0.6),
                   medianprops=dict(color="white", lw=2),
                   whiskerprops=dict(color=ENV_COLORS["B"]),
                   capprops=dict(color=ENV_COLORS["B"]),
                   flierprops=dict(marker=".", color=ENV_COLORS["B"], alpha=0.4))

    ax_box.set_xticks(positions_a + 0.4)
    ax_box.set_xticklabels(["R" + str(r) for r in run_ids], fontsize=7)
    ax_box.set_ylabel("Meilleure fitness (clippee)")
    ax_box.set_title("Distribution fitness / run")
    ax_box.legend(handles=[
        Patch(facecolor=ENV_COLORS["A"], label="Env A"),
        Patch(facecolor=ENV_COLORS["B"], label="Env B"),
    ], fontsize=7)
    ax_box.grid(True, axis="y", alpha=0.3)

    path = os.path.join(out_dir, "00_dashboard.png")
    fig.savefig(path, dpi=150)
    plt.close(fig)
    print("  -> " + path)


# ── Plot 6 : Heatmap (runs x generation) ─────────────────────────────────────

def plot_heatmap(runs, out_dir):
    max_gen = max(len(r) for r in runs)
    n_runs  = len(runs)

    for env, col in [("A", "best_fitness_a"), ("B", "best_fitness_b")]:
        matrix = np.full((n_runs, max_gen), np.nan)
        for i, r in enumerate(runs):
            vals = np.clip(r[col].values.astype(float), None, EXPLOSION_THRESHOLD)
            matrix[i, :len(vals)] = vals

        fig, ax = plt.subplots(figsize=(14, max(4, n_runs * 0.55)))
        im = ax.imshow(matrix, aspect="auto", cmap="viridis",
                       interpolation="nearest",
                       extent=[1, max_gen, n_runs + 0.5, 0.5])
        plt.colorbar(im, ax=ax, label="Meilleure fitness (clippee)")
        ax.set_xlabel("Generation")
        ax.set_ylabel("Run")
        ax.set_yticks(range(1, n_runs + 1))
        ax.set_yticklabels(["Run " + str(i + 1) for i in range(n_runs)], fontsize=8)
        ax.set_title("Heatmap fitness - Env " + env + " (" + col + ")")
        fig.tight_layout()
        path = os.path.join(out_dir, "05_heatmap_env" + env.lower() + ".png")
        fig.savefig(path, dpi=150)
        plt.close(fig)
        print("  -> " + path)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    args = parse_args()

    if not os.path.exists(args.csv):
        sys.exit("[error] CSV non trouve : " + args.csv)

    os.makedirs(args.out, exist_ok=True)

    print("Chargement de " + args.csv + " ...")
    runs = load_runs(args.csv)
    n_exploded = sum(1 for r in runs if r["exploded"].iloc[0])
    print("  " + str(len(runs)) + " run(s) detectes, "
          + str(sum(len(r) for r in runs)) + " lignes au total.")
    if n_exploded:
        print("  /!\\ " + str(n_exploded) + " run(s) avec explosion physique (fitness > 1e6) - traces en pointilles.")
    print()

    smry = summary_table(runs)
    print("=== Resume par run ===")
    print(smry.to_string(index=False))
    print()

    print("Generation des graphiques dans " + args.out)
    plot_dashboard(runs, args.out)
    plot_fitness(runs, args.out)
    plot_diversity(runs, args.out)
    plot_complexity(runs, args.out)
    plot_run_comparison(runs, args.out)
    plot_heatmap(runs, args.out)

    print()
    print("Termine.")


if __name__ == "__main__":
    main()
