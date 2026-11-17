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

## Izhodne datoteke

| datoteka | vsebina |
|---|---|
| `lastnosti_vezij.csv` | število vrat CNOT in globina pred prevajanjem ter število vrat CZ in globina po prevajanju |
| `idealno.csv` | najmanjša pričakovana vrednost stabilizatorja, populaciji P0 in P1, koherenca C, zvestoba F |
| `rezultati_sum.csv` | P0, P1, C in F na šumnem modelu, koherence pri faktorjih 1, 3 in 5 ter ekstrapolirani C_zne in F_zne |

Zvestobo računamo kot F = (P_0...0 + P_1...1)/2 + C/2, koherenco pa iz amplitude paritetnih nihanj pri 2n+2 fazah, kar je ravno nad Nyquistovo mejo za nihanje s frekvenco n.

## Opombe

- Simulacije tečejo na odlitku `FakeFez`, ki vsebuje kalibracijske podatke prave naprave in ne porablja procesorskega časa.
- Šumni model je markovski in ne vsebuje koherentnih napak, zato na njem učinka dinamičnega razklapljanja in Paulijevega sukanja ni mogoče ovrednotiti; ti dve tehniki merimo na pravem procesorju.
- Poročilo prevedemo z `cd naloga && latexmk -pdf editor.tex`.
