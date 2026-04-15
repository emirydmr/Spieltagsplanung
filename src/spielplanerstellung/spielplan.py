"""Spielplan-Generator: Kombiniert Schlüsselplan + Terminplan + SZ-Vergabe.

Erzeugt für jede Staffel einen konkreten Spielplan mit:
  - Spieltag-Nummer, Datum, Anstoßzeit
  - Paarungen (Heim vs. Gast) mit eigener Zeit + Spielfeld
  - Spielfreie Mannschaft (bei ungerader Staffelgröße)
  - Spielfeld-Kollisionserkennung und -auflösung
"""

from dataclasses import dataclass, field
from datetime import date

from src.spielplanerstellung.schluesselplan import (
    get_paarungen_pro_spieltag, get_n_spieltage,
)
from src.spielplanerstellung.terminplan import find_terminplan, Terminplan
from src.spielplanerstellung.sz_vergabe import (
    vergebe_schluesselzahlen, SZZuordnung, SpielplanScore,
)
from src.spielplanerstellung.wuensche import Wunsch


@dataclass
class Spiel:
    """Ein einzelnes Spiel."""
    heim: str       # Mannschaftsname
    gast: str       # Mannschaftsname
    heim_verein: str = ""
    gast_verein: str = ""
    datum: date | None = None
    anstosszeit: str = ""
    spielfeld: str = ""   # Adresse des Heimspielfelds


@dataclass
class Spieltag:
    """Ein Spieltag mit allen Spielen."""
    nummer: int
    datum: date | None = None
    anstosszeit: str = ""
    spiele: list[Spiel] = field(default_factory=list)
    spielfrei: str | None = None   # Mannschaft die spielfrei hat


@dataclass
class StaffelSpielplan:
    """Kompletter Spielplan einer Staffel."""
    staffel_name: str
    altersklasse: str
    topf: str
    staffel_idx: int
    n_teams: int
    doppelrunde: bool
    sz_zuordnungen: list[SZZuordnung] = field(default_factory=list)
    spieltage: list[Spieltag] = field(default_factory=list)
    score: SpielplanScore | None = None


