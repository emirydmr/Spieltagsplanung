# Anforderungen Staffeleinteilung

## 1. Eingabedaten

### 1.1 Mannschaftsmeldungen (Excel-Import)
- Vereinsname
- Mannschaftsbezeichnung (1., 2., 3. Mannschaft etc.)
- Altersklasse (A/B/C/D/E-Junioren, B/C/D-Juniorinnen)
- Spielklasse (Regionenstaffel, Qualistaffel, etc.)
- Topf-Zuordnung (Topf 1 = leistungsorientiert, Topf 2 = Rest)
- Spielstätte(n) mit Adresse
- Wunsch-Spieltag (Woche A / Woche B)
- Wunsch-Anstoßzeit
- Sonderwünsche / Sperrtermine
- Flex-Modell (ja/nein, nur unterste Spielklasse)
- 7er / 9er / 11er Mannschaft

### 1.2 Spielstätten
- Adresse (für Entfernungsberechnung)
- Zuordnung zu Verein(en)
- Kapazität / Anzahl Plätze (Rasen, Kunstrasen)

### 1.3 Historische Daten (optional, für Validierung)
- Einteilungen der Vorsaison (Hin- & Rückrunde)
- Ergebnisse/Tabellen der Hinrunde (für Rückrunden-Einteilung)

### 1.4 Konfiguration
- Saison (z.B. 25/26)
- Runde (Hinrunde / Rückrunde)
- Altersklassen-spezifische Regeln (siehe Abschnitt 3)


## 2. Regionen

| Region | Umfasst | Kürzel |
|---|---|---|
| Unterland | Bezirk Franken – Unterland | UL |
| Hohenlohe Nord | Bezirk Franken – Hohenlohe | HN |
| Hohenlohe Süd | Schwäbisch Hall + Crailsheim (gehört zu Bezirk Rems/Murr/Hall) | HS |

- A/B/C-Junioren + B/C/D-Juniorinnen: alle 3 Regionen
- D/E-Junioren: nur Unterland + Hohenlohe Nord (Bezirk Franken)


## 3. Einteilungsregeln pro Altersklasse

### 3.1 A-/B-/C-Junioren

**Hinrunde:**
- Regionenstaffel: 10 Mannschaften, Zusammensetzung fix durch Auf-/Abstieg → nicht Teil der Optimierung
- Qualistaffeln Topf 1: regionale Einteilung (Unterland / Hohenlohe getrennt)
- Qualistaffeln Topf 2: regionale Einteilung wird versucht, aber kein Muss. **Aber:** Hohenlohe Süd (SHA+CR) darf NICHT mit Unterland in einer Staffel sein

**Rückrunde:**
- 2 Leistungsstaffeln (je 10, 1x Unterland, 1x Hohenlohe) aus den bestplatzierten Mannschaften
- Kreisstaffeln für den Rest (Topf 1 + Topf 2), regional, unter Berücksichtigung der Hinrunde-Ergebnisse

### 3.2 D-Junioren

**Hinrunde:**
- Topf 1 (Quali Bezirksstaffel): Unterland und Hohenlohe-Nord getrennt
- Topf 2 (Qualistaffeln): regional (Unterland / Hohenlohe-Nord)

**Rückrunde:**
- Topf 1: je Region 1 Bezirksstaffel + 1 Leistungsstaffel + Kreisstaffeln
- Topf 2: Kreisstaffeln regional
- Einteilung berücksichtigt Hinrunde-Ergebnisse

### 3.3 E-Junioren

**Hinrunde:**
- Topf 1 + Topf 2: Einteilung nach Geografie (Unterland / Hohenlohe-Nord)
- Einfache Runde

**Rückrunde:**
- Neueinteilung nach Ergebnissen der Qualirunde
- Kreisstaffeln regional

### 3.4 B-/C-Juniorinnen

**Hinrunde:**
- Geografische Einteilung, einfache oder doppelte Runde
- 7er oder 9er Mannschaften möglich

