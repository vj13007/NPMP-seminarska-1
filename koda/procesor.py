from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from mthree import M3Mitigation

from zvestoba import (PONOVITEV, koherenca_bootstrap, napaka_paritete, nalozi, oceni, pariteta,
                      paritete_iz_estimatorja, populaciji, shrani, stevci_iz_samplerja)

NALOGE = "naloge.csv"
IZHOD = "rezultati_procesor.csv"
STOLPCI_NALOG = ["n", "oblika", "konfiguracija", "primitiv", "naloga", "datoteka",
                 "kubiti", "ponovitev", "cas_qpu", "kalibracija"]
GLAVA = ["n", "oblika", "konfiguracija", "P0", "P1", "P_napaka", "C", "C_napaka", "F", "F_napaka",
         "GME", "C_sampler", "C_sampler_napaka", "P0_surovo", "P1_surovo", "mthree", "cas_qpu",
         "nalogi"]


# belezenje nalog ob oddaji (uporabi oddajni program)
###############################################################################

def cas_qpu(naloga) -> float:
    """Porabljen cas procesorja v sekundah iz metapodatkov naloge; nan, ce ga naloga ne pozna."""
    try:
        return float(naloga.usage())
    except Exception:
        pass
    try:
        return float(naloga.metrics()["usage"]["quantum_seconds"])
    except Exception:
        return float("nan")


def ime_datoteke(n: int, oblika: str, konfiguracija: str, primitiv: str) -> str:
    """Dogovorjeno ime JSON datoteke z rezultatom ene naloge."""
    return f"{oblika}_{n}_{konfiguracija}_{primitiv}.json"


def dodaj_nalogo(pot: str | Path, **polja) -> None:
    """V CSV nalog doda eno vrstico; datoteko z glavo ustvari, ce je se ni."""
    vrstica = pd.DataFrame([{stolpec: polja.get(stolpec, "") for stolpec in STOLPCI_NALOG}])
    vrstica.to_csv(pot, mode="a", header=not Path(pot).exists(), index=False)


def kalibriraj(naprava, kubiti: list[int], pot: str | Path,
               ponovitev: int = PONOVITEV) -> M3Mitigation:
    """Kalibracija mthree na danih kubitih naprave, shranjena v JSON za kasnejso analizo."""
    mit = M3Mitigation(naprava)
    mit.cals_from_system(kubiti, shots=ponovitev, async_cal=False)
    mit.cals_to_file(str(pot))
    return mit


def zabelezi(naloga, n: int, oblika: str, konfiguracija: str, primitiv: str, kubiti: list[int],
             ponovitev: int, mapa: str | Path = ".", kalibracija: str = "") -> Path:
    """Pocaka na rezultat naloge, ga shrani v JSON in nalogo vpise v CSV nalog.

    primitiv je "sampler" (populaciji in po zelji paritete kot drugi PUB) ali "estimator"
    (paritete), kalibracija pa ime datoteke mthree iz funkcije kalibriraj, relativno na mapo.
    """
    mapa = Path(mapa)
    datoteka = ime_datoteke(n, oblika, konfiguracija, primitiv)
    shrani(naloga.result(), mapa / datoteka)
    dodaj_nalogo(mapa / NALOGE, n=n, oblika=oblika, konfiguracija=konfiguracija,
                 primitiv=primitiv, naloga=naloga.job_id(), datoteka=datoteka,
                 kubiti=";".join(map(str, kubiti)), ponovitev=ponovitev,
                 cas_qpu=cas_qpu(naloga), kalibracija=kalibracija)
    return mapa / datoteka


# ocena zvestobe iz shranjenih rezultatov
###############################################################################

def kubiti_iz_niza(niz: str) -> list[int]:
    """Seznam fizicnih kubitov iz zapisa "140;141;142"."""
    return [int(x) for x in str(niz).split(";") if x]


def mitigator(pot: str | Path) -> M3Mitigation:
    """mthree s kalibracijo iz datoteke; naprave ne potrebuje."""
    mit = M3Mitigation()
    mit.cals_from_file(str(pot))
    return mit


