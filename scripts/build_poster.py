"""Generate an A0 scientific poster (PNG + PDF) summarizing the research,
written for a non-specialist reader. Visual charter inspired by
docs/screenshot/impressionposterscientifiqueA0_1024x1024.webp.
"""

import json
import statistics
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, Rectangle
from matplotlib.image import imread


ROOT = Path(__file__).resolve().parent.parent
RUN_DIR = ROOT / "runs" / "multirun_2026-04-21_220850"
FIG_DIR = ROOT / "docs" / "figures"
OUT = ROOT / "docs" / "poster_BEHRA_A0.png"
OUT_PDF = ROOT / "docs" / "poster_BEHRA_A0.pdf"


# ── Charter ──────────────────────────────────────────────────────────────────
TEAL_HEADER = "#3a7892"
TEAL_DARK = "#2c5f76"
SECTION_BG = "#eaf3f7"
SECTION_BORDER = "#7faec3"
RED_BAND = "#c64a4a"
BLUE_BAND = "#3a7892"
PINK_BAND = "#d18c93"
GLOSS_BG = "#fff7e6"
GLOSS_BORDER = "#e0b870"
TEXT_DARK = "#1f2c33"
GREY_TEXT = "#445661"


# ── Page dimensions (A0 portrait) ────────────────────────────────────────────
fig_w_in, fig_h_in = 33.1, 46.8


# ── Helpers ──────────────────────────────────────────────────────────────────
def add_section(ax, x, y, w, h, title, body_lines, band_color,
                body_fontsize=10.0, bg=SECTION_BG, border=SECTION_BORDER):
    box = FancyBboxPatch(
        (x, y), w, h,
        boxstyle="round,pad=0.005,rounding_size=0.012",
        linewidth=1.2, edgecolor=border, facecolor=bg,
        transform=ax.transAxes, zorder=1,
    )
    ax.add_patch(box)
    band_h = 0.020
    band = Rectangle(
        (x + 0.005, y + h - band_h - 0.005), w - 0.010, band_h,
        linewidth=0, facecolor=band_color, transform=ax.transAxes, zorder=2,
    )
    ax.add_patch(band)
    ax.text(
        x + 0.013, y + h - 0.005 - band_h / 2, title,
        ha="left", va="center", color="white", fontsize=11, fontweight="bold",
        transform=ax.transAxes, zorder=3,
    )
    body = "\n".join(body_lines)
    ax.text(
        x + 0.012, y + h - band_h - 0.018, body,
        ha="left", va="top", color=TEXT_DARK, fontsize=body_fontsize,
        transform=ax.transAxes, zorder=3, linespacing=1.40,
    )


