"""Render analytical plots for the article: fitness convergence, segment growth,
final distributions, distance heatmaps, parameter specialization."""

import json
import math
from pathlib import Path

import numpy as np
import matplotlib.pyplot as plt


ROOT = Path(__file__).resolve().parent.parent
RUN_DIR = ROOT / "runs" / "multirun_2026-04-21_220850"
REPORT = RUN_DIR / "report.json"
OUT_DIR = ROOT / "docs" / "figures"


def load_report():
    with open(REPORT, "r") as f:
        return json.load(f)


def load_lineage(run_id, env):
    path = RUN_DIR / f"run_{run_id}_{env}_lineage.jsonl"
    out = []
    with open(path, "r") as f:
        for line in f:
            if line.strip():
                out.append(json.loads(line))
    return out


def collect_dna_scalars(dna, keys, out=None):
    if out is None:
        out = {k: [] for k in keys}
    for k in keys:
        if k in dna:
            out[k].append(dna[k])
    for c in dna.get("children", []):
        collect_dna_scalars(c, keys, out)
    return out


# ─────────────────────────────────────────────────────────────────────────────


def plot_fitness_convergence(rep, out_path):
    """Mean ± std fitness over generations across the 20 runs, A vs B."""
    a_hists = np.array([r["fitness_history"] for r in rep["results_a"]])
    b_hists = np.array([r["fitness_history"] for r in rep["results_b"]])
    gens = np.arange(a_hists.shape[1])

    a_mean, a_std = a_hists.mean(0), a_hists.std(0)
    b_mean, b_std = b_hists.mean(0), b_hists.std(0)

    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(gens, a_mean, color="#1f77b4", label="Env A (plaine) — moyenne")
    ax.fill_between(gens, a_mean - a_std, a_mean + a_std, color="#1f77b4", alpha=0.18,
                    label="Env A — ±1 σ (n=20)")
    ax.plot(gens, b_mean, color="#d2691e", label="Env B (terrain) — moyenne")
    ax.fill_between(gens, b_mean - b_std, b_mean + b_std, color="#d2691e", alpha=0.18,
                    label="Env B — ±1 σ (n=20)")
    ax.set_xlabel("Génération")
    ax.set_ylabel("Fitness du meilleur individu")
    ax.set_title("Convergence de la fitness — moyenne ± écart-type sur 20 runs")
    ax.legend(loc="lower right", fontsize=9)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def plot_segments_evolution(out_path):
    """Mean n_segments per generation across 20 runs, from pop_stats."""
    a_segs, b_segs = [], []
    for rid in range(20):
        la = load_lineage(rid, "A")
        lb = load_lineage(rid, "B")
        a_segs.append([g["pop_stats"]["n_segments"]["mean"] for g in la])
        b_segs.append([g["pop_stats"]["n_segments"]["mean"] for g in lb])
    a_segs = np.array(a_segs)
    b_segs = np.array(b_segs)
    gens = np.arange(a_segs.shape[1])

    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(gens, a_segs.mean(0), color="#1f77b4", label="Env A — moyenne pop")
    ax.fill_between(gens, a_segs.mean(0) - a_segs.std(0), a_segs.mean(0) + a_segs.std(0),
                    color="#1f77b4", alpha=0.18, label="Env A — ±1 σ")
    ax.plot(gens, b_segs.mean(0), color="#d2691e", label="Env B — moyenne pop")
    ax.fill_between(gens, b_segs.mean(0) - b_segs.std(0), b_segs.mean(0) + b_segs.std(0),
                    color="#d2691e", alpha=0.18, label="Env B — ±1 σ")
    ax.set_xlabel("Génération")
    ax.set_ylabel("Nombre moyen de segments dans la population")
    ax.set_title("Évolution de la complexité morphologique — n_segments moyen par génération")
    ax.legend(loc="lower right", fontsize=9)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def plot_final_distributions(rep, out_path):
    """Boxplots: best fitness and final n_segments per env."""
    af = [r["best_fitness"] for r in rep["results_a"]]
    bf = [r["best_fitness"] for r in rep["results_b"]]
    asg = [r["final_segments"] for r in rep["results_a"]]
    bsg = [r["final_segments"] for r in rep["results_b"]]

    fig, axes = plt.subplots(1, 2, figsize=(11, 4.5))

    bp1 = axes[0].boxplot([af, bf], labels=["Env A", "Env B"], patch_artist=True, widths=0.55)
    for patch, color in zip(bp1["boxes"], ["#cfe5f5", "#f5dac0"]):
        patch.set_facecolor(color)
    axes[0].scatter(np.random.normal(1, 0.05, len(af)), af, color="#1f77b4", alpha=0.6, s=22, zorder=3)
    axes[0].scatter(np.random.normal(2, 0.05, len(bf)), bf, color="#d2691e", alpha=0.6, s=22, zorder=3)
    axes[0].set_ylabel("Meilleure fitness atteinte (sur 1000 gen)")
    axes[0].set_title("Distribution de la fitness maximale")
    axes[0].grid(alpha=0.3, axis="y")

    bp2 = axes[1].boxplot([asg, bsg], labels=["Env A", "Env B"], patch_artist=True, widths=0.55)
    for patch, color in zip(bp2["boxes"], ["#cfe5f5", "#f5dac0"]):
        patch.set_facecolor(color)
    axes[1].scatter(np.random.normal(1, 0.05, len(asg)), asg, color="#1f77b4", alpha=0.6, s=22, zorder=3)
    axes[1].scatter(np.random.normal(2, 0.05, len(bsg)), bsg, color="#d2691e", alpha=0.6, s=22, zorder=3)
    axes[1].set_ylabel("Nombre de segments du meilleur individu final")
    axes[1].set_title("Distribution de la complexité morphologique finale")
    axes[1].grid(alpha=0.3, axis="y")

    fig.suptitle("Distributions finales — 20 runs par environnement", fontsize=12, fontweight="bold")
    fig.tight_layout(rect=[0, 0, 1, 0.95])
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def plot_paired_scatter(rep, out_path):
    """Scatter A vs B per pair: fitness and segments."""
    af = [r["best_fitness"] for r in rep["results_a"]]
    bf = [r["best_fitness"] for r in rep["results_b"]]
    asg = [r["final_segments"] for r in rep["results_a"]]
    bsg = [r["final_segments"] for r in rep["results_b"]]

    fig, axes = plt.subplots(1, 2, figsize=(11, 4.8))

    lim = max(max(af), max(bf)) * 1.05
    axes[0].plot([0, lim], [0, lim], color="grey", linestyle="--", linewidth=1, label="y = x")
    axes[0].scatter(af, bf, c=range(20), cmap="tab20", s=70, edgecolors="black")
    for i, (x, y) in enumerate(zip(af, bf)):
        axes[0].annotate(str(i), (x, y), fontsize=8, alpha=0.8,
                         xytext=(4, 4), textcoords="offset points")
    axes[0].set_xlabel("Fitness max — Env A")
    axes[0].set_ylabel("Fitness max — Env B")
    axes[0].set_title("Fitness A vs B par paire (même init)")
    axes[0].legend(loc="upper left", fontsize=9)
    axes[0].grid(alpha=0.3)
    axes[0].set_xlim(0, lim)
    axes[0].set_ylim(0, lim)

    smax = max(max(asg), max(bsg)) + 2
    axes[1].plot([0, smax], [0, smax], color="grey", linestyle="--", linewidth=1, label="y = x")
    axes[1].scatter(asg, bsg, c=range(20), cmap="tab20", s=70, edgecolors="black")
    for i, (x, y) in enumerate(zip(asg, bsg)):
        axes[1].annotate(str(i), (x, y), fontsize=8, alpha=0.8,
                         xytext=(4, 4), textcoords="offset points")
    axes[1].set_xlabel("Segments — Env A")
    axes[1].set_ylabel("Segments — Env B")
    axes[1].set_title("Segments A vs B par paire (même init)")
    axes[1].legend(loc="upper left", fontsize=9)
    axes[1].grid(alpha=0.3)
    axes[1].set_xlim(0, smax)
    axes[1].set_ylim(0, smax)

    fig.suptitle("Comparaison appariée A vs B — chaque point = une graine partagée",
                 fontsize=12, fontweight="bold")
    fig.tight_layout(rect=[0, 0, 1, 0.95])
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def plot_distance_heatmaps(rep, out_path):
    """Heatmaps of AA, BB, AB distance matrices."""
    aa = np.array(rep["distance_matrix_aa"])
    bb = np.array(rep["distance_matrix_bb"])
    ab = np.array(rep["distance_matrix_ab"])

    fig, axes = plt.subplots(1, 3, figsize=(15, 4.6))
    vmax = max(aa.max(), bb.max(), ab.max())

    for ax, M, title in zip(axes, [aa, bb, ab],
                            ["Distance intra A (AA)", "Distance intra B (BB)",
                             "Distance inter A↔B (AB)"]):
        im = ax.imshow(M, vmin=0, vmax=vmax, cmap="magma")
        ax.set_title(title, fontsize=11)
        ax.set_xlabel("run")
        ax.set_ylabel("run")
        ax.set_xticks(range(0, 20, 4))
        ax.set_yticks(range(0, 20, 4))
        avg = M[~np.eye(20, dtype=bool)].mean() if M.shape == (20, 20) and title != "Distance inter A↔B (AB)" else M.mean()
        ax.text(0.5, -0.18, f"moyenne = {avg:.3f}", transform=ax.transAxes,
                ha="center", fontsize=10)

    cbar = fig.colorbar(im, ax=axes, fraction=0.022, pad=0.02)
    cbar.set_label("Distance morphologique normalisée")
    fig.suptitle("Matrices de distance morphologique entre meilleurs individus finaux",
                 fontsize=13, fontweight="bold")
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def plot_param_specialization(out_path):
    """Compare distributions of motor_speed and joint_damping aggregated over the
    best DNA tree of each run, A vs B."""
    keys = ["motor_speed", "joint_damping", "motor_force", "friction"]
    a_scal = {k: [] for k in keys}
    b_scal = {k: [] for k in keys}
    for rid in range(20):
        la = load_lineage(rid, "A")[-1]["best_dna"]
        lb = load_lineage(rid, "B")[-1]["best_dna"]
        out_a = collect_dna_scalars(la, keys)
        out_b = collect_dna_scalars(lb, keys)
        for k in keys:
            a_scal[k].extend(out_a[k])
            b_scal[k].extend(out_b[k])

    fig, axes = plt.subplots(2, 2, figsize=(11, 7.5))
    titles = {
        "motor_speed": "Fréquence motrice (motor_speed)",
        "joint_damping": "Amortissement articulaire (joint_damping)",
        "motor_force": "Force motrice (motor_force)",
        "friction": "Friction des segments (friction)",
    }
    for ax, k in zip(axes.flatten(), keys):
        ax.hist(a_scal[k], bins=20, color="#1f77b4", alpha=0.55, label=f"Env A (n={len(a_scal[k])})")
        ax.hist(b_scal[k], bins=20, color="#d2691e", alpha=0.55, label=f"Env B (n={len(b_scal[k])})")
        ax.axvline(np.mean(a_scal[k]), color="#1f77b4", linestyle="--", linewidth=1.5)
        ax.axvline(np.mean(b_scal[k]), color="#d2691e", linestyle="--", linewidth=1.5)
        ax.set_title(titles[k], fontsize=11)
        ax.set_ylabel("Fréquence (segments)")
        ax.legend(fontsize=9)
        ax.grid(alpha=0.3)
    fig.suptitle("Spécialisation paramétrique par environnement — segments des 20 meilleurs DNA finaux",
                 fontsize=12, fontweight="bold")
    fig.tight_layout(rect=[0, 0, 1, 0.96])
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)

    # Print stats for the article
    print("\n[param specialization — means]")
    for k in keys:
        print(f"  {k:15s}  A={np.mean(a_scal[k]):.3f}  B={np.mean(b_scal[k]):.3f}")


