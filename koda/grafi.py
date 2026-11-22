"""Slike in tabele za poglavje Rezultati.

Slike shrani kot PDF v naloga/Skupina30/img/, tabele kot LaTeX v naloga/Skupina30/tabele/.
Vse prebere iz shranjenih rezultatov, zato ne potrebuje omrezja niti procesorskega casa:

    rezultati_sum.csv                 sumni simulator brez popravka branja
    rezultati_zvestoba.csv            sumni simulator s popravkom branja (mthree, TREX)
    idealno.csv                       idealni simulator
    rezultati/rezultati_procesor.csv  procesor ibm_fez
    rezultati/naloge.csv              procesorski cas po nalogah
    rezultati/*_estimator_*.json      paritete po fazah in po faktorjih ojacanja (ZNE)

Pisava je Times (mathptmx), enaka kot v porocilu, zato je potreben LaTeX. Slike so siroke
natanko \\textwidth predloge svmult (117 mm) in jih vkljucimo brez skaliranja,
\\includegraphics{ime.pdf}, da velikost pisave ostane taka, kot je nastavljena tu.

    cd koda && python grafi.py
"""

from pathlib import Path

import matplotlib

matplotlib.use("pdf")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.lines import Line2D
from matplotlib.ticker import FixedLocator, FuncFormatter

from zvestoba import faze, koherenca_bootstrap, nalozi

KODA = Path(__file__).resolve().parent
REZULTATI = KODA / "rezultati"
POGLAVJE = KODA.parent / "naloga" / "Skupina30"
SLIKE = POGLAVJE / "img"
TABELE = POGLAVJE / "tabele"

# videz
###############################################################################

SIRINA = 117 / 25.4          # \textwidth predloge svmult v palcih
PISAVA = 9                   # besedilo poglavja je 10 pt, napisi pod slikami 9 pt
SIGMA = 2                    # napake na slikah so 2 sigma, kot v merilu F - 2 sigma > 0,5
DODATNI_NIZ = "20261121"     # paketi dodatnega niza (datum v imenu paketa)

CRNILO = "#0b0b0b"
CRNILO_2 = "#52514e"
MREZA = "#e4e3df"
SIVA = "#8a8984"
# kategoricne barve v stalnem vrstnem redu (preverjene za barvno slepoto)
MODRA, ORANZNA, ZELENA, RUMENA = "#2a78d6", "#eb6834", "#1baf7a", "#eda100"

BARVA_OBLIKE = {"drevo": MODRA, "veriga": ORANZNA}
OZNAKA_OBLIKE = {"drevo": "o", "veriga": "s"}
IME_OBLIKE = {"drevo": "drevo BFS", "veriga": "linearna veriga"}
KONFIGURACIJE = ("i", "ii", "iii", "iv")
BARVA_KONF = dict(zip(KONFIGURACIJE, (MODRA, ORANZNA, ZELENA, RUMENA)))
OZNAKA_KONF = dict(zip(KONFIGURACIJE, ("o", "s", "^", "D")))
IME_KONF = {"i": "(i) samo popravek branja", "ii": "(ii) + dinamično razklapljanje",
            "iii": "(iii) + Paulijevo sukanje", "iv": "(iv) + ekstrapolacija na ničelni šum"}

