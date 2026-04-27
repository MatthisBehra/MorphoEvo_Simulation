import csv
import json
import math
import os
import statistics
from datetime import datetime

from entities.creature import (
    SCALAR_GENE_KEYS,
    count_segments,
    tree_depth,
    avg_branching,
    iter_genes,
    dna_total_area,
)


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _std(values):
    return statistics.stdev(values) if len(values) > 1 else 0.0


def _median(values):
    return statistics.median(values) if values else 0.0


def _quantile(values, q):
    """Simple linear-interpolation quantile (q in [0, 1])."""
    if not values:
        return 0.0
    s = sorted(values)
    pos = q * (len(s) - 1)
    lo = int(math.floor(pos))
    hi = int(math.ceil(pos))
    if lo == hi:
        return s[lo]
    frac = pos - lo
    return s[lo] * (1 - frac) + s[hi] * frac


def _mean(values):
    return sum(values) / len(values) if values else 0.0


def _flatten_dna(dna):
    """Depth-first flatten into a vector of scalar gene values."""
    values = []
    for key in SCALAR_GENE_KEYS:
        values.append(float(dna.get(key, 0.0)))
    for child in dna.get("children", []):
        values.extend(_flatten_dna(child))
    return values


def _genotype_distance(dna_a, dna_b):
    """Euclidean distance between zero-padded flattened genomes."""
    va = _flatten_dna(dna_a)
    vb = _flatten_dna(dna_b)
    n = max(len(va), len(vb))
    va.extend([0.0] * (n - len(va)))
    vb.extend([0.0] * (n - len(vb)))
    return math.sqrt(sum((a - b) ** 2 for a, b in zip(va, vb)))


def _mean_cross_distance(dnas_a, dnas_b):
    """Mean pairwise genotype distance between two populations."""
    if not dnas_a or not dnas_b:
        return 0.0
    total = 0.0
    n = 0
    for da in dnas_a:
        for db in dnas_b:
            total += _genotype_distance(da, db)
            n += 1
    return total / n if n else 0.0


def _creature_mass(creature):
    return sum(b.mass for b in creature.bodies) if creature.bodies else 0.0


def _gene_means(dnas):
    """Per-gene scalar averages across every segment of every creature."""
    sums = {k: 0.0 for k in SCALAR_GENE_KEYS}
    count = 0
    for dna in dnas:
        for gene in iter_genes(dna):
            for k in SCALAR_GENE_KEYS:
                sums[k] += float(gene.get(k, 0.0))
            count += 1
    if count == 0:
        return {k: 0.0 for k in SCALAR_GENE_KEYS}
    return {k: sums[k] / count for k in SCALAR_GENE_KEYS}


# ─── Per-env metrics block ───────────────────────────────────────────────────

def _env_metrics(fits, creatures, start_x):
    """Compute every metric scoped to one environment's population."""
    dnas = [c.dna for c in creatures]
    seg_counts = [count_segments(d) for d in dnas]
    depths     = [tree_depth(d) for d in dnas]
    branching  = [avg_branching(d) for d in dnas]

    distances   = [max(0.0, c.get_position() - start_x) for c in creatures]
    energies    = [c._energy_spent for c in creatures]
    stabilities = [c.get_trunk_stability() for c in creatures]
    masses      = [_creature_mass(c) for c in creatures]
    areas       = [dna_total_area(d) for d in dnas]

    gene_avg = _gene_means(dnas)

    fit_mean = _mean(fits)
    fit_std  = _std(fits)
    # Selection intensity = (best - mean) / std — how concentrated selection is.
    sel_intensity = (max(fits) - fit_mean) / fit_std if fit_std > 0 else 0.0

    return {
        # Fitness distribution
        "best":         max(fits),
        "avg":          fit_mean,
        "min":          min(fits),
        "std":          fit_std,
        "median":       _median(fits),
        "p25":          _quantile(fits, 0.25),
        "p75":          _quantile(fits, 0.75),
        "sel_intensity": sel_intensity,
        # Morphology
        "avg_segments": _mean(seg_counts),
        "max_segments": max(seg_counts),
        "min_segments": min(seg_counts),
        "avg_depth":    _mean(depths),
        "max_depth":    max(depths),
        "avg_branching": _mean(branching),
        # Physical
        "avg_distance":  _mean(distances),
        "max_distance":  max(distances),
        "avg_energy":    _mean(energies),
        "max_energy":    max(energies),
        "avg_stability": _mean(stabilities),
        "avg_mass":      _mean(masses),
        "avg_seg_area":  _mean(areas),
        # Gene averages
        "avg_motor_force":  gene_avg["motor_force"],
        "avg_motor_speed":  gene_avg["motor_speed"],
        "avg_friction":     gene_avg["friction"],
        "avg_damping":      gene_avg["joint_damping"],
    }