def generiere_spielplan(
    staffel_data: dict,
    altersklasse: str,
    topf: str,
    staffel_idx: int,
    region: str = "alle",
    wuensche: dict[str, list[Wunsch]] | None = None,
) -> StaffelSpielplan:
    """Generiert einen Spielplan für eine einzelne Staffel.

    Args:
        staffel_data: Dict aus der Einteilung (teams, n_teams, doppelrunde, ...)
        altersklasse: z.B. "C-Junioren"
        topf: z.B. "Topf 1"
        staffel_idx: Staffel-Index (0-basiert)
        region: "alle", "Unterland" oder "Hohenlohe"
        wuensche: Wünsche pro Mannschaft

    Returns:
        StaffelSpielplan
    """
    teams = staffel_data["teams"]
    n = staffel_data["n_teams"]
    doppelrunde = staffel_data.get("doppelrunde", False)

    staffelgroesse = n
    n_spieltage = get_n_spieltage(staffelgroesse)

    # 2. Terminplan finden (VOR SZ-Vergabe, damit Daten für Wünsche-Prüfung da sind)
    terminplan = find_terminplan(altersklasse, n_spieltage, region)

    # Spieltag-Daten für Wünsche-Scoring extrahieren
    spieltag_dates: dict[int, "date"] = {}
    if terminplan:
        for st_nr, dt in terminplan.spieltage.items():
            if dt:
                spieltag_dates[st_nr] = dt

    # 1. SZ-Vergabe (Optimierung mit Daten + Wünschen)
    sz_zuordnungen, score = vergebe_schluesselzahlen(
        teams=teams,
        staffelgroesse=staffelgroesse,
        wuensche=wuensche,
        spieltag_dates=spieltag_dates if spieltag_dates else None,
    )

    # Build SZ→Team lookup
    sz_to_team = {z.sz: z for z in sz_zuordnungen}

    # 3. Paarungen pro Spieltag
    paarungen = get_paarungen_pro_spieltag(staffelgroesse)

    spieltage_list = []
    for spieltag_nr in sorted(paarungen.keys()):
        matches = paarungen[spieltag_nr]

        # Datum + Anstoßzeit
        datum = None
        anstosszeit = ""
        if terminplan and spieltag_nr in terminplan.spieltage:
            datum = terminplan.spieltage[spieltag_nr]
            # Nov-Feb → Winterzeit
            if datum and datum.month in (11, 12, 1, 2):
                anstosszeit = terminplan.anstosszeit_winter
            else:
                anstosszeit = terminplan.anstosszeit

        spiele = []
        spielfrei = None

        for h_sz, g_sz in matches:
            h_team = sz_to_team.get(h_sz)
            g_team = sz_to_team.get(g_sz)

            if h_team is None and g_team is not None:
                # h_sz = 1 (bye for odd staffels) → g_team hat spielfrei
                spielfrei = g_team.mannschaft
                continue
            elif g_team is None and h_team is not None:
                # g_sz = 1 → h_team hat spielfrei
                spielfrei = h_team.mannschaft
                continue
            elif h_team is None and g_team is None:
                continue

            spiele.append(Spiel(
                heim=h_team.mannschaft,
                gast=g_team.mannschaft,
                heim_verein=h_team.verein,
                gast_verein=g_team.verein,
                datum=datum,
                anstosszeit=anstosszeit,
                spielfeld=h_team.adresse or "",
            ))

        spieltage_list.append(Spieltag(
            nummer=spieltag_nr,
            datum=datum,
            anstosszeit=anstosszeit,
            spiele=spiele,
            spielfrei=spielfrei,
        ))

    # 4. Doppelrunde: Rückrunde anhängen (Heimrecht tauschen)
    if doppelrunde:
        rueckrunde = []
        for st in spieltage_list:
            rueck_spiele = [
                Spiel(
                    heim=s.gast,
                    gast=s.heim,
                    heim_verein=s.gast_verein,
                    gast_verein=s.heim_verein,
                    datum=None,  # Rückrunde-Termine nicht im Hinrunde-Plan
                    anstosszeit=s.anstosszeit,
                    spielfeld=_find_adresse(sz_zuordnungen, s.gast),
                )
                for s in st.spiele
            ]
            rueckrunde.append(Spieltag(
                nummer=st.nummer + n_spieltage,
                datum=None,  # Rückrunde-Termine nicht im Hinrunde-Plan
                anstosszeit=st.anstosszeit,
                spiele=rueck_spiele,
                spielfrei=st.spielfrei,
            ))
        spieltage_list.extend(rueckrunde)

    return StaffelSpielplan(
        staffel_name=f"Staffel {staffel_idx + 1}",
        altersklasse=altersklasse,
        topf=topf,
        staffel_idx=staffel_idx,
        n_teams=n,
        doppelrunde=doppelrunde,
        sz_zuordnungen=sz_zuordnungen,
        spieltage=spieltage_list,
        score=score,
    )


def _find_adresse(sz_zuordnungen: list[SZZuordnung], mannschaft: str) -> str:
    """Findet die Adresse eines Teams anhand des Namens."""
    for z in sz_zuordnungen:
        if z.mannschaft == mannschaft:
            return z.adresse or ""
    return ""


def generiere_alle_spielplaene(
    einteilung_data: dict,
    wuensche: dict[str, list[Wunsch]] | None = None,
) -> list[StaffelSpielplan]:
    """Generiert Spielpläne für alle Staffeln aus der Einteilung.

    Args:
        einteilung_data: Das JSON-Result von /api/einteilung
        wuensche: Wünsche pro Mannschaftsname

    Returns:
        Liste von StaffelSpielplan
    """
    alle_plaene = []

    for gruppe in einteilung_data.get("gruppen", []):
        ak = gruppe["altersklasse"]
        topf = gruppe["topf"]

        # Region bestimmen (für Terminplan-Lookup)
        region = "alle"
        if ak in ("D-Junioren", "E-Junioren"):
            regions = [t.get("region", "") for s in gruppe["staffeln"] for t in s["teams"]]
            hl_count = sum(1 for r in regions if "Hohenlohe" in r)
            ul_count = sum(1 for r in regions if "Unterland" in r)
            region = "Hohenlohe" if hl_count > ul_count else "Unterland"

        for si, staffel in enumerate(gruppe["staffeln"]):
            plan = generiere_spielplan(
                staffel_data=staffel,
                altersklasse=ak,
                topf=topf,
                staffel_idx=si,
                region=region,
                wuensche=wuensche,
            )
            alle_plaene.append(plan)

    # Spielfeld-Kollisionen über alle Staffeln hinweg auflösen
    resolve_spielfeld_konflikte(alle_plaene)

    return alle_plaene


# ─── Spielfeld-Konflikt-Erkennung und -Auflösung ──────────────

