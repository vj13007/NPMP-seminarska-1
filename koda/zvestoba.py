from __future__ import annotations

import json
import sys
from typing import NamedTuple

import numpy as np
import pandas as pd
from mthree import M3Mitigation
from qiskit import QuantumCircuit, transpile
from qiskit.circuit import Parameter
from qiskit.quantum_info import SparsePauliOp
from qiskit_aer import AerSimulator
from qiskit_aer.primitives import EstimatorV2, SamplerV2
from qiskit_ibm_runtime import RuntimeDecoder, RuntimeEncoder
from qiskit_ibm_runtime.fake_provider import FakeFez

from ghz import ghz_drevo, ghz_veriga

FAZA = Parameter("phi")
FAKTORJI = (1, 3, 5)
PONOVITEV = 1024
BOOTSTRAP = 200


# vezja
####################################################################

class Vezja(NamedTuple):
    """Prevedena vezja za en n in eno obliko; vsa delijo iste fizicne kubite."""

    # GHZ + meritev v bazi Z (Sampler)
    populacijsko: QuantumCircuit

    # GHZ + Rz(phi) + H + meritev (Sampler)
    paritetno: QuantumCircuit

    # GHZ + Rz(phi), brez meritev (Estimator)
    estimatorsko: QuantumCircuit

    # X^n, preslikana na fizicne kubite
    opazljivka: SparsePauliOp

    # logicni kubit i -> fizicni kubiti[i]
    kubiti: list[int]


def faze(n: int) -> np.ndarray:
    """Enakomerno razporejenih 2n+2 faz na [0, 2pi); nad Nyquistovo mejo za cos(n phi)."""
    return 2 * np.pi * np.arange(2 * n + 2) / (2 * n + 2)


def pripravi_vezja(n: int, oblika: str, naprava, stopnja: int = 1) -> Vezja:
    """Vse tri oblike vezja GHZ za dani n, prevedene na iste izbrane kubite."""
    if oblika == "veriga":
        vezje, kubiti = ghz_veriga(n, naprava.target)
    elif oblika == "drevo":
        vezje, kubiti = ghz_drevo(n, naprava.target)
    else:
        raise ValueError(f"neznana oblika: {oblika}")

    populacijsko = vezje.copy()
    populacijsko.measure_all()

    estimatorsko = vezje.copy()
    for q in range(n):
        estimatorsko.rz(FAZA, q)

    paritetno = estimatorsko.copy()
    for q in range(n):
        paritetno.h(q)
    paritetno.measure_all()

    prevedena = transpile([populacijsko, paritetno, estimatorsko], naprava,
                          initial_layout=kubiti, optimization_level=stopnja)
    opazljivka = SparsePauliOp("X" * n).apply_layout(prevedena[2].layout)
    return Vezja(prevedena[0], prevedena[1], prevedena[2], opazljivka, kubiti)


# shranjevanje in branje rezultatov
########################################################################

class Koder(RuntimeEncoder):
    """RuntimeEncoder, ki objekte brez zapisa (npr. Metadata primitivov Executor) zapise kot slovar."""

    def default(self, obj):
        try:
            return super().default(obj)
        except TypeError:
            return vars(obj) if hasattr(obj, "__dict__") else str(obj)


def shrani(rezultat, pot: str) -> None:
    """Rezultat primitiva (Sampler ali Estimator) zapise v JSON, da ga analiza bere brez omrezja."""
    with open(pot, "w") as f:
        json.dump(rezultat, f, cls=Koder)


def nalozi(pot: str):
    """Prebere rezultat primitiva, shranjen s funkcijo shrani."""
    with open(pot) as f:
        return json.load(f, cls=RuntimeDecoder)


def stevci_iz_samplerja(rezultat, i: int = 0, k: int | None = None) -> dict[str, int]:
    """Stevci i-tega PUB-a; k izbere nabor parametrov, ce je bil PUB parametriziran."""
    podatki = rezultat[i].data
    register = podatki[next(iter(podatki))] if hasattr(podatki, "__iter__") else podatki.meas
    if k is not None:
        register = register[k]
    return register.get_counts()


def paritete_iz_estimatorja(rezultat, i: int = 0) -> tuple[np.ndarray, np.ndarray]:
    """Pricakovane vrednosti X^n in njihove napake za vse faze i-tega PUB-a."""
    podatki = rezultat[i].data
    return np.asarray(podatki.evs, dtype=float).ravel(), np.asarray(podatki.stds, dtype=float).ravel()


# populaciji
#############################################################################

def populaciji(stevci: dict[str, int], n: int) -> tuple[float, float]:
    """Verjetnosti izidov 0...0 in 1...1 brez popravka branja."""
    skupaj = sum(stevci.values())
    return stevci.get("0" * n, 0) / skupaj, stevci.get("1" * n, 0) / skupaj


