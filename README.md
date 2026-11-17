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

Brez uv enako deluje `python3 -m venv .venv && source .venv/bin/activate && pip install -r koda/requirements.txt`. Potreben je Python 3.12 ali novejši. Za zagon na pravem procesorju je potreben še račun IBM Quantum s shranjenim žetonom; simulacije delujejo brez njega.

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

Povezava med oddajo nalog in analizo. Oddajni program po vsaki nalogi pokliče `zabelezi`, ki počaka na rezultat, ga shrani v JSON z dogovorjenim imenom `<oblika>_<n>_<konfiguracija>_<primitiv>.json` in v `naloge.csv` vpiše identifikator naloge, uporabljene kubite, število ponovitev in porabljen procesorski čas. Pred prvo nalogo na danih kubitih pokliče še `kalibriraj`, ki kalibracijo mthree opravi na napravi in jo shrani v JSON, da analiza popravek branja izvede s kalibracijo tistega dne.

```python
from procesor import kalibriraj, zabelezi
v = pripravi_vezja(n, "drevo", naprava)
kalibriraj(naprava, v.kubiti, "rezultati/kalibracija_drevo_8.json")
naloga_s = sampler.run([v.populacijsko, (v.paritetno, phi[:, None])], shots=1024)
naloga_e = estimator.run([(v.estimatorsko, v.opazljivka, phi[:, None])])
zabelezi(naloga_s, n, "drevo", "i", "sampler", v.kubiti, 1024, "rezultati", "kalibracija_drevo_8.json")
zabelezi(naloga_e, n, "drevo", "i", "estimator", v.kubiti, 1024, "rezultati")
```

Analiza nato vsako trojico (n, oblika, konfiguracija) oceni iz shranjenih datotek brez omrežja: populaciji iz prvega PUB-a Samplerja s popravkom mthree, paritete iz Estimatorja (ali iz drugega PUB-a Samplerja, če Estimatorja ni), procesorski čas kot vsoto obeh nalog.

```bash
cd koda && python procesor.py rezultati/naloge.csv    # -> rezultati/rezultati_procesor.csv
```

### `analiza.py` -- prileganje krivulje in meja n_max

Iz tabel zvestobe za vsako okolje, obliko in konfiguracijo prilagodi eksponentni upad F(n) = a exp(-n/n0), utežen z napakami točk, in mejo n_max izračuna kot presečišče krivulje z 0,5, torej n_max = n0 ln(2a). Negotovost meje oceni s parametričnim bootstrapom: vsako točko prevzorči znotraj njene napake, krivuljo prilagodi znova in iz porazdelitve presečišč vzame standardni odklon ter 16. in 84. percentil. Poleg prilagojene meje poroča še izmerjeno, torej največji n, pri katerem velja F - 2 sigma > 0,5, in zastavico, če presečišče leži zunaj izmerjenega razpona. Iz koherence oceni še efektivno verjetnost defaziranja na kubit po modelu C(n) = c0 (1 - 2p)^n. Za vsako konfiguracijo nazadnje izračuna razliko meje in procesorskega časa proti osnovni konfiguraciji (i) ter njuno razmerje.

```bash
cd koda && python analiza.py                                     # rezultati_zvestoba.csv in rezultati_procesor.csv, če obstajata
cd koda && python analiza.py rezultati_zvestoba.csv druga.csv    # poljubne tabele; okolje je ime datoteke brez "rezultati_"
# -> analiza.csv
```

Vhodna tabela potrebuje stolpce n, oblika in F; stolpci konfiguracija, F_napaka, C, C_napaka in cas_qpu so neobvezni (brez napak je prileganje neuteženo in bootstrap izpuščen). Za prileganje so potrebne vsaj tri točke.

## Izhodne datoteke

| datoteka | vsebina |
|---|---|
| `lastnosti_vezij.csv` | število vrat CNOT in globina pred prevajanjem ter število vrat CZ in globina po prevajanju |
| `idealno.csv` | najmanjša pričakovana vrednost stabilizatorja, populaciji P0 in P1, koherenca C, zvestoba F |
| `rezultati_sum.csv` | P0, P1, C in F na šumnem modelu, koherence pri faktorjih 1, 3 in 5 ter ekstrapolirani C_zne in F_zne |
| `rezultati_zvestoba.csv` | populaciji z mthree, koherenca iz Estimatorja, F z napako in zastavica GME; za primerjavo koherenca iz Samplerja ter surovi populaciji |
| `naloge.csv` | ena vrstica na nalogo s procesorja: n, oblika, konfiguracija, primitiv, identifikator, datoteka, kubiti, ponovitve, čas QPU, kalibracija |
| `rezultati_procesor.csv` | isti stolpci kot `rezultati_zvestoba.csv` ter konfiguracija, zastavica popravka mthree, čas QPU in identifikatorji nalog |
| `analiza.csv` | po okolju, obliki in konfiguraciji: parametra a in n0, meja n_max z napako in percentiloma, zastavica ekstrapolacije, izmerjena meja, verjetnost defaziranja p, čas QPU ter razlika meje in časa proti konfiguraciji (i) |

Zvestobo računamo kot F = (P_0...0 + P_1...1)/2 + C/2, koherenco pa iz amplitude paritetnih nihanj pri 2n+2 fazah, kar je ravno nad Nyquistovo mejo za nihanje s frekvenco n.

## Opombe

- Simulacije tečejo na odlitku `FakeFez`, ki vsebuje kalibracijske podatke prave naprave in ne porablja procesorskega časa.
- Šumni model je markovski in ne vsebuje koherentnih napak, zato na njem učinka dinamičnega razklapljanja in Paulijevega sukanja ni mogoče ovrednotiti; ti dve tehniki merimo na pravem procesorju.
- Poročilo prevedemo z `cd naloga && latexmk -pdf editor.tex`.
