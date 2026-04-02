import copy
import random

from entities.creature import mutate_dna, crossover_dna, mutate_structure, count_segments


def compute_diversity(dna_list):
    """
    Morphological diversity = standard deviation of segment counts.
    Returns 0.0 for populations of size < 2.
    """
    if len(dna_list) < 2:
        return 0.0
    counts   = [count_segments(d) for d in dna_list]
    mean     = sum(counts) / len(counts)
    variance = sum((c - mean) ** 2 for c in counts) / len(counts)
    return variance ** 0.5


# ─── Niching / Fitness Sharing ────────────────────────────────────────────────

def _morphological_distance(dna_a, dna_b):
    """
    Simple morphological distance: absolute difference in total segment count.
    Fast to compute; captures gross structural divergence.
    """
    return abs(count_segments(dna_a) - count_segments(dna_b))


def _apply_fitness_sharing(fitnesses, dnas, sigma_share=3.0):
    """
    Scale each individual's fitness by the size of its morphological niche.

    Prevents the population from collapsing onto a single body plan.
    niche_count_i = Σ_j  max(0, 1 − dist(i,j) / sigma_share)
    shared_fitness_i = fitness_i / niche_count_i

    :param sigma_share: Distance threshold — individuals further apart than this
                        do not penalise each other.
    """
    n = len(fitnesses)
    shared = []
    for i in range(n):
        niche_count = sum(
            max(0.0, 1.0 - _morphological_distance(dnas[i], dnas[j]) / sigma_share)
            for j in range(n)
        )
        shared.append(fitnesses[i] / max(niche_count, 1e-9))
    return shared


# ─── Selection ────────────────────────────────────────────────────────────────

def _tournament_select(dnas, fitnesses, k=3):
    """Return the DNA of the best individual among k random candidates."""
    indices = random.sample(range(len(dnas)), min(k, len(dnas)))
    best    = max(indices, key=lambda i: fitnesses[i])
    return dnas[best]


# ─── Breeding ─────────────────────────────────────────────────────────────────

def breed_next_generation(dnas, fitnesses, pop_size, n_elite=2, mutation_rate=0.15):
    """
    Produce the next generation of DNAs.

    Strategy:
    1. Elitism — top n_elite individuals (by raw fitness) are deep-copied intact.
    2. Fitness sharing — raw fitnesses are divided by niche size to discourage
       morphological convergence (speciation pressure).
    3. Tournament selection (k=3) on shared fitnesses → crossover → mutation
       (includes structural mutation via mutate_dna's struct_rate default=0.05).

    :param dnas:          List of DNA dicts from the current generation.
    :param fitnesses:     Parallel list of scalar fitness values.
    :param pop_size:      Target population size.
    :param n_elite:       Number of best individuals carried over intact.
    :param mutation_rate: Per-gene mutation probability passed to mutate_dna.
    :return:              List of pop_size new DNA dicts.
    """
    # Elitism: preserve the n_elite best by raw fitness
    paired      = sorted(zip(fitnesses, dnas), reverse=True, key=lambda x: x[0])
    sorted_dnas = [d for _, d in paired]
    next_gen    = [copy.deepcopy(d) for d in sorted_dnas[:n_elite]]

    # Fitness sharing for selection pressure (encourages morphological diversity)
    shared_fits = _apply_fitness_sharing(fitnesses, dnas)

    while len(next_gen) < pop_size:
        pa    = _tournament_select(dnas, shared_fits, k=3)
        pb    = _tournament_select(dnas, shared_fits, k=3)
        child = crossover_dna(copy.deepcopy(pa), copy.deepcopy(pb))
        mutate_dna(child, mutation_rate)
        mutate_structure(child)   # per-creature structural mutation (add/remove segments)
        next_gen.append(child)

    return next_gen
