from __future__ import annotations

from collections import deque

import rustworkx as rx
from qiskit import QuantumCircuit
from qiskit.transpiler import Target


def graf_naprave(target: Target) -> rx.PyGraph:
    """Neusmerjen graf povezav: utez povezave je napaka CZ, utez vozlisca napaka branja."""
    graf = rx.PyGraph()
    graf.add_nodes_from([0.0] * target.num_qubits)

    if "measure" in target:
        for (q,), lastnosti in target["measure"].items():
            if lastnosti is not None and lastnosti.error is not None:
                graf[q] = lastnosti.error

    najboljsa: dict[tuple[int, int], float] = {}
    for (a, b), lastnosti in target["cz"].items():
        if a == b:
            continue
        napaka = 1.0 if lastnosti is None or lastnosti.error is None else lastnosti.error
        kljuc = (min(a, b), max(a, b))
        najboljsa[kljuc] = min(najboljsa.get(kljuc, 1.0), napaka)

    for (a, b), napaka in najboljsa.items():
        graf.add_edge(a, b, napaka)
    return graf


def izberi_podgraf(target: Target, n: int) -> list[int]:
    """Povezan podgraf n kubitov z najmanjso vsoto napak (Primova pozresna rast)."""
    graf = graf_naprave(target)
    if n > graf.num_nodes():
        raise ValueError(f"naprava ima {graf.num_nodes()} kubitov, zahtevanih je {n}")

    najboljsi: set[int] | None = None
    najboljsa_cena = float("inf")
    for zacetek in graf.node_indices():
        izbrani = {zacetek}
        cena = graf[zacetek]
        rob = {(graf.get_edge_data(zacetek, s), zacetek, s) for s in graf.neighbors(zacetek)}
        while len(izbrani) < n and rob:
            napaka, _, novi = min(rob)
            izbrani.add(novi)
            cena += napaka + graf[novi]
            rob = {(w, a, b) for w, a, b in rob if b not in izbrani}
            rob |= {(graf.get_edge_data(novi, s), novi, s)
                    for s in graf.neighbors(novi) if s not in izbrani}
        if len(izbrani) == n and cena < najboljsa_cena:
            najboljsi, najboljsa_cena = izbrani, cena

    if najboljsi is None:
        raise ValueError(f"ni povezanega podgrafa z {n} kubiti")
    return sorted(najboljsi)


def izberi_pot(target: Target, n: int, korakov: int = 50_000) -> list[int]:
    """Pot n kubitov z najmanjso vsoto napak (pozresni DFS z vracanjem)."""
    graf = graf_naprave(target)

    def razsiri(pot: list[int], uporabljeni: set[int], stevec: list[int]) -> list[int] | None:
        if len(pot) == n:
            return list(pot)
        if stevec[0] <= 0:
            return None
        stevec[0] -= 1
        sosedje = sorted(
            (graf.get_edge_data(pot[-1], s) + graf[s], s)
            for s in graf.neighbors(pot[-1]) if s not in uporabljeni
        )
        for _, sosed in sosedje:
            pot.append(sosed)
            uporabljeni.add(sosed)
            if (resitev := razsiri(pot, uporabljeni, stevec)) is not None:
                return resitev
            pot.pop()
            uporabljeni.discard(sosed)
        return None

    najboljsa: list[int] | None = None
    najboljsa_cena = float("inf")
    for zacetek in graf.node_indices():
        pot = razsiri([zacetek], {zacetek}, [korakov])
        if pot is None:
            continue
        cena = sum(graf[q] for q in pot) + sum(
            graf.get_edge_data(a, b) for a, b in zip(pot, pot[1:])
        )
        if cena < najboljsa_cena:
            najboljsa, najboljsa_cena = pot, cena
    if najboljsa is None:
        raise ValueError(f"ni poti z {n} kubiti")
    return najboljsa


def podgraf(graf: rx.PyGraph, kubiti: list[int]) -> rx.PyGraph:
    """Podgraf na danih kubitih, preindeksiran v 0..n-1 po vrstnem redu seznama."""
    indeks = {q: i for i, q in enumerate(kubiti)}
    pod = rx.PyGraph()
    pod.add_nodes_from([graf[q] for q in kubiti])
    for a, b in graf.edge_list():
        if a in indeks and b in indeks:
            pod.add_edge(indeks[a], indeks[b], graf.get_edge_data(a, b))
    return pod