plt.rcParams.update({
    "text.usetex": True,
    "text.latex.preamble": r"\usepackage[T1]{fontenc}\usepackage{mathptmx}",
    "font.family": "serif",
    "font.serif": ["Times"],
    "font.size": PISAVA,
    "axes.labelsize": PISAVA,
    "xtick.labelsize": PISAVA,
    "ytick.labelsize": PISAVA,
    "legend.fontsize": PISAVA,
    "text.color": CRNILO,
    "axes.labelcolor": CRNILO,
    "axes.edgecolor": CRNILO_2,
    "axes.linewidth": 0.6,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.grid": True,
    "axes.grid.axis": "y",
    "grid.color": MREZA,
    "grid.linewidth": 0.6,
    "axes.axisbelow": True,
    "xtick.color": CRNILO_2,
    "ytick.color": CRNILO_2,
    "xtick.major.width": 0.6,
    "ytick.major.width": 0.6,
    "xtick.major.size": 3,
    "ytick.major.size": 3,
    "lines.linewidth": 1.0,
    "lines.markersize": 4.5,
    "errorbar.capsize": 2,          # kratke kapice, da so intervali jasno vidni
    "legend.frameon": False,
    "legend.handlelength": 1.8,
    "legend.borderaxespad": 0.3,
    "savefig.bbox": "standard",
    "pdf.fonttype": 42,
})


def vejica(decimalk: int) -> FuncFormatter:
    """Oznake osi z decimalno vejico, kot v besedilu porocila."""
    return FuncFormatter(lambda v, _: f"${v:.{decimalk}f}$".replace(".", "{,}"))


def odtenek(barva: str, delez: float) -> tuple[float, float, float]:
    """Barva, pomesana z belo: delez 1 je polna barva, 0 bela."""
    r, g, b = matplotlib.colors.to_rgb(barva)
    return tuple(1 - delez * (1 - c) for c in (r, g, b))


def temnejsa(barva: str, delez: float) -> tuple[float, float, float]:
    """Barva, pomesana s crno: delez 1 je polna barva, 0 crna."""
    return tuple(delez * c for c in matplotlib.colors.to_rgb(barva))


def st(x: float, decimalk: int = 2) -> str:
    """Stevilo z decimalno vejico za napise v slikah (LaTeX)."""
    return f"{x:.{decimalk}f}".replace(".", "{,}")


def prag(ax, besedilo: bool = True) -> None:
    """Vodoravna crta F = 0,5, meja pristne vecdelne prepletenosti."""
    ax.axhline(0.5, color=SIVA, lw=0.8, ls=(0, (4, 3)), zorder=1)
    if besedilo:
        ax.text(0.01, 0.5, r"$F = 0{,}5$", transform=ax.get_yaxis_transform(),
                ha="left", va="bottom", color=CRNILO_2)


def oznaka_plosce(ax, crka: str) -> None:
    ax.text(0.98, 0.97, f"({crka})", transform=ax.transAxes, ha="right", va="top")


def shrani(fig, ime: str) -> None:
    SLIKE.mkdir(parents=True, exist_ok=True)
    fig.savefig(SLIKE / ime)
    plt.close(fig)
    print(f"  {SLIKE / ime}")


# podatki
###############################################################################

def procesor() -> pd.DataFrame:
    p = pd.read_csv(REZULTATI / "rezultati_procesor.csv")
    p["dodatni"] = p["paket"].str.contains(DODATNI_NIZ)
    p["n"] = p["n"].astype(int)
    return p


def preberi(ime: str) -> pd.DataFrame:
    pot = KODA / ime
    if not pot.exists():
        return pd.DataFrame(columns=["n", "oblika", "F"])
    d = pd.read_csv(pot)
    d["n"] = d["n"].astype(int)
    return d.sort_values("n")


def estimator(oblika: str, n: int, konf: str):
    """Rezultat Estimatorja iz glavnega niza (prva datoteka, ki ustreza)."""
    naloge = pd.read_csv(REZULTATI / "naloge.csv")
    izbor = naloge[(naloge.oblika == oblika) & (naloge.n == n) & (naloge.konfiguracija == konf)
                   & (naloge.primitiv == "estimator")
                   & ~naloge.cas_oddaje.str.startswith("2026-11-21")]
    return nalozi(REZULTATI / izbor.iloc[0].datoteka)[0]


# slika 1: zvestoba v odvisnosti od n v vseh okoljih
###############################################################################

