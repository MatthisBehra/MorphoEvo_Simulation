"""Render best-individual morphologies from a multi-run session and compose
a side-by-side A vs B comparison figure (PNG). Used by build_article_v4.py."""

import json
import math
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.transforms import Affine2D


ROOT = Path(__file__).resolve().parent.parent
RUN_DIR = ROOT / "runs" / "multirun_2026-04-21_220850"
OUT_DIR = ROOT / "docs" / "figures"


def last_dna(run_id, env):
    path = RUN_DIR / f"run_{run_id}_{env}_lineage.jsonl"
    with open(path, "r") as f:
        last = None
        for line in f:
            if line.strip():
                last = json.loads(line)
    return last


def collect_segments(dna, parent_tip=(0.0, 0.0), inherited_angle=0.0, out=None):
    """Walk the DNA tree exactly like Creature._build_node, accumulating box geometry."""
    if out is None:
        out = []
    world_angle = inherited_angle + dna["attach_angle"]
    w = dna["width"]
    h = dna["height"]
    cx = parent_tip[0] + math.cos(world_angle) * w / 2
    cy = parent_tip[1] + math.sin(world_angle) * w / 2
    out.append({
        "cx": cx, "cy": cy, "w": w, "h": h,
        "angle": world_angle,
        "motor_speed": dna.get("motor_speed", 5.0),
    })
    tip = (
        parent_tip[0] + math.cos(world_angle) * w,
        parent_tip[1] + math.sin(world_angle) * w,
    )
    for child in dna.get("children", []):
        collect_segments(child, tip, world_angle, out)
    return out


def draw_morpho(ax, dna, title, env_label):
    segs = collect_segments(dna)
    color_palette = plt.get_cmap("viridis")
    for s in segs:
        # color encodes motor_speed in [0.3, 15]
        cval = max(0.0, min(1.0, (s["motor_speed"] - 0.3) / 14.7))
        color = color_palette(cval)
        rect = mpatches.Rectangle(
            (-s["w"] / 2, -s["h"] / 2), s["w"], s["h"],
            linewidth=0.8, edgecolor="black", facecolor=color, alpha=0.85,
        )
        t = Affine2D().rotate(s["angle"]).translate(s["cx"], s["cy"]) + ax.transData
        rect.set_transform(t)
        ax.add_patch(rect)
    xs = [s["cx"] for s in segs]
    ys = [s["cy"] for s in segs]
    sizes = [max(s["w"], s["h"]) for s in segs]
    pad = max(sizes) * 1.4
    ax.set_xlim(min(xs) - pad, max(xs) + pad)
    ax.set_ylim(min(ys) - pad, max(ys) + pad)
    ax.set_aspect("equal")
    ax.axhline(min(ys) - pad * 0.3, color="saddlebrown", linewidth=2, alpha=0.5)
    ax.set_xticks([])
    ax.set_yticks([])
    bg = "#eaf4fb" if env_label == "A" else "#fbe9da"
    ax.set_facecolor(bg)
    ax.set_title(title, fontsize=10)


def build_pair_figure(pairs, fname, suptitle):
    """pairs : list of (run_id, label_a, label_b) → 4 rows, 2 cols (A | B)."""
    n = len(pairs)
    fig, axes = plt.subplots(n, 2, figsize=(10, 2.6 * n))
    if n == 1:
        axes = [axes]
    for i, (rid, lbl_a, lbl_b) in enumerate(pairs):
        a = last_dna(rid, "A")
        b = last_dna(rid, "B")
        draw_morpho(
            axes[i][0], a["best_dna"],
            f"Run {rid} — Env A (plaine) — fit={a['best_fitness']:.0f}, segs={a['n_segments']}",
            "A",
        )
        draw_morpho(
            axes[i][1], b["best_dna"],
            f"Run {rid} — Env B (terrain) — fit={b['best_fitness']:.0f}, segs={b['n_segments']}",
            "B",
        )
    fig.suptitle(suptitle, fontsize=13, fontweight="bold")
    fig.tight_layout(rect=[0, 0, 1, 0.97])
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / fname
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out_path


def build_grid_figure(run_ids, env, fname, suptitle):
    n = len(run_ids)
    cols = 5
    rows = (n + cols - 1) // cols
    fig, axes = plt.subplots(rows, cols, figsize=(2.4 * cols, 2.4 * rows))
    axes = axes.flatten() if rows > 1 else list(axes)
    for ax, rid in zip(axes, run_ids):
        d = last_dna(rid, env)
        draw_morpho(
            ax, d["best_dna"],
            f"Run {rid} — fit={d['best_fitness']:.0f} — segs={d['n_segments']}",
            env,
        )
    for ax in axes[len(run_ids):]:
        ax.axis("off")
    fig.suptitle(suptitle, fontsize=13, fontweight="bold")
    fig.tight_layout(rect=[0, 0, 1, 0.96])
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / fname
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out_path


def main():
    # Selected pairs: cover the four observed regimes
    #  - run 5  : both very high fitness, A and B comparable in segments
    #  - run 8  : A dominant (A=25932), B much lower
    #  - run 10 : B dominant (B=31964), B more segments
    #  - run 15 : B dominant with B = max of all runs (32999)
    pairs = [
        (5, "A", "B"),
        (8, "A", "B"),
        (10, "A", "B"),
        (15, "A", "B"),
    ]
    p1 = build_pair_figure(
        pairs, "morpho_pairs_selected.png",
        "Comparaison morphologique A vs B — 4 paires représentatives",
    )
    print("wrote", p1)

    p2 = build_grid_figure(
        list(range(20)), "A", "morpho_all_A.png",
        "Morphologies finales — 20 runs, environnement A (plaine)",
    )
    print("wrote", p2)
    p3 = build_grid_figure(
        list(range(20)), "B", "morpho_all_B.png",
        "Morphologies finales — 20 runs, environnement B (terrain accidenté)",
    )
    print("wrote", p3)


if __name__ == "__main__":
    main()
