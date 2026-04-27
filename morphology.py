# -*- coding: utf-8 -*-
"""
MorphoEvo - Morphology snapshot renderer

Reads lineage.jsonl from a session (best DNA/gen for A and B) and draws the
skeleton of the best creature of a given generation as a static PNG.

Usage:
    python morphology.py                       # latest session, last generation
    python morphology.py --gen 50              # specific generation
    python morphology.py --gen last            # last recorded generation
    python morphology.py --gen all             # one PNG per generation
    python morphology.py --gen "1,10,50,100"   # list of generations
    python morphology.py --env A               # only env A (default: both)
    python morphology.py --session data/session_2026-04-17_120000
    python morphology.py --runs-dir runs       # all multi-run lineages, step 100
    python morphology.py --runs-dir runs --step 50
"""

import argparse
import glob
import json
import math
import os
import re
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
from matplotlib.transforms import Affine2D


ENV_COLORS   = {"A": "#2196F3", "B": "#FF9800"}
ROOT_COLOR   = "#2C3E50"
SEGMENT_EDGE = "#1B2631"
JOINT_COLOR  = "#C0392B"


# ── CLI ──────────────────────────────────────────────────────────────────────

def parse_args():
    p = argparse.ArgumentParser(description="Render morphology snapshots from lineage.jsonl")
    p.add_argument("--gen",     default="last",
                   help="'last', 'all', an integer, or a comma list (e.g. '1,10,50')")
    p.add_argument("--env",     default="both", choices=("A", "B", "both"))
    p.add_argument("--session", default=None, help="Session dir (default: latest under data/)")
    p.add_argument("--data-dir", default="data")
    p.add_argument("--out",     default=None, help="Output file (single gen) or dir (multi).")
    p.add_argument("--runs-dir", default=None,
                   help="Render morphologies for every run_*_*_lineage.jsonl in this dir.")
    p.add_argument("--step",    type=int, default=100,
                   help="Generation stride for --runs-dir (default 100; also keeps gen 1 and last).")
    return p.parse_args()


def resolve_session(args):
    if args.session:
        return args.session
    sessions = sorted(glob.glob(os.path.join(args.data_dir, "session_*")))
    if not sessions:
        sys.exit(f"[error] No sessions in {args.data_dir}/")
    return sessions[-1]


# ── Lineage loading ──────────────────────────────────────────────────────────

def load_lineage(session_dir):
    path = os.path.join(session_dir, "lineage.jsonl")
    if not os.path.exists(path):
        sys.exit(f"[error] lineage.jsonl not found in {session_dir}")
    entries = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                entries.append(json.loads(line))
    return entries


def select_gens(entries, spec):
    available = [e["gen"] for e in entries]
    last_gen  = available[-1]

    if spec == "last":
        return [last_gen]
    if spec == "all":
        return available
    if "," in spec:
        wanted = [int(s.strip()) for s in spec.split(",") if s.strip()]
    else:
        wanted = [int(spec)]

    missing = [g for g in wanted if g not in available]
    if missing:
        sys.exit(f"[error] generations not in lineage: {missing}")
    return wanted


# ── Skeleton layout (no physics) ─────────────────────────────────────────────

def _collect_segments(dna, parent_tip=(0.0, 0.0), inherited_angle=0.0, depth=0, out=None):
    """Recursively compute every segment's (center_x, center_y, angle, width, height, depth)."""
    if out is None:
        out = []
    world_angle = inherited_angle + dna["attach_angle"]
    w = dna["width"]
    h = dna["height"]
    cx = parent_tip[0] + math.cos(world_angle) * w / 2
    cy = parent_tip[1] + math.sin(world_angle) * w / 2
    out.append((cx, cy, world_angle, w, h, depth, parent_tip))

    tip_x = parent_tip[0] + math.cos(world_angle) * w
    tip_y = parent_tip[1] + math.sin(world_angle) * w
    for child in dna["children"]:
        _collect_segments(child, (tip_x, tip_y), world_angle, depth + 1, out)
    return out


def _depth_shade(base_hex, depth, max_depth):
    """Darken segments deeper in the tree (root brightest)."""
    base = tuple(int(base_hex[i:i+2], 16) for i in (1, 3, 5))
    t = 1.0 - 0.15 * min(depth, max_depth)
    return tuple(max(0, min(255, int(c * t))) / 255.0 for c in base)


def draw_skeleton(ax, dna, env_label):
    segments = _collect_segments(dna)
    if not segments:
        return

    max_depth = max(s[5] for s in segments)

    xs = [s[0] for s in segments] + [s[6][0] for s in segments]
    ys = [s[1] for s in segments] + [s[6][1] for s in segments]
    span_x = max(1.0, max(xs) - min(xs) + max(s[3] for s in segments))
    span_y = max(1.0, max(ys) - min(ys) + max(s[4] for s in segments))

    for cx, cy, angle, w, h, depth, parent_tip in segments:
        color = ROOT_COLOR if depth == 0 else _depth_shade(ENV_COLORS[env_label], depth, max_depth)
        rect = Rectangle((-w / 2, -h / 2), w, h,
                         facecolor=color, edgecolor=SEGMENT_EDGE, linewidth=1.2)
        t = Affine2D().rotate(angle).translate(cx, cy) + ax.transData
        rect.set_transform(t)
        ax.add_patch(rect)
        # Joint pivot
        ax.plot(parent_tip[0], parent_tip[1], "o",
                color=JOINT_COLOR, markersize=4, zorder=5)

    margin = 0.15 * max(span_x, span_y)
    ax.set_xlim(min(xs) - margin, max(xs) + margin + max(s[3] for s in segments))
    ax.set_ylim(min(ys) - margin, max(ys) + margin)
    ax.set_aspect("equal")
    ax.grid(True, alpha=0.25)


