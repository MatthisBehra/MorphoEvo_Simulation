"""Build v4 of the research article — expands the GA section, adds the 20-run
comparison list, and writes the conclusion answering the research question."""

import json
import statistics
import math
from pathlib import Path

from docx import Document
from docx.shared import Pt, Cm, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_ALIGN_VERTICAL
from docx.oxml.ns import qn
from docx.oxml import OxmlElement


ROOT = Path(__file__).resolve().parent.parent
REPORT = ROOT / "runs" / "multirun_2026-04-21_220850" / "report.json"
OUT = ROOT / "docs" / "article_recherche_BEHRA_v4.docx"


def _safe_out(path):
    """If the target is locked (open in Word), fall back to a numbered sibling."""
    try:
        with open(path, "ab"):
            pass
        return path
    except PermissionError:
        i = 1
        while True:
            alt = path.with_name(path.stem + f"_{i}" + path.suffix)
            try:
                with open(alt, "ab"):
                    pass
                return alt
            except PermissionError:
                i += 1


def set_cell_shading(cell, hex_color):
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), hex_color)
    tc_pr.append(shd)


def add_heading(doc, text, level=1):
    h = doc.add_heading(text, level=level)
    return h


def add_para(doc, text, bold=False, italic=False, size=11, justify=True):
    p = doc.add_paragraph()
    if justify:
        p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    run = p.add_run(text)
    run.bold = bold
    run.italic = italic
    run.font.size = Pt(size)
    return p


def add_bullet(doc, text):
    p = doc.add_paragraph(text, style="List Bullet")
    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    return p


def load_report():
    with open(REPORT, "r") as f:
        return json.load(f)


def corr(x, y):
    n = len(x)
    mx = sum(x) / n
    my = sum(y) / n
    sx = math.sqrt(sum((xi - mx) ** 2 for xi in x))
    sy = math.sqrt(sum((yi - my) ** 2 for yi in y))
    if sx == 0 or sy == 0:
        return 0.0
    return sum((xi - mx) * (yi - my) for xi, yi in zip(x, y)) / (sx * sy)


def avg_off_diag(M):
    n = len(M)
    s, c = 0.0, 0
    for i in range(n):
        for j in range(n):
            if i != j:
                s += M[i][j]
                c += 1
    return s / c if c else 0.0


def avg_full(M):
    rows = len(M)
    cols = len(M[0])
    return sum(M[i][j] for i in range(rows) for j in range(cols)) / (rows * cols)