**Rückrunde:**
- B-Juniorinnen: 1 Bezirksstaffel + Kreisstaffeln
- C-Juniorinnen: 1 Leistungsstaffel + Kreisstaffeln
- Gemeinsame Staffeln Franken + SHA/CR

### 3.5 D-Juniorinnen
- Hinrunde: geografisch, Quali
- Rückrunde: Kreisstaffeln nach Ergebnissen


## 4. Hard Constraints (müssen eingehalten werden)

- [ ] HC-1: Staffelgröße liegt im erlaubten Bereich (typisch 6–10, abhängig von Altersklasse und Meldezahl)
- [ ] HC-2: Jede gemeldete Mannschaft wird genau einer Staffel zugeordnet
- [ ] HC-3: Mannschaften werden nur in Staffeln ihrer Altersklasse, Spielklasse und Topf-Zugehörigkeit eingeteilt
- [ ] HC-4: Mehrere Mannschaften desselben Vereins im gleichen Topf dürfen NICHT in derselben Staffel sein
- [ ] HC-5: Hohenlohe Süd (SHA+CR) darf NICHT mit Unterland in derselben Staffel sein (bei A/B/C-Junioren Topf 2)
- [ ] HC-6: Topf-1-Mannschaften in eigene Staffeln, Topf-2-Mannschaften in eigene Staffeln (keine Mischung)
- [ ] HC-7: Regionenstaffeln sind fix (10 Mannschaften durch Auf-/Abstieg bestimmt) → werden nicht optimiert


## 5. Soft Constraints (sollen optimiert werden)

- [ ] SC-1: Minimierung der Gesamtfahrdistanz innerhalb jeder Staffel
- [ ] SC-2: Regionale Zugehörigkeit (Unterland/Hohenlohe) möglichst beibehalten
- [ ] SC-3: Möglichst gleichmäßige Staffelgrößen (nicht eine Staffel mit 6 und eine mit 10)
- [ ] SC-4: Rückrunde: Mannschaften mit ähnlichem Leistungsniveau (Tabellenplatz Hinrunde) in gleiche Staffel
- [ ] SC-5: Faire Verteilung – kein Verein soll systematisch benachteiligt werden bei Fahrdistanzen


## 6. Rückrunde – Zusatzlogik

- Hinrunde-Ergebnisse (Tabellenplätze) bestimmen die Einteilung in Leistungs-/Kreisstaffeln
- Die besten X Mannschaften kommen in Leistungsstaffeln, der Rest in Kreisstaffeln
- Die regionale Zuordnung bleibt analog zur Hinrunde
- Auf-/Abstiegsregeln bestimmen Staffelanzahl und -größe


## 7. Entfernungsmatrix

- Paarweise Fahrdistanz (km) zwischen allen Spielstätten
- Quelle: Geocoding-API (z.B. OpenRouteService, Google Maps)
- Wird einmal pro Saison berechnet und gecacht
- Grundlage für SC-1 (Fahrdistanz-Minimierung)


## 8. Erwartetes Output

- Pro Altersklasse/Spielklasse: Liste der Staffeln mit zugeordneten Mannschaften
- Statistiken pro Staffel: Anzahl Teams, durchschnittliche/maximale Fahrdistanz
- Constraint-Verletzungen (falls welche): welche Regel, welche Mannschaft
- Export als Excel/CSV (zur Weiterverarbeitung oder manuellem Import ins DFBnet)


## 9. Interaktion / Entscheidungsunterstützung

- Ergebnis ist ein VORSCHLAG, kein Endprodukt
- Der Spielleiter muss manuell Mannschaften zwischen Staffeln verschieben können
- Nach jeder manuellen Änderung: Constraints neu prüfen, Statistiken aktualisieren
- Visualisierung: Karte mit Staffeln farbcodiert, Distanz-Überblick


## 10. Abgrenzung

Was hier NICHT behandelt wird (kommt später in `spielplanerstellung/`):
- Schlüsselzahlen-Vergabe
- Spieltage/Termine festlegen
- Anstoßzeiten
- Platzbelegungskonflikte
- Spielplan-Generierung