def slika_zvestoba_n() -> None:
    p = procesor()
    p = p[p.konfiguracija == "i"]
    idealno = preberi("idealno.csv")
    sum_ = preberi("rezultati_sum.csv")
    sum_popr = preberi("rezultati_zvestoba.csv")

    # ena plosca na obliko vezja, vse v barvi oblike; simulatorji v svetlejsem odtenku,
    # da procesorske tocke ostanejo v ospredju
    fig, osi = plt.subplots(1, 2, figsize=(SIRINA, 3.05), sharex=True, sharey=True)
    ideal = idealno[idealno.n <= 64]
    for ax, oblika in zip(osi, ("drevo", "veriga")):
        barva, oznaka = BARVA_OBLIKE[oblika], OZNAKA_OBLIKE[oblika]
        prag(ax, besedilo=ax is osi[0])
        i = ideal[ideal.oblika == oblika]
        ax.plot(i.n, i.F, ls="none", marker="x", ms=4, mew=0.9, color=odtenek(barva, 0.55),
                zorder=2)
        s = sum_[sum_.oblika == oblika]
        ax.plot(s.n, s.F, color=odtenek(barva, 0.5), lw=1.2, zorder=2)
        s = sum_popr[sum_popr.oblika == oblika]
        ax.plot(s.n, s.F, color=odtenek(barva, 0.85), lw=1.0, ls=(0, (3, 2)), zorder=2)
        for dodatni, polnilo in ((False, barva), (True, "white")):
            q = p[(p.oblika == oblika) & (p.dodatni == dodatni)]
            ax.errorbar(q.n, q.F, yerr=SIGMA * q.F_napaka, ls="none", marker=oznaka,
                        color=barva, mfc=polnilo, mec=barva, ms=3.8, mew=1.0, elinewidth=0.8,
                        capthick=0.8, zorder=3)
        ax.set_title(IME_OBLIKE[oblika], fontsize=PISAVA, pad=4)
        ax.set_xlabel(r"število kubitov $n$")

    osi[0].set_xlim(0, 66)
    osi[0].set_ylim(0.25, 1.03)
    osi[0].xaxis.set_major_locator(FixedLocator(range(0, 65, 16)))
    osi[0].yaxis.set_major_formatter(vejica(1))
    osi[0].set_ylabel(r"zvestoba $F$")

    # legenda pod ploscama (skupna obema, zato nevtralne barve): levo simulatorji, desno procesor
    siva_oznaka = dict(ls="none", marker="o", color=CRNILO_2, mew=1.0)
    rocaji = [
        Line2D([], [], ls="none", marker="x", ms=4, mew=0.9, color=odtenek(CRNILO_2, 0.55),
               label="idealni simulator"),
        Line2D([], [], color=odtenek(CRNILO_2, 0.5), lw=1.2,
               label="šumni simulator brez popravka branja"),
        Line2D([], [], color=CRNILO_2, lw=1.0, ls=(0, (3, 2)),
               label="šumni simulator s popravkom branja"),
        Line2D([], [], label=r"procesor \texttt{ibm\_fez}, glavni niz", **siva_oznaka),
        Line2D([], [], mfc="white", label=r"procesor \texttt{ibm\_fez}, dodatni niz",
               **siva_oznaka),
    ]
    fig.legend(handles=rocaji, loc="lower center", ncol=2, bbox_to_anchor=(0.5, 0.0),
               handlelength=1.8, columnspacing=1.5, handletextpad=0.5, borderaxespad=0.2)
    fig.tight_layout(pad=0.3, rect=(0, 0.2, 1, 1), w_pad=1.2)
    shrani(fig, "zvestoba_n.pdf")


# slika 2: populaciji in koherenca po konfiguracijah (drevo, procesor)
###############################################################################

