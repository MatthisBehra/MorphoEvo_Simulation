"""
Run Manager — lance K runs indépendants d'évolution morphologique en headless
et produit un rapport de convergence génotypique.

Usage:
    python src/evolution/run_manager.py
"""

import json
import math
import os
import random
import copy
import sys
from typing import Any

# Ajouter le dossier parent au path pour les imports relatifs
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from physics.environment import Environment
from entities.creature import Creature, random_dna, count_segments
from evolution.genetics import breed_next_generation


# ─── Constantes ──────────────────────────────────────────────────────────────

TIME_STEP: float = 1 / 60  # pas de temps physique (60 Hz)

# Clés scalaires du génome (dans l'ordre depth-first pour l'aplatissement)
_SCALAR_KEYS: list[str] = [
    "width", "height", "attach_angle", "rot_min", "rot_max",
    "motor_force", "motor_speed", "motor_phase", "friction", "joint_damping",
]


# ─── Utilitaires ─────────────────────────────────────────────────────────────

def _flatten_dna(dna: dict) -> list[float]:
    """
    Aplatit un arbre DNA en vecteur numérique (parcours depth-first).
    Chaque nœud contribue ses clés scalaires dans l'ordre de _SCALAR_KEYS,
    puis on recurse sur les enfants.
    """
    values: list[float] = []
    for key in _SCALAR_KEYS:
        values.append(float(dna.get(key, 0.0)))
    for child in dna.get("children", []):
        values.extend(_flatten_dna(child))
    return values