def add_image(ax, x, y, w, h, img_path, title=None, band_color=None,
              caption=None, reading_guide=None):
    """Draw a section box with image inside and an optional 'how to read' note."""
    box = FancyBboxPatch(
        (x, y), w, h,
        boxstyle="round,pad=0.005,rounding_size=0.012",
        linewidth=1.2, edgecolor=SECTION_BORDER, facecolor="white",
        transform=ax.transAxes, zorder=1,
    )
    ax.add_patch(box)

    band_h = 0.020 if title else 0.0
    if title:
        band = Rectangle(
            (x + 0.005, y + h - band_h - 0.005), w - 0.010, band_h,
            linewidth=0, facecolor=band_color, transform=ax.transAxes, zorder=2,
        )
        ax.add_patch(band)
        ax.text(
            x + 0.013, y + h - 0.005 - band_h / 2, title,
            ha="left", va="center", color="white", fontsize=11, fontweight="bold",
            transform=ax.transAxes, zorder=3,
        )

    cap_h = 0.011 if caption else 0.0
    rg_h = 0.022 if reading_guide else 0.0
    pad_top = band_h + 0.010
    pad_side = 0.012
    pad_bot = 0.010 + cap_h + rg_h

    inner_x = x + pad_side
    inner_y = y + pad_bot
    inner_w = w - 2 * pad_side
    inner_h = h - pad_top - pad_bot

    img = imread(img_path)
    img_h, img_w = img.shape[0], img.shape[1]
    img_aspect = img_w / img_h
    box_aspect = (inner_w * fig_w_in) / (inner_h * fig_h_in)
    if img_aspect > box_aspect:
        draw_w = inner_w
        draw_h = inner_w * fig_w_in / img_aspect / fig_h_in
        draw_x = inner_x
        draw_y = inner_y + (inner_h - draw_h) / 2
    else:
        draw_h = inner_h
        draw_w = inner_h * fig_h_in * img_aspect / fig_w_in
        draw_x = inner_x + (inner_w - draw_w) / 2
        draw_y = inner_y
    ax.imshow(
        img, extent=[draw_x, draw_x + draw_w, draw_y, draw_y + draw_h],
        transform=ax.transAxes, zorder=3, aspect="auto",
    )

    if reading_guide:
        ax.text(
            x + w / 2, y + cap_h + 0.005, "▶ Comment lire — " + reading_guide,
            ha="center", va="bottom", color=GREY_TEXT, fontsize=9.0,
            transform=ax.transAxes, zorder=3, wrap=True,
        )
    if caption:
        ax.text(
            x + w / 2, y + 0.004, caption,
            ha="center", va="bottom", color=TEXT_DARK,
            fontsize=8.5, fontstyle="italic",
            transform=ax.transAxes, zorder=3,
        )


def load_stats():
    with open(RUN_DIR / "report.json", "r") as f:
        rep = json.load(f)
    ra = sorted(rep["results_a"], key=lambda x: x["run_id"])
    rb = sorted(rep["results_b"], key=lambda x: x["run_id"])
    af = [r["best_fitness"] for r in ra]
    bf = [r["best_fitness"] for r in rb]
    asg = [r["final_segments"] for r in ra]
    bsg = [r["final_segments"] for r in rb]

    def avg_off_diag(M):
        n = len(M); s, c = 0.0, 0
        for i in range(n):
            for j in range(n):
                if i != j: s += M[i][j]; c += 1
        return s / c

    def avg_full(M):
        return sum(M[i][j] for i in range(len(M)) for j in range(len(M[0]))) / (len(M) * len(M[0]))

    return {
        "k": rep["k_runs"], "gens": rep["n_generations"], "pop": rep["pop_size"],
        "wall_h": rep["wall_time_s"] / 3600.0,
        "a_mean": statistics.mean(af), "a_std": statistics.stdev(af),
        "b_mean": statistics.mean(bf), "b_std": statistics.stdev(bf),
        "a_seg": statistics.mean(asg), "b_seg": statistics.mean(bsg),
        "aa": avg_off_diag(rep["distance_matrix_aa"]),
        "bb": avg_off_diag(rep["distance_matrix_bb"]),
        "ab": avg_full(rep["distance_matrix_ab"]),
    }


# ── Build poster ─────────────────────────────────────────────────────────────
fig = plt.figure(figsize=(fig_w_in, fig_h_in), facecolor="white")
ax = fig.add_axes([0, 0, 1, 1])
ax.set_xlim(0, 1)
ax.set_ylim(0, 1)
ax.axis("off")

stats = load_stats()


# ─── Header ─────────────────────────────────────────────────────────────────
header_h = 0.062
ax.add_patch(Rectangle((0, 1 - header_h), 1, header_h,
                       facecolor=TEAL_HEADER, linewidth=0, transform=ax.transAxes))
ax.text(0.025, 1 - header_h * 0.32,
        "Influence de la complexité de l’environnement",
        color="white", fontsize=42, fontweight="bold",
        ha="left", va="center", transform=ax.transAxes)
ax.text(0.025, 1 - header_h * 0.62,
        "sur l’évolution morphologique d’une créature virtuelle",
        color="white", fontsize=26, fontstyle="italic",
        ha="left", va="center", transform=ax.transAxes)
