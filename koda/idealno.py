from __future__ import annotations

import numpy as np
from qiskit import QuantumCircuit
from qiskit.quantum_info import SparsePauliOp
from qiskit_aer import AerSimulator

from ghz import ghz_drevo, ghz_veriga

SIMULATOR = AerSimulator(method="matrix_product_state")


def vezje_ghz(n: int, oblika: str, target=None) -> QuantumCircuit:
    """Vezje GHZ izbrane oblike brez meritev."""
    if oblika == "veriga":
        return ghz_veriga(n)[0]
    if oblika == "drevo":
        return ghz_drevo(n, target)[0]
    raise ValueError(f"neznana oblika: {oblika}")


def stabilizatorji(n: int) -> list[str]:
    """Generatorji stabilizatorske grupe stanja GHZ: X^n in Z_0 Z_i."""
    niz = ["X" * n]
    for i in range(1, n):
        oznake = ["I"] * n
        oznake[0] = oznake[i] = "Z"
        niz.append("".join(reversed(oznake)))
    return niz


def preveri_stabilizatorje(vezje: QuantumCircuit) -> float:
    """Najmanjsa pricakovana vrednost med generatorji; pri pravem GHZ je 1."""
    n = vezje.num_qubits
    qc = vezje.copy()
    for i, pauli in enumerate(stabilizatorji(n)):
        qc.save_expectation_value(SparsePauliOp(pauli), range(n), label=str(i))
    podatki = SIMULATOR.run(qc).result().data()
    return min(float(np.real(podatki[str(i)])) for i in range(n))


def populaciji(vezje: QuantumCircuit, ponovitev: int = 4096) -> tuple[float, float]:
    """Verjetnosti izidov 0...0 in 1...1, izmerjeni v bazi Z."""
    n = vezje.num_qubits
    qc = vezje.copy()
    qc.measure_all()
    stevci = SIMULATOR.run(qc, shots=ponovitev).result().get_counts()
    skupaj = sum(stevci.values())
    return stevci.get("0" * n, 0) / skupaj, stevci.get("1" * n, 0) / skupaj


def faze(n: int) -> np.ndarray:
    """Enakomerno razporejenih 2n+2 faz na [0, 2pi); dovolj gosto za nihanje cos(n phi)."""
    return 2 * np.pi * np.arange(2 * n + 2) / (2 * n + 2)


def pariteta(vezje: QuantumCircuit, phi: float, ponovitev: int) -> float:
    """Pricakovana vrednost X^n po zasuku R_z(phi) na vseh kubitih."""
    n = vezje.num_qubits
    qc = vezje.copy()
    for q in range(n):
        qc.rz(phi, q)
        qc.h(q)
    qc.measure_all()
    stevci = SIMULATOR.run(qc, shots=ponovitev).result().get_counts()
    skupaj = sum(stevci.values())
    return sum(v * (-1) ** izid.count("1") for izid, v in stevci.items()) / skupaj


def koherenca(vezje: QuantumCircuit, ponovitev: int = 4096) -> tuple[float, np.ndarray, np.ndarray]:
    """Koherenca C kot amplituda paritetnih nihanj, dobljena z diskretno Fourierovo vsoto."""
    n = vezje.num_qubits
    phi = faze(n)
    paritete = np.array([pariteta(vezje, p, ponovitev) for p in phi])
    c = 2 * np.abs(np.sum(paritete * np.exp(-1j * n * phi))) / len(phi)
    return float(c), phi, paritete


def zvestoba(vezje: QuantumCircuit, ponovitev: int = 4096) -> dict[str, float]:
    """F = (P_0...0 + P_1...1)/2 + C/2 na idealnem simulatorju."""
    p0, p1 = populaciji(vezje, ponovitev)
    c, _, _ = koherenca(vezje, ponovitev)
    return {"P0": p0, "P1": p1, "C": c, "F": 0.5 * (p0 + p1) + 0.5 * c}


if __name__ == "__main__":
    from qiskit_ibm_runtime.fake_provider import FakeFez

    target = FakeFez().target
    print(f"{'n':>4} {'oblika':8} {'min stab.':>10} {'P0':>7} {'P1':>7} {'C':>7} {'F':>7}")
    for n in (5, 10, 20, 50, 100):
        for oblika in ("veriga", "drevo"):
            vezje = vezje_ghz(n, oblika, target)
            stab = preveri_stabilizatorje(vezje)
            r = zvestoba(vezje)
            print(f"{n:>4} {oblika:8} {stab:10.6f} {r['P0']:7.4f} {r['P1']:7.4f} "
                  f"{r['C']:7.4f} {r['F']:7.4f}")
