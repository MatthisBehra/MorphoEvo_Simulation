"""Generate the A0 scientific poster as a PowerPoint (.pptx) file.

Mirrors scripts/build_poster.py (PNG/PDF) but produces an editable PPTX with
the same charter, layout, content and figures.
"""

import json
import statistics
from pathlib import Path

from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.oxml.ns import qn
from lxml import etree


ROOT = Path(__file__).resolve().parent.parent
RUN_DIR = ROOT / "runs" / "multirun_2026-04-21_220850"
FIG_DIR = ROOT / "docs" / "figures"
OUT_PPTX = ROOT / "docs" / "poster_BEHRA_A0.pptx"


# ── Charter (same as build_poster.py) ────────────────────────────────────────
TEAL_HEADER = RGBColor(0x3A, 0x78, 0x92)
TEAL_DARK = RGBColor(0x2C, 0x5F, 0x76)
SECTION_BG = RGBColor(0xEA, 0xF3, 0xF7)
SECTION_BORDER = RGBColor(0x7F, 0xAE, 0xC3)
RED_BAND = RGBColor(0xC6, 0x4A, 0x4A)
BLUE_BAND = RGBColor(0x3A, 0x78, 0x92)
PINK_BAND = RGBColor(0xD1, 0x8C, 0x93)
GLOSS_BG = RGBColor(0xFF, 0xF7, 0xE6)
GLOSS_BORDER = RGBColor(0xE0, 0xB8, 0x70)
GLOSS_BAND = RGBColor(0xB5, 0x8A, 0x3A)
TEXT_DARK = RGBColor(0x1F, 0x2C, 0x33)
GREY_TEXT = RGBColor(0x44, 0x56, 0x61)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)


# ── A0 portrait dimensions ───────────────────────────────────────────────────
PAGE_W = Inches(33.1)
PAGE_H = Inches(46.8)


# ── Geometry helpers (use fractions of page like the matplotlib version) ─────
def fx(frac: float) -> Emu:
    return Emu(int(PAGE_W * frac))


def fy(frac: float) -> Emu:
    return Emu(int(PAGE_H * frac))


# ── Stats (same loader as build_poster.py) ───────────────────────────────────
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


# ── Drawing helpers ──────────────────────────────────────────────────────────
def add_rect(slide, x, y, w, h, fill, line=None, line_w=None):
    shape = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, x, y, w, h)
    shape.fill.solid()
    shape.fill.fore_color.rgb = fill
    if line is None:
        shape.line.fill.background()
    else:
        shape.line.color.rgb = line
        if line_w is not None:
            shape.line.width = line_w
    shape.shadow.inherit = False
    return shape


def add_round_rect(slide, x, y, w, h, fill, line, line_w):
    shape = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, x, y, w, h)
    # Reduce corner radius a bit
    shape.adjustments[0] = 0.04
    shape.fill.solid()
    shape.fill.fore_color.rgb = fill
    shape.line.color.rgb = line
    shape.line.width = line_w
    shape.shadow.inherit = False
    return shape


def add_textbox(slide, x, y, w, h, text, *, font_size=11, bold=False,
                italic=False, color=TEXT_DARK, align=PP_ALIGN.LEFT,
                anchor=MSO_ANCHOR.TOP, line_spacing=1.30, font_name="Calibri"):
    tb = slide.shapes.add_textbox(x, y, w, h)
    tf = tb.text_frame
    tf.word_wrap = True
    tf.margin_left = Emu(0)
    tf.margin_right = Emu(0)
    tf.margin_top = Emu(0)
    tf.margin_bottom = Emu(0)
    tf.vertical_anchor = anchor

    lines = text.split("\n") if isinstance(text, str) else list(text)
    for i, line in enumerate(lines):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        p.line_spacing = line_spacing
        run = p.add_run()
        run.text = line
        run.font.name = font_name
        run.font.size = Pt(font_size)
        run.font.bold = bold
        run.font.italic = italic
        run.font.color.rgb = color
    return tb


