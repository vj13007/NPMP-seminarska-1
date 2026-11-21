from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import curve_fit

DATOTEKE = {"simulator": "rezultati_zvestoba.csv", "procesor": "rezultati_procesor.csv"}
IZHOD = "analiza.csv"
OSNOVNA = "i"
BOOTSTRAP = 2000
GLAVA = ["okolje", "oblika", "konfiguracija", "tock", "a", "n0", "n_max", "n_max_napaka",
         "n_max_spodnja", "n_max_zgornja", "ekstrapolirano", "n_gme", "p", "p_napaka", "cas_qpu",
         "n_max_razlika", "cas_razlika", "pridobitev_na_sekundo"]


# branje rezultatov
###############################################################################

def nalozi_rezultate(datoteke: dict[str, str]) -> pd.DataFrame:
    """Zdruzi rezultate vec okolij v eno tabelo; manjkajoce stolpce dopolni s privzetimi."""
    privzeto = {"konfiguracija": OSNOVNA, "F_napaka": np.nan, "cas_qpu": np.nan,
                "C": np.nan, "C_napaka": np.nan}
    deli = []
    for okolje, pot in datoteke.items():
        if not Path(pot).exists():
            continue
        df = pd.read_csv(pot)
        df["okolje"] = okolje
        for stolpec, vrednost in privzeto.items():
            if stolpec not in df:
                df[stolpec] = vrednost
        deli.append(df)
    if not deli:
        raise FileNotFoundError(f"nobena od datotek ne obstaja: {list(datoteke.values())}")
    return pd.concat(deli, ignore_index=True)


# prileganje in prag
###############################################################################

def model(n: np.ndarray, a: float, n0: float) -> np.ndarray:
    """Eksponentni upad zvestobe: F(n) = a exp(-n / n0)."""
    return a * np.exp(-n / n0)


def zacetni_priblizek(n: np.ndarray, f: np.ndarray) -> tuple[float, float]:
    """Zacetna parametra iz premice skozi ln F; pri narascajocih podatkih dolg n0."""
    veljavni = f > 0
    naklon, odsek = np.polyfit(n[veljavni], np.log(f[veljavni]), 1)
    n0 = -1 / naklon if naklon < 0 else 1e4
    return float(np.clip(np.exp(odsek), 0.01, 2.0)), float(np.clip(n0, 1e-3, 1e6))


def prilagodi(n: np.ndarray, f: np.ndarray, sigma: np.ndarray | None = None,
              zacetek: tuple[float, float] | None = None) -> tuple[np.ndarray, np.ndarray]:
    """Utezeno prileganje modela; brez napak navadni najmanjsi kvadrati. Vrne parametra in kovarianco."""
    zacetek = zacetek or zacetni_priblizek(n, f)
    return curve_fit(model, n, f, p0=zacetek, sigma=sigma, absolute_sigma=sigma is not None,
                     bounds=([0.0, 1e-3], [2.0, 1e6]), maxfev=10000)


def prag(a: float, n0: float) -> float:
    """Presecisce prilagojene krivulje z 0,5: n_max = n0 ln(2a); nan, ce krivulja 0,5 ne doseze."""
    return float(n0 * np.log(2 * a)) if a > 0.5 else float("nan")


def bootstrap_praga(n: np.ndarray, f: np.ndarray, sigma: np.ndarray, zacetek: tuple[float, float],
                    ponovitev: int = BOOTSTRAP, seme: int = 0) -> tuple[float, float, float]:
    """Napaka praga in 16. ter 84. percentil iz parametricnega bootstrapa tock z njihovimi napakami."""
    rng = np.random.default_rng(seme)
    pragi = []
    for _ in range(ponovitev):
        try:
            koef, _ = prilagodi(n, rng.normal(f, sigma), sigma, zacetek)
            pragi.append(prag(*koef))
        except RuntimeError:
            pragi.append(np.nan)
    pragi = np.array(pragi)
    return (float(np.nanstd(pragi, ddof=1)), float(np.nanpercentile(pragi, 16)),
            float(np.nanpercentile(pragi, 84)))


def izmerjeni_prag(n: np.ndarray, f: np.ndarray, sigma: np.ndarray) -> float:
    """Najvecji izmerjeni n, pri katerem velja F - 2 sigma > 0,5; nan, ce ga ni."""
    gme = n[f - 2 * sigma > 0.5]
    return float(gme.max()) if gme.size else float("nan")


def model_koherence(n: np.ndarray, c0: float, p: float) -> np.ndarray:
    """Geometrijski upad koherence: C(n) = c0 (1 - 2p)^n, p je efektivna verjetnost defaziranja na kubit."""
    return c0 * (1 - 2 * p) ** n


