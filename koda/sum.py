from __future__ import annotations

import numpy as np
from qiskit import QuantumCircuit, transpile
from qiskit.circuit import Parameter
from qiskit.transpiler import PassManager
from qiskit.transpiler.passes import ALAPScheduleAnalysis, PadDelay
from qiskit_aer import AerSimulator
from qiskit_ibm_runtime.fake_provider import FakeFez

from ghz import ghz_drevo, ghz_veriga

NAPRAVA = FakeFez()
FAKTORJI = (1, 3, 5)
FAZA = Parameter("phi")
NITI = 6


def simulator(niti: int | None = NITI) -> AerSimulator:
    """Sumni simulator s sumnim modelom naprave in metodo MPS; niti=None uporabi vsa jedra."""
    moznosti = {"method": "matrix_product_state"}
    if niti is not None:
        moznosti["max_parallel_threads"] = niti
    return AerSimulator.from_backend(NAPRAVA, **moznosti)


def osnovno_vezje(n: int, oblika: str) -> tuple[QuantumCircuit, list[int]]:
    """Vezje GHZ izbrane oblike skupaj z izbranimi fizicnimi kubiti."""
    if oblika == "veriga":
        return ghz_veriga(n, NAPRAVA.target)
    if oblika == "drevo":
        return ghz_drevo(n, NAPRAVA.target)
    raise ValueError(f"neznana oblika: {oblika}")


def faze(n: int) -> np.ndarray:
    """Enakomerno razporejenih 2n+2 faz na [0, 2pi)."""
    return 2 * np.pi * np.arange(2 * n + 2) / (2 * n + 2)


def prepogni_cz(vezje: QuantumCircuit, faktor: int) -> QuantumCircuit:
    """Vsaka vrata CZ ponovljena 'faktor'-krat; CZ je sam svoj inverz, zato za lihe faktorje identicno."""
    if faktor % 2 == 0:
        raise ValueError("faktor mora biti lih, sicer se CZ iznicijo")
    if faktor == 1:
        return vezje
    nov = vezje.copy_empty_like()
    for navodilo in vezje.data:
        ponovitev = faktor if navodilo.operation.name == "cz" else 1
        for _ in range(ponovitev):
            nov.append(navodilo.operation, navodilo.qubits, navodilo.clbits)
    return nov


def z_zakasnitvami(vezje: QuantumCircuit, kubiti: list[int]) -> QuantumCircuit:
    """Vezje z eksplicitnimi zakasnitvami (ALAP) na mirujocih uporabljenih kubitih, da jih Aer sumi."""
    razvrsceno = PassManager([ALAPScheduleAnalysis(target=NAPRAVA.target),
                              PadDelay(target=NAPRAVA.target)]).run(vezje)
    nov = razvrsceno.copy_empty_like()
    for u in razvrsceno.data:
        if u.operation.name != "delay" or razvrsceno.find_bit(u.qubits[0]).index in kubiti:
            nov.append(u)
    return nov


def prevedena_vezja(n: int, oblika: str, zakasnitve: bool = False) -> tuple[QuantumCircuit, QuantumCircuit]:
    """Prevedeno vezje za populaciji in parametrizirano vezje za paritetne meritve."""
    vezje, kubiti = osnovno_vezje(n, oblika)

    populacijsko = vezje.copy()
    populacijsko.measure_all()

    paritetno = vezje.copy()
    for q in range(n):
        paritetno.rz(FAZA, q)
        paritetno.h(q)
    paritetno.measure_all()

    prevedena = transpile([populacijsko, paritetno], NAPRAVA, initial_layout=kubiti, optimization_level=1)
    return tuple(z_zakasnitvami(v, kubiti) for v in prevedena) if zakasnitve else tuple(prevedena)


def pariteta(stevci: dict[str, int]) -> float:
    """Pricakovana vrednost X^n iz izmerjenih izidov."""
    skupaj = sum(stevci.values())
    return sum(v * (-1) ** izid.count("1") for izid, v in stevci.items()) / skupaj


def koherenca(n: int, paritete: np.ndarray) -> float:
    """Koherenca C kot amplituda nihanja cos(n phi) pri frekvenci n."""
    phi = faze(n)
    return float(2 * np.abs(np.sum(paritete * np.exp(-1j * n * phi))) / len(phi))