# Offizielle Spielzeiten WFV Jugendfußball + Puffer
# Spielzeit = 2 × Halbzeit + Halbzeitpause + Nachspielzeit + Wechselpuffer
# Halbfeld-AK (D und jünger): 2 Spiele passen gleichzeitig auf 1 Großfeld
AK_SPIELDAUER: dict[str, dict] = {
    "A-Junioren":   {"halbzeit": 45, "pause": 15, "puffer": 20, "halbfeld": False},  # 2×45 + 15 + 20 = 125 min
    "A-Juniorinnen": {"halbzeit": 45, "pause": 15, "puffer": 20, "halbfeld": False},
    "B-Junioren":   {"halbzeit": 40, "pause": 15, "puffer": 15, "halbfeld": False},  # 2×40 + 15 + 15 = 110 min
    "B-Juniorinnen": {"halbzeit": 40, "pause": 15, "puffer": 15, "halbfeld": False},
    "C-Junioren":   {"halbzeit": 35, "pause": 15, "puffer": 15, "halbfeld": False},  # 2×35 + 15 + 15 = 100 min
    "C-Juniorinnen": {"halbzeit": 35, "pause": 15, "puffer": 15, "halbfeld": False},
    "D-Junioren":   {"halbzeit": 25, "pause": 10, "puffer": 15, "halbfeld": True},   # 2×25 + 10 + 15 =  75 min
    "D-Juniorinnen": {"halbzeit": 25, "pause": 10, "puffer": 15, "halbfeld": True},
    "E-Junioren":   {"halbzeit": 20, "pause": 10, "puffer": 10, "halbfeld": True},   # 2×20 + 10 + 10 =  60 min
    "E-Juniorinnen": {"halbzeit": 20, "pause": 10, "puffer": 10, "halbfeld": True},
    "F-Junioren":   {"halbzeit": 15, "pause":  5, "puffer": 10, "halbfeld": True},   # 2×15 +  5 + 10 =  45 min
    "F-Juniorinnen": {"halbzeit": 15, "pause":  5, "puffer": 10, "halbfeld": True},
}

_DEFAULT_DAUER = {"halbzeit": 35, "pause": 15, "puffer": 15, "halbfeld": False}


def _get_spieldauer_min(altersklasse: str) -> int:
    """Gibt die gesamte Blockdauer (inkl. Puffer) in Minuten für eine AK zurück."""
    d = AK_SPIELDAUER.get(altersklasse, _DEFAULT_DAUER)
    return 2 * d["halbzeit"] + d["pause"] + d["puffer"]


def _ist_halbfeld(altersklasse: str) -> bool:
    """Prüft ob die AK auf Halbfeld spielt (D-Jugend und jünger)."""
    d = AK_SPIELDAUER.get(altersklasse, _DEFAULT_DAUER)
    return d["halbfeld"]


def _parse_time(zeit_str: str) -> tuple[int, int] | None:
    """Parst "14:15" → (14, 15). Gibt None zurück bei leerem/ungültigem String."""
    if not zeit_str or ":" not in zeit_str:
        return None
    try:
        parts = zeit_str.strip().split(":")
        return (int(parts[0]), int(parts[1]))
    except (ValueError, IndexError):
        return None


def _format_time(h: int, m: int) -> str:
    """Formatiert (14, 15) → "14:15"."""
    return f"{h:02d}:{m:02d}"


