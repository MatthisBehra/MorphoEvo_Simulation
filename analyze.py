# -*- coding: utf-8 -*-
"""
MorphoEvo - Evolution Data Analysis

By default, loads the most recent session from data/session_*/stats.csv.
Override with --csv PATH or --session DIR.

Usage:
    python analyze.py                          # latest session, plots -> <session>/plots/
    python analyze.py --csv evolution_data.csv # specific CSV
    python analyze.py --session data/session_2026-04-17_120000
    python analyze.py --out custom_plots/
"""

import argparse
import glob
import json
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import numpy as np
import pandas as pd


# ── CLI ──────────────────────────────────────────────────────────────────────

def parse_args():
    p = argparse.ArgumentParser(description="Plot MorphoEvo evolution stats.")
    p.add_argument("--csv",     default=None, help="Explicit CSV path.")
    p.add_argument("--session", default=None, help="Session directory containing stats.csv.")
    p.add_argument("--out",     default=None, help="Output directory for plots.")
    p.add_argument("--data-dir", default="data", help="Root dir holding session_*/ folders.")
    return p.parse_args()


def resolve_paths(args):
    """Return (csv_path, out_dir, session_meta_or_None)."""
    if args.csv:
        csv_path = args.csv
        out_dir  = args.out or os.path.join(os.path.dirname(csv_path) or ".", "plots")
        return csv_path, out_dir, None

    session_dir = args.session
    if session_dir is None:
        pattern   = os.path.join(args.data_dir, "session_*")
        sessions  = sorted(glob.glob(pattern))
        if not sessions:
            sys.exit(f"[error] No sessions found under {pattern}. "
                     f"Run a simulation first, or pass --csv.")
        session_dir = sessions[-1]

    csv_path = os.path.join(session_dir, "stats.csv")
    if not os.path.exists(csv_path):
        sys.exit(f"[error] stats.csv not found in {session_dir}")

    out_dir = args.out or os.path.join(session_dir, "plots")

    meta_path = os.path.join(session_dir, "session.json")
    meta = None
    if os.path.exists(meta_path):
        with open(meta_path, encoding="utf-8") as f:
            meta = json.load(f)

    return csv_path, out_dir, meta


# ── Constants ────────────────────────────────────────────────────────────────

ENV_COLORS          = {"A": "#2196F3", "B": "#FF9800"}
EXPLOSION_THRESHOLD = 1e6


# ── Data loading ─────────────────────────────────────────────────────────────

def load_csv(csv_path):
    df = pd.read_csv(csv_path)

    # Clip explosions to keep plots legible
    for col in df.columns:
        if col.startswith(("best_", "avg_", "min_", "max_", "median_", "p25_", "p75_", "std_")):
            df[col] = df[col].clip(lower=-EXPLOSION_THRESHOLD, upper=EXPLOSION_THRESHOLD)

    return df


# ── Plot helpers ─────────────────────────────────────────────────────────────

def _line_both(ax, df, col_a, col_b, ylabel, title,
               label_a="Env A (Plaine)", label_b="Env B (Terrain)",
               logy=False):
    g = df["generation"]
    if col_a in df.columns:
        ax.plot(g, df[col_a], color=ENV_COLORS["A"], lw=2.0, label=label_a)
    if col_b in df.columns:
        ax.plot(g, df[col_b], color=ENV_COLORS["B"], lw=2.0, label=label_b)
    ax.set_xlabel("Generation")
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3)
    if logy:
        ax.set_yscale("symlog")


def _band_both(ax, df, lo_a, hi_a, mid_a, lo_b, hi_b, mid_b, title, ylabel):
    g = df["generation"]
    ax.fill_between(g, df[lo_a], df[hi_a], color=ENV_COLORS["A"], alpha=0.20)
    ax.plot(g, df[mid_a], color=ENV_COLORS["A"], lw=2.0, label="Env A median")
    ax.fill_between(g, df[lo_b], df[hi_b], color=ENV_COLORS["B"], alpha=0.20)
    ax.plot(g, df[mid_b], color=ENV_COLORS["B"], lw=2.0, label="Env B median")
    ax.set_xlabel("Generation")
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3)


# ── Plots ────────────────────────────────────────────────────────────────────

def plot_fitness(df, out_dir):
    fig, axes = plt.subplots(2, 2, figsize=(14, 9))
    fig.suptitle("Evolution de la fitness", fontsize=14, fontweight="bold")

    _line_both(axes[0, 0], df, "best_a",   "best_b",   "Fitness",  "Meilleure fitness")
    _line_both(axes[0, 1], df, "avg_a",    "avg_b",    "Fitness",  "Fitness moyenne")
    _band_both(axes[1, 0], df, "p25_a", "p75_a", "median_a",
                              "p25_b", "p75_b", "median_b",
                              "Distribution fitness (p25-p75, mediane)", "Fitness")
    _line_both(axes[1, 1], df, "std_a",    "std_b",    "sigma",    "Ecart-type fitness")

    fig.tight_layout()
    path = os.path.join(out_dir, "01_fitness.png")
    fig.savefig(path, dpi=150)
    plt.close(fig)
    print(f"  -> {path}")