def add_section(slide, x, y, w, h, title, body_lines, band_color,
                body_fontsize=11.0, bg=SECTION_BG, border=SECTION_BORDER):
    add_round_rect(slide, x, y, w, h, fill=bg, line=border, line_w=Pt(1.2))
    band_h_frac = 0.020
    band_h = fy(band_h_frac)
    pad = fx(0.005)
    band_x = x + pad
    band_y = y + pad
    band_w = w - 2 * pad
    add_rect(slide, band_x, band_y, band_w, band_h, fill=band_color)

    add_textbox(
        slide,
        band_x + fx(0.004), band_y, band_w, band_h,
        title, font_size=18, bold=True, color=WHITE,
        anchor=MSO_ANCHOR.MIDDLE,
    )

    body_x = x + fx(0.012)
    body_y = band_y + band_h + fy(0.005)
    body_w = w - 2 * fx(0.012)
    body_h = h - (band_y + band_h - y) - fy(0.010)
    add_textbox(
        slide,
        body_x, body_y, body_w, body_h,
        "\n".join(body_lines),
        font_size=body_fontsize, color=TEXT_DARK,
        line_spacing=1.40,
    )


def add_image_section(slide, x, y, w, h, img_path, title, band_color,
                      caption=None, reading_guide=None):
    add_round_rect(slide, x, y, w, h, fill=WHITE, line=SECTION_BORDER, line_w=Pt(1.2))
    band_h = fy(0.020)
    pad = fx(0.005)
    band_x = x + pad
    band_y = y + pad
    band_w = w - 2 * pad
    add_rect(slide, band_x, band_y, band_w, band_h, fill=band_color)
    add_textbox(
        slide,
        band_x + fx(0.004), band_y, band_w, band_h,
        title, font_size=18, bold=True, color=WHITE,
        anchor=MSO_ANCHOR.MIDDLE,
    )

    # Reserve space for reading guide + caption at the bottom
    rg_h = fy(0.022) if reading_guide else 0
    cap_h = fy(0.012) if caption else 0
    pad_top = band_h + fy(0.010)
    pad_side = fx(0.012)
    pad_bot = fy(0.010) + cap_h + rg_h

    inner_x = x + pad_side
    inner_y = y + pad + pad_top
    inner_w = w - 2 * pad_side
    inner_h = h - pad - pad_top - pad_bot

    # Read image to get aspect ratio
    from PIL import Image
    with Image.open(img_path) as im:
        img_w, img_h = im.size
    img_aspect = img_w / img_h
    box_aspect = inner_w / inner_h
    if img_aspect > box_aspect:
        draw_w = inner_w
        draw_h = Emu(int(inner_w / img_aspect))
        draw_x = inner_x
        draw_y = inner_y + Emu(int((inner_h - draw_h) / 2))
    else:
        draw_h = inner_h
        draw_w = Emu(int(inner_h * img_aspect))
        draw_x = inner_x + Emu(int((inner_w - draw_w) / 2))
        draw_y = inner_y

    slide.shapes.add_picture(str(img_path), draw_x, draw_y, draw_w, draw_h)

    if reading_guide:
        rg_y = y + h - fy(0.010) - cap_h - rg_h
        add_textbox(
            slide,
            x + pad_side, rg_y, w - 2 * pad_side, rg_h,
            "▶ Comment lire — " + reading_guide,
            font_size=10, color=GREY_TEXT, align=PP_ALIGN.CENTER,
            anchor=MSO_ANCHOR.MIDDLE, line_spacing=1.15,
        )

    if caption:
        cap_y = y + h - fy(0.010) - cap_h
        add_textbox(
            slide,
            x + pad_side, cap_y, w - 2 * pad_side, cap_h,
            caption,
            font_size=10, italic=True, color=TEXT_DARK,
            align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE,
        )