def slika_konfiguracije() -> None:
    p = procesor()
    p = p[(p.oblika == "drevo") & ~p.dodatni & (p.n <= 40)]

    fig, (ax_p, ax_c) = plt.subplots(1, 2, figsize=(SIRINA, 3.0), sharex=True)
    for konf in KONFIGURACIJE:
        q = p[p.konfiguracija == konf].sort_values("n")
        slog = dict(color=BARVA_KONF[konf], marker=OZNAKA_KONF[konf], elinewidth=0.8, lw=0.8,
                    ms=3.8, capthick=0.8, label=IME_KONF[konf])
        if konf != "iv":   # (iv) uporablja populaciji iz (iii)
            ax_p.errorbar(q.n, q.P0 + q.P1, yerr=SIGMA * q.P_napaka, **slog)
        ax_c.errorbar(q.n, q.C, yerr=SIGMA * q.C_napaka.fillna(0), **slog)

    for ax, naslov, oznaka in ((ax_p, "populaciji", r"$P_{0\ldots0} + P_{1\ldots1}$"),
                               (ax_c, "koherenca", r"$C$")):
        ax.set_title(naslov, fontsize=PISAVA, pad=4)
        ax.set_xlabel(r"število kubitov $n$")
        ax.set_ylabel(oznaka)
        ax.set_ylim(0.3, 1.0)
        ax.yaxis.set_major_formatter(vejica(1))
    ax_p.xaxis.set_major_locator(FixedLocator([4, 8, 16, 24, 32, 40]))
    ax_p.set_xlim(1, 43)

    # legenda pod ploscama; vrstni red tak, da se v dveh stolpcih bere (i), (ii) / (iii), (iv)
    rocaji, imena = ax_c.get_legend_handles_labels()
    red = [0, 2, 1, 3]
    fig.legend([rocaji[i] for i in red], [imena[i] for i in red], loc="lower center", ncol=2,
               bbox_to_anchor=(0.5, 0.0), handlelength=1.8, columnspacing=1.5,
               handletextpad=0.5, borderaxespad=0.2)
    fig.tight_layout(pad=0.3, rect=(0, 0.15, 1, 1), w_pad=1.5)
    shrani(fig, "konfiguracije.pdf")


# slika 3: paritetna nihanja
###############################################################################

# barve po n, enake na slikah paritet in ekstrapolacije
BARVA_N = {8: MODRA, 24: ORANZNA, 40: ZELENA}


def slika_paritete(nabor=(8, 24, 40)) -> None:
    """Paritete drevesa v (i) v odvisnosti od n*phi mod 2 pi.

    Pariteta niha kot C cos(n phi + phi0), zato v spremenljivki n phi vse tocke danega n
    lezijo na eni kosinusni krivulji z amplitudo C, ne glede na to, koliko nihajev je v [0, 2 pi).
    """
    p = procesor()
    # ena plosca na n, vsaka v svoji barvi
    fig, osi = plt.subplots(1, len(nabor), figsize=(SIRINA, 2.2), sharey=True)
    gosto = np.linspace(0, 2 * np.pi, 400)
    for ax, n in zip(osi, nabor):
        r = estimator("drevo", n, "i")
        par, nap = np.ravel(r.data.evs), np.ravel(r.data.stds)
        phi = faze(n)
        amp = 2 * np.sum(par * np.exp(-1j * n * phi)) / len(phi)
        c = p[(p.oblika == "drevo") & (p.n == n) & (p.konfiguracija == "i") & ~p.dodatni].C.iloc[0]
        ax.axhline(0, color=MREZA, lw=0.6, zorder=1)
        barva = BARVA_N[n]
        # prilagojena krivulja nad tockami v temnejsem odtenku, da je vidna tudi pri n = 40
        ax.plot(gosto, np.abs(amp) * np.cos(gosto + np.angle(amp)), color=temnejsa(barva, 0.6),
                lw=1.0, zorder=4)
        ax.errorbar(np.mod(n * phi, 2 * np.pi), par, yerr=SIGMA * nap, ls="none", marker="o",
                    ms=2.8, color=barva, elinewidth=0.6, capsize=0, zorder=3)
        ax.set_title(rf"$n = {n}$, $C = {st(c)}$", fontsize=PISAVA, pad=4)
        ax.set_xlim(-0.15, 2 * np.pi + 0.15)
        ax.xaxis.set_major_locator(FixedLocator([0, np.pi, 2 * np.pi]))
        ax.xaxis.set_major_formatter(FuncFormatter(
            lambda v, _: ["$0$", r"$\pi$", r"$2\pi$"][int(round(v / np.pi))]))
        ax.set_xlabel(r"$n\varphi \bmod 2\pi$")
    osi[0].set_ylim(-1.15, 1.15)
    osi[0].yaxis.set_major_locator(FixedLocator([-1, -0.5, 0, 0.5, 1]))
    osi[0].yaxis.set_major_formatter(vejica(1))
    osi[0].set_ylabel(r"pariteta $\langle P(\varphi) \rangle$")
    fig.tight_layout(pad=0.3, w_pad=0.8)
    shrani(fig, "paritete.pdf")