# ─── DataStore ───────────────────────────────────────────────────────────────

class DataStore:
    """
    Persistance des données d'évolution, organisée par session horodatée.

    Structure sur disque :
        data/
          session_YYYY-MM-DD_HHMMSS/
            session.json   ← paramètres de la simulation + timestamp
            stats.csv      ← statistiques par génération (schéma enrichi)
            lineage.jsonl  ← meilleur génome par génération (JSONL)
    """

    _METRIC_KEYS = [
        "best", "avg", "min", "std", "median", "p25", "p75", "sel_intensity",
        "avg_segments", "max_segments", "min_segments",
        "avg_depth", "max_depth", "avg_branching",
        "avg_distance", "max_distance",
        "avg_energy", "max_energy",
        "avg_stability", "avg_mass", "avg_seg_area",
        "avg_motor_force", "avg_motor_speed", "avg_friction", "avg_damping",
    ]

    STATS_HEADER = (
        ["generation"]
        + [f"{k}_a" for k in _METRIC_KEYS]
        + [f"{k}_b" for k in _METRIC_KEYS]
        + ["diversity_a", "diversity_b", "genotype_dist_ab", "wall_time_s"]
    )

    def __init__(self, base_dir: str = "data") -> None:
        timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        self.session_dir  = os.path.join(base_dir, f"session_{timestamp}")
        os.makedirs(self.session_dir, exist_ok=True)
        self.stats_path   = os.path.join(self.session_dir, "stats.csv")
        self.lineage_path = os.path.join(self.session_dir, "lineage.jsonl")
        self._init_stats_csv()

    # ── Initialisation ────────────────────────────────────────────────────────

    def _init_stats_csv(self) -> None:
        with open(self.stats_path, "w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(self.STATS_HEADER)

    # ── Métadonnées de session ────────────────────────────────────────────────

    def save_metadata(self, **kwargs) -> None:
        metadata = {"timestamp": datetime.now().isoformat(), **kwargs}
        path = os.path.join(self.session_dir, "session.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)

    # ── Données par génération ────────────────────────────────────────────────

    def append_generation(
        self,
        generation,
        creatures_a, creatures_b,
        fits_a, fits_b,
        div_a, div_b,
        start_x,
        wall_time_s=0.0,
    ):
        """
        Écrit une ligne dans stats.csv et une entrée dans lineage.jsonl.

        :param creatures_a/b: liste de Creature vivants (pour masses, énergie, stabilité, distance)
        :param fits_a/b:      listes de fitness parallèles
        :param div_a/b:       diversité morphologique (σ du nombre de segments)
        :param start_x:       abscisse de spawn (pour calculer la distance parcourue)
        :param wall_time_s:   temps mur de la génération (secondes)
        """
        m_a = _env_metrics(fits_a, creatures_a, start_x)
        m_b = _env_metrics(fits_b, creatures_b, start_x)

        dnas_a = [c.dna for c in creatures_a]
        dnas_b = [c.dna for c in creatures_b]

        dist_ab = _mean_cross_distance(dnas_a, dnas_b)

        best_idx_a = max(range(len(fits_a)), key=lambda i: fits_a[i])
        best_idx_b = max(range(len(fits_b)), key=lambda i: fits_b[i])

        def _r(x, n=3):
            return round(float(x), n) if isinstance(x, (int, float)) else x

        row = [generation]
        row.extend(_r(m_a[k]) for k in self._METRIC_KEYS)
        row.extend(_r(m_b[k]) for k in self._METRIC_KEYS)
        row.extend([_r(div_a), _r(div_b), _r(dist_ab), _r(wall_time_s)])

        with open(self.stats_path, "a", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(row)

        entry = {
            "gen":            generation,
            "best_fitness_a": round(fits_a[best_idx_a], 4),
            "best_fitness_b": round(fits_b[best_idx_b], 4),
            "best_dna_a":     dnas_a[best_idx_a],
            "best_dna_b":     dnas_b[best_idx_b],
        }
        with open(self.lineage_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
