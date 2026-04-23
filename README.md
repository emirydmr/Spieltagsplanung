# Spieltagsplaner – WFV Bezirk Franken

> Automatisierte Staffeleinteilung und Spielplanerstellung für den Jugendfußball  
> Württembergischer Fußballverband (WFV), Bezirk Franken

---

## Inhaltsverzeichnis

1. [Überblick](#überblick)
2. [Installation & Start](#installation--start)
3. [Projektstruktur](#projektstruktur)
4. [Pipeline-Übersicht](#pipeline-übersicht)
5. [Daten-Import (Meldeliste)](#1-daten-import-meldeliste)
6. [Staffeleinteilung (Liga-Einteilungs-Algorithmus)](#2-staffeleinteilung-liga-einteilungs-algorithmus)
7. [Spielplanerstellung](#3-spielplanerstellung)
8. [API-Endpunkte](#api-endpunkte)
9. [Benutzeroberfläche (UI)](#benutzeroberfläche-ui)
10. [Konfigurationsdateien](#konfigurationsdateien)
11. [Tests](#tests)
12. [Technologie-Stack](#technologie-stack)
13. [Logging & Debugging](#logging--debugging)
14. [Spielplan-Logs](#spielplan-logs)

---

## Überblick

Der Spieltagsplaner unterstützt die Staffelleiter des Bezirks Franken bei zwei Kernaufgaben:

1. **Staffeleinteilung**: Automatische Zuordnung von ~560 Jugendmannschaften (13 Altersklassen, A- bis E-Junioren + Juniorinnen) in ~114 Staffeln – optimiert nach geografischer Nähe, regionaler Zugehörigkeit und Staffelgrößen-Balance.
2. **Spielplanerstellung**: Generierung konfliktfreier Spielpläne für ~3.064 Spiele pro Saison – mit Schlüsselzahlen-Vergabe, Terminplan-Zuordnung, Vereinswunsch-Berücksichtigung und CP-SAT-basierter Venue-Konfliktauflösung.

### Maßstab der realen Daten

| Kennzahl | Wert |
|---|---|
| Teams | ~560 |
| Staffeln | ~114 |
| Altersklassen | 13 (A/B/C/D/E-Junioren + B/C/D-Juniorinnen) |
| Spiele pro Saison | ~3.064 |
| Teams mit Wünschen | ~266 |
| Simulated Annealing (SA) | ~12 min (alle Staffeln) |
| CP-SAT Slot-Solver | ~2 min |
| **Gesamt-Pipeline** | **~14 min** |

---

## Installation & Start

### Voraussetzungen
- Windows 10/11
- Internetzugang (nur für Ersteinrichtung)
- Python wird bei Bedarf automatisch installiert

### Option A: Ferninstallation (1 Datei)

Nur die Datei `install.bat` herunterladen und doppelklicken:

```
https://github.com/emirydmr/Spieltagsplanung/raw/marek/install.bat
```

Was passiert automatisch:
1. Prüft ob Python installiert ist (installiert Python 3.13 falls nötig)
2. Lädt das Projekt als ZIP von GitHub herunter
3. Entpackt nach `C:\Users\<Name>\Spieltagsplaner\`
4. Erstellt virtuelle Umgebung + installiert alle Pakete
5. Generiert App-Icon aus dem WFV-Logo
6. Erstellt Desktop-Verknüpfung "Spieltagsplaner" mit WFV-Icon
7. Fragt ob direkt gestartet werden soll

Bei erneutem Ausführen: Update (neuer Code wird kopiert, `.venv` und `output/` bleiben erhalten).

### Option B: Lokales Setup

```bash
# Automatisches Setup (erstellt .venv, installiert Dependencies, Desktop-Verknüpfung)
setup.bat

# Oder manuell:
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
```

### Starten
```bash
# Option 1: Desktop-Verknüpfung "Spieltagsplaner" (nach Setup)
# → GUI-Fenster mit WFV-Logo, startet Server automatisch, öffnet Browser

# Option 2: GUI-Launcher direkt
.venv\Scripts\pythonw.exe launcher.pyw

# Option 3: Batch-Skript (Terminal-basiert)
start.bat

# Option 4: Direkt
.venv\Scripts\python -m uvicorn src.api.server:app --port 8000
```

Der Server läuft auf `http://localhost:8000`. Die Web-UI öffnet sich unter `/app`.

### GUI-Launcher (`launcher.pyw`)

Kleines Tkinter-Fenster mit:
- WFV-Logo
- Status-Anzeige (Bereit / Startet / Läuft) mit farbigem Indikator
- **Starten** – startet den Server im Hintergrund
- **Browser öffnen** – öffnet die Web-UI
- **Beenden** – stoppt Server und schließt das Fenster
- Startet automatisch wenn `.venv` vorhanden ist
- Kein Terminal-Fenster (`.pyw`-Extension)

---

## Projektstruktur

```
Spieltagsplaner/
├── src/                          # Quellcode
│   ├── api/
│   │   └── server.py             # FastAPI Backend (alle Endpunkte)
│   ├── common/
│   │   ├── models.py             # Datenmodelle (Mannschaft, Spielstaette, Staffel)
│   │   ├── distanz.py            # Geocoding (Nominatim), Haversine, Distanzmatrix
│   │   └── erstelle_distanzmatrix.py  # CLI-Tool zur Distanzmatrix-Erstellung
│   ├── data_import/
│   │   ├── meldeliste_parser.py  # DFBnet Excel-Parser
│   │   └── rueckrunde_parser.py  # Rückrunde-Einteilungs-Parser
│   ├── spielplanerstellung/
│   │   ├── spielplan.py          # Spielplan-Generator (Orchestrierung)
│   │   ├── schluesselplan.py     # Round-Robin Paarungstabellen (DFBnet 1-L Schema)
│   │   ├── sz_vergabe.py         # Schlüsselzahlen-Vergabe (SA + Brute-Force)
│   │   ├── slot_solver.py        # CP-SAT Solver (konfliktfreie Slot-Vergabe)
│   │   ├── terminplan.py         # Rahmenterminkalender (Daten pro AK)
│   │   ├── wuensche.py           # Wunsch-Datenmodelle (Kategorien, Prioritäten)
│   │   └── wuensche_parser.py    # LLM-basierte Wunsch-Extraktion (Ollama/OpenAI)
│   └── staffeleinteilung/
│       ├── algorithmus.py        # Einteilungs-Algorithmus (Geo-Clustering + Swaps)
│       ├── scoring.py            # Score-Berechnung (Distanz, Region, Balance, HC)
│       ├── ANFORDERUNGEN.md      # Fachliche Anforderungen
│       └── run_einteilung.py     # CLI-Runner
├── ui/                           # Web-Frontend
│   ├── index.html                # Landingpage
│   ├── app.html                  # Hauptanwendung (Einteilung + Spielplan)
│   ├── builder.html              # Manueller Staffel-Builder (Drag & Drop)
│   └── assets/
│       ├── app.js                # Client-Logik
│       ├── builder.js            # Builder-Logik
│       └── style.css             # Styling
├── config/
│   ├── geocode_cache.json        # Gecachte Geokoordinaten aller Spielstätten
│   └── distanzmatrix.csv         # Paarweise Luftlinien-Distanzen (km)
├── anleitung/                    # PDF-Anleitungen (WFV-Dokumente)
├── output/                       # Generierte Einteilungsdateien
├── spielplan_logs/               # Persistierte Spielplan-JSON-Dateien
├── raw_data/                     # Eingabe-Excel-Dateien
├── tests/                        # Testdateien
├── requirements.txt              # Python-Abhängigkeiten
├── setup.bat / install.bat       # Windows-Setup-Skripte
├── start.bat                     # Server-Startskript
└── launcher.pyw                  # GUI-Launcher (Tkinter)
```

---

## Pipeline-Übersicht

Die gesamte Verarbeitung folgt einer mehrstufigen Pipeline:

```
Meldeliste (Excel)
    │
    ▼
┌──────────────────────────┐
│ 1. DATEN-IMPORT          │  meldeliste_parser.py
│    Excel → Mannschaften  │  + Geocoding (Nominatim)
│    + Koordinaten-Cache   │  + Vereins-Fallback
└──────────┬───────────────┘
           │
           ▼
┌──────────────────────────┐
│ 2. STAFFELEINTEILUNG     │  algorithmus.py + scoring.py
│    Gruppierung → Töpfe   │
│    Geo-Clustering        │
│    Duplikat-Reparatur    │
│    Swap-Optimierung      │
└──────────┬───────────────┘
           │
           ▼
┌──────────────────────────┐
│ 3. SZ-VERGABE            │  sz_vergabe.py
│    Brute-Force (≤7)      │
│    Simulated Annealing   │
│    Wünsche-Scoring       │
└──────────┬───────────────┘
           │
           ▼
┌──────────────────────────┐
│ 4. SPIELPLAN-GENERIERUNG │  spielplan.py
│    Schlüsselplan (1-L)   │
│    Terminplan-Zuordnung  │
│    Cross-Staffel SZ-Opt  │
│    Spieltag-Reordering   │
└──────────┬───────────────┘
           │
           ▼
┌──────────────────────────┐
│ 5. CP-SAT SLOT-SOLVER    │  slot_solver.py
│    15-Min-Raster         │
│    Cumulative-Constraint │
│    Wunsch-Optimierung    │
│    Greedy Repair         │
└──────────┬───────────────┘
           │
           ▼
    Spielplan (JSON/Excel)
```

---

## 1. Daten-Import (Meldeliste)

### Datei: `src/data_import/meldeliste_parser.py`

Parst die DFBnet-Meldeliste (Excel-Export). Unterstützt zwei Formate:

#### Erwartete Excel-Spalten

| Interner Name | Excel-Header (Aliases) |
|---|---|
| `verein_nr` | "V. Nr.", "V.Nr." |
| `vereinsname` | "Vereinsname" |
| `mannschaftsname` | "Mannschaftsname" |
| `altersklasse` | "MS-Art" |
| `spielklasse` | "Spielklasse" |
| `region` | "Region" |
| `bezirk_alt` | "Bezirk alt" |
| `ms_nr` | "MS-Nr.", "MS-Nr" |
| `topf` | "Topf" |
| `wuensche` | "Wünsche" |
| `spielfeld_1`...`spielfeld_4` | "Spielfeld 1"..."Spielfeld 4" |
| `spielstaette_name` | "Spielstätte" |
| `strasse` | "Straße" |
| `plz` / `ort` | "PLZ" / "Ort" |

#### Format-Erkennung

- **Format 24/25**: Spielstätte als kombinierter String im Feld "Spielfeld 1" (`"Name, Straße, PLZ Ort"`)
- **Format 25/26**: Separate Spalten für Spielstätte, Straße, PLZ, Ort
- **Formel-Erkennung**: Wenn der Wert in "Straße" mit `=` beginnt (Excel-Formel), wird stattdessen "Spielfeld 1" verwendet

#### Topf-Ableitung

```
Explizite Topf-Spalte vorhanden → verwende diese
Sonst: MS-Nr. 1 → Topf 1, MS-Nr. 2+ → Topf 2
```

### Geocoding (`src/common/distanz.py`)

Spielstätten-Adressen werden über **Nominatim (OpenStreetMap)** geocodiert.

#### Fallback-Strategie (5 Stufen)
1. Originaladresse + ", Deutschland"
2. Ohne "-Zentrum"-Suffix
3. Ohne Vereinsnamen-Prefix (bei >2 Komma-Teilen)
4. Nur PLZ + Ortsname (ohne Stadtteil)
5. Nur PLZ → Stadtmitte

Ergebnisse werden in `config/geocode_cache.json` persistent gecacht (kein erneuter API-Call bei wiederholtem Import).

#### Vereins-Fallback
Teams ohne eigene Spielstätte erhalten automatisch die Spielstätte eines anderen Teams desselben Vereins (gleiche `verein_nr`).

### Haversine-Distanz

```python
R = 6371.0  # Erdradius in km
d = R × 2 × atan2(√a, √(1−a))
# wobei a = sin²(Δlat/2) + cos(lat1) × cos(lat2) × sin²(Δlon/2)
```

### Rückrunde-Parser (`src/data_import/rueckrunde_parser.py`)

Parst die vom Spielleiter vorgegebene Rückrunde-Einteilung (Excel).

- **Erkennung**: Staffel-Header per Regex (`A-Junioren Leistungsstaffel 1`, `B-Junioren Kreisstaffel 2`, etc.)
- **Layout**: Bis zu 3 Staffel-Blöcke nebeneinander, Teams darunter mit Rang/Name/Punkte/Quotient
- **Matching gegen Meldeliste** (5-stufig):
  1. Exakter Name + Altersklasse
  2. Exakter Name ohne AK
  3. Substring-Match mit AK-Präferenz
  4. Substring-Match ohne AK
  5. Wort-basierter Fuzzy-Match (≥2 gemeinsame Wörter, inkl. Abkürzungs-Match auf 4 Zeichen)

---

## 2. Staffeleinteilung (Liga-Einteilungs-Algorithmus)

### Datei: `src/staffeleinteilung/algorithmus.py`

### Konzepte

#### Topf (Leistungstopf)
Jede Mannschaft gehört einem **Topf** an:
- **Topf 1**: 1. Mannschaft eines Vereins (leistungsorientiert)
- **Topf 2**: 2./3. Mannschaft (breitenorientiert)
- Mannschaften verschiedener Töpfe werden getrennt eingeteilt.

#### Regionenstaffel
Staffeln der höchsten Spielklasse (Regionenstaffel, Verbandsstaffel, Landesstaffel). Diese haben eine **fixe Zusammensetzung** (durch Auf-/Abstieg bestimmt) und werden **nicht** vom Algorithmus optimiert (`topf=0`).

#### Regionen

| Region | Gebiet |
|---|---|
| Unterland | Bezirk Franken – Unterland |
| Hohenlohe Nord | Bezirk Franken – Hohenlohe |
| Hohenlohe Süd | Schwäbisch Hall + Crailsheim (Bezirk Rems/Murr/Hall) |

### Algorithmus (5 Schritte)

#### Schritt 1: Gruppierung (`gruppiere_mannschaften`)

Mannschaften werden nach `(Altersklasse, Spielklasse_grob, Topf)` gruppiert:
- Regionenstaffeln → `topf=0` (fix, wird übersprungen)
- Qualistaffeln → `topf=1` oder `topf=2`
- **Juniorinnen-Merge**: Wenn Topf 2 oder Regionenstaffel weniger als 5 Teams hat, wird in Topf 1 gemergt.

#### Schritt 2: Staffelanzahl bestimmen (`bestimme_staffelanzahl`)

```python
Parameter:
  min_size = 5    # Minimale Staffelgröße
  max_size = 12   # Maximale Staffelgröße (konfigurierbar, default 11)
  target_size = 8 # Ziel-Staffelgröße

Algorithmus:
  Für n_staffeln in [⌈n/max⌉ ... ⌊n/min⌋+1]:
    avg = n / n_staffeln
    Wenn min ≤ avg ≤ max: wähle n_staffeln mit geringstem |avg - target|
```

#### Schritt 3: Initiale Geo-Zuweisung (`_initiale_zuweisung_geo`)

Einfacher geografischer Split:
1. Sortiere alle Mannschaften nach **Längengrad** (West → Ost)
2. Teile in `n_staffeln` gleichgroße Gruppen auf
3. Funktioniert gut für den Bezirk Franken (längliche West-Ost-Ausdehnung)
4. Fallback-Koordinate für Teams ohne Geocoding: `(49.15°N, 9.4°E)` (Mitte Bezirk)

#### Schritt 4: Hard-Constraint-Reparatur (`_repariere_verein_duplikate`)

Iteratives Reparaturverfahren (max. 100 Iterationen):
- Findet Verein-Duplikate innerhalb einer Staffel
- Tauscht überzählige Mannschaften mit einem Team aus einer anderen Staffel
- Prüft dabei, dass der Tausch kein neues Duplikat erzeugt

#### Schritt 5: Swap-Optimierung (`_optimiere_swaps`)

Hill-Climbing mit Konvergenz-Erkennung:
```
Wiederhole bis max_ohne_verbesserung (= n_teams × 30) Versuche ohne Verbesserung:
  1. Wähle 2 zufällige Staffeln
  2. Wähle je 1 zufällige Mannschaft
  3. Tausche die beiden Mannschaften
  4. Berechne neuen Gesamt-Score
  5. Wenn neuer Score < alter Score → akzeptiere
     Sonst → mache Tausch rückgängig
```

### Score-Berechnung (`src/staffeleinteilung/scoring.py`)

#### Formel

$$\text{TOTAL} = w_{\text{distanz}} \times \bar{d} + w_{\text{region}} \times R + w_{\text{balance}} \times \sigma_{\text{size}} + 10{,}000 \times V_{\text{hard}}$$

| Komponente | Symbol | Beschreibung | Default-Gewicht |
|---|---|---|---|
| Distanz-Score | $\bar{d}$ | Durchschnittliche paarweise Luftliniendistanz (km) pro Staffel, gemittelt über alle Staffeln | `w_distanz = 1.0` |
| Region-Score | $R$ | Anzahl Mannschaften in "falscher" Region (≠ Mehrheitsregion der Staffel) | `w_region = 50.0` |
| Balance-Score | $\sigma_{\text{size}}$ | Standardabweichung der Staffelgrößen | `w_balance = 20.0` |
| Hard-Constraint-Penalty | $V_{\text{hard}}$ | Anzahl Hard-Constraint-Verletzungen × 10.000 | `PENALTY = 10,000` |

**Niedriger Score = bessere Einteilung.**

#### Hard Constraints

| # | Constraint | Beschreibung |
|---|---|---|
| HC-1 | Staffelgröße | Muss im Bereich `[min_staffel_size, max_staffel_size]` liegen (default: 5–11) |
| HC-4 | Verein-Duplikat | Keine zwei Mannschaften desselben Vereins in derselben Staffel |
| HC-5 | Hohenlohe Süd / Unterland | Hohenlohe Süd (SHA/CR) darf nicht mit Unterland gemischt werden (bei A/B/C-Junioren Topf 2) |

#### Distanz-Cache

Alle paarweisen Distanzen werden vor der Optimierung vorberechnet und in einem In-Memory-Cache gehalten, damit das Scoring O(1) pro Paar ist.

---

## 3. Spielplanerstellung

### Übersicht der Dateien

| Datei | Aufgabe |
|---|---|
| `spielplan.py` | Orchestrierung: SZ-Vergabe → Schlüsselplan → Terminplan → Slot-Vergabe |
| `schluesselplan.py` | Round-Robin Paarungstabellen (DFBnet "1-L" Schema) |
| `sz_vergabe.py` | Optimale Zuordnung Team → Schlüsselzahl (SA / Brute-Force) |
| `slot_solver.py` | CP-SAT Constraint-Solver für konfliktfreie Zeitslots |
| `terminplan.py` | Rahmenterminkalender (feste Daten pro AK/Region) |
| `wuensche.py` | Wunsch-Datenmodelle |
| `wuensche_parser.py` | LLM-basierte Freitext → Strukturierte-Wünsche-Extraktion |

---

### 3.1 Schlüsselplan (`schluesselplan.py`)

#### Was ist eine Schlüsselzahl (SZ)?

Jedes Team in einer Staffel bekommt eine **Schlüsselzahl** (SZ). Die SZ bestimmt über den Schlüsselplan das gesamte **Heim/Auswärts-Muster** der Saison.

#### DFBnet 1-L Schema

Für jede gerade Staffelgröße (4, 6, 8, 10, 12, 14, 16) ist eine Round-Robin-Tabelle hinterlegt:

```
Staffelgröße 8, Schlüsseltag 7:
  SZ 1 vs SZ 7 (Heim : Gast)
  SZ 3 vs SZ 4
  SZ 5 vs SZ 2
  SZ 8 vs SZ 6
```

**Schlüsseltag-Umrechnung**: Im DFBnet gilt "1-L", d.h. Schlüsseltag 1 ist der LETZTE Spieltag:
$$\text{Spieltag} = n_{\text{Schlüsseltage}} - \text{Schlüsseltag} + 1$$

**Ungerade Staffelgrößen**: Nutzen den nächsthöheren geraden Plan. SZ 1 wird nicht vergeben → das Team gegen SZ 1 hat an diesem Spieltag **spielfrei**.

---

### 3.2 Schlüsselzahlen-Vergabe (`sz_vergabe.py`)

Die SZ-Zuordnung bestimmt, wer wann Heim und wann Auswärts spielt. Die Optimierung berücksichtigt:

#### Score-Formel (SpielplanScore)

$$\text{Total} = 10 \times H + 25 \times C + 1 \times D + 100 \times W + 50 \times P$$

| Komponente | Symbol | Beschreibung |
|---|---|---|
| Heim-Balance | $H$ | Varianz der Anzahl Heimspiele über alle Teams |
| Consecutive Penalty | $C$ | Strafe für 3+ aufeinanderfolgende Heim- oder Auswärtsspiele |
| Distanz-Fairness | $D$ | Standardabweichung der Gesamt-Auswärtskilometer |
| Wunsch-Verletzungen | $W$ | Anzahl verletzter Vereinswünsche (Sperrtage, Wochentage, H/A) |
| Platz-Konflikte | $P$ | Anzahl Doppelbelegungen am selben Spielfeld am selben Tag |

#### Algorithmus

| Staffelgröße | Methode | Details |
|---|---|---|
| ≤ 7 Teams (≤5.040 Permutationen) | **Brute-Force** | Alle Permutationen werden durchprobiert, beste gewinnt |
| > 7 Teams | **Simulated Annealing (SA)** mit Multi-Start | Mehrere unabhängige SA-Läufe, globales Optimum |

#### SA-Parameter

```
n_restarts  = max(3, min(8, 40.000 / (n × 500)))
iters       = min(8.000, n × 800)
T_start     = 500.0
T_end       = 0.1
Cooling     = exponentiell: T = T_start × (T_end / T_start)^(step / (iters-1))
Neighborhood = Swap zweier zufälliger SZ-Zuordnungen
Akzeptanz   = Delta < 0 → immer; Delta ≥ 0 → mit P = e^(-Δ/T)
```

#### Wunsch-Kategorien

| Kategorie | Beschreibung | Beispiel |
|---|---|---|
| `SPERRTAG` | Team kann an Datum nicht spielen | "Am 12.10. Vereinsfest" |
| `HEIMWUNSCH` | Heimspiel an bestimmtem Datum | "Am 20.09. bitte Heim" |
| `AUSWAERTSWUNSCH` | Auswärtsspiel an bestimmtem Datum | "Am 20.09. bitte Auswärts" |
| `WOCHENTAG` | Bevorzugter Spieltag | "Samstags spielen" |
| `ANSTOSSZEIT` | Gewünschte Anstoßzeit | "Anstoß 14:00 Uhr" |
| `PLATZSHARING` | Platz wird geteilt | "Teilen Platz mit C1" |
| `GLEICHZEITIG` | Gleichzeitig mit anderem Team | "Sollen gleichzeitig wie B1 spielen" |
| `ABWECHSELND` | Abwechselndes Heimrecht | "Abwechselnd Heim mit C1" |
| `REIHENFOLGE` | Heim/Auswärts-Reihenfolge | "Erst auswärts, dann heim" |
| `SONSTIGES` | Alles andere | Freitext |

Prioritäten: **HART** (muss beachtet werden) oder **WEICH** (wenn möglich).

#### Wunsch-Parsing

Zwei Methoden:

1. **Regelbasiert** (`_parse_wuensche_fast` in `server.py`): Schnell, kein LLM nötig. Regex-Erkennung von Sperrtagen, Wochentagen, Uhrzeiten. Erkennt Datums-Kontexte und filtert Wochentag-Namen neben Datumsangaben heraus.

2. **LLM-basiert** (`wuensche_parser.py`): Unterstützt Ollama (lokal) und OpenAI-kompatible APIs. Freitext → JSON-Array mit strukturierten Wunsch-Objekten.

---

### 3.3 Terminplan (`terminplan.py`)

Definiert pro Altersklasse und Region feste Spieltag-Termine für die Hinrunde 2025/26:

| Altersklasse | Regelspieltag | Anstoß (Sommer) | Anstoß (Winter) | Region |
|---|---|---|---|---|
| A-Junioren | Samstag | 16:00 | 14:30 | alle |
| B-Junioren (Regionenstaffel) | Sonntag | 10:30 | 09:00 | alle |
| B-Junioren (Qualistaffel) | Freitag | 19:00 | 17:30 | alle |
| C-Junioren | Samstag | 14:15 | 12:45 | alle |
| D-Junioren | Samstag / Mittwoch | 12:30 / 18:00 | 11:00 / 16:30 | UL / HL |
| E-Junioren | Samstag / Dienstag | 11:15 / 18:00 | 09:45 / 16:30 | UL / HL |
| B-Juniorinnen | Freitag | 18:30 | 17:00 | alle |
| C-Juniorinnen | Samstag | 14:15 | 12:45 | alle |
| D-Juniorinnen | Freitag | 18:00 | 16:30 | alle |

Winterzeit gilt für November–Februar.

#### Terminplan-Lookup
```python
find_terminplan(altersklasse, n_spieltage, region)
# → Findet den passenden Terminplan mit ≥ n_spieltage Terminen
```

---

### 3.4 Spielplan-Generierung (`spielplan.py`)

#### Spieldauer pro Altersklasse

| AK | Halbzeit | Pause | Puffer | Gesamt | Halbfeld |
|---|---|---|---|---|---|
| A-Junioren | 2×45 | 15 | 20 | **125 min** | Nein (Großfeld) |
| B-Junioren | 2×40 | 15 | 15 | **110 min** | Nein |
| C-Junioren | 2×35 | 15 | 15 | **100 min** | Nein |
| D-Junioren | 2×25 | 10 | 15 | **75 min** | Ja (Halbfeld) |
| E-Junioren | 2×20 | 10 | 10 | **60 min** | Ja |
| F-Junioren | 2×15 | 5 | 10 | **45 min** | Ja |

**Halbfeld**: D-Junioren und jünger spielen auf dem Halbfeld → 2 Spiele können gleichzeitig auf einem Großfeld stattfinden.

#### Orchestrierung (`generiere_alle_spielplaene`)

1. **SZ-Vergabe** pro Staffel (SA/Brute-Force)
2. **Paarungen** aus Schlüsselplan ableiten
3. **Terminplan** zuordnen (Daten, Anstoßzeiten, Winter-Korrektur)
4. **Cross-Staffel SZ-Optimierung**: Swappt SZ-Zuordnungen _innerhalb_ einer Staffel, um Venue-Kollisionen _zwischen_ Staffeln zu reduzieren. Paarungen bleiben identisch – nur das Heim/Auswärts-Muster ändert sich.
5. **Spieltag-Reordering**: Permutiert die Zuordnung Spieltag → Kalenderdatum pro Staffel, um Cross-Staffel Venue-Kollisionen vorab zu minimieren. Nutzt Brute-Force (≤9! = 362.880) oder SA (>9 Spieltage).
6. **CP-SAT Slot-Solver**: Globale Optimierung der Anstoßzeiten (siehe unten)
7. **Doppelrunde**: Bei kleinen Staffeln (<5 Teams) wird eine Rückrunde angehängt (Heimrecht getauscht)

---

### 3.5 CP-SAT Slot-Solver (`slot_solver.py`)

Der leistungsfähigste Teil der Pipeline. Nutzt Google OR-Tools CP-SAT, um für ~3.000 Spiele konfliktfreie Zeitslots zu finden.

#### Kernidee

Jedes Spiel hat mehrere **Optionen** (Datum × Venue × Zeitbereich):
- **Primärdatum** (geplanter Spieltag)
- **Alternative Daten** in derselben KW (Fr/Sa/So)
- **Heim-Venue** oder **Gast-Venue** (H/A-Tausch)

#### Zeitdiskretisierung
- **15-Minuten-Raster**: Alle Anstoßzeiten sind Vielfache von 15 min
- Start-Variable pro Spiel: `start_var ∈ [earliest_slot, latest_slot]`

#### Constraints

| Constraint | Beschreibung |
|---|---|
| **Exactly-One** | Jedes Spiel wählt genau eine Option |
| **Cumulative per (Venue, Datum)** | Kapazität 2 pro Spielfeld. Halbfeld-Spiele (Demand 1): 2 parallel möglich. Großfeld-Spiele (Demand 2): blockieren das Feld komplett |
| **Wochentag-Zeiten** | Mo–Fr: frühestens 17:30, spätestens 20:00 |
| **Wochenend-Zeiten** | Sa: 09:00–19:30 (Winter: bis 17:00), So: 09:00–18:00 (Winter: bis 16:00) |
| **Harte Sperrtage** | Option wird komplett ausgeschlossen |

#### Penalty-Gewichte (Zielfunktion)

| Penalty | Gewicht | Beschreibung |
|---|---|---|
| `ALT_WEEKEND` | 10 | Ausweichen auf anderes Wochenend-Datum |
| `ALT_WEEKDAY` | 30 | Ausweichen auf Wochentag |
| `SWAP` | 20 | Heim/Auswärts-Tausch |
| `TIME_PER_15` | 1 | Je 15 min Abweichung von Wunschzeit |
| `SPERRTAG` | 500 | Spiel auf weichem Sperrtag |
| `WOCHENTAG` | 400 | Spiel nicht am Wunschwochentag |
| `BONUS_WOCHENTAG` | -100 | Bonus für Treffen des Wunschwochentags |
| `ANSTOSSZEIT` | 200 | Anstoßzeit > 30 min vom Wunsch entfernt |
| `FAIRNESS_WEIGHT` | 3 | Minimiert maximale Wunsch-Last pro Team |

#### Solver-Architektur (Multi-Pass)

1. **Pass 1 – Wöchentliche Cluster**: Spiele werden nach ISO-Woche gruppiert. Jeder Cluster wird separat gelöst (proportionale Zeitverteilung, max. 90s pro Cluster).
2. **Pass 2 – Cross-Date Reparatur**: Löst Konflikte, die durch date-shifting in Pass 1 entstanden (Spiele auf alternative Tage verschoben können mit anderen Spielen kollidieren).
3. **Pass 3 – Globale Wunsch-Optimierung** (bis zu 3 Zyklen):
   - Identifiziert alle Wunsch-Verletzungen
   - Baut einen großen CP-SAT mit allen verletzten Spielen + ihren Venue-Nachbarn
   - Hintergrund-Spiele werden fixiert, Pool-Spiele sind frei
4. **Pass 4 – Greedy Wish Repair**:
   - Für jedes noch verletzte Spiel: versuche direktes Verschieben auf Wunsch-Wochentag
   - Mini-CP-SAT pro Spiel für Zeitslot-Umordnung am selben Venue
   - Anstoßzeit-Wünsche: einfache Verschiebung wenn nur 1 Spiel am Slot

#### Ergebnisse auf realen Daten

```
Input:   ~3.064 Spiele, 560 Teams, 114 Staffeln
Pass 1:  437 → 16 Venue-Konflikte (96% Reduktion)
Pass 2:  Reparatur verbleibender Cross-Date-Konflikte
Pass 3+4: Wunsch-Verletzungen minimiert
Gesamt:  ~2 min Laufzeit (8 Worker-Threads)
```

---

### 3.6 Vereinswünsche – Kompletter Ablauf

1. **Parsing**: Freitext aus Meldeliste → strukturierte `Wunsch`-Objekte (regelbasiert oder LLM)
2. **SZ-Vergabe**: SA berücksichtigt Sperrtage, Heim/Auswärts-Wünsche, Wochentage im Scoring
3. **CP-SAT**: Optionen werden pro Team mit Wunsch-Penalties versehen. Harte Sperrtage → Option ausgeschlossen. Weiche Sperrtage → 500 Strafpunkte. Wunschwochentage → ±400/−100.
4. **Post-Processing**: `_update_wunsch_verletzungen` berechnet finale Violations auf tatsächlichen Spiel-Daten. Wochentag-Verletzungen zählen nur, wenn der gewünschte Tag innerhalb ±2 Tage erreichbar war.

---

## API-Endpunkte

Alle Endpunkte sind in `src/api/server.py` definiert. Server läuft als FastAPI auf Port 8000.

### Seiten

| Methode | Pfad | Beschreibung |
|---|---|---|
| GET | `/` | Landingpage (`index.html`) |
| GET | `/app` | Hauptanwendung (`app.html`) |
| GET | `/builder` | Manueller Staffel-Builder (`builder.html`) |

### Staffeleinteilung

| Methode | Pfad | Beschreibung |
|---|---|---|
| POST | `/api/einteilung` | Upload Meldeliste → automatische Staffeleinteilung. Parameter: `w_distanz`, `w_region`, `w_balance`, `max_staffel_size` |
| POST | `/api/einteilung/rueckrunde` | Upload Meldeliste + Einteilungs-Excel → Rückrunde-Staffelzuordnung |

### Spielplan

| Methode | Pfad | Beschreibung |
|---|---|---|
| POST | `/api/spielplan` | Generiert Spielpläne aus Einteilung. Body: `{einteilung, saison, sperrtage}` |
| GET | `/api/spielplan/history` | Liste aller gespeicherten Spielpläne (Metadaten) |
| GET | `/api/spielplan/history/{filename}` | Lädt einen gespeicherten Spielplan (vollständig) |
| POST | `/api/spielplan/edit` | Manuelle Änderungen anwenden + Konflikte neu berechnen |

### Export

| Methode | Pfad | Beschreibung |
|---|---|---|
| POST | `/api/export` | Einteilung als Excel-Datei (Übersicht + Sheets pro AK/Topf) |
| POST | `/api/export/rueckrunde` | Einteilung im "Jochen-Format" (Rückrunde-Layout) |
| POST | `/api/spielplan/export` | Spielpläne als Excel (Übersicht + Sheets pro Staffel) |

### Sonstiges

| Methode | Pfad | Beschreibung |
|---|---|---|
| POST | `/api/builder/teams` | Parst Meldeliste → flacher Team-Pool für Staffel-Builder |
| POST | `/api/wuensche/parse` | Freitext-Wünsche per LLM parsen (Ollama/OpenAI) |
| GET | `/api/rueckrunde/einteilung` | Gibt gespeicherte Rückrunde-Einteilung zurück |

---

## Benutzeroberfläche (UI)

Die Web-UI besteht aus drei Seiten:

### 1. Landingpage (`/`)
- Projekt-Vorstellung mit Feature-Übersicht
- Links zur Hauptanwendung und zum Builder

### 2. Hauptanwendung (`/app`) – 4 Tabs

#### Tab: Hinrunde
- **Upload**: Meldeliste (Excel) per Drag & Drop hochladen
- **Parameter-Slider**: Gewichtung Distanz / Region / Balance, max. Staffelgröße
- **Ergebnis-Anzeige**: Statistiken (Teams, Staffeln, Ø Distanz)
- **Interaktive Karte** (Leaflet.js): Teams farbcodiert nach Staffel
- **Staffel-Details**: Aufklappbare Gruppen pro AK/Topf mit Team-Liste
- **Drag & Drop**: Teams zwischen Staffeln manuell verschieben
- **Wünsche bearbeiten**: Freitext pro Team änderbar
- **Excel-Export**: Download der Einteilung

#### Tab: Rückrunde
- **Upload**: Meldeliste + Einteilungs-Excel (2 Dateien)
- **Regionenstaffeln-Übernahme**: Regionenstaffeln aus der Hinrunde werden automatisch in den Staffel-Builder übertragen (gesperrt, nicht editierbar)
- Leitet zum Staffel-Builder weiter

#### Tab: Spielplan HR (Hinrunde)
- **Spielplan generieren**: Aus aktueller Einteilung
- **Sperrtage**: Kalender-Widget zur Auswahl globaler Sperrtage (Feiertage, Vereinsfeste, etc.)
- **Ergebnis**: Pro Staffel alle Spieltage mit Paarungen, Zeiten, Spielorten
- **SZ-Anzeige**: Schlüsselzahlen werden pro Team angezeigt
- **Datum-Spalte**: Zeigt das tatsächliche Spieldatum wenn es vom Spieltag-Datum abweicht (z.B. Freitag statt Sonntag wegen Wunsch) – in Orange hervorgehoben
- **Konflikte**: Farbliche Hervorhebung von Venue-Konflikten
- **Wunsch-Verletzungen**: Detailansicht aller verletzten Wünsche
- **Excel-Export**: Download der Spielpläne (mit SZ-Spalten: Zeit, SZ, Heim, SZ, Gast, Spielort, Datum)
- **History**: Gespeicherte Spielpläne laden und vergleichen

#### Tab: Spielplan RR (Rückrunde)
- Wie Hinrunde, aber basierend auf Rückrunde-Einteilung

### 3. Staffel-Builder (`/builder`)
- **Manueller Modus**: Teams per Drag & Drop in Staffeln zuordnen
- **Team-Pool**: Alle verfügbaren Teams, filterbar nach AK
- **Gesperrte Staffeln**: Regionenstaffeln aus der Hinrunde werden automatisch übernommen (grüner Rahmen, 🔒-Label, nicht editierbar – kein Drag, kein Löschen, keine Namensänderung)
- **Karte**: Echtzeit-Anzeige der Staffel-Zusammensetzung
- **Validierung**: Warnung bei Verein-Duplikaten, Größenverletzungen
- **Export**: Ergebnis als Excel im Jochen-Format

---

## Konfigurationsdateien

### `config/geocode_cache.json`

JSON-Cache aller geocodierten Spielstätten-Adressen:

```json
{
  "kirschenwiesen, 74232 abstatt-zentrum": {
    "lat": 49.0699,
    "lon": 9.3048,
    "display": "Kirschenwiesen, 74232 Abstatt, ..."
  },
  ...
}
```

- Key: normalisierte Adresse (lowercase, stripped)
- Value: `{lat, lon, display}` oder `{lat: null, lon: null}` für nicht gefundene
- Wird automatisch bei jedem Import erweitert
- Verhindert wiederholte Nominatim-API-Calls

### `config/distanzmatrix.csv`

Paarweise Luftlinien-Distanzen zwischen allen Spielstätten in km:

```csv
;Adresse A;Adresse B;...
Adresse A;0.0;12.3;...
Adresse B;12.3;0.0;...
```

- Generiert via `python src/common/erstelle_distanzmatrix.py <meldeliste.xlsx>`
- Semikolon-getrennt (CSV)
- Symmetrische Matrix (Haversine-Formel)

---

## Tests

```
tests/
├── test_api.py                  # API-Integrationstests
├── test_cpsat.py                # CP-SAT Solver Tests
├── test_cpsat_stress.py         # Stress-Tests für den Solver
├── test_e2e.py                  # End-to-End Pipeline-Tests
├── test_halbfeld.py             # Halbfeld-Logik Tests
├── test_konflikte.py            # Konflikterkennung Tests
├── test_solver.py               # Solver-Unit-Tests
├── test_wuensche.py             # Wunsch-Parsing Tests
├── test_data_import/            # Daten-Import Tests
└── test_spielplanerstellung/    # Spielplan-Modul Tests
```

---

## Technologie-Stack

| Komponente | Technologie |
|---|---|
| Backend | Python 3.13, FastAPI, Uvicorn |
| Constraint-Solver | Google OR-Tools CP-SAT |
| Excel-Verarbeitung | openpyxl |
| Geocoding | geopy (Nominatim / OpenStreetMap) |
| Frontend | Vanilla JS, Leaflet.js (Karten), HTML/CSS |
| LLM-Integration | Ollama (lokal) / OpenAI-kompatible APIs |
| GUI-Launcher | Tkinter + PIL |

### Dependencies (`requirements.txt`)

```
fastapi>=0.135
uvicorn>=0.44
openpyxl>=3.1
ortools>=9.15
geopy>=2.4
pydantic>=2.0
python-multipart>=0.0.20
requests>=2.30
Pillow>=10.0
```

---

## Logging & Debugging

### Fortschritts-Logging

Die Staffeleinteilung und Spielplan-Generierung loggen detailliert auf `stdout` und in Dateien:

| Log-Datei | Inhalt |
|---|---|
| `output/einteilung_log.txt` | Detaillierter Fortschritt der Swap-Optimierung (alle 500 Iterationen) |
| `output/server.log` | Gesamte Server-Ausgabe (nur bei Verwendung des GUI-Launchers) |

Beispiel-Ausgabe:
```
[Einteilung] B-Junioren Qualistaffel Topf 1 - 48 Teams ...
    Initial (6 Staffeln): Score=142.3 (Distanz=38.2km, Region=12, Violations=0)
      Swap-Optimierung: 48 Teams, 6 Staffeln, max 1440 ohne Verbesserung
      ... Iteration 500, Score=98.7, Swaps=23, Stagnation=312/1440, Zeit=2.1s
      ... Iteration 1000, Score=96.1, Swaps=28, Stagnation=780/1440, Zeit=4.0s
      Fertig: 1468 Iterationen, 28 Swaps, 5.8s
    Nach Optimierung (28 Swaps): Score=96.1 (Distanz=31.4km, Region=5, Violations=0)
[Einteilung] B-Junioren Qualistaffel Topf 1 - fertig in 6.2s
```

### Performance-Optimierung

- **Distanz-Cache**: Alle paarweisen Haversine-Distanzen werden beim ersten Aufruf berechnet und global gecacht (verhindert redundante Berechnungen im Swap-Loop)
- **UTF-8 erzwungen**: `sys.stdout.reconfigure(encoding="utf-8")` am Server-Start, damit Unicode-Zeichen in Logs auf allen Windows-Systemen funktionieren

---

## Spielplan-Logs

Jeder generierte Spielplan wird automatisch als JSON unter `spielplan_logs/` gespeichert:

```
spielplan_logs/
├── spielplan_20260419_152145.json
├── spielplan_20260420_213930.json
└── ...
```

Format: `spielplan_YYYYMMDD_HHMMSS.json`

Enthalt alle Staffeln, Spiele, Zeiten, Konflikte und Wunsch-Verletzungen. Kann uber die UI (History-Tab) geladen und verglichen werden.

---

## Autoren

Entwickelt fur den **Wurttembergischen Fussballverband (WFV), Bezirk Franken** – Jugendspielausschuss.