from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd
from qiskit import QuantumCircuit, transpile
from qiskit.circuit.library import XGate
from qiskit.transpiler import PassManager, Target
from qiskit.transpiler.passes import ALAPScheduleAnalysis, PadDelay, PadDynamicalDecoupling
from qiskit_ibm_runtime.fake_provider import FakeFez
from qiskit_ibm_runtime.models import BackendProperties
from qiskit_ibm_runtime.utils.backend_converter import convert_to_target

from oddaja import SEKUND_NA_NALOGO, SEKUND_NA_STREL
from ghz import drevo_bfs, ghz_veriga, graf_naprave, plasti_cnot, podgraf
from procesor import kubiti_iz_niza
from zvestoba import FAKTORJI

MAPA = Path("rezultati")
IZHOD = "pregled_vezij.csv"


def target_dneva(lastnosti: str) -> Target:
    """Target ibm_fez s kalibracijo, shranjeno ob oddaji."""
    with open(MAPA / lastnosti) as f:
        return convert_to_target(FakeFez().configuration(), BackendProperties.from_dict(json.load(f)))


def vezje_na_kubitih(oblika: str, kubiti: list[int], target: Target) -> QuantumCircuit:
    """Vezje GHZ z meritvijo na danih kubitih, kot ga je dobil Sampler."""
    n = len(kubiti)
    if oblika == "veriga":
        vezje, _ = ghz_veriga(n)
    else:
        koren, otroci = drevo_bfs(podgraf(graf_naprave(target), kubiti))
        vezje = QuantumCircuit(n)
        vezje.h(koren)
        for plast in plasti_cnot(koren, otroci):
            for stars, otrok in plast:
                vezje.cx(stars, otrok)
    vezje.measure_all()
    return transpile(vezje, target=target, initial_layout=kubiti, optimization_level=1)


def x_po_kubitih(vezje: QuantumCircuit) -> Counter:
    """Stevilo vrat X na vsakem fizicnem kubitu."""
    return Counter(vezje.find_bit(u.qubits[0]).index for u in vezje.data if u.operation.name == "x")


def napake(vezje: QuantumCircuit, kubiti: list[int], target: Target) -> dict[str, float]:
    """Vsota napak CZ in branja ter najkrajsi T2 na izbranih kubitih po kalibraciji dneva."""
    cz = [tuple(vezje.find_bit(q).index for q in u.qubits) for u in vezje.data if u.operation.name == "cz"]
    return {"napaka_cz": sum(target["cz"][par].error for par in cz),
            "napaka_branja": sum(target["measure"][(q,)].error for q in kubiti),
            "t2_min_us": min(target.qubit_properties[q].t2 for q in kubiti) * 1e6}


def prosti_cas(oblika: str, kubiti: list[int], target: Target) -> dict[str, float]:
    """Napake kubitov, trajanje, cas mirovanja uporabljenih kubitov po prvih vratih in impulzi XY4, ki jih vstavi razklapljanje."""
    vezje = vezje_na_kubitih(oblika, kubiti, target)
    # stiri X imajo enako trajanje in napako kot XY4 (Y = X do virtualnega rz)
    razvrsti = [ALAPScheduleAnalysis(target=target)]
    z_zakasnitvami = PassManager(razvrsti + [PadDelay(target=target)]).run(vezje)
    z_dd = PassManager(razvrsti + [PadDynamicalDecoupling(target=target, dd_sequence=[XGate()] * 4)]).run(vezje)

    uporabljeni = set(kubiti)
    # steje le mirovanje po prvih vratih kubita; cakanje v |0> pred njimi ne defazira
    zaceli, prosto = set(), 0
    for u in z_zakasnitvami.data:
        q = [z_zakasnitvami.find_bit(x).index for x in u.qubits]
        if u.operation.name == "delay":
            prosto += u.operation.duration if q[0] in uporabljeni and q[0] in zaceli else 0
        elif u.operation.name != "barrier":
            zaceli.update(q)
    prosto *= target.dt
    trajanje = z_zakasnitvami.estimate_duration(target, unit="s")
    pred, po = x_po_kubitih(vezje), x_po_kubitih(z_dd)
    impulzi = {q: po[q] - pred[q] for q in uporabljeni}
    napaka = 1 - np.prod([(1 - target["x"][(q,)].error) ** k for q, k in impulzi.items()])
    return {"trajanje_us": trajanje * 1e6, "prosti_us": prosto * 1e6,
            "delez_prosti": prosto / (trajanje * len(kubiti)), "impulzi_dd": sum(impulzi.values()),
            "napaka_impulzov": napaka, **napake(vezje, kubiti, target)}


def poraba(paket: pd.DataFrame) -> dict[str, float]:
    """Ocena porabe po modelu iz oddaja.py in dejanska poraba nalog Sampler in Estimator v paketu."""
    m = paket[paket.primitiv != "kalibracija"]
    n = m.n.astype(int).to_numpy()
    faz = np.where(m.primitiv == "estimator", (2 * n + 2) * np.where(m.konfiguracija == "iv", len(FAKTORJI), 1), 1)
    strelov = (m.ponovitev.astype(int).to_numpy() * faz).sum()
    return {"ocena_qpu_s": len(m) * SEKUND_NA_NALOGO + strelov * SEKUND_NA_STREL,
            "poraba_qpu_s": m.cas_qpu.astype(float).sum()}


if __name__ == "__main__":
    vse = pd.read_csv(MAPA / "naloge.csv", dtype=str, keep_default_na=False)
    naloge = vse[vse.primitiv == "sampler"].drop_duplicates("lastnosti")
    vrstice = []
    for r in naloge.itertuples():
        kubiti = kubiti_iz_niza(r.kubiti)
        vrstice.append({"n": int(r.n), "oblika": r.oblika,
                        "paket": r.lastnosti.removeprefix("lastnosti_").removesuffix(".json"),
                        **prosti_cas(r.oblika, kubiti, target_dneva(r.lastnosti)),
                        **poraba(vse[vse.lastnosti == r.lastnosti])})
    tabela = pd.DataFrame(vrstice).sort_values(["oblika", "n", "paket"])
    print(tabela.to_string(index=False, float_format="%.3f"))
    tabela.to_csv(IZHOD, index=False)