# slika 4: ekstrapolacija na nicelni sum (ustvarimo jo, v porocilu pa je ni)
###############################################################################

def koherence_po_faktorjih(n: int) -> tuple[np.ndarray, np.ndarray]:
    """Koherenca pri faktorjih ojacanja 1, 3, 5 iz paritet, ki jih vrne Runtime pri (iv)."""
    r = estimator("drevo", n, "iv")
    evs, stds = np.asarray(r.data.evs_noise_factors), np.asarray(r.data.stds_noise_factors)
    c = [koherenca_bootstrap(n, evs[:, j], stds[:, j]) for j in range(evs.shape[1])]
    return np.array([x[0] for x in c]), np.array([x[1] for x in c])


def slika_zne(nabor=(8, 24, 40)) -> None:
    """Ena plosca na n (kot pri paritetah); oblika oznake pove le, za kaksno tocko gre."""
    p = procesor()
    p = p[(p.oblika == "drevo") & ~p.dodatni]
    faktorji = np.array([1, 3, 5])
    tocke = dict(ls="none", elinewidth=0.8, capthick=0.8, ms=3.8)

    fig, osi = plt.subplots(1, len(nabor), figsize=(SIRINA, 2.75), sharey=True)
    for ax, n in zip(osi, nabor):
        barva = BARVA_N[n]
        c, c_nap = koherence_po_faktorjih(n)
        k, nicla = np.polyfit(faktorji, c, 1)
        x = np.array([0, 5])
        ax.plot(x, nicla + k * x, color=barva, lw=0.8, ls=(0, (3, 2)), zorder=2)
        ax.errorbar(faktorji, c, yerr=SIGMA * c_nap, marker="o", color=barva, zorder=3, **tocke)
        iv = p[(p.n == n) & (p.konfiguracija == "iv")].iloc[0]
        ax.errorbar(0, iv.C, yerr=SIGMA * np.nan_to_num(iv.C_napaka), marker="*", color=barva,
                    zorder=4, **{**tocke, "ms": 7.5})
        # meritev (iii) na istem vezju brez ojacanja, pri natancno lambda = 1
        iii = p[(p.n == n) & (p.konfiguracija == "iii")].iloc[0]
        ax.errorbar(1, iii.C, yerr=SIGMA * iii.C_napaka, marker="o", color=barva, mfc="white",
                    mew=1.0, zorder=3, **tocke)
        print(f"  ZNE n = {n}: C(1, 3, 5) = {np.round(c, 3)}, premica pri 0: {nicla:.3f}, "
              f"Runtime: {iv.C:.3f}, (iii): {iii.C:.3f}")
        ax.set_title(rf"$n = {n}$", fontsize=PISAVA, pad=4)
        ax.set_xlim(-0.5, 5.5)
        ax.xaxis.set_major_locator(FixedLocator([0, 1, 3, 5]))
        ax.set_xlabel(r"faktor ojačanja $\lambda$")
    osi[0].set_ylim(0, 1.05)
    osi[0].yaxis.set_major_formatter(vejica(1))
    osi[0].set_ylabel(r"koherenca $C$")

    # legenda pod ploscami, nevtralne barve, ker velja za vse tri
    siva = dict(ls="none", color=CRNILO_2)
    pomen = [
        Line2D([], [], marker="o", label=r"izmerjeno v (iv) pri $\lambda = 1, 3, 5$", **siva),
        Line2D([], [], marker="*", ms=7.5, label=r"ekstrapolacija na $\lambda = 0$ (Runtime)",
               **siva),
        Line2D([], [], color=CRNILO_2, lw=0.8, ls=(0, (3, 2)), label="premica skozi tri točke"),
        Line2D([], [], marker="o", mfc="white", mew=1.0,
               label=r"izmerjeno v (iii), brez ojačanja", **siva),
    ]
    fig.legend(handles=pomen, loc="lower center", ncol=2, bbox_to_anchor=(0.5, 0.0),
               handlelength=1.8, columnspacing=1.5, handletextpad=0.5, borderaxespad=0.2)
    fig.tight_layout(pad=0.3, rect=(0, 0.17, 1, 1), w_pad=0.8)
    shrani(fig, "zne.pdf")