def prevzorci(stevci: dict[str, int], rng: np.random.Generator) -> dict[str, int]:
    """Multinomsko prevzorcenje stevcev z enakim skupnim stevilom ponovitev."""
    izidi = list(stevci)
    vrednosti = np.array([stevci[x] for x in izidi], dtype=float)
    novi = rng.multinomial(int(vrednosti.sum()), vrednosti / vrednosti.sum())
    return {x: int(v) for x, v in zip(izidi, novi) if v}


def populaciji_mthree(stevci: dict[str, int], kubiti: list[int], mit,
                      ponovitev: int = BOOTSTRAP, seme: int = 0) -> tuple[float, float, float]:
    """Populaciji s popravkom mthree in napaka njune vsote iz vzorcenja bootstrap.

    kubiti so v logicnem vrstnem redu: kubiti[0] ustreza skrajno desnemu bitu v stevcih,
    kar je ravno dogovor mthree. mit je kalibriran M3Mitigation na istih kubitih.
    """
    n = len(kubiti)

    def popravi(s: dict[str, int]) -> tuple[float, float]:
        kvazi = mit.apply_correction(s, kubiti)
        verjetnosti = kvazi.nearest_probability_distribution()
        return float(verjetnosti.get("0" * n, 0.0)), float(verjetnosti.get("1" * n, 0.0))

    p0, p1 = popravi(stevci)
    rng = np.random.default_rng(seme)
    vsote = [sum(popravi(prevzorci(stevci, rng))) for _ in range(ponovitev)]
    return p0, p1, float(np.std(vsote, ddof=1))


def populaciji_bootstrap(stevci: dict[str, int], n: int,
                         ponovitev: int = BOOTSTRAP, seme: int = 0) -> tuple[float, float, float]:
    """Populaciji brez popravka branja in napaka njune vsote; za simulator brez mthree."""
    p0, p1 = populaciji(stevci, n)
    rng = np.random.default_rng(seme)
    vsote = [sum(populaciji(prevzorci(stevci, rng), n)) for _ in range(ponovitev)]
    return p0, p1, float(np.std(vsote, ddof=1))


# koherenca
#########################################################################

def pariteta(stevci: dict[str, int]) -> float:
    """Pricakovana vrednost X^n iz izmerjenih izidov: +1 za sodo, -1 za liho stevilo enic."""
    skupaj = sum(stevci.values())
    return sum(v * (-1) ** izid.count("1") for izid, v in stevci.items()) / skupaj


def napaka_paritete(paritete: np.ndarray, ponovitev: int) -> np.ndarray:
    """Statisticna napaka povprecja +-1 vrednosti pri danem stevilu ponovitev."""
    p = np.asarray(paritete, dtype=float)
    return np.sqrt(np.clip(1 - p ** 2, 0, None) / ponovitev)


def koherenca(n: int, paritete: np.ndarray) -> float:
    """Koherenca C kot amplituda nihanja cos(n phi), odcitana z diskretno Fourierovo vsoto."""
    phi = faze(n)
    return float(2 * np.abs(np.sum(paritete * np.exp(-1j * n * phi))) / len(phi))


def koherenca_bootstrap(n: int, paritete: np.ndarray, napake: np.ndarray,
                        ponovitev: int = 1000, seme: int = 0) -> tuple[float, float]:
    """Koherenca in njena napaka iz parametricnega bootstrapa paritet z danimi napakami."""
    paritete = np.asarray(paritete, dtype=float)
    napake = np.asarray(napake, dtype=float)
    rng = np.random.default_rng(seme)
    vzorci = [koherenca(n, paritete + rng.normal(0, napake)) for _ in range(ponovitev)]
    return koherenca(n, paritete), float(np.std(vzorci, ddof=1))


# ekstrapolacija in zvestoba
##############################################################

def ekstrapoliraj(faktorji: tuple[int, ...], vrednosti, napake=None) -> tuple[float, float]:
    """Utezena linearna ekstrapolacija na faktor 0 in napaka ocene.

    Napaka vsebuje negotovost vhodnih vrednosti in, ce premica tocke slabo opisuje,
    se raztros ostankov; brez podanih napak je enaka navadni metodi najmanjsih kvadratov.
    """
    x = np.asarray(faktorji, dtype=float)
    y = np.asarray(vrednosti, dtype=float)
    w = np.ones_like(x) if napake is None else 1 / np.asarray(napake, dtype=float) ** 2
    A = np.vstack([np.ones_like(x), x]).T
    kovarianca = np.linalg.inv(A.T @ (w[:, None] * A))
    koef = kovarianca @ A.T @ (w * y)
    if len(x) > 2:
        ostanki = y - A @ koef
        hi2 = float(np.sum(w * ostanki ** 2) / (len(x) - 2))
        if napake is None or hi2 > 1:
            kovarianca = kovarianca * hi2
    return float(koef[0]), float(np.sqrt(kovarianca[0, 0]))