# ── Build presentation ───────────────────────────────────────────────────────
def main():
    stats = load_stats()

    prs = Presentation()
    prs.slide_width = PAGE_W
    prs.slide_height = PAGE_H

    blank_layout = prs.slide_layouts[6]
    slide = prs.slides.add_slide(blank_layout)

    # White background full page
    add_rect(slide, Emu(0), Emu(0), PAGE_W, PAGE_H, fill=WHITE)

    # ─── Header ────────────────────────────────────────────────────────────
    header_h_frac = 0.062
    header_h = fy(header_h_frac)
    add_rect(slide, Emu(0), Emu(0), PAGE_W, header_h, fill=TEAL_HEADER)

    # Left header
    add_textbox(
        slide,
        fx(0.025), fy(0.005), fx(0.65), fy(0.030),
        "Influence de la complexité de l'environnement",
        font_size=64, bold=True, color=WHITE,
    )
    add_textbox(
        slide,
        fx(0.025), fy(0.034), fx(0.65), fy(0.018),
        "sur l'évolution morphologique d'une créature virtuelle",
        font_size=38, italic=True, color=WHITE,
    )
    add_textbox(
        slide,
        fx(0.025), fy(0.052), fx(0.65), fy(0.012),
        "BEHRA Matthis  —  A4 FISE INFO 2024 / 2025  —  Étude multi-runs (k = 20 paires)",
        font_size=22, color=WHITE,
    )

    # Right header
    add_textbox(
        slide,
        fx(0.65), fy(0.005), fx(0.325), fy(0.018),
        "Algorithme génétique classique",
        font_size=22, bold=True, color=WHITE, align=PP_ALIGN.RIGHT,
    )
    add_textbox(
        slide,
        fx(0.65), fy(0.026), fx(0.325), fy(0.016),
        "Encodage direct paramétrique  ·  Pas de neuro-évolution",
        font_size=18, color=WHITE, align=PP_ALIGN.RIGHT,
    )
    add_textbox(
        slide,
        fx(0.65), fy(0.046), fx(0.325), fy(0.016),
        "Reproduction expérimentale d'Auerbach & Bongard (2012)",
        font_size=18, italic=True, color=WHITE, align=PP_ALIGN.RIGHT,
    )

    # ─── Context / glossary band ───────────────────────────────────────────
    margin = 0.012
    ctx_top = header_h_frac + 0.008
    ctx_h_frac = 0.058
    ctx_x = fx(margin)
    ctx_y = fy(ctx_top)
    ctx_w = fx(1 - 2 * margin)
    ctx_h = fy(ctx_h_frac)
    add_section(
        slide, ctx_x, ctx_y, ctx_w, ctx_h,
        "EN BREF — pour qui découvre le sujet",
        [
            "Les êtres vivants ont la forme qu'ils ont parce qu'ils ont dû s'adapter à leur milieu. Cette étude pose la même question dans un monde virtuel : si on laisse un programme « inventer » la forme d'une "
            "petite créature pour lui apprendre à se déplacer, l'environnement (terrain plat ou accidenté) influence-t-il la forme finale ?",
            "Méthode :  on ne dessine PAS les créatures à la main. On utilise un algorithme génétique — une population de 100 corps virtuels qui se reproduisent, mutent et sont sélectionnés sur 1000 générations, comme une évolution darwinienne accélérée.",
            "Lecture du poster :  les couleurs des bandeaux n'ont pas de sens technique, elles servent juste à séparer les sections. Bleu = environnement A (plaine), orange/crème = environnement B (terrain accidenté). 20 runs ont été lancés pour la robustesse statistique.",
        ],
        band_color=GLOSS_BAND, body_fontsize=15,
        bg=GLOSS_BG, border=GLOSS_BORDER,
    )

    # ─── Layout grid ───────────────────────────────────────────────────────
    top = ctx_top + ctx_h_frac + margin
    bot_footer_frac = 0.045
    col_w_frac = (1 - 4 * margin) / 3
    col_x_frac = [margin, margin + col_w_frac + margin, margin + 2 * (col_w_frac + margin)]

    col_w = fx(col_w_frac)

    # ── Column 1 (left) ────────────────────────────────────────────────────
    y_cursor = top

    # 1.1 Problématique & contexte
    h_frac = 0.16
    add_section(
        slide, fx(col_x_frac[0]), fy(y_cursor), col_w, fy(h_frac),
        "1 ▸ Problématique & contexte scientifique",
        [
            "En biologie, on observe que la forme du corps d'un animal — nageoires,",
            "pattes longues, carapace — est largement « dictée » par le milieu où il",
            "vit. On peut tester cette idée en simulation, sans biologie réelle.",
            "",
            "Question de recherche :",
            "▶ Si on laisse un algorithme génétique « inventer » la morphologie",
            "    d'une créature virtuelle, la complexité de son environnement",
            "    influence-t-elle la forme finale qu'elle va adopter ?",
            "",
            "Référence pivot : Auerbach & Bongard (GECCO 2012) montrent que oui,",
            "sur des robots simulés. Notre travail le reproduit indépendamment, sur",
            "un protocole strict : 4 études primaires retenues par revue systématique",
            "(Kitchenham & Charters, 2007), puis 20 simulations comparatives.",
        ],
        band_color=RED_BAND, body_fontsize=14,
    )
    y_cursor += h_frac + margin

    # 1.2 Algorithme génétique
    h_frac = 0.31
    add_section(
        slide, fx(col_x_frac[0]), fy(y_cursor), col_w, fy(h_frac),
        "2 ▸ L'algorithme génétique en 5 étapes",
        [
            "Un algorithme génétique imite l'évolution naturelle. À chaque génération :",
            "",
            "  ① ÉVALUATION  — chaque créature tente de se déplacer pendant 15 s.",
            "      Sa note (fitness) mesure la distance parcourue, moins l'énergie",
            "      dépensée, moins une pénalité de complexité (0,5 × n_segments).",
            "",
            "  ② SÉLECTION  — les meilleures ont plus de chances d'être « parents ».",
            "      Tournoi à 3 + élitisme (les 2 meilleures passent intactes).",
            "      Niching : les corps trop similaires sont pénalisés (diversité).",
            "",
            "  ③ CROISEMENT — chaque scalaire d'un nouveau corps est tiré chez",
            "      l'un des deux parents. Les sous-arbres en trop sont gardés p=0,5.",
            "",
            "  ④ MUTATION SCALAIRE — chaque paramètre est légèrement perturbé",
            "      (gaussienne) : largeur, vitesse moteur, friction…",
            "",
            "  ⑤ MUTATION STRUCTURELLE — 1×/individu/génération :",
            "      ajout d'un segment (12 %), retrait (5 %), plafond à 12 segments.",
            "      C'est cette étape qui fait émerger la complexité morphologique.",
            "",
            "GÉNOME — chaque créature = un arbre de segments rigides reliés par des",
            "articulations motorisées. Paramètres par segment : taille, angle, vitesse",
            "de moteur, friction, amortissement. Pas de cerveau, pas d'apprentissage —",
            "le moteur suit une simple sinusoïde universelle ω = motor_speed × sin(t·10",
            "+ motor_phase). Toute la « stratégie » est dans la forme.",
        ],
        band_color=BLUE_BAND, body_fontsize=12.5,
    )
    y_cursor += h_frac + margin

    # 1.3 Protocole expérimental
    h_frac = 0.13
    add_section(
        slide, fx(col_x_frac[0]), fy(y_cursor), col_w, fy(h_frac),
        "3 ▸ Protocole — un test équitable",
        [
            "On lance K = 20 simulations indépendantes. Pour CHAQUE simulation, on",
            "duplique la population initiale et on la fait évoluer en parallèle dans",
            "deux environnements différents (A et B). Toute différence finale est",
            "donc imputable à l'environnement, pas au hasard de l'initialisation.",
            "",
            "  • A — Plaine ouverte (sol uniforme)",
            "  • B — Terrain accidenté (pentes ±25°, zones molles)",
            "  • 100 individus × 1000 générations × 2 envs × 20 runs = 4 M évaluations",
            f"  • Temps de calcul : {stats['wall_h']:.0f} h, 8 workers parallèles.",
        ],
        band_color=PINK_BAND, body_fontsize=13,
    )
    y_cursor += h_frac + margin

    # 1.4 Convergence fitness
    bottom_limit = 1 - bot_footer_frac - margin
    remaining = bottom_limit - y_cursor
    add_image_section(
        slide, fx(col_x_frac[0]), fy(y_cursor), col_w, fy(remaining),
        FIG_DIR / "fitness_convergence.png",
        title="4 ▸ Apprentissage — la fitness progresse-t-elle ?",
        band_color=BLUE_BAND,
        caption="Fig. 1 — Fitness moyenne du meilleur individu par génération, 20 runs.",
        reading_guide=("ligne = moyenne sur 20 runs, bande = ±1 écart-type. "
                       "Plus la courbe monte, mieux la population se déplace. Les deux "
                       "environnements progressent, mais l'écart se creuse à partir de la gen ~200."),
    )

    # ── Column 2 (middle) ──────────────────────────────────────────────────
    y_cursor = top

    # 2.1 Émergence segments
    h_frac = 0.235
    add_image_section(
        slide, fx(col_x_frac[1]), fy(y_cursor), col_w, fy(h_frac),
        FIG_DIR / "segments_evolution.png",
        title="5 ▸ La complexité du corps grandit-elle ?",
        band_color=RED_BAND,
        caption="Fig. 2 — Nombre moyen de segments dans la population par génération.",
        reading_guide=("toutes les créatures démarrent avec 2 segments. Plus la "
                       "courbe monte, plus les corps deviennent compliqués. La courbe orange "
                       "(B, terrain) finit nettement plus haut que la bleue (A, plaine)."),
    )
    y_cursor += h_frac + margin

    # 2.2 Morphologies
    h_frac = 0.42
    add_image_section(
        slide, fx(col_x_frac[1]), fy(y_cursor), col_w, fy(h_frac),
        FIG_DIR / "morpho_pairs_selected.png",
        title="6 ▸ À quoi ressemblent les créatures finales ?",
        band_color=BLUE_BAND,
        caption="Fig. 3 — Reconstruction des meilleures créatures à la dernière génération.",
        reading_guide=("chaque ligne = une simulation, fond bleu pâle = plaine, "
                       "fond crème = terrain. Même graine de départ pour A et B → toute différence "
                       "vient de l'environnement, pas du hasard."),
    )
    y_cursor += h_frac + margin

    # 2.3 Distance heatmaps
    remaining = bottom_limit - y_cursor
    add_image_section(
        slide, fx(col_x_frac[1]), fy(y_cursor), col_w, fy(remaining),
        FIG_DIR / "distance_heatmaps.png",
        title="7 ▸ Les morphologies des deux mondes se ressemblent-elles ?",
        band_color=PINK_BAND,
        caption=f"Fig. 4 — Plus c'est sombre, plus les corps sont semblables. AA={stats['aa']:.2f} · BB={stats['bb']:.2f} · AB={stats['ab']:.2f}.",
        reading_guide=("on compare deux à deux les 20 corps finaux. À gauche : "
                       "entre eux les corps évolués en plaine se ressemblent (sombre). "
                       "À droite : un corps de plaine vs un corps de terrain → couleurs claires = "
                       "ils sont différents."),
    )

    # ── Column 3 (right) ───────────────────────────────────────────────────
    y_cursor = top

    # 3.1 Distributions
    h_frac = 0.18
    add_image_section(
        slide, fx(col_x_frac[2]), fy(y_cursor), col_w, fy(h_frac),
        FIG_DIR / "final_distributions.png",
        title="8 ▸ Combien de segments à la fin ?",
        band_color=RED_BAND,
        caption=f"Fig. 5 — Médianes : segs A=9, B=11. Fitness médiane : A≈{stats['a_mean']:.0f}, B≈{stats['b_mean']:.0f}.",
        reading_guide=("chaque point = un run. La boîte = la moitié centrale "
                       "des résultats. La médiane B est plus haute que A → en moyenne, "
                       "B fabrique plus de segments."),
    )
    y_cursor += h_frac + margin

    # 3.2 Spécialisation paramétrique
    h_frac = 0.21
    add_image_section(
        slide, fx(col_x_frac[2]), fy(y_cursor), col_w, fy(h_frac),
        FIG_DIR / "param_specialization.png",
        title="9 ▸ Au-delà de la forme : les muscles sont-ils différents ?",
        band_color=BLUE_BAND,
        caption="Fig. 6 — Distribution des paramètres physiques sur les segments des 20 meilleurs corps.",
        reading_guide=("histogrammes des paramètres « moteur » et « friction » "
                       "sur tous les segments. Tirets = moyennes. Les courbes A et B "
                       "ne se superposent pas exactement → chaque environnement règle "
                       "ses muscles différemment."),
    )
    y_cursor += h_frac + margin

    # 3.3 Paired scatter
    h_frac = 0.18
    add_image_section(
        slide, fx(col_x_frac[2]), fy(y_cursor), col_w, fy(h_frac),
        FIG_DIR / "paired_scatter.png",
        title="10 ▸ Même point de départ → mêmes corps ?",
        band_color=PINK_BAND,
        caption="Fig. 7 — Chaque point = une paire (A, B) issue de la même graine initiale.",
        reading_guide=("si l'environnement n'avait aucun effet, les points "
                       "seraient sur la diagonale (y = x). Ils ne le sont pas → le "
                       "même point de départ donne des corps différents selon le milieu."),
    )
    y_cursor += h_frac + margin

    # 3.4 Conclusion
    remaining = bottom_limit - y_cursor
    add_section(
        slide, fx(col_x_frac[2]), fy(y_cursor), col_w, fy(remaining),
        "11 ▸ Conclusion — réponse à la problématique",
        [
            "OUI — la complexité de l'environnement façonne effectivement la",
            "morphologie de la créature, et ce à 4 niveaux observés simultanément :",
            "",
            "  ▣ TOPOLOGIE  (le corps a-t-il plus de segments ?)",
            f"      B sélectionne {stats['b_seg']:.1f} segments en moyenne contre {stats['a_seg']:.1f} en A.",
            "      L'écart se creuse dès la génération ~200 (Fig. 2).",
            "",
            "  ▣ STRUCTURE  (les plans corporels diffèrent-ils ?)",
            f"      Distance A ↔ B = {stats['ab']:.2f} > distance entre runs A = {stats['aa']:.2f}.",
            "      Visuellement (Fig. 3) : A = corps allongés horizontaux,",
            "      B = corps verticaux et touffus, plusieurs points d'appui.",
            "",
            "  ▣ PARAMÈTRES  (les « muscles » sont-ils calibrés autrement ?)",
            "      Plaine = moteurs rapides + adhérents (motor_speed 4,95 ;",
            "      friction 1,13). Terrain = moteurs lents + glissants",
            "      (3,48 ; 0,82). La sélection règle la mécanique, pas seulement",
            "      la forme.",
            "",
            "  ▣ ÉVOLUTION  (la pression du milieu domine-t-elle l'héritage ?)",
            "      Corrélation morpho A ↔ B entre paires partageant la même graine",
            "      ≈ 0 (Fig. 7) : la graine initiale n'a pas de pouvoir prédictif —",
            "      le milieu décide.",
            "",
            "→ INTERPRÉTATION POUR LE GRAND PUBLIC :",
            "    on observe in silico le même phénomène que la sélection naturelle",
            "    en biologie. Un milieu plus dur ne fabrique pas un seul « bon »",
            "    corps, il pousse vers une famille de corps plus complexes et",
            "    plus variés. La forme est bien dictée — au moins partiellement —",
            "    par les contraintes du milieu.",
        ],
        band_color=RED_BAND, body_fontsize=13,
    )

    # ─── Footer ───────────────────────────────────────────────────────────
    footer_y = fy(1 - bot_footer_frac)
    footer_h = fy(bot_footer_frac)
    add_rect(slide, Emu(0), footer_y, PAGE_W, footer_h, fill=TEAL_DARK)

    add_textbox(
        slide,
        fx(0.025), footer_y + fy(0.006), fx(0.85), fy(0.016),
        "Références principales :  Auerbach & Bongard (GECCO 2012)  ·  Funes & Pollack (Artificial Life 1998)  ·  "
        "Moore & McKinley (GECCO 2012)  ·  Nordmoen et al. (Frontiers in Robotics and AI 2021)  ·  "
        "Sims (SIGGRAPH 1994)  ·  Kitchenham & Charters (EBSE 2007)",
        font_size=15, color=WHITE,
    )
    add_textbox(
        slide,
        fx(0.025), footer_y + fy(0.026), fx(0.85), fy(0.016),
        "Outils :  Python · Pymunk (physique 2D) · Matplotlib · NumPy   ·   "
        f"Session multi-run : 2026-04-21 · {stats['k']} runs × {stats['gens']} générations × 100 individus",
        font_size=15, color=WHITE,
    )
    add_textbox(
        slide,
        fx(0.65), footer_y + fy(0.014), fx(0.325), fy(0.018),
        "BEHRA Matthis  ·  A4 FISE INFO 2024 / 2025",
        font_size=17, bold=True, color=WHITE, align=PP_ALIGN.RIGHT,
    )

    prs.save(OUT_PPTX)
    print(f"Saved: {OUT_PPTX}")


if __name__ == "__main__":
    main()