class RunManager:
    """
    Gestionnaire de runs multiples d'évolution morphologique.

    Lance K simulations indépendantes (headless, sans pygame),
    sauvegarde les meilleurs génomes, et génère un rapport de convergence.
    """

    def __init__(
        self,
        k_runs: int = 3,
        n_generations: int = 20,
        pop_size: int = 30,
        gen_duration: float = 15.0,
    ) -> None:
        self.k_runs: int = k_runs
        self.n_generations: int = n_generations
        self.pop_size: int = pop_size
        self.gen_duration: float = gen_duration

    # ── Simulation d'un run unique ───────────────────────────────────────────

    def _run_single(self, run_id: int, seed: int) -> dict[str, Any]:
        """
        Simule un run complet d'évolution sur Env A (sol plat avec zones de friction).

        :param run_id: Identifiant du run (0-indexed).
        :param seed:   Graine aléatoire pour la reproductibilité.
        :return:       Dict contenant run_id, seed, best_fitness, best_dna, fitness_history.
        """
        random.seed(seed)

        fitness_history: list[float] = []
        best_fitness_overall: float = float("-inf")
        best_dna_overall: dict = {}

        # Générer la population initiale
        dnas: list[dict] = [random_dna() for _ in range(self.pop_size)]

        for gen in range(self.n_generations):
            # Créer un environnement neuf à chaque génération
            env = Environment(gravity=(0, -900))
            env.add_friction_zones(total_x=216000, ground_y=5, zone_width=800, thickness=5.0)

            # Réinitialiser le compteur de groupes pour les ShapeFilters
            Creature._group_counter = 1

            # Instancier les créatures
            start_x: float = 300.0
            creatures: list[Creature] = []
            for dna in dnas:
                creature = Creature(env.space, (start_x, 205), dna=copy.deepcopy(dna))
                creatures.append(creature)

            # Simuler gen_duration secondes de physique
            n_steps: int = int(self.gen_duration / TIME_STEP)
            sim_time: float = 0.0

            for _ in range(n_steps):
                env.step(TIME_STEP)
                for creature in creatures:
                    creature.act(sim_time, TIME_STEP)
                    creature.record_stability()
                sim_time += TIME_STEP

            # Calculer les fitness
            fitnesses: list[float] = [
                creature.get_fitness(start_x=start_x) for creature in creatures
            ]

            # Meilleur de cette génération
            gen_best_idx: int = max(range(len(fitnesses)), key=lambda i: fitnesses[i])
            gen_best_fitness: float = fitnesses[gen_best_idx]
            fitness_history.append(gen_best_fitness)

            if gen_best_fitness > best_fitness_overall:
                best_fitness_overall = gen_best_fitness
                best_dna_overall = copy.deepcopy(dnas[gen_best_idx])

            # Afficher le progrès
            print(
                f"Run {run_id + 1}/{self.k_runs} — "
                f"Gen {gen + 1}/{self.n_generations} — "
                f"Best: {gen_best_fitness:.1f}"
            )

            # Nettoyer les créatures de l'espace physique
            for creature in creatures:
                creature.remove()
            creatures.clear()

            # Breed pour la prochaine génération (sauf à la dernière)
            if gen < self.n_generations - 1:
                dnas = breed_next_generation(dnas, fitnesses, self.pop_size)

        return {
            "run_id": run_id,
            "seed": seed,
            "best_fitness": best_fitness_overall,
            "best_dna": best_dna_overall,
            "fitness_history": fitness_history,
        }

    # ── Sauvegarde des résultats ─────────────────────────────────────────────

    def save_results(self, results: list[dict], output_dir: str = "runs") -> None:
        """
        Sauvegarde chaque meilleur génome en JSON dans output_dir/.

        :param results:    Liste de dicts retournés par _run_single.
        :param output_dir: Dossier de sortie (créé s'il n'existe pas).
        """
        os.makedirs(output_dir, exist_ok=True)

        for result in results:
            filepath: str = os.path.join(output_dir, f"run_{result['run_id']}.json")
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "run_id": result["run_id"],
                        "seed": result["seed"],
                        "best_fitness": result["best_fitness"],
                        "best_dna": result["best_dna"],
                        "fitness_history": result["fitness_history"],
                    },
                    f,
                    indent=2,
                    ensure_ascii=False,
                )

    # ── Distance génotypique ─────────────────────────────────────────────────

    @staticmethod
    def genotype_distance(dna_a: dict, dna_b: dict) -> float:
        """
        Distance euclidienne entre deux génomes aplatis.

        Chaque DNA est convertie en vecteur numérique (depth-first, clés scalaires).
        Si les vecteurs ont des longueurs différentes (arbres de tailles différentes),
        le plus court est complété avec des zéros.

        :param dna_a: Premier génome (dict arbre).
        :param dna_b: Second génome (dict arbre).
        :return:      Distance euclidienne.
        """
        vec_a: list[float] = _flatten_dna(dna_a)
        vec_b: list[float] = _flatten_dna(dna_b)

        # Padding du vecteur le plus court avec des zéros
        max_len: int = max(len(vec_a), len(vec_b))
        vec_a.extend([0.0] * (max_len - len(vec_a)))
        vec_b.extend([0.0] * (max_len - len(vec_b)))

        return math.sqrt(sum((a - b) ** 2 for a, b in zip(vec_a, vec_b)))

    # ── Rapport de convergence ───────────────────────────────────────────────

    def generate_report(
        self, results: list[dict], output_dir: str = "runs"
    ) -> dict[str, Any]:
        """
        Génère un rapport de convergence entre les meilleurs génomes de chaque run.

        - Matrice de distances KxK entre les meilleurs génomes.
        - Flag convergence : True si toutes les distances < 10% de la distance max.
        - Sauvegarde dans output_dir/report.json.

        :param results:    Liste de dicts retournés par _run_single.
        :param output_dir: Dossier de sortie.
        :return:           Dict du rapport.
        """
        os.makedirs(output_dir, exist_ok=True)

        k: int = len(results)
        best_dnas: list[dict] = [r["best_dna"] for r in results]

        # Construire la matrice de distances
        distance_matrix: list[list[float]] = [
            [0.0] * k for _ in range(k)
        ]
        for i in range(k):
            for j in range(i + 1, k):
                dist: float = self.genotype_distance(best_dnas[i], best_dnas[j])
                distance_matrix[i][j] = round(dist, 4)
                distance_matrix[j][i] = round(dist, 4)

        # Déterminer la distance maximale
        max_distance: float = 0.0
        for i in range(k):
            for j in range(i + 1, k):
                if distance_matrix[i][j] > max_distance:
                    max_distance = distance_matrix[i][j]

        # Seuil de convergence : 10% de la distance maximale
        threshold: float = 0.1 * max_distance if max_distance > 0 else 0.0
        convergence: bool = all(
            distance_matrix[i][j] < threshold
            for i in range(k)
            for j in range(i + 1, k)
        )

        report: dict[str, Any] = {
            "k_runs": k,
            "n_generations": self.n_generations,
            "pop_size": self.pop_size,
            "gen_duration": self.gen_duration,
            "distance_matrix": distance_matrix,
            "max_distance": round(max_distance, 4),
            "convergence_threshold": round(threshold, 4),
            "convergence": convergence,
            "best_fitnesses": [r["best_fitness"] for r in results],
        }

        filepath: str = os.path.join(output_dir, "report.json")
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)

        return report

    # ── Méthode principale ───────────────────────────────────────────────────

    def run_all(self) -> dict[str, Any]:
        """
        Lance les K runs séquentiellement, sauvegarde les résultats et le rapport.

        :return: Dict du rapport de convergence.
        """
        results: list[dict] = []

        for k in range(self.k_runs):
            seed: int = k  # Chaque run utilise sa propre seed
            result: dict = self._run_single(run_id=k, seed=seed)
            results.append(result)

        # Sauvegarde des résultats individuels
        self.save_results(results)

        # Génération et sauvegarde du rapport
        report: dict[str, Any] = self.generate_report(results)

        return report


# ─── Point d'entrée direct ───────────────────────────────────────────────────

if __name__ == "__main__":
    import pygame

    pygame.init()
    pygame.display.set_mode((1, 1))  # Fenêtre minimale pour pymunk

    manager = RunManager(k_runs=3, n_generations=10, pop_size=20, gen_duration=10.0)
    report = manager.run_all()
    print(f"\nConvergence: {report['convergence']}")
    print(f"Distances: {report['distance_matrix']}")

    pygame.quit()