def ekstrapoliraj(faktorji: tuple[int, ...], vrednosti: list[float]) -> tuple[float, float]:
    """Linearna ekstrapolacija na faktor 0 in standardna napaka ocene."""
    x = np.asarray(faktorji, dtype=float)
    y = np.asarray(vrednosti, dtype=float)
    A = np.vstack([np.ones_like(x), x]).T
    koef, ostanki, *_ = np.linalg.lstsq(A, y, rcond=None)
    napaka = 0.0
    if len(x) > 2 and len(ostanki):
        s2 = float(ostanki[0]) / (len(x) - 2)
        napaka = float(np.sqrt(s2 * np.linalg.inv(A.T @ A)[0, 0]))
    return float(koef[0]), napaka


def meritev(n: int, oblika: str, ponovitev: int = 1024, faktorji: tuple[int, ...] = FAKTORJI,
            sim: AerSimulator | None = None, zakasnitve: bool = False) -> dict[str, float]:
    """Zvestoba brez blazenja in z rocnim ZNE na koherenci; vsa vezja v enem zagonu."""
    if zakasnitve and faktorji != (1,):
        raise ValueError("prepogibanje bi porusilo razvrstitev zakasnitev; uporabi faktorji=(1,)")
    sim = sim or simulator()
    populacijsko, paritetno = prevedena_vezja(n, oblika, zakasnitve)
    phi = faze(n)

    vezja = [populacijsko]
    for faktor in faktorji:
        vezja += [prepogni_cz(paritetno.assign_parameters({FAZA: p}), faktor) for p in phi]

    stevci = sim.run(vezja, shots=ponovitev).result().get_counts()
    skupaj = sum(stevci[0].values())
    p0 = stevci[0].get("0" * n, 0) / skupaj
    p1 = stevci[0].get("1" * n, 0) / skupaj

    koherence = []
    for i in range(len(faktorji)):
        odsek = stevci[1 + i * len(phi): 1 + (i + 1) * len(phi)]
        koherence.append(koherenca(n, np.array([pariteta(s) for s in odsek])))

    rezultat = {"n": float(n), "P0": p0, "P1": p1, "C": koherence[0],
                "F": 0.5 * (p0 + p1) + 0.5 * koherence[0]}
    if len(faktorji) > 1:
        c0, napaka = ekstrapoliraj(faktorji, koherence)
        rezultat.update(C_zne=c0, C_zne_napaka=napaka, F_zne=0.5 * (p0 + p1) + 0.5 * c0)
    for faktor, c in zip(faktorji, koherence):
        rezultat[f"C_{faktor}"] = c
    return rezultat


if __name__ == "__main__":
    import csv
    import sys

    if "--zakasnitve" in sys.argv:
        # isto vezje brez in z zakasnitvami mirujocih kubitov, le faktor 1
        nabor = [int(x) for x in sys.argv[1:] if x.isdigit()] or [16, 24, 32]
        sim = simulator()
        vrstice = []
        for n in nabor:
            for oblika in ("veriga", "drevo"):
                for zak in (False, True):
                    r = meritev(n, oblika, faktorji=(1,), sim=sim, zakasnitve=zak)
                    r.update(oblika=oblika, zakasnitve=int(zak))
                    vrstice.append(r)
                    print(f"{n:>4} {oblika:8} zakasnitve={int(zak)} P0+P1={r['P0'] + r['P1']:.4f} "
                          f"C={r['C']:.4f} F={r['F']:.4f}", flush=True)
        with open("rezultati_sum_zakasnitve.csv", "w", newline="") as f:
            pisec = csv.DictWriter(f, fieldnames=["n", "oblika", "zakasnitve", "P0", "P1", "C", "F"],
                                   extrasaction="ignore")
            pisec.writeheader()
            pisec.writerows(vrstice)
        sys.exit()

    nabor = [int(x) for x in sys.argv[1:]] or [4, 8, 12, 16, 20, 24, 28, 32, 36, 40, 44, 48]
    sim = simulator()
    glava = ["n", "oblika", "P0", "P1", "C", "F", "C_1", "C_3", "C_5", "C_zne", "F_zne"]
    print(f"{'n':>4} {'oblika':8}" + "".join(f"{k:>8}" for k in glava[2:]))

    vrstice = []
    for n in nabor:
        for oblika in ("veriga", "drevo"):
            r = meritev(n, oblika, sim=sim)
            r["oblika"] = oblika
            vrstice.append(r)
            print(f"{n:>4} {oblika:8}" + "".join(f"{r[k]:8.4f}" for k in glava[2:]))

    with open("rezultati_sum.csv", "w", newline="") as f:
        pisec = csv.DictWriter(f, fieldnames=glava, extrasaction="ignore")
        pisec.writeheader()
        pisec.writerows(vrstice)