def plot_diversity(df, out_dir):
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    fig.suptitle("Diversite et divergence", fontsize=13, fontweight="bold")

    _line_both(axes[0], df, "diversity_a", "diversity_b",
               "sigma segments", "Diversite morphologique (std segments)")

    ax = axes[1]
    if "genotype_dist_ab" in df.columns:
        ax.plot(df["generation"], df["genotype_dist_ab"],
                color="#8E44AD", lw=2.0, label="mean dist(A,B)")
    ax.set_title("Divergence genotypique A <-> B")
    ax.set_xlabel("Generation")
    ax.set_ylabel("Distance genotype (Euclidean)")
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3)

    fig.tight_layout()
    path = os.path.join(out_dir, "02_diversity.png")
    fig.savefig(path, dpi=150)
    plt.close(fig)
    print(f"  -> {path}")


def plot_morphology(df, out_dir):
    fig, axes = plt.subplots(2, 2, figsize=(14, 9))
    fig.suptitle("Morphologie des populations", fontsize=13, fontweight="bold")

    _line_both(axes[0, 0], df, "avg_segments_a", "avg_segments_b",
               "Segments", "Segments moyens")
    _line_both(axes[0, 1], df, "max_segments_a", "max_segments_b",
               "Segments", "Segments max")
    _line_both(axes[1, 0], df, "avg_depth_a", "avg_depth_b",
               "Profondeur", "Profondeur moyenne de l'arbre")
    _line_both(axes[1, 1], df, "avg_branching_a", "avg_branching_b",
               "Enfants / noeud", "Facteur de branchement moyen")

    fig.tight_layout()
    path = os.path.join(out_dir, "03_morphology.png")
    fig.savefig(path, dpi=150)
    plt.close(fig)
    print(f"  -> {path}")


def plot_physical(df, out_dir):
    fig, axes = plt.subplots(2, 2, figsize=(14, 9))
    fig.suptitle("Metriques physiques", fontsize=13, fontweight="bold")

    _line_both(axes[0, 0], df, "avg_distance_a", "avg_distance_b",
               "Distance (px)", "Distance parcourue moyenne")
    _line_both(axes[0, 1], df, "avg_energy_a", "avg_energy_b",
               "Energie", "Energie metabolique moyenne", logy=True)
    _line_both(axes[1, 0], df, "avg_stability_a", "avg_stability_b",
               "Stabilite [0-1]", "Stabilite du tronc")
    _line_both(axes[1, 1], df, "avg_mass_a", "avg_mass_b",
               "Masse", "Masse totale moyenne")

    fig.tight_layout()
    path = os.path.join(out_dir, "04_physical.png")
    fig.savefig(path, dpi=150)
    plt.close(fig)
    print(f"  -> {path}")


def plot_genes(df, out_dir):
    fig, axes = plt.subplots(2, 2, figsize=(14, 9))
    fig.suptitle("Derive des genes (moyenne population)", fontsize=13,
                 fontweight="bold")

    _line_both(axes[0, 0], df, "avg_motor_force_a", "avg_motor_force_b",
               "Force",  "Motor force")
    _line_both(axes[0, 1], df, "avg_motor_speed_a", "avg_motor_speed_b",
               "Vitesse", "Motor speed")
    _line_both(axes[1, 0], df, "avg_friction_a", "avg_friction_b",
               "Friction", "Friction segments")
    _line_both(axes[1, 1], df, "avg_damping_a", "avg_damping_b",
               "Damping", "Joint damping")

    fig.tight_layout()
    path = os.path.join(out_dir, "05_genes.png")
    fig.savefig(path, dpi=150)
    plt.close(fig)
    print(f"  -> {path}")


def plot_selection(df, out_dir):
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    fig.suptitle("Pression de selection et cout temporel", fontsize=13,
                 fontweight="bold")

    _line_both(axes[0], df, "sel_intensity_a", "sel_intensity_b",
               "(best-mean)/sigma", "Intensite de selection")

    ax = axes[1]
    if "wall_time_s" in df.columns:
        ax.plot(df["generation"], df["wall_time_s"],
                color="#2ECC71", lw=1.8, label="wall time")
    ax.set_title("Temps mur par generation")
    ax.set_xlabel("Generation")
    ax.set_ylabel("Secondes")
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3)

    fig.tight_layout()
    path = os.path.join(out_dir, "06_selection_timing.png")
    fig.savefig(path, dpi=150)
    plt.close(fig)
    print(f"  -> {path}")