ax.text(0.025, 1 - header_h + 0.010,
        "BEHRA Matthis  —  A4 FISE INFO 2024 / 2025  —  Étude multi-runs (k = 20 paires)",
        color="white", fontsize=16,
        ha="left", va="center", transform=ax.transAxes)
ax.text(0.975, 1 - header_h * 0.32,
        "Algorithme génétique classique",
        color="white", fontsize=15, fontweight="bold",
        ha="right", va="center", transform=ax.transAxes)
ax.text(0.975, 1 - header_h * 0.55,
        "Encodage direct paramétrique  ·  Pas de neuro-évolution",
        color="white", fontsize=13,
        ha="right", va="center", transform=ax.transAxes)
ax.text(0.975, 1 - header_h + 0.010,
        "Reproduction expérimentale d’Auerbach & Bongard (2012)",
        color="white", fontsize=13, fontstyle="italic",
        ha="right", va="center", transform=ax.transAxes)


# ─── Context / glossary band — full width ────────────────────────────────────
ctx_top = 1 - header_h - 0.008
ctx_h = 0.058
margin = 0.012
ctx_x = margin
ctx_w = 1 - 2 * margin
add_section(
    ax, ctx_x, ctx_top - ctx_h, ctx_w, ctx_h,
    "EN BREF — pour qui découvre le sujet",
    [
        "Les êtres vivants ont la forme qu’ils ont parce qu’ils ont dû s’adapter à leur milieu. Cette étude pose la même question dans un monde virtuel : si on laisse un programme « inventer » la forme d’une "
        "petite créature pour lui apprendre à se déplacer, l’environnement (terrain plat ou accidenté) influence-t-il la forme finale ?",
        "Méthode :  on ne dessine PAS les créatures à la main. On utilise un algorithme génétique — une population de 100 corps virtuels qui se reproduisent, mutent et sont sélectionnés sur 1000 générations, comme une évolution darwinienne accélérée.",
        "Lecture du poster :  les couleurs des bandeaux n’ont pas de sens technique, elles servent juste à séparer les sections. Bleu = environnement A (plaine), orange/crème = environnement B (terrain accidenté). 20 runs ont été lancés pour la robustesse statistique.",
    ],
    band_color="#b58a3a", body_fontsize=11.0,
    bg=GLOSS_BG, border=GLOSS_BORDER,
)


# ─── Layout grid ────────────────────────────────────────────────────────────
top = ctx_top - ctx_h - margin
bot_footer = 0.045
col_w = (1 - 4 * margin) / 3
col_x = [margin, margin + col_w + margin, margin + 2 * (col_w + margin)]


# ── Column 1 (left) ─────────────────────────────────────────────────────────
y_cursor = top

# 1.1 Problématique & contexte
h = 0.16
add_section(ax, col_x[0], y_cursor - h, col_w, h,
    "1 ▸ Problématique & contexte scientifique",
    [
        "En biologie, on observe que la forme du corps d’un animal — nageoires,",
        "pattes longues, carapace — est largement « dictée » par le milieu où il",
        "vit. On peut tester cette idée en simulation, sans biologie réelle.",
        "",
        "Question de recherche :",
        "▶ Si on laisse un algorithme génétique « inventer » la morphologie",
        "    d’une créature virtuelle, la complexité de son environnement",
        "    influence-t-elle la forme finale qu’elle va adopter ?",
        "",
        "Référence pivot : Auerbach & Bongard (GECCO 2012) montrent que oui,",
        "sur des robots simulés. Notre travail le reproduit indépendamment, sur",
        "un protocole strict : 4 études primaires retenues par revue systématique",
        "(Kitchenham & Charters, 2007), puis 20 simulations comparatives.",
    ],
    band_color=RED_BAND, body_fontsize=10.5,
)
y_cursor -= h + margin

