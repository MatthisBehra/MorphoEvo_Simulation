import csv
import os


CSV_HEADER = [
    "generation",
    "best_fitness_a", "avg_fitness_a",
    "best_fitness_b", "avg_fitness_b",
    "diversity_a", "diversity_b",
    "avg_complexity_a", "avg_complexity_b",
]


def init_csv(path):
    """Create the CSV file with header row if it does not already exist."""
    if not os.path.exists(path):
        with open(path, "w", newline="") as f:
            csv.writer(f).writerow(CSV_HEADER)


def append_row(path, generation, best_a, avg_a, best_b, avg_b,
               div_a, div_b, cmplx_a, cmplx_b):
    """Append one row of generation statistics."""
    with open(path, "a", newline="") as f:
        csv.writer(f).writerow([
            generation,
            round(best_a, 2), round(avg_a, 2),
            round(best_b, 2), round(avg_b, 2),
            round(div_a, 2), round(div_b, 2),
            round(cmplx_a, 2), round(cmplx_b, 2),
        ])
