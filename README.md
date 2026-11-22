# Koliko kubitov lahko prepletemo?

Seminarska naloga 1 pri predmetu NPMP, skupina 30 -- Veno Jakomin, Jure Pahor in Grega Potočnik.

Merimo, pri kolikšnem številu kubitov procesor IBM še pripravi stanje GHZ z zvestobo nad 0,5, kar je zadosten pogoj za pristno večdelno prepletenost, in koliko to mejo premaknejo dinamično razklapljanje, Paulijevo sukanje ter ekstrapolacija na ničelni šum. Stanje pripravimo na dva načina: z linearno verigo vrat CNOT in z drevesom BFS na grafu povezav procesorja.

## Struktura

- `koda/` -- priprava vezij, simulacije in zagoni
- `naloga/` -- poročilo v predlogi svmult; poglavje naše skupine je v `naloga/Skupina30/main.tex`, viri v skupni `naloga/references.bib`

## Namestitev

```bash
uv venv
VIRTUAL_ENV=.venv uv pip install -r koda/requirements.txt
```

Brez uv enako deluje `python3 -m venv .venv && source .venv/bin/activate && pip install -r koda/requirements.txt`. Potreben je Python 3.12 ali novejši. Simulacije delujejo brez računa IBM; za zagon na pravem procesorju glej naslednje poglavje.

## Zagon na procesorju IBM

Procesorski čas je omejen (Open Plan: 10 minut v 28 dneh na račun), zato vsak član oddaja svoj nabor n s svojega računa in nikoli ne odda ničesar brez predhodnega izpisa ocene porabe.

### 1. Račun IBM Quantum (enkrat na člana)

