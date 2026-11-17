from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
from qiskit_ibm_runtime import Batch, EstimatorV2, QiskitRuntimeService, SamplerV2
from qiskit_ibm_runtime.executor_estimator.prepare import prepare as pripravi_estimator
from qiskit_ibm_runtime.executor_sampler.prepare import prepare as pripravi_sampler
from qiskit_ibm_runtime.fake_provider import FakeFez
from qiskit_ibm_runtime.options_models import EstimatorOptions, SamplerOptions

from procesor import NALOGE, dodaj_nalogo, kalibriraj, kubiti_iz_niza, zabelezi
from zvestoba import FAKTORJI, PONOVITEV, Vezja, faze, pripravi_vezja, shrani

#Tukaj dajta pot do svojega qiskit-ibm.json. Ask claude how to set it up.
RACUNI = Path(__file__).resolve().parents[2] / "qiskit-ibm.json"
KONFIGURACIJE = ("i", "ii", "iii", "iv")
ODDANE = "oddane.csv"
PONOVITEV_SAMPLER = 4096
PONOVITEV_ESTIMATOR = 512
REZERVA = 1.3
# iz testne naloge n = 4 (17. 11. 2026): 1,9 s na nalogo in 0,33 ms na strel, zaokrozeno navzgor
SEKUND_NA_NALOGO = 2.0
SEKUND_NA_STREL = 0.35e-3
PRIMITIVI = {"sampler": (SamplerV2, SamplerOptions, pripravi_sampler),
             "estimator": (EstimatorV2, EstimatorOptions, pripravi_estimator)}


def moznosti(konfiguracija: str, primitiv: str) -> dict:
    """Moznosti Runtime za konfiguracijo (i)-(iv); vse, kar ni vklopljeno, je izrecno izklopljeno."""
    stopnja = KONFIGURACIJE.index(konfiguracija)
    m = {"default_shots": PONOVITEV_SAMPLER if primitiv == "sampler" else PONOVITEV_ESTIMATOR,
         "dynamical_decoupling": {"enable": stopnja >= 1, "sequence_type": "XY4"},
         # sukanje meritev je del TREX pri Estimatorju; pri Samplerju bi pokvarilo popravek mthree
         "twirling": {"enable_gates": stopnja >= 2, "enable_measure": primitiv == "estimator"}}
    if primitiv == "estimator":
        m["resilience_level"] = 0
        m["resilience"] = {"measure_mitigation": True, "pec_mitigation": False,
                           "zne_mitigation": stopnja >= 3}
        if stopnja >= 3:
            m["resilience"]["zne"] = {"noise_factors": FAKTORJI, "extrapolator": "linear",
                                      "amplifier": "gate_folding"}
    return m


def povzetek(v: Vezja, n: int, oblika: str, konfiguracije: list[str]) -> None:
    """Izpis vezij, vklopljenih tehnik in stevila ponovitev; ob tem preveri veljavnost moznosti."""
    print(f"{oblika} n={n}: kubiti {v.kubiti}")
    print(f"  CZ {v.estimatorsko.count_ops().get('cz', 0)}, globina {v.estimatorsko.depth()}, "
          f"faz {2 * n + 2}, ponovitev na vezje: Sampler {PONOVITEV_SAMPLER}, Estimator {PONOVITEV_ESTIMATOR}")
    for k in konfiguracije:
        s = SamplerOptions(**moznosti(k, "sampler"))
        e = EstimatorOptions(**moznosti(k, "estimator"))
        print(f"  ({k}) Sampler: {'-' if k == 'iv' else f'DD={s.dynamical_decoupling.enable} sukanje={s.twirling.enable_gates}'}"
              f" | Estimator: DD={e.dynamical_decoupling.enable} sukanje={e.twirling.enable_gates} "
              f"TREX={e.resilience.measure_mitigation} ZNE={e.resilience.zne_mitigation}")


def naloge(v: Vezja, n: int, konfiguracije: list[str]) -> list[tuple[str, str, list]]:
    """(konfiguracija, primitiv, PUB-i) za en n: Sampler (i)-(iii) za populaciji, Estimator (i)-(iv) za C."""
    phi = faze(n)
    seznam = []
    for konf in konfiguracije:
        if konf != "iv":
            seznam.append((konf, "sampler", [v.populacijsko]))
        seznam.append((konf, "estimator", [(v.estimatorsko, v.opazljivka, phi[:, None])]))
    return seznam


def preizkusi(vezja: dict[int, Vezja], konfiguracije: list[str], backend) -> tuple[int, int]:
    """Lokalna priprava vseh nalog, enaka tisti pred oddajo; vrne stevilo nalog in strelov s kalibracijami."""
    nalog, strelov = len(vezja), 2 * PONOVITEV * len(vezja)
    for n, v in vezja.items():
        for konf, primitiv, pubi in naloge(v, n, konfiguracije):
            _, Moznosti, pripravi = PRIMITIVI[primitiv]
            program, _ = pripravi(pubi, Moznosti(**moznosti(konf, primitiv)), None, backend=backend)
            nalog += 1
            strelov += program.shots * sum(postavka.size() for postavka in program.items)
    return nalog, strelov