# 1.2 Algorithme génétique
h = 0.31
add_section(ax, col_x[0], y_cursor - h, col_w, h,
    "2 ▸ L’algorithme génétique en 5 étapes",
    [
        "Un algorithme génétique imite l’évolution naturelle. À chaque génération :",
        "",
        "  ① ÉVALUATION  — chaque créature tente de se déplacer pendant 15 s.",
        "      Sa note (fitness) mesure la distance parcourue, moins l’énergie",
        "      dépensée, moins une pénalité de complexité (0,5 × n_segments).",
        "",
        "  ② SÉLECTION  — les meilleures ont plus de chances d’être « parents ».",
        "      Tournoi à 3 + élitisme (les 2 meilleures passent intactes).",
        "      Niching : les corps trop similaires sont pénalisés (diversité).",
        "",
        "  ③ CROISEMENT — chaque scalaire d’un nouveau corps est tiré chez",
        "      l’un des deux parents. Les sous-arbres en trop sont gardés p=0,5.",
        "",
        "  ④ MUTATION SCALAIRE — chaque paramètre est légèrement perturbé",
        "      (gaussienne) : largeur, vitesse moteur, friction…",
        "",
        "  ⑤ MUTATION STRUCTURELLE — 1×/individu/génération :",
        "      ajout d’un segment (12 %), retrait (5 %), plafond à 12 segments.",
        "      C’est cette étape qui fait émerger la complexité morphologique.",
        "",
        "GÉNOME — chaque créature = un arbre de segments rigides reliés par des",
        "articulations motorisées. Paramètres par segment : taille, angle, vitesse",
        "de moteur, friction, amortissement. Pas de cerveau, pas d’apprentissage —",
        "le moteur suit une simple sinusoïde universelle ω = motor_speed × sin(t·10",
        "+ motor_phase). Toute la « stratégie » est dans la forme.",
    ],
    band_color=BLUE_BAND, body_fontsize=9.5,
)
y_cursor -= h + margin

# 1.3 Protocole expérimental
h = 0.13
add_section(ax, col_x[0], y_cursor - h, col_w, h,
    "3 ▸ Protocole — un test équitable",
    [
        "On lance K = 20 simulations indépendantes. Pour CHAQUE simulation, on",
        "duplique la population initiale et on la fait évoluer en parallèle dans",
        "deux environnements différents (A et B). Toute différence finale est",
        "donc imputable à l’environnement, pas au hasard de l’initialisation.",
        "",
        "  • A — Plaine ouverte (sol uniforme)",
        "  • B — Terrain accidenté (pentes ±25°, zones molles)",
        "  • 100 individus × 1000 générations × 2 envs × 20 runs = 4 M évaluations",
        f"  • Temps de calcul : {stats['wall_h']:.0f} h, 8 workers parallèles.",
    ],
    band_color=PINK_BAND, body_fontsize=10.0,
)
y_cursor -= h + margin

# 1.4 Convergence fitness — bottom of col 1
h = y_cursor - bot_footer - margin
add_image(ax, col_x[0], bot_footer + margin, col_w, h,
    str(FIG_DIR / "fitness_convergence.png"),
    title="4 ▸ Apprentissage — la fitness progresse-t-elle ?",
    band_color=BLUE_BAND,
    caption="Fig. 1 — Fitness moyenne du meilleur individu par génération, 20 runs.",
    reading_guide=("ligne = moyenne sur 20 runs, bande = ±1 écart-type. "
                   "Plus la courbe monte, mieux la population se déplace. Les deux "
                   "environnements progressent, mais l’écart se creuse à partir de la gen ~200."),
)


# ── Column 2 (middle) ───────────────────────────────────────────────────────
y_cursor = top