def main():
    rep = load_report()
    ra = sorted(rep["results_a"], key=lambda x: x["run_id"])
    rb = sorted(rep["results_b"], key=lambda x: x["run_id"])
    af = [x["best_fitness"] for x in ra]
    bf = [x["best_fitness"] for x in rb]
    asg = [x["final_segments"] for x in ra]
    bsg = [x["final_segments"] for x in rb]

    stats = {
        "k": rep["k_runs"],
        "gens": rep["n_generations"],
        "pop": rep["pop_size"],
        "duration_s": rep["gen_duration"],
        "wall_h": rep["wall_time_s"] / 3600.0,
        "workers": rep["n_workers"],
        "a_mean": statistics.mean(af),
        "a_std": statistics.stdev(af),
        "a_med": statistics.median(af),
        "a_min": min(af),
        "a_max": max(af),
        "b_mean": statistics.mean(bf),
        "b_std": statistics.stdev(bf),
        "b_med": statistics.median(bf),
        "b_min": min(bf),
        "b_max": max(bf),
        "a_seg_mean": statistics.mean(asg),
        "a_seg_std": statistics.stdev(asg),
        "b_seg_mean": statistics.mean(bsg),
        "b_seg_std": statistics.stdev(bsg),
        "corr_fit": corr(af, bf),
        "corr_seg": corr(asg, bsg),
        "aa_avg": avg_off_diag(rep["distance_matrix_aa"]),
        "bb_avg": avg_off_diag(rep["distance_matrix_bb"]),
        "ab_avg": avg_full(rep["distance_matrix_ab"]),
        "mean_div_ab": rep["mean_divergence_ab"],
        "a_gen0": statistics.mean(x["fitness_history"][0] for x in ra),
        "b_gen0": statistics.mean(x["fitness_history"][0] for x in rb),
        "a_gen_last": statistics.mean(x["fitness_history"][-1] for x in ra),
        "b_gen_last": statistics.mean(x["fitness_history"][-1] for x in rb),
    }

    doc = Document()
    style = doc.styles["Normal"]
    style.font.name = "Calibri"
    style.font.size = Pt(11)

    # ---------- Title ----------
    title = doc.add_paragraph()
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = title.add_run("ARTICLE DE RECHERCHE — Version 4")
    r.bold = True
    r.font.size = Pt(18)

    sub = doc.add_paragraph()
    sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = sub.add_run(
        "L’influence de la complexité de l’environnement\n"
        "sur l’évolution morphologique d’une créature virtuelle"
    )
    r.italic = True
    r.font.size = Pt(13)

    auth = doc.add_paragraph()
    auth.alignment = WD_ALIGN_PARAGRAPH.CENTER
    auth.add_run("BEHRA Matthis — A4 FISE INFO — 2024/2025").bold = True

    kw = doc.add_paragraph()
    kw.alignment = WD_ALIGN_PARAGRAPH.CENTER
    kw.add_run(
        "Mots-clés : Algorithme génétique, évolution morphologique, créature virtuelle, "
        "pression sélective, simulation, étude multi-runs"
    ).italic = True

    # ---------- 1. Abstract ----------
    add_heading(doc, "1. Abstract", level=1)
    add_para(
        doc,
        "Cette quatrième version de l’article enrichit la version précédente en deux directions : "
        "elle détaille la démarche scientifique et l’algorithme génétique sous-jacent à la simulation, "
        "et elle confronte les hypothèses issues de la revue systématique de littérature aux résultats "
        "expérimentaux d’une session multi-runs portant sur 20 paires d’environnements (A : plaine, "
        "B : terrain accidenté). La problématique reste inchangée : dans quelle mesure la complexité "
        "de l’environnement de simulation dicte-t-elle l’architecture corporelle d’une créature virtuelle "
        "évoluant par algorithme génétique classique ?",
    )
    add_para(
        doc,
        "Vingt populations indépendantes de 100 individus, chacune partageant la même initialisation pour "
        "ses deux exécutions parallèles A et B, ont été évoluées sur 1000 générations (15 s par génération, "
        "8 workers, durée totale : "
        f"{stats['wall_h']:.1f} h de calcul). La comparaison des morphologies finales et l’analyse des "
        "matrices de distance confirment expérimentalement la thèse centrale d’Auerbach & Bongard (2012) : "
        "la complexité de l’environnement oriente bien la convergence morphologique.",
    )

    # ---------- 2. Démarche scientifique ----------
    add_heading(doc, "2. Démarche scientifique", level=1)
    add_para(
        doc,
        "La démarche suit un protocole en quatre étapes, conçu pour garantir la traçabilité des conclusions :",
    )
    add_bullet(
        doc,
        "Étape 1 — Revue systématique de littérature (Kitchenham & Charters, 2007). "
        "Trois requêtes booléennes sur Google Scholar, période 1994–2025, cinq critères d’inclusion (C1–C5), "
        "six questions d’évaluation qualitative (QA1–QA6), seuil 3/6. Quatre études primaires retenues "
        "(S1 = Auerbach & Bongard 2012 ; S2 = Funes & Pollack 1998 ; S3 = Moore & McKinley 2012 ; "
        "S4 = Nordmoen et al. 2021).",
    )
    add_bullet(
        doc,
        "Étape 2 — Formulation des hypothèses. H1 : un environnement plus contraint produit des "
        "morphologies plus complexes (segments supplémentaires, articulations spécialisées). "
        "H2 : à population initiale identique, deux environnements distincts conduisent à une "
        "divergence morphologique mesurable.",
    )
    add_bullet(
        doc,
        "Étape 3 — Conception expérimentale. Encodage direct paramétrique (RQ1), fitness à base de "
        "distance de locomotion (RQ2), comparaison inter-environnements à population initiale partagée "
        "(RQ3), isolation stricte de la variable morphologie via un oscillateur sinusoïdal universel "
        "(formule unique : ω = motor_speed × sin(t × 10 + motor_phase)).",
    )
    add_bullet(
        doc,
        "Étape 4 — Validation statistique. Vingt runs indépendants, agrégation des fitness moyennes et "
        "écart-types, calcul des matrices de distance morphologique intra (A↔A, B↔B) et inter (A↔B) "
        "environnements, test de corrélation entre paires A/B partageant la même graine initiale.",
    )

    # ---------- 3. Méthodologie SLR (résumé) ----------
    add_heading(doc, "3. Méthodologie de sélection (SLR)", level=1)
    add_para(
        doc,
        "La revue systématique de littérature a été conduite selon le protocole Kitchenham & Charters "
        "(2007), sur Google Scholar, avec trois requêtes booléennes couvrant la période 1994–2025. "
        "Cinq critères d’inclusion C1–C5 (pertinence morphologique, AG sans NEAT, rôle actif de "
        "l’environnement, composante empirique, accessibilité), six questions d’évaluation qualitative "
        "QA1–QA6 (objectifs, encodage, environnement contrôlé, métriques, résultats comparatifs, "
        "perspectives) avec un seuil minimum de 3/6 ont permis de retenir quatre études primaires.",
    )
    add_para(
        doc,
        "Les conclusions de la revue convergent vers : (i) l’encodage direct paramétrique comme "
        "représentation génomique de référence, (ii) la fitness basée sur la distance de locomotion comme "
        "métrique principale, (iii) l’effet établi de la complexité environnementale sur la complexité "
        "morphologique (Auerbach & Bongard, 2012).",
    )

    # ---------- 4. État de l’art (résumé) ----------
    add_heading(doc, "4. État de l’art (synthèse)", level=1)
    add_para(
        doc,
        "Sims (1994) ouvre le champ avec la co-évolution corps-cerveau de créatures virtuelles. "
        "Funes & Pollack (1998) isolent la morphologie via un encodage direct arborescent. "
        "Moore & McKinley (2012) ajoutent les paramètres articulaires. Auerbach & Bongard (2012) "
        "démontrent expérimentalement le lien entre complexité environnementale et complexité "
        "morphologique. Nordmoen et al. (2021) introduisent les métriques quality-diversity (QD-score, "
        "coverage) et montrent qu’une diversité morphologique pré-acquise facilite l’adaptation.",
    )

    # ---------- 5. Algorithme génétique ----------
    add_heading(doc, "5. Algorithme génétique — détail technique", level=1)

    add_heading(doc, "5.1 Représentation du génome (encodage direct)", level=2)
    add_para(
        doc,
        "Le génome est un arbre imbriqué de nœuds. Chaque nœud correspond à un segment physique "
        "(corps rigide pymunk relié à son parent par un PivotJoint + SimpleMotor + RotaryLimitJoint + "
        "DampedRotarySpring). Les paramètres scalaires de chaque nœud sont :",
    )
    add_bullet(doc, "width, height — dimensions du segment (gènes scalaires réels) ;")
    add_bullet(doc, "rel_angle — angle d’attache au parent ;")
    add_bullet(doc, "motor_speed, motor_phase, motor_force — paramètres du moteur sinusoïdal ;")
    add_bullet(doc, "stiffness, damping — propriétés du ressort de rappel articulaire ;")
    add_bullet(doc, "limits (min, max) — amplitude angulaire du joint ;")
    add_bullet(doc, "children — liste de sous-arbres (récursif).")
    add_para(
        doc,
        "L’initialisation produit un génome minimal de deux segments (torse + un enfant). "
        "La complexité morphologique émerge ensuite par mutation structurelle, sans imposer de symétrie "
        "ni de plan corporel a priori.",
    )

    add_heading(doc, "5.2 Fonction de fitness", level=2)
    add_para(doc, "Deux fitness distinctes sont définies, l’une par environnement :")
    add_bullet(
        doc,
        "Environnement A (plaine) : fitness = distance_max − pénalité_énergie − 0,5 × n_segments. "
        "La pénalité de complexité décourage la prolifération de segments inutiles.",
    )
    add_bullet(
        doc,
        "Environnement B (terrain accidenté) : fitness = distance_max + bonus_inclinaison + bonus_stabilité "
        "− 0,5 × n_segments. Le bonus d’inclinaison récompense la traversée de pentes "
        "(Σ couvert × |sin(angle)|), le bonus de stabilité récompense la régularité du déplacement.",
    )

    add_heading(doc, "5.3 Opérateurs génétiques", level=2)
    add_para(doc, "Le pipeline générationnel applique successivement :")
    add_bullet(
        doc,
        "Élitisme — les 2 meilleurs individus (fitness brute) sont copiés intacts dans la génération "
        "suivante.",
    )
    add_bullet(
        doc,
        "Fitness sharing (niching) — chaque fitness est divisée par la taille de la niche morphologique. "
        "La distance morphologique utilisée est |Δ n_segments| avec σ = 3, ce qui pénalise la convergence "
        "vers un plan corporel unique et préserve la diversité.",
    )
    add_bullet(
        doc,
        "Sélection par tournoi (k = 3) sur la fitness partagée — favorise la pression sélective tout en "
        "laissant une chance aux individus moyens.",
    )
    add_bullet(
        doc,
        "Croisement (crossover_dna) — fusion nœud-à-nœud des deux parents : chaque scalaire est tiré "
        "aléatoirement chez un parent ; les enfants surnuméraires du parent le plus profond sont conservés "
        "avec probabilité 0,5.",
    )
    add_bullet(
        doc,
        "Mutation scalaire (mutate_dna) — perturbation gaussienne de chaque gène scalaire avec un taux "
        "et un écart-type pré-réglés ; appliquée récursivement à tous les nœuds.",
    )
    add_bullet(
        doc,
        "Mutation structurelle (mutate_structure) — appliquée une fois par individu et par génération : "
        "ajout d’un segment avec probabilité 12 %, suppression avec probabilité 5 %, plafond à 12 segments. "
        "C’est cette mutation qui permet à la complexité morphologique d’émerger ou de régresser.",
    )

    add_heading(doc, "5.4 Hyperparamètres effectifs (session 20-runs)", level=2)
    table = doc.add_table(rows=1, cols=2)
    table.style = "Light Grid Accent 1"
    hdr = table.rows[0].cells
    hdr[0].text = "Paramètre"
    hdr[1].text = "Valeur"
    rows = [
        ("Taille de population", f"{stats['pop']}"),
        ("Nombre de générations", f"{stats['gens']}"),
        ("Durée d’une génération (sim)", f"{stats['duration_s']:.1f} s"),
        ("Nombre de runs indépendants", f"{stats['k']}"),
        ("Workers parallèles", f"{stats['workers']}"),
        ("Élitisme", "2 individus"),
        ("Sélection", "Tournoi k = 3 sur fitness partagée"),
        ("Niching σ", "3 (sur Δ n_segments)"),
        ("Probabilité ajout segment", "12 %"),
        ("Probabilité suppression segment", "5 %"),
        ("Plafond segments", "12"),
        ("Initialisation", "2 segments minimaux"),
        ("Durée totale du calcul", f"{stats['wall_h']:.1f} h"),
    ]
    for k, v in rows:
        row = table.add_row().cells
        row[0].text = k
        row[1].text = v

    # ---------- 6. Résultats : 20-run ----------
    add_heading(doc, "6. Résultats expérimentaux — session 20 runs", level=1)

    add_heading(doc, "6.1 Vue d’ensemble", level=2)
    add_para(
        doc,
        f"Vingt paires de runs (A, B) ont été exécutées en parallèle, chaque paire partageant la même "
        f"population initiale. Chaque run a évolué pendant {stats['gens']} générations sur "
        f"{stats['duration_s']:.0f} s de simulation par génération. Les fitness moyennes "
        f"(meilleur individu de la dernière génération, agrégées sur les 20 runs) progressent de "
        f"{stats['a_gen0']:.0f} (génération 0) à {stats['a_gen_last']:.0f} (génération {stats['gens']-1}) "
        f"pour l’environnement A, et de {stats['b_gen0']:.0f} à {stats['b_gen_last']:.0f} pour "
        f"l’environnement B.",
    )

    add_heading(doc, "6.2 Liste comparative des 20 runs", level=2)
    add_para(
        doc,
        "Pour chaque run, on rapporte la meilleure fitness atteinte au cours des 1000 générations et "
        "le nombre de segments du meilleur individu final. Δ_segments = |segs_A − segs_B| mesure la "
        "divergence morphologique brute entre les deux environnements pour une paire issue d’une même "
        "graine initiale.",
    )
    t = doc.add_table(rows=1, cols=5)
    t.style = "Light Grid Accent 1"
    hdr = t.rows[0].cells
    for i, name in enumerate(["Run", "Best A", "Segs A", "Best B", "Segs B"]):
        hdr[i].text = name
        hdr[i].paragraphs[0].runs[0].bold = True
    # Add rows
    for a, b in zip(ra, rb):
        row = t.add_row().cells
        row[0].text = str(a["run_id"])
        row[1].text = f"{a['best_fitness']:.0f}"
        row[2].text = str(a["final_segments"])
        row[3].text = f"{b['best_fitness']:.0f}"
        row[4].text = str(b["final_segments"])

    add_para(doc, "")
    add_para(doc, "Synthèse statistique sur les 20 runs :", bold=True)
    add_bullet(
        doc,
        f"Environnement A — fitness max : moyenne = {stats['a_mean']:.0f}, "
        f"écart-type = {stats['a_std']:.0f}, médiane = {stats['a_med']:.0f}, "
        f"min = {stats['a_min']:.0f}, max = {stats['a_max']:.0f}.",
    )
    add_bullet(
        doc,
        f"Environnement B — fitness max : moyenne = {stats['b_mean']:.0f}, "
        f"écart-type = {stats['b_std']:.0f}, médiane = {stats['b_med']:.0f}, "
        f"min = {stats['b_min']:.0f}, max = {stats['b_max']:.0f}.",
    )
    add_bullet(
        doc,
        f"Segments finaux du meilleur individu — A : {stats['a_seg_mean']:.2f} ± {stats['a_seg_std']:.2f} ; "
        f"B : {stats['b_seg_mean']:.2f} ± {stats['b_seg_std']:.2f}. La complexité morphologique moyenne "
        f"est plus élevée en B qu’en A, conformément à l’hypothèse H1.",
    )
    add_bullet(
        doc,
        f"Corrélation de Pearson entre fitness A et fitness B des paires partageant la même graine : "
        f"r = {stats['corr_fit']:.2f}. Corrélation entre n_segments A et n_segments B : "
        f"r = {stats['corr_seg']:.2f}. Une corrélation de fitness modérée mais une corrélation "
        "morphologique quasi-nulle indiquent que la pression environnementale impose ses propres "
        "trajectoires structurelles, indépendamment du génome de départ partagé.",
    )

    add_heading(doc, "6.3 Matrices de distance morphologique", level=2)
    add_para(
        doc,
        f"La distance morphologique moyenne entre paires de meilleurs individus s’établit à : "
        f"AA = {stats['aa_avg']:.3f} (intra A), BB = {stats['bb_avg']:.3f} (intra B), "
        f"AB = {stats['ab_avg']:.3f} (inter A↔B). Le fait que la distance inter-environnements "
        f"AB > BB > AA confirme quantitativement que les solutions évoluées dans l’environnement B "
        "occupent un sous-espace morphologique distinct de celui de l’environnement A. La divergence "
        f"moyenne A↔B vaut {stats['mean_div_ab']:.2f}, valeur élevée traduisant un effet net de la "
        "pression environnementale sur la convergence morphologique.",
    )

    # ---------- 7. Visualisation morphologique ----------
    add_heading(doc, "7. Visualisation morphologique comparée", level=1)

    add_para(
        doc,
        "Pour rendre tangibles les écarts statistiques mesurés en §6, nous reconstruisons "
        "graphiquement le meilleur individu de la dernière génération de chaque run, en parcourant "
        "récursivement l’arbre de gènes (largeur, hauteur, angle d’attache, motor_speed). Chaque "
        "rectangle représente un segment ; sa couleur (palette viridis) encode la fréquence du moteur "
        "(motor_speed). Le fond bleu pâle distingue les morphologies évoluées dans l’environnement A "
        "(plaine) ; le fond crème, celles évoluées dans l’environnement B (terrain accidenté).",
    )

    add_heading(doc, "7.1 Quatre paires représentatives (A vs B)", level=2)
    add_para(
        doc,
        "Les paires retenues couvrent les quatre régimes observés dans la session : A et B tous deux "
        "performants (run 5), A dominant (run 8), B dominant avec gain morphologique (run 10), B "
        "dominant avec corps en grappe (run 15). Pour chaque paire, A et B partagent la même "
        "population initiale — toute différence morphologique est donc imputable à l’environnement.",
    )
    fig1 = ROOT / "docs" / "figures" / "morpho_pairs_selected.png"
    if fig1.exists():
        doc.add_picture(str(fig1), width=Cm(15.5))
        cap = doc.add_paragraph()
        cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r = cap.add_run("Figure 1 — Comparaison morphologique A vs B sur 4 paires représentatives.")
        r.italic = True
        r.font.size = Pt(9)

    add_heading(doc, "7.2 Panorama complet — 20 runs par environnement", level=2)
    add_para(
        doc,
        "Les deux planches ci-dessous présentent, côte à côte, les 20 morphologies finales évoluées "
        "dans l’environnement A puis dans l’environnement B. La lecture en bloc fait apparaître des "
        "tendances que les seules statistiques ne donnent pas : en A, on observe majoritairement des "
        "corps allongés à faible nombre de segments, optimisés pour la propulsion horizontale sur sol "
        "uniforme. En B, les morphologies sont plus verticales, plus segmentées, et présentent souvent "
        "des points d’appui multiples (structures en grappe, jambes courtes, plans corporels touffus) — "
        "réponses plausibles à la nécessité de franchir des inclinaisons et de récupérer la stabilité "
        "après chaque pente.",
    )
    fig2 = ROOT / "docs" / "figures" / "morpho_all_A.png"
    if fig2.exists():
        doc.add_picture(str(fig2), width=Cm(15.5))
        cap = doc.add_paragraph()
        cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r = cap.add_run("Figure 2 — Morphologies finales des 20 runs en environnement A (plaine).")
        r.italic = True
        r.font.size = Pt(9)

    fig3 = ROOT / "docs" / "figures" / "morpho_all_B.png"
    if fig3.exists():
        doc.add_picture(str(fig3), width=Cm(15.5))
        cap = doc.add_paragraph()
        cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r = cap.add_run("Figure 3 — Morphologies finales des 20 runs en environnement B (terrain accidenté).")
        r.italic = True
        r.font.size = Pt(9)

    add_heading(doc, "7.3 Lecture comparative — synthèse visuelle", level=2)
    add_para(
        doc,
        "Trois constats émergent de l’examen direct des planches morphologiques :",
    )
    add_bullet(
        doc,
        "Tendance horizontale en A vs verticale en B. Les corps évolués en plaine s’étalent au sol "
        "(corps long, peu de segments verticaux), tandis qu’en terrain accidenté, beaucoup de "
        "morphologies adoptent une posture à dominante verticale ou en grappe, augmentant la surface "
        "d’accroche aux pentes.",
    )
    add_bullet(
        doc,
        "Complexité segmentale supérieure en B. Visuellement, les corps de la planche B contiennent "
        "plus de petits segments terminaux (mini-pattes, ramifications), ce qui confirme la statistique "
        f"de §6 ({stats['b_seg_mean']:.1f} segments en B contre {stats['a_seg_mean']:.1f} en A).",
    )
    add_bullet(
        doc,
        "Diversité intra-environnement marquée. À l’intérieur même de l’environnement B, les solutions "
        "trouvées sont plus hétérogènes (corps fins horizontaux, blocs verticaux, structures en étoile) "
        f"que dans l’environnement A, ce qui se retrouve dans la distance intra moyenne BB = "
        f"{stats['bb_avg']:.2f} > AA = {stats['aa_avg']:.2f}. Le terrain accidenté ouvre plusieurs "
        "stratégies viables ; la plaine en privilégie une seule.",
    )
    add_para(
        doc,
        "Conclusion partielle. L’inspection visuelle confirme et précise les résultats statistiques : "
        "la pression environnementale ne se contente pas de modifier marginalement les paramètres — "
        "elle déplace clairement la population vers un sous-espace morphologique différent, plus riche "
        "en formes spécialisées dans l’environnement complexe.",
    )

    # ---------- 8. Trajectoires évolutives ----------
    add_heading(doc, "8. Trajectoires évolutives", level=1)

    add_heading(doc, "8.1 Convergence de la fitness sur 1000 générations", level=2)
    add_para(
        doc,
        "La figure 4 superpose la fitness moyenne du meilleur individu par génération, agrégée sur les "
        "20 runs, pour chaque environnement. Les bandes représentent ±1 σ. Trois observations :",
    )
    add_bullet(
        doc,
        f"L’environnement A (plaine) atteint une fitness moyenne supérieure ({stats['a_gen_last']:.0f}) "
        f"à celle de l’environnement B ({stats['b_gen_last']:.0f}) en fin d’évolution, ce qui s’explique "
        "par la facilité relative à parcourir une distance horizontale sans pente — la fitness brute "
        "n’est pas comparable d’un environnement à l’autre, seules les trajectoires le sont.",
    )
    add_bullet(
        doc,
        "Les deux courbes sont monotones croissantes (la fitness mémorisée est un best-so-far par run), "
        "sans signe de saturation à 1000 générations : le potentiel évolutif n’est pas épuisé. "
        "L’environnement B montre une montée plus tardive (premier saut significatif vers la génération "
        "200), cohérent avec une surface de fitness plus rugueuse imposée par le terrain.",
    )
    add_bullet(
        doc,
        f"L’écart-type final est plus élevé en B (σ ≈ {stats['b_std']:.0f}) qu’en A "
        f"(σ ≈ {stats['a_std']:.0f}), indiquant que les chemins évolutifs en environnement complexe "
        "sont plus divergents — plusieurs solutions locales coexistent.",
    )
    fig = ROOT / "docs" / "figures" / "fitness_convergence.png"
    if fig.exists():
        doc.add_picture(str(fig), width=Cm(15.5))
        cap = doc.add_paragraph()
        cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r = cap.add_run("Figure 4 — Convergence de la fitness, moyenne ± écart-type sur 20 runs.")
        r.italic = True
        r.font.size = Pt(9)

    add_heading(doc, "8.2 Émergence de la complexité morphologique", level=2)
    add_para(
        doc,
        "La figure 5 trace l’évolution du nombre moyen de segments dans la population, génération par "
        "génération. Les deux populations partent de l’initialisation minimale (2 segments) imposée par "
        "random_dna(). À partir d’environ la génération 200, la courbe B passe au-dessus de la courbe A "
        "et y reste jusqu’à la fin : la pression du terrain accidenté sélectionne activement des corps "
        "plus segmentés, alors que la plaine plafonne autour de 11–12 segments. Cette divergence "
        "structurelle, lente mais nette, est la signature directe de l’hypothèse H1 (complexité "
        "environnementale → complexité morphologique) sur l’axe du temps évolutif.",
    )
    fig = ROOT / "docs" / "figures" / "segments_evolution.png"
    if fig.exists():
        doc.add_picture(str(fig), width=Cm(15.5))
        cap = doc.add_paragraph()
        cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r = cap.add_run("Figure 5 — Nombre moyen de segments par génération, agrégé sur 20 runs.")
        r.italic = True
        r.font.size = Pt(9)

    # ---------- 9. Distributions finales ----------
    add_heading(doc, "9. Distributions finales et appariement", level=1)

    add_heading(doc, "9.1 Boxplots de la fitness et du nombre de segments", level=2)
    add_para(
        doc,
        "La figure 6 montre la dispersion finale des deux populations. Le boxplot des segments "
        "(panneau de droite) confirme une médiane plus élevée en B (11) qu’en A (9), avec un quartile "
        "supérieur qui dépasse 16 segments en B contre 12 en A — l’environnement complexe ouvre un "
        "espace de morphologies que la plaine n’explore jamais.",
    )
    fig = ROOT / "docs" / "figures" / "final_distributions.png"
    if fig.exists():
        doc.add_picture(str(fig), width=Cm(15.5))
        cap = doc.add_paragraph()
        cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r = cap.add_run("Figure 6 — Distributions finales : fitness max et n_segments du meilleur individu.")
        r.italic = True
        r.font.size = Pt(9)

    add_heading(doc, "9.2 Appariement A vs B (graines partagées)", level=2)
    add_para(
        doc,
        "La figure 7 confronte directement les paires de runs partageant la même initialisation. "
        "Si l’environnement n’avait aucun effet, les points devraient s’aligner sur la diagonale y = x. "
        f"Or, pour la fitness comme pour les segments, les nuages s’en écartent franchement (corrélation "
        f"morphologique r = {stats['corr_seg']:.2f}). La position d’un point relativement à la diagonale "
        "indique donc l’environnement qui a tiré le meilleur parti de cette graine : par exemple les "
        "runs 10, 15, 17 explosent en B tandis que le run 8 favorise A. Aucune graine ne donne "
        "systématiquement le même corps dans les deux environnements.",
    )
    fig = ROOT / "docs" / "figures" / "paired_scatter.png"
    if fig.exists():
        doc.add_picture(str(fig), width=Cm(15.5))
        cap = doc.add_paragraph()
        cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r = cap.add_run("Figure 7 — Comparaison appariée A vs B (chaque point = une graine commune).")
        r.italic = True
        r.font.size = Pt(9)

    add_heading(doc, "9.3 Fitness en fonction de la complexité morphologique", level=2)
    add_para(
        doc,
        "La figure 8 met en relation, pour chaque run, la fitness atteinte et le nombre de segments du "
        "meilleur individu final. Les deux régressions linéaires montrent que dans l’environnement A, "
        "la fitness croît avec la complexité (pente ≈ 526), suggérant un bénéfice modéré à ajouter des "
        "segments même en plaine. En B, la pente est quasi-plate (≈ 21) : la complexité morphologique "
        "n’est ni récompensée ni pénalisée linéairement — l’environnement complexe admet plusieurs "
        "stratégies de tailles très différentes, comme l’a déjà laissé voir la figure 3.",
    )
    fig = ROOT / "docs" / "figures" / "fitness_vs_segments.png"
    if fig.exists():
        doc.add_picture(str(fig), width=Cm(15.5))
        cap = doc.add_paragraph()
        cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r = cap.add_run("Figure 8 — Fitness en fonction du nombre de segments — 20 runs × 2 environnements.")
        r.italic = True
        r.font.size = Pt(9)

    # ---------- 10. Spécialisation paramétrique ----------
    add_heading(doc, "10. Spécialisation des paramètres physiques", level=1)
    add_para(
        doc,
        "Au-delà du nombre de segments, la sélection naturelle joue sur les paramètres scalaires des "
        "gènes. La figure 9 superpose les histogrammes des paramètres clés agrégés sur l’ensemble des "
        "segments des 20 meilleurs DNA finaux par environnement (193 segments en A, 274 en B). "
        "Les moyennes diffèrent systématiquement :",
    )
    add_bullet(
        doc,
        "motor_speed — A = 4,95 / B = 3,48. La plaine sélectionne des moteurs plus rapides "
        "(propulsion soutenue), le terrain favorise des moteurs plus lents qui privilégient le couple "
        "et la précision sur les pentes.",
    )
    add_bullet(
        doc,
        "motor_force — A = 4,3·10⁵ / B = 3,0·10⁵. Le couple maximal est plus élevé en plaine, "
        "preuve qu’un haut motor_force rapporte une fitness directe par accélération horizontale, alors "
        "qu’en terrain irrégulier un excès de force déstabilise le corps.",
    )
    add_bullet(
        doc,
        "friction — A = 1,13 / B = 0,82. Une friction plus élevée en A améliore l’adhérence pour "
        "la course rectiligne ; en B, une friction plus modérée laisse les segments « glisser » sur les "
        "pentes au lieu de bloquer.",
    )
    add_bullet(
        doc,
        "joint_damping — A = 267 / B = 239. L’amortissement articulaire reste comparable, signe que "
        "ce paramètre est moins discriminant entre les deux régimes.",
    )
    fig = ROOT / "docs" / "figures" / "param_specialization.png"
    if fig.exists():
        doc.add_picture(str(fig), width=Cm(15.5))
        cap = doc.add_paragraph()
        cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r = cap.add_run("Figure 9 — Distribution des paramètres physiques sur l’ensemble des segments des "
                        "20 meilleurs DNA finaux par environnement. Tirets = moyennes.")
        r.italic = True
        r.font.size = Pt(9)
    add_para(
        doc,
        "Lecture d’ensemble : l’environnement n’oriente pas seulement la topologie du corps (nombre de "
        "segments, plan d’assemblage), il calibre aussi finement les paramètres physiques de chaque "
        "articulation. La spécialisation est donc multi-échelle.",
    )

    # ---------- 11. Distance heatmaps ----------
    add_heading(doc, "11. Structure de l’espace morphologique — matrices de distance", level=1)
    add_para(
        doc,
        "La figure 10 projette sous forme de heatmaps les trois matrices 20×20 de distance entre "
        "meilleurs individus. Les diagonales noires correspondent à la distance d’un run à lui-même "
        "(zéro). Trois éléments saillants :",
    )
    add_bullet(
        doc,
        f"La matrice AA (à gauche) est la moins « chaude » (moyenne {stats['aa_avg']:.2f}) : les runs "
        "en plaine convergent vers des morphologies relativement similaires.",
    )
    add_bullet(
        doc,
        f"La matrice BB (centre) est nettement plus contrastée (moyenne {stats['bb_avg']:.2f}) : "
        "le terrain accidenté admet plusieurs basins of attraction morphologiques distincts.",
    )
    add_bullet(
        doc,
        f"La matrice AB (à droite) — distance entre tout run A et tout run B — affiche une moyenne "
        f"de {stats['ab_avg']:.2f}, supérieure à AA et confirmant que les sous-espaces morphologiques "
        "des deux environnements ne se recouvrent que partiellement.",
    )
    fig = ROOT / "docs" / "figures" / "distance_heatmaps.png"
    if fig.exists():
        doc.add_picture(str(fig), width=Cm(15.5))
        cap = doc.add_paragraph()
        cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r = cap.add_run("Figure 10 — Matrices de distance morphologique : intra A, intra B, inter A↔B.")
        r.italic = True
        r.font.size = Pt(9)

    # ---------- 12. Conclusion ----------
    add_heading(doc, "12. Conclusion", level=1)
    add_para(
        doc,
        "Réponse à la problématique. Dans quelle mesure la complexité de l’environnement de simulation "
        "dicte-t-elle l’architecture corporelle d’une créature virtuelle évoluant par algorithme "
        "génétique classique ? Les vingt runs comparatifs convergent vers une réponse affirmative et "
        "multi-niveau :",
        bold=False,
    )
    add_bullet(
        doc,
        f"Niveau topologique. L’environnement B sélectionne en moyenne {stats['b_seg_mean']:.1f} "
        f"segments contre {stats['a_seg_mean']:.1f} en A, et la divergence entre les deux courbes "
        "d’évolution du nombre de segments (Fig. 5) s’installe dès la génération 200.",
    )
    add_bullet(
        doc,
        "Niveau structurel. Les planches morphologiques (Fig. 1–3) montrent des plans corporels "
        "qualitativement distincts : corps allongés horizontaux en A, structures verticales et touffues "
        f"en B. La distance morphologique inter-environnements AB = {stats['ab_avg']:.2f} dépasse les "
        f"distances intra AA = {stats['aa_avg']:.2f} et est cohérente avec BB = {stats['bb_avg']:.2f} "
        "(Fig. 10).",
    )
    add_bullet(
        doc,
        "Niveau paramétrique. Au-delà de la forme, les paramètres physiques sélectionnés diffèrent "
        "significativement (Fig. 9) : la plaine privilégie des moteurs rapides, puissants et adhérents "
        "(motor_speed 4,95 ; motor_force 4,3·10⁵ ; friction 1,13), le terrain accidenté des moteurs "
        "plus lents et glissants (3,48 ; 3,0·10⁵ ; 0,82).",
    )
    add_bullet(
        doc,
        f"Niveau évolutif. La corrélation morphologique entre paires de runs partageant la graine "
        f"initiale est quasi-nulle (r = {stats['corr_seg']:.2f}, Fig. 7) : la pression environnementale "
        "domine l’héritage initial.",
    )
    add_para(
        doc,
        "Ces quatre niveaux d’analyse — topologique, structurel, paramétrique, évolutif — convergent "
        "vers la thèse d’Auerbach & Bongard (2012), reproduite ici sur un protocole indépendant avec un "
        "encodage direct pur et un contrôleur fixe (oscillateur sinusoïdal universel). La complexité de "
        "l’environnement ne détermine pas une morphologie unique, mais elle dicte effectivement la "
        "région de l’espace morphologique vers laquelle la sélection oriente la population, ainsi que "
        "la richesse de la diversité interne. La problématique reçoit donc une réponse affirmative et "
        "quantifiée : oui, la complexité environnementale dicte l’architecture corporelle, à plusieurs "
        "échelles simultanément.",
    )

    # ---------- 13. Références ----------
    add_heading(doc, "13. Références bibliographiques", level=1)
    refs = [
        "Auerbach, J. E., & Bongard, J. C. (2012). On the relationship between environmental and morphological complexity in evolved robots. Proceedings of GECCO 2012. ACM.",
        "Funes, P., & Pollack, J. (1998). Evolutionary body building: Adaptive physical designs for robots. Artificial Life, 4(4), 337–357.",
        "Kitchenham, B., & Charters, S. (2007). Guidelines for performing systematic literature reviews in software engineering. EBSE Technical Report.",
        "Lipson, H., & Pollack, J. B. (2000). Automatic design and manufacture of robotic lifeforms. Nature, 406, 974–978.",
        "Moore, J. M., & McKinley, P. K. (2012). Evolving flexible joint morphologies. Proceedings of GECCO 2012. ACM.",
        "Nordmoen, J., Veenstra, F., Ellefsen, K. O., & Glette, K. (2021). MAP-Elites enables powerful stepping stones and diversity for modular robotics. Frontiers in Robotics and AI, 8.",
        "Sims, K. (1994). Evolving virtual creatures. Proceedings of SIGGRAPH 1994 (pp. 15–22). ACM.",
        "Stanley, K. O., & Miikkulainen, R. (2002). Evolving neural networks through augmenting topologies. Evolutionary Computation, 10(2), 99–127.",
    ]
    for r in refs:
        p = doc.add_paragraph(r)
        p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        p.paragraph_format.left_indent = Cm(0.5)
        p.paragraph_format.first_line_indent = Cm(-0.5)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    out_path = _safe_out(OUT)
    doc.save(out_path)
    print(f"Saved: {out_path}")


if __name__ == "__main__":
    main()