1. Na [quantum.cloud.ibm.com](https://quantum.cloud.ibm.com) se registriraj z IBMid.
2. Ustvari instanco (*Instances* → *Create instance*) z brezplačnim paketom **Open Plan** in iz seznama instanc kopiraj njen CRN.
3. Na nadzorni plošči ustvari ključ API (*API key* → *Create*) in ga takoj kopiraj, ker ga kasneje ni več mogoče prebrati.

### 2. Shranjevanje računa (zunaj repozitorija)

Program bere račune iz datoteke `qiskit-ibm.json` v mapi **nad** repozitorijem (`../qiskit-ibm.json` glede na koren repozitorija), da ključ nikoli ne pride v git. Vsak član shrani svoj račun pod svojim imenom (`grega`, `jure`, `veno`); ključ in CRN program vpraša, zato ne ostaneta v zgodovini ukazov:

```bash
cd koda && ../.venv/bin/python -c "
from getpass import getpass
from qiskit_ibm_runtime import QiskitRuntimeService
from oddaja import RACUNI
QiskitRuntimeService.save_account(channel='ibm_quantum_platform', token=getpass('kljuc API: '),
    instance=input('CRN instance: ') or None, filename=str(RACUNI), name='grega', overwrite=True)
"
chmod 600 ../../qiskit-ibm.json
```

### 3. Preverjanje povezave (ne porabi procesorskega časa)

```bash
cd koda && ../.venv/bin/python -c "
from qiskit_ibm_runtime import QiskitRuntimeService
from oddaja import RACUNI
s = QiskitRuntimeService(filename=str(RACUNI), name='grega')
b = s.backend('ibm_fez')
print(b.name, 'deluje:', b.status().operational, 'v vrsti:', b.status().pending_jobs)
print('preostanek:', s.usage().get('usage_remaining_seconds'), 's')
"
```

### 4. Oddaja

Program teče, dokler IBM ne vrne vseh rezultatov, kar je ob polni vrsti lahko več ur, zato ga poženemo v `tmux` (`Ctrl+B`, nato `D` odklopi; `tmux attach -t oddaja` vrne). Ne uporabljaj `nohup`, ker program pred oddajo čaka na potrditev.

```bash
tmux new -s oddaja
cd koda
../.venv/bin/python oddaja.py 16 --suho                                   # lokalno, brez računa: kubiti, možnosti, ponovitve
../.venv/bin/python oddaja.py 16 --racun grega                            # drevo, konfiguracije (i)-(iv)
../.venv/bin/python oddaja.py 16 24 --oblika veriga --konf i --racun grega # veriga, samo (i)
```

Pred potrditvijo (`da`) preveri izpis: izbrane kubite (izbrani so iz današnje kalibracije naprave), tabelo vklopljenih tehnik po konfiguracijah ter število nalog, strelov, oceno porabe in preostanek na računu. Program sam zavrne oddajo, če ocena s 30 % rezervo preseže preostanek. Po potrditvi počaka še na kalibracijo mthree in zaključi z izpisom `zabelezeno v rezultati/naloge.csv`; do takrat terminala ne zapiraj, ker se sicer kalibracija mthree izgubi.

Po prvi oddaji večjega n primerjaj dejansko porabo v stolpcu `cas_qpu` z oceno in po potrebi popravi `SEKUND_NA_NALOGO` in `SEKUND_NA_STREL` v `oddaja.py`.

### 5. Po prekinitvi in po koncu

```bash
cd koda && ../.venv/bin/python oddaja.py --dokoncaj --racun grega   # prenese in zabeleži manjkajoče rezultate
cd koda && ../.venv/bin/python procesor.py rezultati/naloge.csv     # zvestoba za vse oddane n
cd koda && ../.venv/bin/python analiza.py                           # prileganje F(n) in meja n_max
```

Mapo `koda/rezultati/` (rezultati, kalibracije, lastnosti naprave, `oddane.csv`, `naloge.csv`) dodamo v git, ker poročilo potrebuje identifikatorje nalog, napravo in število ponovitev.

## Programi

Vsi se poženejo iz mape `koda/` in CSV zapišejo tja.

### `ghz.py` -- vezja in izbira kubitov

Gradi obe obliki vezja za stanje GHZ in izbere, na katerih fizičnih kubitih naj se izvedeta. Graf povezav naprave utežimo z izmerjenimi napakami, povezave z napako vrat CZ in vozlišča z napako branja: za drevo iščemo najcenejši povezan podgraf s pohlepno rastjo po Primovem načelu, za verigo pa pot z iskanjem v globino z vračanjem.

```python
from ghz import ghz_veriga, ghz_drevo
vezje, kubiti = ghz_drevo(n, naprava.target)
prevedeno = transpile(vezje, naprava, initial_layout=kubiti, optimization_level=1)
```

Vezje je zgrajeno na logičnih kubitih od 0 do n-1, logični kubit i pripada fizičnemu `kubiti[i]`, meritev pa vezje ne vsebuje -- doda jih tisti, ki vezje uporabi.

```bash
cd koda && python ghz.py        # -> lastnosti_vezij.csv
```

### `idealno.py` -- preverjanje pravilnosti

Potrdi, da je pripravljeno stanje res GHZ. Ker vektorja stanja pri 100 kubitih ni mogoče zapisati, izmerimo pričakovane vrednosti generatorjev stabilizatorske grupe, torej X na vseh kubitih in Z_0 Z_i za vse i; stanje GHZ je edino, pri katerem so vse te vrednosti enake 1, zato je to dokaz pravilnosti in ne vzorčni test. Simulacija je izvedljiva v matričnem produktnem zapisu, ker ima GHZ vezno dimenzijo 2 in zato porabi O(n) namesto 2^n števil. Isti program izmeri še zvestobo iz populacij in paritetnih nihanj.

```bash
cd koda && python idealno.py    # -> idealno.csv
```

### `sum.py` -- šumne simulacije in ekstrapolacija

Isti vezji na šumnem modelu naprave `FakeFez`. Vsebuje lastno izvedbo ekstrapolacije na ničelni šum: vsaka vrata CZ nadomestimo z lambda kopijami, in ker je CZ sam svoj inverz, je za lihe lambda vezje matematično nespremenjeno, fizično pa gre skozi lambda-krat več šumnih vrat. Koherence pri lambda = 1, 3, 5 nato ekstrapoliramo premico na lambda = 0. Prepogibanje mora biti izvedeno po prevajanju, prepognjeno vezje pa se ne sme ponovno prevajati, sicer prevajalnik kopije takoj odstrani.

```bash
cd koda && python sum.py             # privzeto n = 4, 8, ..., 32
cd koda && python sum.py 36 40 44    # izbrane vrednosti n
# -> rezultati_sum.csv
```

Privzeto je 1024 ponovitev meritve in faktorji ojačanja 1, 3, 5. Čas raste kot n^2, zato zagon do n = 32 vzame okoli uro in pol.

### `zvestoba.py` -- cevovod za zvestobo

Skupne funkcije za oceno zvestobe iz surovih rezultatov primitivov SamplerV2 in EstimatorV2, enake za procesor in simulator. Populaciji popravi z mthree in njuno negotovost oceni z vzorčenjem bootstrap znotraj popravka, koherenco odčita iz paritet pri 2n+2 fazah in negotovost oceni s parametričnim bootstrapom iz napak ocenjevalnika, pri ekstrapolaciji pa v skupno napako vključi tudi negotovost prilagajanja premice. GME razglasi le pri F - 2 sigma > 0,5.

```python
from zvestoba import pripravi_vezja, stevci_iz_samplerja, paritete_iz_estimatorja, oceni, oceni_zne
v = pripravi_vezja(n, "drevo", naprava)   # populacijsko, paritetno, estimatorsko, opazljivka, kubiti
stevci = stevci_iz_samplerja(rezultat_samplerja, 0)
paritete, napake = paritete_iz_estimatorja(rezultat_estimatorja, 0)
r = oceni(n, stevci, paritete, napake, v.kubiti, mit)   # P0, P1, C, F, F_napaka, GME
r = oceni_zne(r, (1, 3, 5), koherence, napake_koherenc)  # doda C_zne, F_zne, GME_zne
```

Vezja iz `pripravi_vezja` so prevedena na iste fizične kubite, opazljivka X^n pa je že preslikana nanje. Rezultate nalog s procesorja shranimo s `shrani(rezultat, pot)` in beremo z `nalozi(pot)`, da analiza ne potrebuje omrežja; `mit` je `M3Mitigation`, kalibriran na `v.kubiti`.

```bash
cd koda && python zvestoba.py          # lokalni preizkus na FakeFez, privzeto n = 4, 8, 12
cd koda && python zvestoba.py 16 20    # -> rezultati_zvestoba.csv
```

Preizkus teče na Aerjevih primitivih z metodo MPS, ker lokalni način Runtime (`SamplerV2(mode=FakeFez())`) pri Estimatorju poskuša simulirati vseh 156 kubitov z vektorjem stanja in odpove. Aerjev Estimator ne vsebuje napake branja, zato njegova koherenca ustreza meritvi s popravkom TREX; koherenca iz Samplerja (stolpec `C_sampler`) napako branja vsebuje.

### `procesor.py` -- zvestoba iz nalog s procesorja

Povezava med oddajo nalog in analizo. Oddajni program (`oddaja.py`) po vsaki nalogi pokliče `zabelezi`, ki počaka na rezultat, ga shrani v JSON z imenom `<oblika>_<n>_<konfiguracija>_<primitiv>_<naloga>.json` (identifikator naloge prepreči prepis ob ponovni oddaji) in v `naloge.csv` vpiše identifikator naloge, napravo, račun, čas oddaje, uporabljene kubite, število ponovitev in porabljen procesorski čas. `kalibriraj` opravi kalibracijo mthree v istem paketu kot meritve in jo shrani v JSON, da analiza popravek branja izvede s kalibracijo tistega dne; tudi kalibracijske naloge so vpisane v `naloge.csv` (primitiv `kalibracija`).

Analiza nato vsako trojico (n, oblika, konfiguracija) oceni iz shranjenih datotek brez omrežja: populaciji iz prvega PUB-a Samplerja s popravkom mthree, paritete iz Estimatorja (ali iz drugega PUB-a Samplerja, če Estimatorja ni), procesorski čas kot vsoto obeh nalog. Konfiguracija (iv) se od (iii) razlikuje le pri koherenci, zato populaciji vzame iz Samplerja (iii) in GME zanjo ni razglašen.

```bash
cd koda && python procesor.py rezultati/naloge.csv    # -> rezultati/rezultati_procesor.csv
```

### `oddaja.py` -- oddaja nalog na procesor

Za vsak n v enem paketu (`Batch`) odda vse naloge na istih vezjih in kubitih: Sampler za populaciji pri konfiguracijah (i)--(iii), Estimator za koherenco pri (i)--(iv) in kalibracijo mthree. Konfiguracije: (i) le popravek branja (mthree za populaciji, TREX za C), (ii) + DD XY4, (iii) + sukanje vrat, (iv) + ZNE na C (faktorji 1, 3, 5, linearna ekstrapolacija). Vse konfiguracije imajo enako število ponovitev: 4096 pri Samplerju, ker napaka populacij prevladuje v napaki zvestobe in je Sampler z enim vezjem poceni, in 512 na fazo pri Estimatorju, ker koherenco ocenimo iz 2n+2 faz hkrati in je zato že pri 512 ponovitvah natančnejša od populacij. Kalibracija mthree ostane pri 1024 ponovitvah. Paritet s Samplerjem na procesorju ne merimo, ker bi podvojile porabo za isto količino.

Pred oddajo vse naloge lokalno pripravi natanko tako, kot jih primitivi pripravijo pred pošiljanjem, s čimer preveri možnosti in prešteje strele. Porabo oceni kot `SEKUND_NA_NALOGO` na nalogo in `SEKUND_NA_STREL` na strel (konstanti nastavimo iz testne naloge). Če ocena, povečana za 30 %, presega preostanek časa na računu, ne odda ničesar; sicer izpiše oceno in zahteva potrditev. Suha oddaja na strežniku (`dry_run`) za račune Open Plan ni na voljo. Vsako oddano nalogo takoj vpiše v `oddane.csv`, zato se ob prekinitvi nič ne izgubi: `--dokoncaj` shrani in zabeleži vse oddane naloge, ki še niso v `naloge.csv`.

Nastavitev računa in potek oddaje sta opisana v poglavju [Zagon na procesorju IBM](#zagon-na-procesorju-ibm).

```bash
cd koda && python oddaja.py 4 8 --suho                         # izpis na FakeFez, brez oddaje
cd koda && python oddaja.py 4 --racun grega                    # priprava, ocena porabe, potrditev, oddaja
cd koda && python oddaja.py --dokoncaj --racun grega           # dokonca belezenje po prekinitvi
# -> rezultati/
```

### `analiza.py` -- prileganje krivulje in meja n_max

Iz tabel zvestobe za vsako okolje, obliko in konfiguracijo prilagodi eksponentni upad F(n) = a exp(-n/n0), utežen z napakami točk, in mejo n_max izračuna kot presečišče krivulje z 0,5, torej n_max = n0 ln(2a). Negotovost meje oceni s parametričnim bootstrapom: vsako točko prevzorči znotraj njene napake, krivuljo prilagodi znova in iz porazdelitve presečišč vzame standardni odklon ter 16. in 84. percentil. Poleg prilagojene meje poroča še izmerjeno, torej največji n, pri katerem velja F - 2 sigma > 0,5, in zastavico, če presečišče leži zunaj izmerjenega razpona. Iz koherence oceni še efektivno verjetnost defaziranja na kubit po modelu C(n) = c0 (1 - 2p)^n. Za vsako konfiguracijo nazadnje izračuna razliko meje in procesorskega časa proti osnovni konfiguraciji (i) ter njuno razmerje.

```bash
cd koda && python analiza.py                                     # rezultati_zvestoba.csv in rezultati_procesor.csv, če obstajata
cd koda && python analiza.py rezultati_zvestoba.csv druga.csv    # poljubne tabele; okolje je ime datoteke brez "rezultati_"
# -> analiza.csv
```

Vhodna tabela potrebuje stolpce n, oblika in F; stolpci konfiguracija, F_napaka, C, C_napaka in cas_qpu so neobvezni (brez napak je prileganje neuteženo in bootstrap izpuščen). Za prileganje so potrebne vsaj tri točke.

### `grafi.py` -- slike in tabele za poglavje Rezultati

Iz shranjenih rezultatov (brez omrežja) nariše slike v `naloga/Skupina30/img/` (`zvestoba_n.pdf`, `konfiguracije.pdf`, `paritete.pdf`; `zne.pdf` z ekstrapolacijo na ničelni šum ustvari, a je poročilo ne vključuje) in zapiše tabeli `naloga/Skupina30/tabele/rezultati.tex` in `meje.tex`, ki ju poročilo vključi z `\input`. Pisava je Times iz paketa mathptmx kot v poročilu, zato je potreben LaTeX; slike so široke natanko `\textwidth` predloge svmult in se vključijo brez skaliranja. Po novih simulacijah program preprosto ponovno poženemo.

```bash
cd koda && python grafi.py
```

## Izhodne datoteke

| datoteka | vsebina |
|---|---|
| `lastnosti_vezij.csv` | število vrat CNOT in globina pred prevajanjem ter število vrat CZ in globina po prevajanju |
| `idealno.csv` | najmanjša pričakovana vrednost stabilizatorja, populaciji P0 in P1, koherenca C, zvestoba F |
| `rezultati_sum.csv` | P0, P1, C in F na šumnem modelu, koherence pri faktorjih 1, 3 in 5 ter ekstrapolirani C_zne in F_zne |
| `rezultati_zvestoba.csv` | populaciji z mthree, koherenca iz Estimatorja, F z napako in zastavica GME; za primerjavo koherenca iz Samplerja ter surovi populaciji |
| `rezultati/oddane.csv` | ena vrstica na nalogo, zapisana takoj ob oddaji; osnova za `--dokoncaj` |
| `rezultati/naloge.csv` | ena vrstica na zabeleženo nalogo: n, oblika, konfiguracija, primitiv, identifikator, datoteka, kubiti, ponovitve, čas QPU, kalibracija, naprava, račun, čas oddaje, lastnosti naprave |
| `rezultati/*.json` | rezultati nalog, kalibracije mthree (`kalibracija_*`) in lastnosti naprave ob izvedbi (`lastnosti_*`) |
| `rezultati_procesor.csv` | isti stolpci kot `rezultati_zvestoba.csv` ter konfiguracija, zastavica popravka mthree, čas QPU in identifikatorji nalog |
| `analiza.csv` | po okolju, obliki in konfiguraciji: parametra a in n0, meja n_max z napako in percentiloma, zastavica ekstrapolacije, izmerjena meja, verjetnost defaziranja p, čas QPU ter razlika meje in časa proti konfiguraciji (i) |

Zvestobo računamo kot F = (P_0...0 + P_1...1)/2 + C/2, koherenco pa iz amplitude paritetnih nihanj pri 2n+2 fazah, kar je ravno nad Nyquistovo mejo za nihanje s frekvenco n.

## Opombe

- Simulacije tečejo na odlitku `FakeFez`, ki vsebuje kalibracijske podatke prave naprave in ne porablja procesorskega časa.
- Šumni model je markovski in ne vsebuje koherentnih napak, zato na njem učinka dinamičnega razklapljanja in Paulijevega sukanja ni mogoče ovrednotiti; ti dve tehniki merimo na pravem procesorju.
- Poročilo prevedemo z `cd naloga && latexmk -pdf editor.tex`.
