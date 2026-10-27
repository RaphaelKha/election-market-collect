# Marchés et élections israéliennes (Knesset, 27 octobre 2026)

Ce dépôt contient les programmes qui me servent à **observer les marchés financiers pendant les élections législatives israéliennes du 27 octobre 2026**. L'objectif est double :

1. **Mesurer la réaction des marchés à l'élection.** Je veux voir comment le shekel, la bourse de Tel-Aviv (TASE), les sociétés israéliennes cotées à New York et les marchés de prédiction réagissent à l'arrivée des résultats.
2. **Suivre l'écart de prix entre Tel-Aviv et New York.** Plusieurs sociétés israéliennes sont cotées sur les deux places. En théorie, une fois converti en dollars, leur prix devrait être le même. Je mesure minute par minute de combien il s'en écarte et combien de temps dure l'écart, pour savoir si un arbitrage serait possible une fois les frais payés.

Il s'agit d'un **projet d'observation et de recherche personnelle**. Aucun ordre de bourse n'est passé par ce code, et rien ici ne constitue un conseil en investissement.

> Dernière mise à jour du README : 27/10/2026.

---

## Pourquoi cette période

- Le jour du scrutin, le **27/10/2026**, la bourse de Tel-Aviv est **fermée** (jour férié). Les marchés américains, eux, sont ouverts.
- Les **sondages de sortie des urnes** tombent à 22:00, heure d'Israël, soit **20:00 UTC**. C'est **exactement l'heure de clôture de Wall Street** (16:00 à New York). La première réaction se lit donc sur les titres israéliens cotés aux États-Unis, dans les échanges après la clôture, avant que Tel-Aviv rouvre.
- Une bonne partie de ces données n'est **plus téléchargeable après coup**. Yahoo ne garde les cours à la minute que quelques semaines et ne conserve aucun historique des options. Il faut donc les enregistrer au fil de l'eau.

---

## Volet 1 : collecte autour de l'élection (26 au 31/10/2026)

| Catégorie | Ce qui est suivi | Fréquence |
|---|---|---|
| Change | USD/ILS, EUR/ILS, indice dollar (DXY) | barres de 1 minute, toutes les heures |
| Bourse de Tel-Aviv | indices TA-35 et TA-125 ; banques Leumi, Hapoalim, Discount, Mizrahi-Tefahot ; Teva, Elbit Systems, NICE, ICL | 1 minute |
| Titres israéliens à New York | TEVA, ESLT, CHKP, NICE, ICL, et l'ETF EIS (iShares MSCI Israel), y compris avant et après la séance | 1 minute |
| Obligations d'État israéliennes | indices Tel-Gov (ensemble, 0-2 ans, 2-5 ans, 5-10 ans, indexées sur l'inflation) | 1 minute |
| Volatilité | VTA35 (volatilité du TA-35), VIX9D, GVZ (or), OVX (pétrole) | 1 minute |
| Repères | S&P 500, Nasdaq, VIX, bitcoin, or, pétrole WTI | 1 minute |
| Options | chaînes complètes (calls et puts, échéances jusqu'au 31/12/2026) sur TEVA, CHKP, ESLT, NICE, ICL | une photo par heure |
| Polymarket | 12 marchés de prédiction sur l'élection (futur Premier ministre, parti en tête, nombre de sièges, blocs, coalition…), soit 189 questions | prix à la minute |
| Sondages | pages Wikipedia des sondages et de l'élection, avec une copie à chaque nouvelle révision | toutes les heures |

**Calendrier automatique (heures UTC)**
- Toutes les heures : cours à la minute (:05), options (:20), Polymarket (:35), sondages (:50).
- Soir de l'élection (27/10) : une photo des options à 19:50, juste avant les sondages de sortie, puis un passage complet à 20:15.
- 30/10 à 22:00 : photo finale de l'historique plus long (barres de 5 minutes, d'une heure et quotidiennes).
- Après le 31/10, ces tâches s'arrêtent d'elles-mêmes.

`collect_history.py` récupère aussi l'historique quotidien autour des **élections précédentes**, pour comparer les réactions d'un scrutin à l'autre.

---

## Volet 2 : écart de prix Tel-Aviv / New York (`parity_track.py`)

### Le principe

Une action Teva achetée à Tel-Aviv et une action Teva achetée à New York sont le même titre. Converti en dollars, leur prix devrait donc être identique. Pour chaque minute où **les deux places ont réellement échangé le titre** :

```
prix théorique en $ = (prix à Tel-Aviv en agorot / 100) / taux USD/ILS × ratio
écart (en points de base) = (prix à New York / prix théorique − 1) × 10 000
```

Un point de base (bp) vaut 0,01 %.

Un petit écart permanent est normal (frais, fiscalité, sens des flux). Ce qui compte, c'est **la déviation par rapport à l'écart habituel** : l'écart de la minute, moins sa médiane sur les 300 minutes communes précédentes.

Un **épisode** est une suite de minutes consécutives où cette déviation dépasse un seuil, toujours du même côté. Je teste trois seuils (20, 40 et 60 bp), qui représentent différents niveaux de frais aller-retour. Seuls les épisodes d'au moins **3 minutes** sont retenus, car ce sont les seuls qui laissent le temps de passer les deux ordres.

### Les paires suivies