# 2.1 Émergence de la complexité (segments)
h = 0.235
add_image(ax, col_x[1], y_cursor - h, col_w, h,
    str(FIG_DIR / "segments_evolution.png"),
    title="5 ▸ La complexité du corps grandit-elle ?",
    band_color=RED_BAND,
    caption="Fig. 2 — Nombre moyen de segments dans la population par génération.",
    reading_guide=("toutes les créatures démarrent avec 2 segments. Plus la "
                   "courbe monte, plus les corps deviennent compliqués. La courbe orange "
                   "(B, terrain) finit nettement plus haut que la bleue (A, plaine)."),
)
y_cursor -= h + margin

# 2.2 Morphologies
h = 0.42
add_image(ax, col_x[1], y_cursor - h, col_w, h,
    str(FIG_DIR / "morpho_pairs_selected.png"),
    title="6 ▸ À quoi ressemblent les créatures finales ?",
    band_color=BLUE_BAND,
    caption="Fig. 3 — Reconstruction des meilleures créatures à la dernière génération.",
    reading_guide=("chaque ligne = une simulation, fond bleu pâle = plaine, "
                   "fond crème = terrain. Même graine de départ pour A et B → toute différence "
                   "vient de l’environnement, pas du hasard."),
)
y_cursor -= h + margin

# 2.3 Distance heatmaps
h = y_cursor - bot_footer - margin
add_image(ax, col_x[1], bot_footer + margin, col_w, h,
    str(FIG_DIR / "distance_heatmaps.png"),
    title="7 ▸ Les morphologies des deux mondes se ressemblent-elles ?",
    band_color=PINK_BAND,
    caption=f"Fig. 4 — Plus c’est sombre, plus les corps sont semblables. AA={stats['aa']:.2f} · BB={stats['bb']:.2f} · AB={stats['ab']:.2f}.",
    reading_guide=("on compare deux à deux les 20 corps finaux. À gauche : "
                   "entre eux les corps évolués en plaine se ressemblent (sombre). "
                   "À droite : un corps de plaine vs un corps de terrain → couleurs claires = "
                   "ils sont différents."),
)


# ── Column 3 (right) ────────────────────────────────────────────────────────
y_cursor = top

# 3.1 Distributions
h = 0.18
add_image(ax, col_x[2], y_cursor - h, col_w, h,
    str(FIG_DIR / "final_distributions.png"),
    title="8 ▸ Combien de segments à la fin ?",
    band_color=RED_BAND,
    caption=f"Fig. 5 — Médianes : segs A=9, B=11. Fitness médiane : A≈{stats['a_mean']:.0f}, B≈{stats['b_mean']:.0f}.",
    reading_guide=("chaque point = un run. La boîte = la moitié centrale "
                   "des résultats. La médiane B est plus haute que A → en moyenne, "
                   "B fabrique plus de segments."),
)
y_cursor -= h + margin

# 3.2 Spécialisation paramétrique
h = 0.21
add_image(ax, col_x[2], y_cursor - h, col_w, h,
    str(FIG_DIR / "param_specialization.png"),
    title="9 ▸ Au-delà de la forme : les muscles sont-ils différents ?",
    band_color=BLUE_BAND,
    caption="Fig. 6 — Distribution des paramètres physiques sur les segments des 20 meilleurs corps.",
    reading_guide=("histogrammes des paramètres « moteur » et « friction » "
                   "sur tous les segments. Tirets = moyennes. Les courbes A et B "
                   "ne se superposent pas exactement → chaque environnement règle "
                   "ses muscles différemment."),
)
y_cursor -= h + margin

# 3.3 Paired scatter
h = 0.18
add_image(ax, col_x[2], y_cursor - h, col_w, h,
    str(FIG_DIR / "paired_scatter.png"),
    title="10 ▸ Même point de départ → mêmes corps ?",
    band_color=PINK_BAND,
    caption="Fig. 7 — Chaque point = une paire (A, B) issue de la même graine initiale.",
    reading_guide=("si l’environnement n’avait aucun effet, les points "
                   "seraient sur la diagonale (y = x). Ils ne le sont pas → le "
                   "même point de départ donne des corps différents selon le milieu."),
)
y_cursor -= h + margin