def plot_correlation(df, out_dir):
    """Scatter: complexity vs best fitness (all gens lumped)."""
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    fig.suptitle("Correlations complexite <-> fitness", fontsize=13,
                 fontweight="bold")

    for ax, env in zip(axes, ("a", "b")):
        x = df[f"avg_segments_{env}"]
        y = df[f"best_{env}"]
        ax.scatter(x, y, alpha=0.55, s=18,
                   color=ENV_COLORS[env.upper()])
        mask = np.isfinite(x) & np.isfinite(y)
        if mask.sum() > 2:
            coef = np.polyfit(x[mask], y[mask], 1)
            xr   = np.linspace(x[mask].min(), x[mask].max(), 100)
            ax.plot(xr, np.polyval(coef, xr),
                    color=ENV_COLORS[env.upper()], lw=1.5,
                    label=f"linreg slope={coef[0]:.1f}")
        ax.set_xlabel("Segments moyens")
        ax.set_ylabel("Best fitness")
        ax.set_title(f"Env {env.upper()}")
        ax.legend(fontsize=8)
        ax.grid(True, alpha=0.3)

    fig.tight_layout()
    path = os.path.join(out_dir, "07_correlation.png")
    fig.savefig(path, dpi=150)
    plt.close(fig)
    print(f"  -> {path}")


def plot_dashboard(df, out_dir):
    fig = plt.figure(figsize=(18, 11))
    fig.suptitle("MorphoEvo - Dashboard", fontsize=15, fontweight="bold")
    gs = gridspec.GridSpec(3, 3, figure=fig, hspace=0.50, wspace=0.35)

    _line_both(fig.add_subplot(gs[0, 0]), df, "best_a", "best_b",
               "Fitness", "Meilleure fitness")
    _line_both(fig.add_subplot(gs[0, 1]), df, "avg_a", "avg_b",
               "Fitness", "Fitness moyenne")
    ax = fig.add_subplot(gs[0, 2])
    _band_both(ax, df, "p25_a", "p75_a", "median_a",
                        "p25_b", "p75_b", "median_b",
                        "Distribution (p25-p75)", "Fitness")

    _line_both(fig.add_subplot(gs[1, 0]), df, "diversity_a", "diversity_b",
               "sigma segs", "Diversite")
    _line_both(fig.add_subplot(gs[1, 1]), df, "avg_segments_a", "avg_segments_b",
               "Segments", "Complexite")
    _line_both(fig.add_subplot(gs[1, 2]), df, "avg_depth_a", "avg_depth_b",
               "Depth", "Profondeur arbre")

    _line_both(fig.add_subplot(gs[2, 0]), df, "avg_distance_a", "avg_distance_b",
               "px", "Distance")
    _line_both(fig.add_subplot(gs[2, 1]), df, "avg_energy_a", "avg_energy_b",
               "E", "Energie", logy=True)

    ax_div = fig.add_subplot(gs[2, 2])
    if "genotype_dist_ab" in df.columns:
        ax_div.plot(df["generation"], df["genotype_dist_ab"],
                    color="#8E44AD", lw=2.0)
    ax_div.set_title("Divergence A <-> B")
    ax_div.set_xlabel("Generation")
    ax_div.set_ylabel("Distance genotype")
    ax_div.grid(True, alpha=0.3)

    path = os.path.join(out_dir, "00_dashboard.png")
    fig.savefig(path, dpi=150)
    plt.close(fig)
    print(f"  -> {path}")


# ── Summary ──────────────────────────────────────────────────────────────────

def print_summary(df, meta):
    print("=== Session summary ===")
    if meta:
        for k in ("n_creatures", "gen_duration", "speed_mode", "timestamp"):
            if k in meta:
                print(f"  {k:>16}: {meta[k]}")
    print(f"  {'generations':>16}: {len(df)}")
    if "wall_time_s" in df.columns:
        print(f"  {'total wall time':>16}: {df['wall_time_s'].sum():.1f}s")
    print()

    rows = []
    for env in ("a", "b"):
        rows.append([
            env.upper(),
            df[f"best_{env}"].max(),
            df[f"avg_{env}"].mean(),
            df[f"avg_segments_{env}"].iloc[-1],
            df[f"avg_distance_{env}"].iloc[-1],
        ])
    summary = pd.DataFrame(rows, columns=[
        "env", "peak_best", "mean_avg", "final_segments", "final_distance"
    ])
    print(summary.to_string(index=False))
    print()


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    args = parse_args()
    csv_path, out_dir, meta = resolve_paths(args)

    os.makedirs(out_dir, exist_ok=True)

    print(f"Loading {csv_path}")
    df = load_csv(csv_path)
    print(f"  {len(df)} generations")
    print()

    print_summary(df, meta)

    print(f"Generating plots in {out_dir}")
    plot_dashboard(df, out_dir)
    plot_fitness(df, out_dir)
    plot_diversity(df, out_dir)
    plot_morphology(df, out_dir)
    plot_physical(df, out_dir)
    plot_genes(df, out_dir)
    plot_selection(df, out_dir)
    plot_correlation(df, out_dir)

    print()
    print("Termine.")


if __name__ == "__main__":
    main()