def oddaj(v: Vezja, n: int, oblika: str, konfiguracije: list[str], backend, racun: str,
          mapa: Path) -> None:
    """Vse naloge za en n v enem paketu s kalibracijo mthree; vsako takoj vpise v oddane.csv."""
    oznaka = f"{oblika}_{n}_{datetime.now():%Y%m%d_%H%M%S}"
    kalibracija, lastnosti = f"kalibracija_{oznaka}.json", f"lastnosti_{oznaka}.json"
    mapa.mkdir(exist_ok=True)
    skupno = dict(n=n, oblika=oblika, kubiti=";".join(map(str, v.kubiti)), racun=racun, lastnosti=lastnosti)

    with Batch(backend=backend) as paket:
        for konf, primitiv, pubi in naloge(v, n, konfiguracije):
            naloga = PRIMITIVI[primitiv][0](mode=paket, options=moznosti(konf, primitiv)).run(pubi)
            dodaj_nalogo(mapa / ODDANE, konfiguracija=konf, primitiv=primitiv, naloga=naloga.job_id(),
                         ponovitev=moznosti(konf, primitiv)["default_shots"],
                         kalibracija=kalibracija if primitiv == "sampler" else "", **skupno)
            print(f"  oddano ({konf}) {primitiv}: {naloga.job_id()}")
        try:
            for naloga in kalibriraj(backend, v.kubiti, mapa / kalibracija, paket=paket):
                dodaj_nalogo(mapa / ODDANE, primitiv="kalibracija", naloga=naloga.job_id(),
                             ponovitev=PONOVITEV, kalibracija=kalibracija, **skupno)
        except Exception as napaka:
            print(f"NAPAKA pri kalibraciji mthree: {napaka}", file=sys.stderr)


def dokoncaj(mapa: Path, naloga_po_id) -> None:
    """Shrani in zabelezi vse oddane naloge, ki se niso v naloge.csv; napaka ene ne ustavi ostalih."""
    oddane = pd.read_csv(mapa / ODDANE, dtype=str, keep_default_na=False)
    zabelezene = set()
    if (mapa / NALOGE).exists():
        zabelezene = set(pd.read_csv(mapa / NALOGE, dtype=str).naloga)
    for r in oddane.itertuples():
        if r.naloga in zabelezene:
            continue
        try:
            naloga = naloga_po_id(r.naloga)
            zabelezi(naloga, int(r.n), r.oblika, r.konfiguracija, r.primitiv,
                     kubiti_iz_niza(r.kubiti), int(r.ponovitev), mapa, r.kalibracija, r.racun,
                     r.lastnosti)
            if not (mapa / r.lastnosti).exists():
                if (lastnosti := naloga.properties()) is None:
                    print(f"OPOZORILO: ni lastnosti naprave za {r.naloga}", file=sys.stderr)
                else:
                    shrani(lastnosti.to_dict(), mapa / r.lastnosti)
        except Exception as napaka:
            print(f"NAPAKA pri nalogi {r.naloga}: {napaka}; ponovi z --dokoncaj", file=sys.stderr)
    print(f"zabelezeno v {mapa / NALOGE}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Oddaja nalog GHZ na procesor IBM.")
    ap.add_argument("n", type=int, nargs="*")
    ap.add_argument("--oblika", choices=("veriga", "drevo"), default="drevo")
    ap.add_argument("--konf", nargs="+", choices=KONFIGURACIJE, default=list(KONFIGURACIJE))
    ap.add_argument("--racun", help=f"ime racuna v {RACUNI}")
    ap.add_argument("--naprava", default="ibm_fez")
    ap.add_argument("--mapa", type=Path, default=Path("rezultati"))
    ap.add_argument("--suho", action="store_true", help="samo lokalni izpis na FakeFez")
    ap.add_argument("--dokoncaj", action="store_true", help="zabelezi oddane, pa se ne zabelezene naloge")
    a = ap.parse_args()
    if "iv" in a.konf and "iii" not in a.konf:
        ap.error("(iv) potrebuje populaciji iz Samplerja (iii)")
    if not a.suho and not a.racun:
        ap.error("potreben je --racun")
    if not a.n and not a.dokoncaj:
        ap.error("podaj vsaj en n")

    if a.suho:
        for n in a.n:
            povzetek(pripravi_vezja(n, a.oblika, FakeFez()), n, a.oblika, a.konf)
        sys.exit()

    storitev = QiskitRuntimeService(filename=str(RACUNI), name=a.racun)
    if a.dokoncaj:
        dokoncaj(a.mapa, storitev.job)
        sys.exit()

    backend = storitev.backend(a.naprava)
    vezja = {n: pripravi_vezja(n, a.oblika, backend) for n in a.n}
    for n, v in vezja.items():
        povzetek(v, n, a.oblika, a.konf)
    nalog, strelov = preizkusi(vezja, a.konf, backend)
    ocena = nalog * SEKUND_NA_NALOGO + strelov * SEKUND_NA_STREL
    ostane = storitev.usage().get("usage_remaining_seconds")
    print(f"{nalog} nalog, {strelov} strelov, ocena {ocena:.0f} s; na racunu ostane {ostane} s")
    if ostane is None or REZERVA * ocena > ostane:
        sys.exit(f"ne oddam: ocena x {REZERVA} presega preostanek ali ta ni znan")

    if input(f"Oddam na {backend.name} z racunom {a.racun}? [da/ne] ") == "da":
        for n, v in vezja.items():
            oddaj(v, n, a.oblika, a.konf, backend, a.racun, a.mapa)
        dokoncaj(a.mapa, storitev.job)