# ── Top-level render ─────────────────────────────────────────────────────────

def render_generation(entry, envs, out_path):
    fig, axes = plt.subplots(1, len(envs), figsize=(6 * len(envs), 6), squeeze=False)
    fig.suptitle(f"Morphologie best / Generation {entry['gen']}", fontsize=14, fontweight="bold")

    for ax, env in zip(axes[0], envs):
        dna = entry[f"best_dna_{env.lower()}"]
        fit = entry[f"best_fitness_{env.lower()}"]
        n_segments = 1 + _count_children(dna)
        draw_skeleton(ax, dna, env)
        ax.set_title(f"Env {env}  -  fitness={fit:.1f}  -  {n_segments} segments",
                     fontsize=11, color=ENV_COLORS[env])

    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def _count_children(dna):
    return len(dna["children"]) + sum(_count_children(c) for c in dna["children"])


# ── Run-lineage rendering (multi-run mode) ───────────────────────────────────

def render_single_env(dna, fitness, env_label, gen, out_path):
    """Render a single-env morphology snapshot (for per-run lineages)."""
    fig, ax = plt.subplots(1, 1, figsize=(6, 6))
    fig.suptitle(f"Morphologie best / Generation {gen}", fontsize=14, fontweight="bold")
    n_segments = 1 + _count_children(dna)
    draw_skeleton(ax, dna, env_label)
    ax.set_title(f"Env {env_label}  -  fitness={fitness:.1f}  -  {n_segments} segments",
                 fontsize=11, color=ENV_COLORS[env_label])
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def _strided_gens(available, step):
    """Keep gen 1, every `step`-th gen, and the last gen — deduped and sorted."""
    last = available[-1]
    wanted = {1, last}
    wanted.update(g for g in available if g % step == 0)
    return sorted(wanted)


def _resolve_runs_dir(runs_dir):
    """If ``runs_dir`` has no lineages but holds multirun_* subfolders, pick latest."""
    if glob.glob(os.path.join(runs_dir, "run_*_*_lineage.jsonl")):
        return runs_dir
    subdirs = sorted(glob.glob(os.path.join(runs_dir, "multirun_*")))
    if subdirs:
        return subdirs[-1]
    return runs_dir


def process_runs_dir(runs_dir, step, out_root):
    runs_dir = _resolve_runs_dir(runs_dir)
    print(f"  resolved -> {runs_dir}")

    pattern = os.path.join(runs_dir, "run_*_*_lineage.jsonl")
    files = sorted(glob.glob(pattern))
    if not files:
        sys.exit(f"[error] No run_*_*_lineage.jsonl in {runs_dir}/")

    out_root = out_root or os.path.join(runs_dir, "morphology")
    os.makedirs(out_root, exist_ok=True)

    total = 0
    for fp in files:
        m = re.match(r"run_(\d+)_([AB])_lineage\.jsonl", os.path.basename(fp))
        if not m:
            continue
        run_id, env = m.group(1), m.group(2)

        entries = []
        with open(fp, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    entries.append(json.loads(line))
        if not entries:
            print(f"  [skip] {fp} empty")
            continue

        available = [e["gen"] for e in entries]
        gens = _strided_gens(available, step)
        by_gen = {e["gen"]: e for e in entries}

        out_dir = os.path.join(out_root, f"run_{run_id}_{env}")
        os.makedirs(out_dir, exist_ok=True)

        for g in gens:
            e = by_gen[g]
            path = os.path.join(out_dir, f"gen_{g:04d}.png")
            render_single_env(e["best_dna"], e["best_fitness"], env, g, path)
            print(f"  -> {path}")
            total += 1

    print(f"\nDone. {total} image(s) under {out_root}")


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    args = parse_args()

    if args.runs_dir:
        print(f"Runs dir: {args.runs_dir}  (step={args.step})")
        process_runs_dir(args.runs_dir, args.step, args.out)
        return

    session_dir = resolve_session(args)
    print(f"Session: {session_dir}")

    entries  = load_lineage(session_dir)
    gens     = select_gens(entries, args.gen)
    envs     = ("A", "B") if args.env == "both" else (args.env,)
    by_gen   = {e["gen"]: e for e in entries}

    if len(gens) == 1 and args.out and not args.out.endswith(os.sep) and not os.path.isdir(args.out):
        out_path = args.out
        os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
        render_generation(by_gen[gens[0]], envs, out_path)
        print(f"  -> {out_path}")
        return

    out_dir = args.out or os.path.join(session_dir, "morphology")
    os.makedirs(out_dir, exist_ok=True)
    for g in gens:
        path = os.path.join(out_dir, f"gen_{g:04d}.png")
        render_generation(by_gen[g], envs, path)
        print(f"  -> {path}")

    print(f"\nDone. {len(gens)} image(s) in {out_dir}")


if __name__ == "__main__":
    main()