| New York | Tel-Aviv | Ratio |
|---|---|---|
| TEVA | TEVA.TA | 1 : 1 (actions ordinaires sur les deux places depuis le 14/09/2026) |
| NICE | NICE.TA | 1 : 1 (à revérifier sur le dernier rapport annuel 20-F) |
| ESLT | ESLT.TA | 1 : 1 (à vérifier) |
| ICL | ICL.TA | 1 : 1 (à vérifier) |

Check Point (CHKP) n'est pas coté à Tel-Aviv, il est donc exclu de ce volet.

### La fenêtre commune

Les deux bourses ne sont ouvertes en même temps que peu de temps chaque jour :
- environ **1 heure** (13:30–14:30 UTC) jusqu'au 23/10 ;
- environ **2 heures** (13:30–15:30 UTC) depuis le passage à l'heure d'hiver en Israël, le 25/10 ;
- de nouveau environ 1 heure à partir du 1er/11, quand les États-Unis passeront à l'heure d'hiver.

Le vendredi, la séance de Tel-Aviv se termine avant l'ouverture de New York, donc il n'y a pas de fenêtre commune.

### Premiers résultats (13 séances communes, du 5 au 26/10/2026)

| Paire | Minutes communes | Écart habituel (médiane) | Déviation typique haute (p95) | Minutes au-delà de 40 bp | Épisodes ≥ 3 min au-delà de 40 bp |
|---|---|---|---|---|---|
| TEVA | 652 | −5,3 bp | 17,0 bp | 0,2 % | 0 |
| ESLT | 359 | −12,8 bp | 23,3 bp | 2,5 % | 0 |
| NICE | 440 | −10,7 bp | 30,3 bp | 2,7 % | 0 |
| ICL | 467 | −15,0 bp | 27,3 bp | 0,9 % | 1 |

Lecture : l'écart est négatif pour les quatre titres, c'est-à-dire que le titre est un peu moins cher à New York qu'à Tel-Aviv. Au-delà de 40 bp de frais, un écart qui dure au moins 3 minutes ne s'est produit qu'une seule fois en 13 séances. **À ce stade, l'arbitrage ne paraît pas exploitable**, mais l'échantillon est court, et la période de l'élection est justement celle où l'écart a le plus de chances de s'ouvrir.

Le suivi continue **chaque jour de semaine à 21:30 UTC**, après la clôture américaine, et **au-delà du 31/10**. Les résultats vont dans `data/parity/daily.csv` (une ligne par séance et par paire) et dans `data/parity/gaps/<paire>.parquet` (le détail minute par minute).

### Limites

- Les écarts sont calculés sur le **dernier prix échangé** de chaque minute, pas sur les meilleures offres d'achat et de vente. Une partie des écarts d'une minute vient simplement du rebond entre acheteurs et vendeurs. Les chiffres ci-dessus sont donc une **borne haute**.
- Le taux de change utilisé est celui de Yahoo (USD/ILS), qui n'est pas forcément un taux exécutable.
- Plusieurs ratios restent à confirmer (voir le tableau des paires).
- Les données Yahoo Finance ne sont pas officielles et peuvent avoir des trous.

---

## Organisation du dépôt

| Fichier | Rôle |
|---|---|
| `config.yaml` | liste des titres, marchés Polymarket, pages Wikipedia, réglages de l'écart de prix |
| `collect_intraday.py` | cours à la minute (Yahoo garde environ 7 jours) |
| `collect_options.py` | photos horaires des chaînes d'options |
| `collect_polymarket.py` | historiques de prix Polymarket (API publique, sans clé) |
| `collect_polls.py` | copies des pages Wikipedia de sondages et de l'élection |
| `collect_snapshots.py` | historiques plus longs (5 minutes, 1 heure, quotidien) |
| `collect_history.py` | cours quotidiens autour des élections passées |
| `parity_track.py` | suivi quotidien de l'écart Tel-Aviv / New York |
| `parity_check.py` | première version, ponctuelle, de l'analyse d'écart |
| `status.py` | bilan de santé : dernier point reçu, jours manquants, derniers lancements |
| `common.py` | fonctions partagées (configuration, journaux, téléchargements avec relance, fusion sans doublons) |

Les **données** (`data/`) et les **journaux** (`logs/`) ne sont pas dans le dépôt. Elles restent sur le serveur de collecte et seront archivées à part.

---

## Installation et utilisation

Testé avec Python 3.12.

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

.venv/bin/python status.py                    # état de la collecte
.venv/bin/python parity_track.py              # écart Tel-Aviv / New York (télécharge les 5 derniers jours)
.venv/bin/python parity_track.py --no-fetch   # recalcule à partir des données déjà présentes
```

Les tâches automatiques sont programmées avec `cron` sur un serveur Linux en heure UTC. Les collecteurs lancés avec `--cron` ne font plus rien après la date `collect_until` de `config.yaml`.

---

## Prochaines étapes

- Analyser la réaction du shekel, de Tel-Aviv et des titres cotés à New York autour de 20:00 UTC le 27/10.
- Comparer Polymarket et les marchés : qui a anticipé le résultat en premier ?
- Comparer la volatilité implicite des options avant et après le scrutin.
- Trouver une source de taux d'emprunt d'État israéliens (Banque d'Israël / TASE), absents de Yahoo Finance.
- Confirmer les ratios des paires ESLT, ICL et NICE.