def plot_fitness_vs_segments(rep, out_path):
    """Scatter: fitness vs final n_segments, colored by env."""
    af = [r["best_fitness"] for r in rep["results_a"]]
    bf = [r["best_fitness"] for r in rep["results_b"]]
    asg = [r["final_segments"] for r in rep["results_a"]]
    bsg = [r["final_segments"] for r in rep["results_b"]]

    fig, ax = plt.subplots(figsize=(8, 5))
    ax.scatter(asg, af, color="#1f77b4", s=70, edgecolors="black", label="Env A (plaine)", alpha=0.85)
    ax.scatter(bsg, bf, color="#d2691e", s=70, edgecolors="black", label="Env B (terrain)", alpha=0.85)

    # Linear regression per env
    for xs, ys, color, lbl in [(asg, af, "#1f77b4", "A"), (bsg, bf, "#d2691e", "B")]:
        coef = np.polyfit(xs, ys, 1)
        xl = np.linspace(min(xs), max(xs), 50)
        ax.plot(xl, np.polyval(coef, xl), color=color, linestyle=":", alpha=0.7,
                label=f"Tendance {lbl} (pente={coef[0]:.0f})")

    ax.set_xlabel("Nombre de segments du meilleur individu final")
    ax.set_ylabel("Meilleure fitness atteinte")
    ax.set_title("Fitness en fonction de la complexité morphologique — 20 runs × 2 environnements")
    ax.legend(fontsize=9)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    rep = load_report()

    plot_fitness_convergence(rep, OUT_DIR / "fitness_convergence.png")
    print("wrote fitness_convergence.png")

    plot_segments_evolution(OUT_DIR / "segments_evolution.png")
    print("wrote segments_evolution.png")

    plot_final_distributions(rep, OUT_DIR / "final_distributions.png")
    print("wrote final_distributions.png")

    plot_paired_scatter(rep, OUT_DIR / "paired_scatter.png")
    print("wrote paired_scatter.png")

    plot_distance_heatmaps(rep, OUT_DIR / "distance_heatmaps.png")
    print("wrote distance_heatmaps.png")

    plot_param_specialization(OUT_DIR / "param_specialization.png")
    print("wrote param_specialization.png")

    plot_fitness_vs_segments(rep, OUT_DIR / "fitness_vs_segments.png")
    print("wrote fitness_vs_segments.png")


if __name__ == "__main__":
    main()