def oceni_skupino(skupina: pd.DataFrame, mapa: Path, mitigatorji: dict) -> dict[str, float]:
    """Zvestoba za en n, obliko in konfiguracijo iz vrstic CSV nalog.

    Potrebna je naloga Sampler s populacijami v prvem PUB-u. Paritete vzame iz naloge
    Estimator, ce obstaja, sicer iz drugega PUB-a Samplerja. Populaciji popravi z mthree,
    kadar ima vrstica Samplerja navedeno datoteko kalibracije.
    """
    po_primitivu = {v.primitiv: v for v in skupina.itertuples()}
    if "sampler" not in po_primitivu:
        raise ValueError("manjka naloga Sampler")
    s = po_primitivu["sampler"]
    n, kubiti, ponovitev = int(s.n), kubiti_iz_niza(s.kubiti), int(s.ponovitev)
    rez_s = nalozi(mapa / s.datoteka)
    stevci = stevci_iz_samplerja(rez_s, 0)

    # paritete iz Samplerja, ce jih ima v drugem PUB-u
    par_s = napake_s = None
    c_sampler = c_sampler_napaka = float("nan")
    if len(rez_s) > 1:
        par_s = np.array([pariteta(stevci_iz_samplerja(rez_s, 1, k)) for k in range(2 * n + 2)])
        napake_s = napaka_paritete(par_s, ponovitev)
        c_sampler, c_sampler_napaka = koherenca_bootstrap(n, par_s, napake_s)

    # paritete za zvestobo: Estimator ima prednost
    if "estimator" in po_primitivu:
        paritete, napake = paritete_iz_estimatorja(nalozi(mapa / po_primitivu["estimator"].datoteka), 0)
    elif par_s is not None:
        paritete, napake = par_s, napake_s
    else:
        raise ValueError("ni paritet: manjka naloga Estimator ali drugi PUB Samplerja")

    mit = None
    if s.kalibracija:
        if s.kalibracija not in mitigatorji:
            mitigatorji[s.kalibracija] = mitigator(mapa / s.kalibracija)
        mit = mitigatorji[s.kalibracija]

    r = oceni(n, stevci, paritete, napake, kubiti, mit)
    r["P0_surovo"], r["P1_surovo"] = populaciji(stevci, n)
    r.update({"n": n, "oblika": s.oblika, "konfiguracija": s.konfiguracija,
              "C_sampler": c_sampler, "C_sampler_napaka": c_sampler_napaka,
              "mthree": float(mit is not None), "cas_qpu": float(skupina.cas_qpu.sum(min_count=1)),
              "nalogi": ";".join(skupina.naloga.astype(str))})
    return r


if __name__ == "__main__":
    pot = Path(sys.argv[1] if len(sys.argv) > 1 else NALOGE)
    mapa = pot.parent
    naloge = pd.read_csv(pot, dtype=str, keep_default_na=False)
    naloge["n"] = naloge["n"].astype(int)
    naloge["cas_qpu"] = pd.to_numeric(naloge["cas_qpu"], errors="coerce")

    mitigatorji: dict[str, M3Mitigation] = {}
    vrstice = []
    print(f"{'n':>4} {'oblika':8} {'konf.':5} {'P0':>7} {'P1':>7} {'C':>7} {'F':>7} {'sigma':>7} "
          f"{'GME':>4} {'m3':>3} {'QPU [s]':>8}")

    for _, skupina in naloge.groupby(["n", "oblika", "konfiguracija"], sort=True):
        r = oceni_skupino(skupina, mapa, mitigatorji)
        vrstice.append(r)
        print(f"{r['n']:>4} {r['oblika']:8} {r['konfiguracija']:5} {r['P0']:7.4f} {r['P1']:7.4f} "
              f"{r['C']:7.4f} {r['F']:7.4f} {r['F_napaka']:7.4f} {int(r['GME']):>4} "
              f"{int(r['mthree']):>3} {r['cas_qpu']:8.1f}")

    pd.DataFrame(vrstice)[GLAVA].to_csv(mapa / IZHOD, index=False)