def zvestoba(p0: float, p1: float, napaka_populacij: float,
             c: float, napaka_koherence: float) -> dict[str, float]:
    """F = (P0 + P1)/2 + C/2, njena napaka in pogoj F - 2 sigma > 0,5 za GME."""
    f = 0.5 * (p0 + p1) + 0.5 * c
    sigma = 0.5 * float(np.hypot(napaka_populacij, napaka_koherence))
    return {"P0": p0, "P1": p1, "P_napaka": napaka_populacij,
            "C": c, "C_napaka": napaka_koherence,
            "F": f, "F_napaka": sigma, "GME": float(f - 2 * sigma > 0.5)}


def oceni(n: int, stevci: dict[str, int], paritete: np.ndarray, napake: np.ndarray,
          kubiti: list[int] | None = None, mit=None) -> dict[str, float]:
    """Zvestoba iz surovih podatkov: stevci populacij ter paritete in napake pri 2n+2 fazah.

    Z mit in kubiti se populaciji popravita z mthree, sicer ostaneta nepopravljeni.
    """
    if mit is not None and kubiti is not None:
        p0, p1, napaka_p = populaciji_mthree(stevci, kubiti, mit)
    else:
        p0, p1, napaka_p = populaciji_bootstrap(stevci, n)
    c, napaka_c = koherenca_bootstrap(n, paritete, napake)
    return zvestoba(p0, p1, napaka_p, c, napaka_c)


def oceni_zne(rezultat: dict[str, float], faktorji: tuple[int, ...],
              koherence, napake) -> dict[str, float]:
    """Rezultatu funkcije oceni doda ekstrapolirano koherenco in zvestobo (konfiguracija iv)."""
    c0, napaka_c0 = ekstrapoliraj(faktorji, koherence, napake)
    zne = zvestoba(rezultat["P0"], rezultat["P1"], rezultat["P_napaka"], c0, napaka_c0)
    dodatek = {f"C_{f}": float(c) for f, c in zip(faktorji, koherence)}
    dodatek.update({"C_zne": zne["C"], "C_zne_napaka": zne["C_napaka"],
                    "F_zne": zne["F"], "F_zne_napaka": zne["F_napaka"], "GME_zne": zne["GME"]})
    return {**rezultat, **dodatek}


# lokalni preizkus na odlitku naprave
###############################################################################

NITI = 6

if __name__ == "__main__":
    nabor = [int(x) for x in sys.argv[1:]] or [4, 8, 12]
    naprava = FakeFez()
    sim = AerSimulator.from_backend(naprava, method="matrix_product_state",
                                    max_parallel_threads=NITI)
    sampler, estimator = SamplerV2.from_backend(sim), EstimatorV2.from_backend(sim)
    mit = M3Mitigation(sim)

    glava = ["n", "oblika", "P0", "P1", "P_napaka", "C", "C_napaka", "F", "F_napaka", "GME",
             "C_sampler", "C_sampler_napaka", "P0_surovo", "P1_surovo"]
    print(f"{'n':>4} {'oblika':8} {'P0':>7} {'P1':>7} {'C':>7} {'F':>7} {'sigma':>7} "
          f"{'GME':>4} {'C sampl.':>9} {'P0 sur.':>8}")

    vrstice = []
    for n in nabor:
        phi = faze(n)
        for oblika in ("veriga", "drevo"):
            v = pripravi_vezja(n, oblika, naprava)
            mit.cals_from_system(v.kubiti, shots=PONOVITEV, async_cal=False)

            # populaciji in paritete s Samplerjem (paritete kot en parametriziran PUB)
            rez_s = sampler.run([v.populacijsko, (v.paritetno, phi[:, None])],
                                shots=PONOVITEV).result()
            stevci = stevci_iz_samplerja(rez_s, 0)
            par_s = np.array([pariteta(stevci_iz_samplerja(rez_s, 1, k)) for k in range(len(phi))])
            c_s, c_s_napaka = koherenca_bootstrap(n, par_s, napaka_paritete(par_s, PONOVITEV))

            # paritete z Estimatorjem (en parametriziran PUB)
            rez_e = estimator.run([(v.estimatorsko, v.opazljivka, phi[:, None])],
                                  precision=1 / np.sqrt(PONOVITEV)).result()
            par_e, nap_e = paritete_iz_estimatorja(rez_e, 0)

            r = oceni(n, stevci, par_e, nap_e, v.kubiti, mit)
            r.update({"n": n, "oblika": oblika, "C_sampler": c_s, "C_sampler_napaka": c_s_napaka})
            r["P0_surovo"], r["P1_surovo"] = populaciji(stevci, n)
            vrstice.append(r)
            print(f"{n:>4} {oblika:8} {r['P0']:7.4f} {r['P1']:7.4f} {r['C']:7.4f} {r['F']:7.4f} "
                  f"{r['F_napaka']:7.4f} {int(r['GME']):>4} {c_s:9.4f} {r['P0_surovo']:8.4f}")

    pd.DataFrame(vrstice)[glava].to_csv("rezultati_zvestoba.csv", index=False)