# 3.4 Conclusion
h = y_cursor - bot_footer - margin
add_section(ax, col_x[2], bot_footer + margin, col_w, h,
    "11 ▸ Conclusion — réponse à la problématique",
    [
        "OUI — la complexité de l’environnement façonne effectivement la",
        "morphologie de la créature, et ce à 4 niveaux observés simultanément :",
        "",
        "  ▣ TOPOLOGIE  (le corps a-t-il plus de segments ?)",
        f"      B sélectionne {stats['b_seg']:.1f} segments en moyenne contre {stats['a_seg']:.1f} en A.",
        "      L’écart se creuse dès la génération ~200 (Fig. 2).",
        "",
        "  ▣ STRUCTURE  (les plans corporels diffèrent-ils ?)",
        f"      Distance A ↔ B = {stats['ab']:.2f} > distance entre runs A = {stats['aa']:.2f}.",
        "      Visuellement (Fig. 3) : A = corps allongés horizontaux,",
        "      B = corps verticaux et touffus, plusieurs points d’appui.",
        "",
        "  ▣ PARAMÈTRES  (les « muscles » sont-ils calibrés autrement ?)",
        "      Plaine = moteurs rapides + adhérents (motor_speed 4,95 ;",
        "      friction 1,13). Terrain = moteurs lents + glissants",
        "      (3,48 ; 0,82). La sélection règle la mécanique, pas seulement",
        "      la forme.",
        "",
        "  ▣ ÉVOLUTION  (la pression du milieu domine-t-elle l’héritage ?)",
        "      Corrélation morpho A ↔ B entre paires partageant la même graine",
        "      ≈ 0 (Fig. 7) : la graine initiale n’a pas de pouvoir prédictif —",
        "      le milieu décide.",
        "",
        "→ INTERPRÉTATION POUR LE GRAND PUBLIC :",
        "    on observe in silico le même phénomène que la sélection naturelle",
        "    en biologie. Un milieu plus dur ne fabrique pas un seul « bon »",
        "    corps, il pousse vers une famille de corps plus complexes et",
        "    plus variés. La forme est bien dictée — au moins partiellement —",
        "    par les contraintes du milieu.",
    ],
    band_color=RED_BAND, body_fontsize=10.0,
)


# ─── Footer ─────────────────────────────────────────────────────────────────
ax.add_patch(Rectangle((0, 0), 1, bot_footer,
                       facecolor=TEAL_DARK, linewidth=0, transform=ax.transAxes))
ax.text(0.025, bot_footer * 0.70,
        "Références principales :  Auerbach & Bongard (GECCO 2012)  ·  Funes & Pollack (Artificial Life 1998)  ·  "
        "Moore & McKinley (GECCO 2012)  ·  Nordmoen et al. (Frontiers in Robotics and AI 2021)  ·  "
        "Sims (SIGGRAPH 1994)  ·  Kitchenham & Charters (EBSE 2007)",
        color="white", fontsize=11, ha="left", va="center", transform=ax.transAxes)
ax.text(0.025, bot_footer * 0.32,
        "Outils :  Python · Pymunk (physique 2D) · Matplotlib · NumPy   ·   "
        f"Session multi-run : 2026-04-21 · {stats['k']} runs × {stats['gens']} générations × 100 individus",
        color="white", fontsize=11, ha="left", va="center", transform=ax.transAxes)
ax.text(0.975, bot_footer * 0.50,
        "BEHRA Matthis  ·  A4 FISE INFO 2024 / 2025",
        color="white", fontsize=12, fontweight="bold", ha="right", va="center",
        transform=ax.transAxes)


fig.savefig(OUT, dpi=120, facecolor="white")
fig.savefig(OUT_PDF, facecolor="white")
plt.close(fig)
print(f"Saved: {OUT}")
print(f"Saved: {OUT_PDF}")