# tabele
###############################################################################

# slog vseh tabel v poglavju Rezultati: zunanji okvir, navpicne crte za stolpci z oznakami,
# vodoravne crte brez booktabsovega razmika (sicer prekinejo navpicne crte), visje vrstice
SLOG_TABELE = r"""\setlength{\aboverulesep}{0pt}
\setlength{\belowrulesep}{0pt}
\renewcommand{\arraystretch}{1.2}
"""

def zapis(f: float, s: float) -> str:
    """Zvestoba z negotovostjo, npr. 0,607 $\\pm$ 0,015."""
    if not np.isfinite(s):
        return f"{f:.3f}".replace(".", ",")
    return f"{f:.3f} $\\pm$ {s:.3f}".replace(".", ",")


def tabela_rezultati() -> str:
    """Zvestoba po konfiguracijah; vrstice zdruzene po obliki, znotraj nje po nizu meritev."""
    p = procesor()
    p["niz"] = np.where(p.dodatni, "dodatni", np.where(p.n == 4, "testni", "glavni"))
    vrstice = []
    for k, oblika in enumerate(("drevo", "veriga")):
        q_oblika = p[p.oblika == oblika]
        nizi = [niz for niz in ("testni", "glavni", "dodatni") if (q_oblika.niz == niz).any()]
        n_vrstic = sum(q_oblika[q_oblika.niz == niz].n.nunique() for niz in nizi)
        if k:
            vrstice.append(r"\midrule")
        prva_oblike = True
        for j, niz in enumerate(nizi):
            q = q_oblika[q_oblika.niz == niz]
            nji = sorted(q.n.unique())
            if j:
                # \cline (in ne \cmidrule), ker ne zavzame navpicnega prostora in zato ne
                # prekine navpicnih crt
                vrstice.append(r"\cline{2-7}")
            for i, n in enumerate(nji):
                celice = []
                for konf in KONFIGURACIJE:
                    r = q[(q.n == n) & (q.konfiguracija == konf)]
                    if r.empty:
                        celice.append("--")
                        continue
                    r = r.iloc[0]
                    besedilo = zapis(r.F, r.F_napaka)
                    celice.append(rf"{{\boldmath\bfseries {besedilo}}}" if r.GME == 1 else besedilo)
                stolpec_oblika = rf"\multirow{{{n_vrstic}}}{{*}}{{{oblika}}}" if prva_oblike else ""
                stolpec_niz = rf"\multirow{{{len(nji)}}}{{*}}{{{niz}}}" if i == 0 else ""
                prva_oblike = False
                vrstice.append(f"{stolpec_oblika} & {stolpec_niz} & {n} & " + " & ".join(celice)
                               + r" \\")
    telo = "\n".join(vrstice)
    # navpicna crta med obliko in nizom; booktabs okoli vodoravnih crt pusti prazen prostor,
    # ki bi navpicno crto prekinil, zato ga izklopimo in vrstice raje nekoliko razmaknemo
    return (SLOG_TABELE + r"""\begin{tabular*}{\textwidth}{|@{}>{\hspace{5pt}}l@{\hspace{5pt}}|@{}>{\hspace{5pt}}l@{\hspace{5pt}}|@{}>{\hspace{5pt}}r@{\extracolsep{\fill}\hspace{5pt}}cccc<{\hspace{5pt}}@{\extracolsep{0pt}}|}
\toprule
Oblika & Niz & $n$ & (i) & (ii) & (iii) & (iv) \\
\midrule
""" + telo + r"""
\bottomrule
\end{tabular*}
""")