def defaziranje(n: np.ndarray, c: np.ndarray, sigma: np.ndarray | None = None) -> tuple[float, float]:
    """Verjetnost defaziranja na kubit in njena napaka iz prileganja koherence."""
    koef, kov = curve_fit(model_koherence, n, c, p0=(1.0, 0.01), sigma=sigma,
                          absolute_sigma=sigma is not None, bounds=([0.0, 0.0], [2.0, 0.5]),
                          maxfev=10000)
    return float(koef[1]), float(np.sqrt(kov[1, 1]))


# analiza po skupinah
###############################################################################

def analiziraj_skupino(skupina: pd.DataFrame) -> dict[str, float]:
    """Prag n_max z napako, izmerjeni prag in defaziranje za eno okolje, obliko in konfiguracijo."""
    skupina = skupina.sort_values("n")
    n = skupina["n"].to_numpy(dtype=float)
    f = skupina["F"].to_numpy(dtype=float)
    sigma = skupina["F_napaka"].to_numpy(dtype=float)
    ima_napake = bool(np.isfinite(sigma).all())
    prva = skupina.iloc[0]

    r = {stolpec: float("nan") for stolpec in GLAVA}
    r.update({"okolje": prva["okolje"], "oblika": prva["oblika"],
              "konfiguracija": prva["konfiguracija"], "tock": float(len(n)),
              "cas_qpu": float(skupina["cas_qpu"].sum(min_count=1))})
    if ima_napake:
        r["n_gme"] = izmerjeni_prag(n, f, sigma)
    if len(n) < 3:
        return r

    koef, _ = prilagodi(n, f, sigma if ima_napake else None)
    r["a"], r["n0"] = float(koef[0]), float(koef[1])
    r["n_max"] = prag(*koef)
    r["ekstrapolirano"] = float(not n.min() <= r["n_max"] <= n.max())
    if ima_napake:
        r["n_max_napaka"], r["n_max_spodnja"], r["n_max_zgornja"] = bootstrap_praga(
            n, f, sigma, tuple(koef))

    c = skupina["C"].to_numpy(dtype=float)
    c_sigma = skupina["C_napaka"].to_numpy(dtype=float)
    if np.isfinite(c).all():
        r["p"], r["p_napaka"] = defaziranje(n, c, c_sigma if np.isfinite(c_sigma).all() else None)
    return r


def dodaj_primerjavo(analiza: pd.DataFrame) -> pd.DataFrame:
    """Razlika praga in procesorskega casa proti osnovni konfiguraciji istega okolja in oblike."""
    analiza = analiza.copy()
    for _, skupina in analiza.groupby(["okolje", "oblika"]):
        osnova = skupina[skupina["konfiguracija"] == OSNOVNA]
        if osnova.empty:
            continue
        o = osnova.iloc[0]
        analiza.loc[skupina.index, "n_max_razlika"] = skupina["n_max"] - o["n_max"]
        analiza.loc[skupina.index, "cas_razlika"] = skupina["cas_qpu"] - o["cas_qpu"]
    cas = analiza["cas_razlika"].where(analiza["cas_razlika"] != 0)
    analiza["pridobitev_na_sekundo"] = analiza["n_max_razlika"] / cas
    return analiza


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Prileganje F(n), prag n_max in primerjava konfiguracij.")
    ap.add_argument("datoteke", nargs="*")
    ap.add_argument("--do", type=int, help="upostevaj le n <= DO (primerjava na enakem razponu n)")
    a = ap.parse_args()
    datoteke = {Path(p).stem.removeprefix("rezultati_"): p for p in a.datoteke} or DATOTEKE
    rezultati = nalozi_rezultate(datoteke)
    if a.do is not None:
        rezultati = rezultati[rezultati["n"] <= a.do]

    vrstice = [analiziraj_skupino(skupina) for _, skupina
               in rezultati.groupby(["okolje", "oblika", "konfiguracija"], sort=True)]
    analiza = dodaj_primerjavo(pd.DataFrame(vrstice))

    print(f"{'okolje':10} {'oblika':8} {'konf.':5} {'tock':>4} {'a':>6} {'n0':>7} {'n_max':>7} "
          f"{'sigma':>6} {'[16,84]':>14} {'ekst':>4} {'n_gme':>5} {'p':>7} {'QPU [s]':>8}")
    for r in analiza.itertuples(index=False):
        print(f"{r.okolje:10} {r.oblika:8} {r.konfiguracija:5} {int(r.tock):>4} {r.a:6.3f} "
              f"{r.n0:7.1f} {r.n_max:7.1f} {r.n_max_napaka:6.1f} "
              f"{f'[{r.n_max_spodnja:.1f}, {r.n_max_zgornja:.1f}]':>14} "
              f"{int(r.ekstrapolirano) if np.isfinite(r.ekstrapolirano) else '-':>4} "
              f"{r.n_gme:5.0f} {r.p:7.4f} {r.cas_qpu:8.1f}")

    analiza[GLAVA].to_csv(IZHOD if a.do is None else f"analiza_do{a.do}.csv", index=False)