def _add_minutes(h: int, m: int, minutes: int) -> tuple[int, int]:
    """Addiert Minuten zu einer Uhrzeit."""
    total = h * 60 + m + minutes
    return (total // 60) % 24, total % 60


@dataclass
class _SpielRef:
    """Referenz auf ein Spiel mit Metadaten für die Kollisionsprüfung."""
    spiel: Spiel
    altersklasse: str
    dauer_min: int
    halbfeld: bool


def resolve_spielfeld_konflikte(plaene: list[StaffelSpielplan]) -> int:
    """Erkennt und löst Spielfeld-Kollisionen über alle Staffeln.

    Berücksichtigt:
      - AK-spezifische Spieldauer (A=125min, B=110, C=100, D=75, E=60, F=45)
      - Halbfeld-AK (D und jünger): 2 Spiele gleichzeitig auf 1 Großfeld erlaubt
      - Staffelt Anstoßzeiten wenn das Spielfeld nicht reicht

    Returns:
        Anzahl verschobener Spiele
    """
    # Sammle alle Spiele: Key = (spielfeld_lower, datum_iso)
    belegung: dict[tuple[str, str], list[_SpielRef]] = {}

    for plan in plaene:
        ak = plan.altersklasse
        dauer = _get_spieldauer_min(ak)
        halbfeld = _ist_halbfeld(ak)

        for st in plan.spieltage:
            for spiel in st.spiele:
                if not spiel.spielfeld or not spiel.datum:
                    continue
                key = (spiel.spielfeld.strip().lower(), spiel.datum.isoformat())
                belegung.setdefault(key, []).append(
                    _SpielRef(spiel=spiel, altersklasse=ak, dauer_min=dauer, halbfeld=halbfeld)
                )

    konflikte_behoben = 0

    for (feld, datum_str), refs in belegung.items():
        if len(refs) < 2:
            continue

        # Sortiere nach Anstoßzeit
        refs.sort(key=lambda r: _parse_time(r.spiel.anstosszeit) or (12, 0))

        # Prüfe Belegungsslots: Großfeld = 1 Großfeldspiel ODER 2 Halbfeldspiele gleichzeitig
        # Wir tracken belegte Zeitfenster als Liste von (start_min, end_min, halbfeld_count)
        slots: list[dict] = []
        # slot = {"start": int, "end": int, "halbfeld_count": int, "grossfeld": bool}

        for ref in refs:
            zeit = _parse_time(ref.spiel.anstosszeit)
            if zeit is None:
                continue

            start_total = zeit[0] * 60 + zeit[1]
            end_total = start_total + ref.dauer_min

            placed = False

            if ref.halbfeld:
                # Halbfeld-Spiel: kann parallel mit 1 anderem Halbfeld-Spiel
                for slot in slots:
                    # Passt zeitlich in diesen Slot UND Slot ist Halbfeld mit <2 Spielen?
                    if (slot["halbfeld_count"] < 2
                            and not slot["grossfeld"]
                            and slot["start"] == start_total):
                        slot["halbfeld_count"] += 1
                        slot["end"] = max(slot["end"], end_total)
                        placed = True
                        break

            if not placed:
                # Prüfe ob dieser Zeitslot mit bestehenden Slots kollidiert
                conflict = True
                while conflict:
                    conflict = False
                    for slot in slots:
                        # Überlappung?
                        if start_total < slot["end"] and end_total > slot["start"]:
                            # Konflikt → verschiebe nach Ende dieses Slots
                            new_start = slot["end"]
                            new_h, new_m = new_start // 60, new_start % 60
                            ref.spiel.anstosszeit = _format_time(new_h % 24, new_m)
                            start_total = new_start
                            end_total = start_total + ref.dauer_min
                            conflict = True
                            konflikte_behoben += 1
                            break

                slots.append({
                    "start": start_total,
                    "end": end_total,
                    "halbfeld_count": 1 if ref.halbfeld else 0,
                    "grossfeld": not ref.halbfeld,
                })

    return konflikte_behoben


def spielplan_to_dict(plan: StaffelSpielplan) -> dict:
    """Konvertiert einen Spielplan in ein JSON-fähiges Dict."""
    return {
        "staffel_name": plan.staffel_name,
        "altersklasse": plan.altersklasse,
        "topf": plan.topf,
        "staffel_idx": plan.staffel_idx,
        "n_teams": plan.n_teams,
        "doppelrunde": plan.doppelrunde,
        "sz_zuordnungen": [
            {"mannschaft": z.mannschaft, "verein": z.verein, "sz": z.sz, "region": z.region}
            for z in plan.sz_zuordnungen
        ],
        "score": {
            "total": round(plan.score.total, 1),
            "heim_balance": round(plan.score.heim_balance, 2),
            "distanz_fairness": round(plan.score.distanz_fairness, 1),
            "wunsch_verletzungen": plan.score.wunsch_verletzungen,
            "platz_konflikte": plan.score.platz_konflikte,
        } if plan.score else None,
        "spieltage": [
            {
                "nummer": st.nummer,
                "datum": st.datum.isoformat() if st.datum else None,
                "anstosszeit": st.anstosszeit,
                "spiele": [
                    {
                        "heim": s.heim,
                        "gast": s.gast,
                        "datum": s.datum.isoformat() if s.datum else None,
                        "anstosszeit": s.anstosszeit,
                        "spielfeld": s.spielfeld,
                    }
                    for s in st.spiele
                ],
                "spielfrei": st.spielfrei,
            }
            for st in plan.spieltage
        ],
    }