def drevo_bfs(pod: rx.PyGraph) -> tuple[int, dict[int, list[int]]]:
    """Koren z najmanjso ekscentricnostjo in drevo BFS kot slovar otrok."""
    razdalje = rx.distance_matrix(pod)
    koren = int(razdalje.max(axis=1).argmin())

    otroci: dict[int, list[int]] = {v: [] for v in pod.node_indices()}
    obiskani, vrsta = {koren}, deque([koren])
    while vrsta:
        v = vrsta.popleft()
        sosedje = sorted(pod.neighbors(v), key=lambda s: pod.get_edge_data(v, s))
        for s in sosedje:
            if s not in obiskani:
                obiskani.add(s)
                otroci[v].append(s)
                vrsta.append(s)
    return koren, otroci


def plasti_cnot(koren: int, otroci: dict[int, list[int]]) -> list[list[tuple[int, int]]]:
    """Vrata CNOT, razvrscena v plasti: v vsaki plasti vsak kubit nastopa najvec enkrat."""
    velikost: dict[int, int] = {}

    def izracunaj(v: int) -> int:
        velikost[v] = 1 + sum(izracunaj(o) for o in otroci[v])
        return velikost[v]

    izracunaj(koren)
    cakajo = {v: sorted(o, key=lambda x: -velikost[x]) for v, o in otroci.items()}

    aktivni, plasti = [koren], []
    while any(cakajo[v] for v in aktivni):
        plast, novi = [], []
        for v in aktivni:
            if cakajo[v]:
                otrok = cakajo[v].pop(0)
                plast.append((v, otrok))
                novi.append(otrok)
        plasti.append(plast)
        aktivni = aktivni + novi
    return plasti


def ghz_veriga(n: int, target: Target | None = None) -> tuple[QuantumCircuit, list[int] | None]:
    """Stanje GHZ z linearno verigo vrat CNOT (globina ~n)."""
    vezje = QuantumCircuit(n, name=f"ghz_veriga_{n}")
    vezje.h(0)
    for i in range(n - 1):
        vezje.cx(i, i + 1)
    return vezje, None if target is None else izberi_pot(target, n)


def ghz_drevo(n: int, target: Target) -> tuple[QuantumCircuit, list[int]]:
    """Stanje GHZ z drevesom BFS na grafu povezav (globina ~polmer podgrafa)."""
    kubiti = izberi_podgraf(target, n)
    pod = podgraf(graf_naprave(target), kubiti)
    koren, otroci = drevo_bfs(pod)

    vezje = QuantumCircuit(n, name=f"ghz_drevo_{n}")
    vezje.h(koren)
    for plast in plasti_cnot(koren, otroci):
        for stars, otrok in plast:
            vezje.cx(stars, otrok)
    return vezje, kubiti


if __name__ == "__main__":
    import csv

    from qiskit import transpile
    from qiskit_ibm_runtime.fake_provider import FakeFez

    naprava = FakeFez()
    glava = ["n", "oblika", "cx", "globina", "cz_prevedeno", "globina_prevedeno"]
    print(f"{'n':>4} {'oblika':8} {'CX':>4} {'glob.':>6} {'CZ po prev.':>12} {'glob. po prev.':>15}")

    with open("lastnosti_vezij.csv", "w", newline="") as f:
        pisec = csv.writer(f)
        pisec.writerow(glava)
        for n in (5, 10, 20, 50, 100, 120):
            for ime, (vezje, kubiti) in (
                ("veriga", ghz_veriga(n, naprava.target)),
                ("drevo", ghz_drevo(n, naprava.target)),
            ):
                prevedeno = transpile(vezje, naprava, initial_layout=kubiti, optimization_level=1)
                vrstica = [n, ime, vezje.count_ops()["cx"], vezje.depth(),
                           prevedeno.count_ops().get("cz", 0), prevedeno.depth()]
                pisec.writerow(vrstica)
                f.flush()
                print(f"{n:>4} {ime:8} {vrstica[2]:>4} {vrstica[3]:>6} "
                      f"{vrstica[4]:>12} {vrstica[5]:>15}")
