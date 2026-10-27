"""
Écart de parité TASE vs ADR sur les fenêtres communes (minute par minute).
À lancer sur le VPS, depuis ~/election-market-collect :
    .venv/bin/python parity_check.py
    .venv/bin/python parity_check.py --cost-bps 40      # seuil de coûts aller-retour à tester

Parité : prix_ADR_USD  vs  (prix_TASE_agorot / 100) / USDILS * ratio
gap_bps = (ADR / parité_TASE - 1) * 10_000
"""
import argparse
from pathlib import Path
import pandas as pd

DATA = Path("data/intraday/1m")

# Ratio ADR : 1 ADR = N actions TASE. 1:1 pour ces 4 noms -> À VÉRIFIER (site investisseurs).
PAIRS = {"TEVA": ("TEVA.TA", 1.0), "ESLT": ("ESLT.TA", 1.0),
         "NICE": ("NICE.TA", 1.0), "ICL": ("ICL.TA", 1.0)}
# CHKP exclu : pas coté à la TASE.


def load(group, ticker):
    f = DATA / group / f"{ticker}.parquet"
    if not f.exists():
        print(f"  [manquant] {f}")
        return None
    df = pd.read_parquet(f)
    df.index = pd.to_datetime(df.index, utc=True)
    df.columns = [c.lower() if isinstance(c, str) else str(c[0]).lower() for c in df.columns]
    return df


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cost-bps", type=float, default=None,
                    help="Coût aller-retour total en bps (si absent : calculé avec les hypothèses ci-dessous)")
    # HYPOTHÈSES DE COÛTS, à remplacer par tes vrais frais (bps = 0,01 %) :
    ap.add_argument("--tase-half-spread", type=float, default=10)   # demi-spread payé sur la jambe TASE
    ap.add_argument("--adr-half-spread", type=float, default=3)     # demi-spread payé sur la jambe ADR
    ap.add_argument("--commission", type=float, default=10)         # commissions, par jambe et par sens
    ap.add_argument("--fx", type=float, default=10)                 # conversion ILS<->USD
    ap.add_argument("--borrow", type=float, default=5)              # emprunt de titres pour la vente à découvert
    a = ap.parse_args()

    # Aller-retour = ouvrir les 2 jambes + les fermer
    cost = a.cost_bps if a.cost_bps is not None else \
        2 * (a.tase_half_spread + a.adr_half_spread + 2 * a.commission) + a.fx + a.borrow
    print(f"Seuil de coûts aller-retour testé : {cost:.0f} bps\n")

    fx = load("fx", "ILS=X")
    if fx is None:
        return
    rows = []
    for adr_t, (tase_t, ratio) in PAIRS.items():
        adr, tase = load("adr", adr_t), load("tase", tase_t)
        if adr is None or tase is None:
            continue
        # Minutes communes avec du volume des deux côtés (évite les prix figés)
        df = pd.concat({"adr": adr["close"], "adr_v": adr["volume"],
                        "tase": tase["close"], "tase_v": tase["volume"],
                        "fx": fx["close"]}, axis=1).dropna()
        df = df[(df.adr_v > 0) & (df.tase_v > 0)]
        if df.empty:
            print(f"{adr_t}: aucune minute commune avec volume")
            continue
        parity = (df.tase / 100) / df.fx * ratio
        df["gap_bps"] = (df.adr / parity - 1) * 1e4
        df["pair"] = adr_t
        rows.append(df)

        g = df["gap_bps"]
        print(f"=== {adr_t} vs {tase_t} : {len(df)} minutes communes, {df.index.normalize().nunique()} séances")
        for day, gd in g.groupby(g.index.date):
            print(f"  {day}  médiane {gd.median():+6.1f} bps | |gap| médian {gd.abs().median():5.1f} "
                  f"| p95 {gd.abs().quantile(.95):5.1f} | max {gd.abs().max():6.1f} "
                  f"| min > coûts : {(gd.abs() > cost).mean():5.1%}")
        # Écart "mean-reverting" exploitable = écart AUTOUR du biais habituel (frictions structurelles)
        dev = (g - g.median()).abs()
        print(f"  TOTAL |gap| médian {g.abs().median():.1f} bps, p95 {g.abs().quantile(.95):.1f} | "
              f"écart au biais médian : médian {dev.median():.1f}, p95 {dev.quantile(.95):.1f} | "
              f"minutes où écart au biais > coûts : {(dev > cost).mean():.1%}\n")

    if rows:
        out = Path("parity_gaps.parquet")
        pd.concat(rows).to_parquet(out)
        print(f"Détail minute par minute -> {out}")


if __name__ == "__main__":
    main()