def tabela_meje() -> str:
    """Meja n_max in procesorski cas po konfiguracijah; tabela ni raztegnjena cez celo sirino."""
    p = procesor()
    naloge = pd.read_csv(REZULTATI / "naloge.csv")
    naloge = naloge[(naloge.primitiv != "kalibracija") & ~naloge.cas_oddaje.str.startswith("2026-11-21")]

    def meja(oblika: str, konf: str) -> str:
        q = p[(p.oblika == oblika) & (p.konfiguracija == konf)]
        if q.GME.isna().all():
            return "--"
        glavni = q[~q.dodatni & (q.GME == 1)]
        n_max = int(glavni.n.max())
        ponovljena = q[(q.n == n_max) & q.dodatni]
        # ce ponovitev pri n_max prepletenosti ni dosegla, je meja le zgornja: lezece
        return rf"\textit{{{n_max}}}" if (ponovljena.GME == 0).any() else str(n_max)

    def cas(oblika: str, konf: str, nabor) -> float:
        q = naloge[(naloge.oblika == oblika) & (naloge.konfiguracija == konf) & naloge.n.isin(nabor)]
        return float(q.cas_qpu.sum())

    drevo_n = range(8, 41, 8)
    vrstice = []
    for i, konf in enumerate(KONFIGURACIJE):
        oblika = rf"\multirow{{{len(KONFIGURACIJE)}}}{{*}}{{drevo}}" if i == 0 else ""
        vrstice.append(f"{oblika} & ({konf}) & {meja('drevo', konf)} & {cas('drevo', konf, drevo_n):.0f}"
                       + r" \\")
    vrstice.append(r"\midrule")
    vrstice.append(f"veriga & (i) & {meja('veriga', 'i')} & {cas('veriga', 'i', (16, 32)):.0f}" + r" \\")
    L, R = r"@{}>{\hspace{5pt}}", r"@{\hspace{5pt}}"
    return (SLOG_TABELE + r"\begin{tabular}{|" + L + "l" + R + "|" + L + "l" + R + "|" + L + "c" + R
            + "|" + L + "c" + R + r"""|}
\toprule
Oblika & Konf. & $n_{\mathrm{max}}$ & $t_{\mathrm{QPU}}$ [\si{\second}] \\
\midrule
""" + "\n".join(vrstice) + r"""
\bottomrule
\end{tabular}
""")


def shrani_tabelo(besedilo: str, ime: str) -> None:
    TABELE.mkdir(parents=True, exist_ok=True)
    (TABELE / ime).write_text("% samodejno ustvari koda/grafi.py, ne urejaj rocno\n" + besedilo)
    print(f"  {TABELE / ime}")


if __name__ == "__main__":
    print("slike:")
    slika_zvestoba_n()
    slika_konfiguracije()
    slika_paritete()
    slika_zne()        # le v repozitoriju, v porocilu je ni
    print("tabele:")
    shrani_tabelo(tabela_rezultati(), "rezultati.tex")
    shrani_tabelo(tabela_meje(), "meje.tex")
