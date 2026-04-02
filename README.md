# MorphoEvo — Spécifications du projet

> Matthis Behra — EvoMorpho  
> Dernière mise à jour : 2026-04-01

---

## Table des matières

1. [Vue d'ensemble](#1-vue-densemble)
2. [Architecture des fichiers](#2-architecture-des-fichiers)
3. [Dépendances](#3-dépendances)
4. [Représentation génétique (ADN)](#4-représentation-génétique-adn)
5. [Physique des créatures](#5-physique-des-créatures)
6. [Comportement — l'oscillateur sinusoïdal](#6-comportement--loscillateur-sinusoïdal)
7. [Algorithme génétique](#7-algorithme-génétique)
8. [Environnements](#8-environnements)
9. [Fonctions de fitness](#9-fonctions-de-fitness)
10. [Interface utilisateur](#10-interface-utilisateur)
11. [Export des données (CSV)](#11-export-des-données-csv)
12. [Invariants — à ne jamais violer](#12-invariants--à-ne-jamais-violer)
13. [Fonctionnalités planifiées](#13-fonctionnalités-planifiées)

---

## 1. Vue d'ensemble

MorphoEvo est une simulation d'**évolution morphologique** basée sur un algorithme génétique.  
Des créatures articulées évoluent dans un environnement physique 2D ; seule leur morphologie (forme, taille des membres, paramètres musculaires) évolue — aucun réseau de neurones, aucun apprentissage par renforcement.

Le moteur de locomotion est un **oscillateur sinusoïdal universel** : chaque muscle est piloté par `ω = motor_speed × sin(t×10 + motor_phase)`. Les créatures se distinguent uniquement par la structure de leur arbre corporel et les valeurs de leurs gènes.

**Objectif de recherche :** étudier comment des pressions sélectives différentes (terrain plat vs obstacles dynamiques sur pente) produisent des morphologies divergentes à partir d'une population initiale identique.

---

## 2. Architecture des fichiers

```
MorphoEvo_Simulation/
├── src/
│   ├── main.py                    # Point d'entrée unique — boucle principale
│   ├── entities/
│   │   └── creature.py            # ADN, opérateurs génétiques, classe Creature
│   ├── physics/
│   │   ├── environment.py         # Espace pymunk, sol, obstacles
│   │   └── renderer.py            # Utilitaire de rendu pymunk (debug/sol)
│   ├── evolution/
│   │   ├── __init__.py
│   │   └── genetics.py            # Sélection, croisement, niching
│   ├── ui/
│   │   ├── camera.py              # Caméra scrolling + transformations monde→écran
│   │   ├── config_screen.py       # Écran de configuration pré-simulation
│   │   └── summary_screen.py      # Bannière de showcase entre générations
│   └── utils/
│       ├── __init__.py
│       └── csv_export.py          # Écriture des statistiques par génération
├── docs/
│   ├── specifications.md          # Ce fichier
│   ├── article_recherche_BEHRA.docx
│   └── RSL_Evolution_Morphologique_BEHRA_v3.docx
├── requirements.txt
├── CLAUDE.md
└── evolution_data.csv             # Créé au lancement, à la racine du projet
```

---

## 3. Dépendances

| Bibliothèque | Version | Rôle |
|---|---|---|
| `pygame` | 2.6.1 | Fenêtre, rendu 2D, boucle d'événements |
| `pymunk` | 7.2.0 | Physique rigide 2D (wrapper Chipmunk) |
| `numpy` | 2.3.5 | Calculs numériques (disponible, non utilisé directement) |
| `matplotlib` | 3.10.7 | Visualisation post-simulation (disponible) |

Installer avec `pip install -r requirements.txt` (venv activé).

---

## 4. Représentation génétique (ADN)

### 4.1 Structure

L'ADN est un **arbre de dicts imbriqués**. Chaque nœud représente un segment physique.

```
root (torso)
└── child_1  (membre 1)
```

La racine est le torse ; ses enfants sont les membres ; leurs enfants sont les sous-membres (etc.). La morphologie initiale est minimale (2 segments) ; la complexité émerge par mutations additives au fil des générations. Cap absolu : **12 segments** par créature.

Les arbres sont **asymétriques** : chaque nœud a ses propres paramètres indépendants, aucun mirroring n'est appliqué.

### 4.2 Gènes par nœud (`random_segment_gene`)

| Gène | Type | Plage initiale | Description |
|---|---|---|---|
| `width` | float | [20, 55] | Longueur du segment (axe local X) |
| `height` | float | [6, 18] | Épaisseur du segment (axe local Y) |
| `attach_angle` | float | [−π/2, π/2] | Angle d'attache par rapport au parent |
| `rot_min` | float | [−1.2, −0.2] | Limite basse de rotation de l'articulation |
| `rot_max` | float | [0.2, 1.2] | Limite haute de rotation |
| `motor_force` | float | [50 000, 500 000] | Force max du moteur (N·m) |
| `motor_speed` | float | [1.5, 8.0] | Amplitude angulaire du moteur (rad/s) |
| `motor_phase` | float | [0, 2π] | Déphasage du moteur |
| `friction` | float | [0.3, 1.8] | Friction de surface du segment |
| `joint_damping` | float | [50, 500] | Amortissement du joint (Ns/rad) |
| `children` | list | [] | Sous-nœuds (membres enfants) |

> Le nœud racine a `attach_angle = 0`, `width ∈ [35, 60]`, `height ∈ [12, 22]`.

### 4.3 Mutation paramétrique (`mutate_dna`)

- **Scalaires** : chaque gène mute avec probabilité `mutation_rate=0.15` via `δ = valeur × 0.25 × U(−1, 1)`.
- Appliqué récursivement sur tout l'arbre.

### 4.4 Mutation structurelle (`mutate_structure`)

Appliquée **une fois par créature par génération** (pas récursivement) :
- **Ajout de segment** (probabilité 12%) : un nœud aléatoire de l'arbre reçoit un nouvel enfant. Bloqué si le cap de 12 segments est atteint.
- **Retrait de segment** (probabilité 5%) : une feuille aléatoire (non-racine) est supprimée.

### 4.5 Croisement (`crossover_dna`)

Croisement uniforme nœud-par-nœud :
- Chaque gène scalaire est choisi chez le parent A ou B à 50/50.
- Les enfants en surplus du parent le plus long sont inclus avec probabilité 50%.

---

## 5. Physique des créatures

### 5.1 Construction (`Creature._build_node`)

Chaque nœud de l'ADN produit :
- Un `pymunk.Body` avec masse `m = max(0.1, width × height × 0.002)`.
- Un `pymunk.Poly.create_box` de dimensions `(width, height)`.
- Si le nœud a un parent :
  - `PivotJoint` — pivot à l'extrémité du segment parent.
  - `SimpleMotor` — moteur piloté par l'oscillateur.
  - `RotaryLimitJoint` — limite angulaire (ROM différenciée par profondeur, voir §5.3).
  - `DampedRotarySpring(stiffness=0, damping=joint_damping)` — amortissement pur.

### 5.2 Masse variable

```
mass = width × height × 0.002
```

Les segments volumineux sont plus lourds → locomotion plus difficile pour les créatures massives → pression vers des morphologies efficientes.

### 5.3 Articulations différenciées par profondeur

| Profondeur | Analogie | ROM |
|---|---|---|
| 1 | Hanche | `rot_min × 1.3 … rot_max × 1.3` (amplitude élargie) |
| 2 | Genou | `rot_min … rot_max` (valeurs ADN brutes) |
| ≥ 3 | Cheville / extrémité | `max(rot_min, −0.4) … min(rot_max, 0.4)` (restreinte) |

### 5.4 Amortissement des joints

`DampedRotarySpring` avec `stiffness=0` et `damping = gene["joint_damping"]`.  
Torque appliqué : `τ = −damping × vitesse_angulaire_relative`  
→ simule la résistance musculaire / la fatigue sans rappel vers un angle neutre.

### 5.5 Isolation des collisions (ShapeFilter)

Chaque créature reçoit un bit unique :

```python
_category = 1 << ((group_counter − 1) % 30)
mask = ALL_MASKS ^ ALL_CREATURE_BITS   # collide avec le sol, pas avec les autres créatures
```

Les segments d'une même créature ne se collisionnent pas entre eux (même `group`). Les créatures ne se collisionnent pas entre elles. Seul le contact sol ↔ segment est actif.

### 5.6 Système de coordonnées

Pymunk : Y vers le haut. Pygame : Y vers le bas.  
Conversion exclusive via `Camera.world_to_screen` :

```
screen_x = world_x − camera.x_offset
screen_y = (screen_h − ground_margin + ground_y_world) − world_y
```

Ne jamais inverser Y en dehors de cette méthode.

---

## 6. Comportement — l'oscillateur sinusoïdal

```python
rate = motor_speed × sin(time × 10 + motor_phase)
motor.rate = direction_bias × rate
```

- `time` : horloge globale de la simulation (secondes écoulées).
- `direction_bias` : `−1` si le torse recule (vx < −5 px/s), `+1` sinon.
- Toutes les créatures partagent la même formule ; seuls les paramètres génétiques varient.

### Énergie métabolique

À chaque appel de `act(time, dt)` :

```python
_energy_spent += |motor.rate| × motor_force × dt
```

L'énergie est soustraite du fitness (voir §9) pour pénaliser les créatures « coûteuses ».

---

## 7. Algorithme génétique

### 7.1 Cycle de génération

```
10 s de simulation
→ 3 s de showcase (meilleures créatures affichées)
→ Calcul du fitness + export CSV
→ breed_next_generation() pour les deux environnements
→ Suppression des créatures + recréation
→ Génération N+1
```

### 7.2 Sélection — tournoi k=3 avec fitness sharing

1. **Fitness sharing (niching)** : pénalise les individus morphologiquement trop proches.

   ```
   distance(i, j) = |count_segments(dna_i) − count_segments(dna_j)|
   niche_count_i  = Σ_j max(0, 1 − dist(i,j) / σ_share)   [σ_share = 3]
   shared_fitness_i = fitness_i / niche_count_i
   ```

2. **Tournoi** : 3 individus tirés au hasard → le meilleur (par shared_fitness) est sélectionné comme parent.

### 7.3 Élitisme

Les 2 meilleurs individus (par fitness brut) sont copiés intacts dans la génération suivante.

### 7.4 Croisement → Mutation paramétrique → Mutation structurelle

```
parent_A × parent_B → crossover_dna() → mutate_dna() → mutate_structure()
```

- `mutate_dna()` mute les paramètres scalaires de chaque nœud (récursif).
- `mutate_structure()` ajoute ou retire un segment (une fois par créature, cap 12 segments).

---

## 8. Environnements

### 8.1 Env A — Plaine à friction variable

- Sol plat `y = GROUND_Y = 5`.
- Zones de friction alternées toutes les **800 unités** :

  | Zone | Friction | Couleur |
  |---|---|---|
  | Herbe | 1.0 | Vert `(34, 139, 34)` |
  | Glace | 0.2 | Bleu clair `(180, 220, 240)` |
  | Sable | 2.2 | Beige `(210, 170, 110)` |

- Implémentation : `env_a.add_friction_zones(total_x, ground_y, zone_width=800)` retourne `[(shape, color), …]`.

### 8.2 Env B — Terrain procédural

Terrain composé de segments inclinés enchaînés, **régénéré à chaque génération** pour éviter le surapprentissage.

- **Zone plate initiale** : les 400 premières unités sont plates (zone de spawn).
- **Segments inclinés** : longueur 200 unités, angle aléatoire ∈ [−25°, +25°]. Les segments s'enchaînent bout à bout (continuité du profil).
- **Clamp Y** : l'altitude reste dans `[GROUND_Y − 40, GROUND_Y + 80]` pour garder le terrain praticable.
- **Zones de sol mou** (~25 % des segments hors zone plate) :
  - Friction élevée : `U(1.5, 2.0)` vs 0.7 standard.
  - Restitution nulle : 0.0 vs 0.3 standard.
  - Couleur distincte : vert-brun `(70, 100, 60)` vs brun standard `(100, 70, 30)`.
- Implémentation : `env_b.generate_terrain(total_x, ground_y)` retourne `[(shape, color), …]` pour le rendu.
- Données complètes dans `env_b.terrain_zones` : `[(shape, color, x_start, x_end, angle_rad), …]` pour le calcul de fitness.

### 8.3 Paramètres communs

| Constante | Valeur | Description |
|---|---|---|
| `GRAVITY` | (0, −900) | Gravité (m/s² × facteur échelle) |
| `GROUND_Y` | 5 | Ordonnée du sol (monde Pymunk) |
| `SPAWN_X` | 300 | Position initiale X des créatures |
| `SPAWN_Y` | GROUND_Y + 200 | Position initiale Y (chute libre jusqu'au sol) |
| `FPS` | 60 | Images par seconde |
| `TIME_STEP` | 1/60 | Pas de simulation physique |
| `gen_duration` | 5–60 s (slider, défaut 15) | Durée de chaque génération |
| `SHOWCASE_DURATION` | 3 s | Durée d'affichage des gagnants |

---

## 9. Fonctions de fitness

### 9.1 Env A — Distance nette

```
fitness_A = (x_torse − SPAWN_X) − ENERGY_PENALTY × energy_spent − 0.5 × n_segments
```

`ENERGY_PENALTY = 1e-6` (ajustable dans `creature.py`).  
La pénalité de complexité `−0.5 × n_segments` décourage le bloat (accumulation de segments inutiles).

### 9.2 Env B — Score composite

```
fitness_B = 1.0 × fitness_A    (inclut déjà la pénalité de complexité)
           + 0.3 × trunk_stability
           + 0.5 × terrain_bonus
```

- `trunk_stability = 1 / (1 + std(angle_torse))` — score dans (0, 1], 1 = torse parfaitement stable.
- `terrain_bonus = Σ covered_length × |sin(angle)|` — récompense la progression sur terrain incliné. Les pentes raides valent plus que les segments plats.
- La pénalité de complexité est appliquée via `fitness_A`.

---

## 10. Interface utilisateur

### 10.1 Écran de configuration (`ConfigScreen`)

Affiché avant la simulation. Permet de régler :
- **Durée de génération (s)** : slider 5–60, défaut 15.
- **Taille de population** : slider 1–30, défaut 5.

Toutes les créatures démarrent avec 2 segments (fixe). Bouton « LAUNCH SIMULATION » démarre la simulation.

### 10.2 Fenêtre principale

Résolution fixe : **1080 × 720 px**.  
Split-screen vertical :
- **Moitié haute** : Env A (fond bleu clair).
- **Moitié basse** : Env B (fond jaune clair).
- Séparateur horizontal noir (3 px) au centre.

HUD par environnement (coin supérieur gauche) :
- Label de l'environnement.
- Distance du meilleur individu.
- Numéro de génération ou `SHOWCASING`.

Label `* BEST` flottant au-dessus du leader.

### 10.3 Bannière de showcase (`draw_summary_overlay`)

Affichée pendant les 3 s de showcase, centrée sur la ligne de séparation :
- Numéro de génération.
- Meilleur fitness Env A (px).
- Meilleur fitness Env B (score composite).
- Compte à rebours avant la prochaine génération.

### 10.4 Caméra (`Camera`)

Scrolling horizontal uniquement. Lissage : `x_offset += (target − x_offset) × 0.08`.  
La caméra suit le leader de chaque environnement indépendamment.

---

## 11. Export des données (CSV)

Fichier : `evolution_data.csv` à la racine du projet (relatif au répertoire de lancement).  
Une ligne est ajoutée à la fin de chaque génération (dans la phase SHOWCASE).

| Colonne | Description |
|---|---|
| `generation` | Numéro de génération |
| `best_fitness_a` | Meilleur fitness brut Env A |
| `avg_fitness_a` | Fitness moyen Env A |
| `best_fitness_b` | Meilleur fitness brut Env B |
| `avg_fitness_b` | Fitness moyen Env B |
| `diversity_a` | Écart-type du nombre de segments (Env A) |
| `diversity_b` | Écart-type du nombre de segments (Env B) |
| `avg_complexity_a` | Nombre moyen de segments par créature (Env A) |
| `avg_complexity_b` | Nombre moyen de segments par créature (Env B) |

---

## 12. Invariants — à ne jamais violer

| # | Règle | Raison |
|---|---|---|
| 1 | **Pas de neuro-évolution.** Aucun réseau de neurones, aucun NEAT, aucun apprentissage. | Le projet étudie l'évolution *morphologique* pure. |
| 2 | **ShapeFilter unique par créature.** Chaque `Creature` alloue son propre bit `_category` ; le mask exclut tous les bits créatures. | Sans cela les créatures se percuteraient mutuellement. |
| 3 | **La formule de l'oscillateur est universelle.** `motor_speed × sin(t×10 + motor_phase)` — seuls les paramètres génétiques varient, jamais la formule. | Garantit que les différences de comportement viennent de la morphologie, pas d'un comportement appris. |
| 4 | **`src/main.py` reste à ce chemin.** | Point d'entrée fixe. |
| 5 | **Ne jamais modifier `venv/` ni `.remember/`.** | Environnement virtuel et mémoire de session. |

---

## 13. Fonctionnalités planifiées

| Fonctionnalité | État | Notes |
|---|---|---|
| Zones de friction Env A | ✅ Implémenté | Herbe / glace / sable en alternance |
| Terrain procédural Env B | ✅ Implémenté | Segments inclinés [−25°, +25°] + zones molles, régénéré chaque génération |
| Masse variable par segment | ✅ Implémenté | `mass = w × h × 0.002` |
| Amortissement des joints | ✅ Implémenté | `DampedRotarySpring(stiffness=0)` |
| Énergie limitée / coût métabolique | ✅ Implémenté | Pénalité dans `get_fitness` |
| Morphologie asymétrique | ✅ Implémenté | Pas de mirroring, chaque branche est indépendante |
| Articulations différenciées | ✅ Implémenté | Hanche / genou / cheville par profondeur |
| Mutation structurelle additive | ✅ Implémenté | `mutate_structure()` — ajout 12%, retrait 5%, cap 12 segments |
| Pénalité de complexité | ✅ Implémenté | `−0.5 × n_segments` dans les deux environnements |
| Morphologie initiale minimale | ✅ Implémenté | 2 segments fixes au départ, complexité émergente |
| Niching / spéciation | ✅ Implémenté | Fitness sharing avec σ = 3 segments |
| Écran de configuration | ✅ Implémenté | Sliders durée de génération + population |
| Split-screen Env A / Env B | ✅ Implémenté | Demi-écran par environnement |
| Export CSV par génération | ✅ Implémenté | 9 colonnes de métriques |
| Showcase inter-générations | ✅ Implémenté | Bannière 3 s + caméra sur le leader |
