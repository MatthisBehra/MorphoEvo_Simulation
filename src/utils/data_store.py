import csv
import json
import os
import statistics
from datetime import datetime


class DataStore:
    """
    Persistance des données d'évolution, organisée par session horodatée.

    Structure sur disque :
        data/
          session_YYYY-MM-DD_HHMMSS/
            session.json   ← paramètres de la simulation + timestamp
            stats.csv      ← statistiques par génération (étendu)
            lineage.jsonl  ← meilleur génome par génération (JSONL)
    """

    STATS_HEADER = [
        "generation",
        "best_fitness_a", "avg_fitness_a", "min_fitness_a", "std_fitness_a",
        "best_fitness_b", "avg_fitness_b", "min_fitness_b", "std_fitness_b",
        "diversity_a",    "diversity_b",
        "avg_complexity_a", "avg_complexity_b",
        "max_complexity_a", "max_complexity_b",
    ]

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
        """Sauvegarde les paramètres de la session dans session.json."""
        metadata = {"timestamp": datetime.now().isoformat(), **kwargs}
        path = os.path.join(self.session_dir, "session.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)

    # ── Données par génération ────────────────────────────────────────────────

    def append_generation(
        self,
        generation: int,
        fits_a:     list,
        fits_b:     list,
        dnas_a:     list,
        dnas_b:     list,
        div_a:      float,
        div_b:      float,
        count_fn,
    ) -> None:
        """
        Écrit une ligne dans stats.csv et une entrée dans lineage.jsonl.

        :param count_fn: Fonction count_segments(dna) → int, passée en paramètre
                         pour éviter l'import circulaire.
        """
        seg_counts_a = [count_fn(d) for d in dnas_a]
        seg_counts_b = [count_fn(d) for d in dnas_b]

        best_idx_a = max(range(len(fits_a)), key=lambda i: fits_a[i])
        best_idx_b = max(range(len(fits_b)), key=lambda i: fits_b[i])

        def _std(values):
            return statistics.stdev(values) if len(values) > 1 else 0.0

        # ── stats.csv ─────────────────────────────────────────────────────────
        row = [
            generation,
            round(max(fits_a),                           2),
            round(sum(fits_a) / len(fits_a),             2),
            round(min(fits_a),                           2),
            round(_std(fits_a),                          2),
            round(max(fits_b),                           2),
            round(sum(fits_b) / len(fits_b),             2),
            round(min(fits_b),                           2),
            round(_std(fits_b),                          2),
            round(div_a,                                 2),
            round(div_b,                                 2),
            round(sum(seg_counts_a) / len(seg_counts_a), 2),
            round(sum(seg_counts_b) / len(seg_counts_b), 2),
            max(seg_counts_a),
            max(seg_counts_b),
        ]
        with open(self.stats_path, "a", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(row)

        # ── lineage.jsonl ─────────────────────────────────────────────────────
        entry = {
            "gen":            generation,
            "best_fitness_a": round(fits_a[best_idx_a], 4),
            "best_fitness_b": round(fits_b[best_idx_b], 4),
            "best_dna_a":     dnas_a[best_idx_a],
            "best_dna_b":     dnas_b[best_idx_b],
        }
        with open(self.lineage_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
