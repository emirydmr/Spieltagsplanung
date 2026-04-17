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

    Ansatz: Inkrementelle Slot-Vergabe, jüngste AK zuerst.
      1. Alle Spielpläne generieren (SZ-Vergabe, Paarungen, Daten)
      2. Alle Anstoßzeiten löschen
      3. AK für AK (jüngste zuerst) jedem Spiel einen freien Slot zuweisen
      4. Bei Konflikt: nächsten freien Slot oder H/A-Tausch
      5. Garantie: Jedes Spiel bekommt eine Uhrzeit, keine Überlappungen

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

    # CP-SAT Slot-Vergabe: globale Optimierung, konfliktfrei
    from src.spielplanerstellung.slot_solver import solve_game_slots
    solve_game_slots(alle_plaene, time_limit_seconds=120)

    # Zähle verbleibende Konflikte (sollte 0 oder nahe 0 sein)
    _update_platz_konflikte(alle_plaene)

    return alle_plaene


def _update_platz_konflikte(plaene: list[StaffelSpielplan]) -> None:
    """Zählt verbleibende Spielfeld-Konflikte nach der Auflösung und aktualisiert Scores."""
    # Sammle alle Spiele → (feld, datum) → [(zeit_start, zeit_end, halbfeld)]
    from collections import defaultdict
    belegung: dict[tuple[str, str], list[tuple[int, int, bool]]] = defaultdict(list)

    for plan in plaene:
        halbfeld = _ist_halbfeld(plan.altersklasse)
        dauer = _get_spieldauer_min(plan.altersklasse)
        for st in plan.spieltage:
            for spiel in st.spiele:
                if not spiel.spielfeld or not spiel.datum:
                    continue
                key = (spiel.spielfeld.strip().lower(), spiel.datum.isoformat())
                zeit = _parse_time(spiel.anstosszeit)
                start = zeit[0] * 60 + zeit[1] if zeit else 720
                belegung[key].append((start, start + dauer, halbfeld))

    # Zähle Konflikte pro Feld/Datum
    remaining: dict[tuple[str, str], int] = {}
    for key, entries in belegung.items():
        entries.sort()
        konflikte = 0
        for i in range(len(entries)):
            for j in range(i + 1, len(entries)):
                s_i, e_i, hf_i = entries[i]
                s_j, e_j, hf_j = entries[j]
                # Überlappung?
                if s_j < e_i:
                    # Halbfeld: 2 gleichzeitig OK
                    if hf_i and hf_j and s_i == s_j:
                        continue
                    konflikte += 1
        remaining[key] = konflikte

    # Verteile auf Staffeln: Jede Staffel bekommt die Konflikte ihrer Heimspiele
    for plan in plaene:
        if not plan.score:
            continue
        plan.score.platz_konflikte = 0
        for st in plan.spieltage:
            for spiel in st.spiele:
                if not spiel.spielfeld or not spiel.datum:
                    continue
                key = (spiel.spielfeld.strip().lower(), spiel.datum.isoformat())
                if remaining.get(key, 0) > 0:
                    plan.score.platz_konflikte += 1
                    remaining[key] -= 1
        plan.score.berechne_total()


# ─── Inkrementelle Slot-Vergabe ────────────────────────────────

# AK-Reihenfolge: jüngste zuerst (bekommen die Wunschzeiten)
_AK_ORDER: dict[str, int] = {
    "F-Junioren": 0, "F-Juniorinnen": 1,
    "E-Junioren": 2, "E-Juniorinnen": 3,
    "D-Junioren": 4, "D-Juniorinnen": 5,
    "C-Junioren": 6, "C-Juniorinnen": 7,
    "B-Junioren": 8, "B-Juniorinnen": 9,
    "A-Junioren": 10, "A-Juniorinnen": 11,
}

# Frühester / spätester Anstoß (Sommer vs. Winter)
_EARLIEST_SUMMER = 9 * 60           # 09:00
_LATEST_SUMMER = 19 * 60 + 30       # 19:30
_EARLIEST_WINTER = 9 * 60           # 09:00
_LATEST_WINTER = 17 * 60            # 17:00


def _assign_slots_incremental(plaene: list[StaffelSpielplan]) -> None:
    """Weist allen Spielen konfliktfrei Anstoßzeiten zu.

    Vorgehen:
      1. Sammle alle Spiele aller Staffeln
      2. Sortiere: jüngste AK zuerst → bekommen ihre Wunschzeit
      3. Für jedes Spiel: finde an (spielfeld, datum) den ersten freien Slot
      4. Falls kein Slot frei: tausche Heim/Auswärts und probiere Gast-Venue
      5. Fallback: nächster freier Slot (auch nach Standardzeiten)
    """
    # Globale Belegung: (venue_lower, datum_iso) → [(start_min, end_min, halbfeld)]
    venue_slots: dict[tuple[str, str], list[tuple[int, int, bool]]] = {}

    # Sammle alle Spiele mit Metadaten
    all_games: list[tuple[int, StaffelSpielplan, Spieltag, Spiel]] = []
    for plan in plaene:
        ak_order = _AK_ORDER.get(plan.altersklasse, 99)
        for st in plan.spieltage:
            for spiel in st.spiele:
                all_games.append((ak_order, plan, st, spiel))

    # Sortiere: jüngste AK zuerst
    all_games.sort(key=lambda x: x[0])

    for _, plan, st, spiel in all_games:
        if not spiel.datum:
            # Kein Datum (z.B. Rückrunde) → Standardzeit behalten
            continue

        ak = plan.altersklasse
        dauer = _get_spieldauer_min(ak)
        halbfeld = _ist_halbfeld(ak)

        # Winter oder Sommer?
        is_winter = spiel.datum.month in (11, 12, 1, 2)
        earliest = _EARLIEST_WINTER if is_winter else _EARLIEST_SUMMER
        latest = _LATEST_WINTER if is_winter else _LATEST_SUMMER

        # Gewünschte Startzeit (aus Terminplan)
        preferred = _parse_time(spiel.anstosszeit)
        preferred_min = preferred[0] * 60 + preferred[1] if preferred else (earliest + 60)

        # Versuche zuerst am Heim-Venue
        venue = spiel.spielfeld.strip().lower() if spiel.spielfeld else ""
        datum_iso = spiel.datum.isoformat()

        if venue:
            slot = _find_free_slot(
                venue_slots, venue, datum_iso, preferred_min, dauer, halbfeld, earliest, latest
            )
            if slot is not None:
                _book_slot(venue_slots, venue, datum_iso, slot, dauer, halbfeld)
                spiel.anstosszeit = _format_time(slot // 60, slot % 60)
                continue

        # Heim-Venue voll → versuche H/A-Tausch
        gast_addr = _find_adresse(plan.sz_zuordnungen, spiel.gast)
        gast_venue = gast_addr.strip().lower() if gast_addr else ""

        if gast_venue and gast_venue != venue:
            slot = _find_free_slot(
                venue_slots, gast_venue, datum_iso, preferred_min, dauer, halbfeld, earliest, latest
            )
            if slot is not None:
                # Tausche Heim/Auswärts
                spiel.heim, spiel.gast = spiel.gast, spiel.heim
                spiel.heim_verein, spiel.gast_verein = spiel.gast_verein, spiel.heim_verein
                spiel.spielfeld = gast_addr
                _book_slot(venue_slots, gast_venue, datum_iso, slot, dauer, halbfeld)
                spiel.anstosszeit = _format_time(slot // 60, slot % 60)
                continue

        # Fallback: forciere am Heim-Venue (auch spätere Zeiten)
        if venue:
            slot = _find_free_slot(
                venue_slots, venue, datum_iso, earliest, dauer, halbfeld, earliest, 23 * 60
            )
            if slot is not None:
                _book_slot(venue_slots, venue, datum_iso, slot, dauer, halbfeld)
                spiel.anstosszeit = _format_time(slot // 60, slot % 60)
                continue

        # Absoluter Fallback: behalte Standardzeit (kann Konflikt geben)
        if preferred:
            _book_slot(venue_slots, venue or "__unknown__", datum_iso, preferred_min, dauer, halbfeld)


def _find_free_slot(
    venue_slots: dict[tuple[str, str], list[tuple[int, int, bool]]],
    venue: str,
    datum_iso: str,
    preferred_start: int,
    dauer: int,
    halbfeld: bool,
    earliest: int,
    latest: int,
) -> int | None:
    """Findet den nächsten freien Slot ab preferred_start.

    Gibt die Startzeit in Minuten zurück, oder None wenn nichts passt.
    """
    key = (venue, datum_iso)
    existing = venue_slots.get(key, [])

    # Versuche preferred_start zuerst, dann in 15-Min-Schritten aufwärts
    for offset in range(0, latest - earliest + dauer, 15):
        candidate = preferred_start + offset
        if candidate < earliest:
            continue
        if candidate + dauer > latest + dauer:  # Spiel darf bis latest + dauer_min laufen
            break

        end = candidate + dauer

        conflict = False
        for s_start, s_end, s_hf in existing:
            # Überlappung?
            if candidate < s_end and end > s_start:
                # Halbfeld: 2 gleichzeitig OK wenn gleiche Startzeit
                if halbfeld and s_hf and candidate == s_start:
                    # Zähle wie viele schon zu dieser Zeit laufen
                    same_time = sum(1 for ss, se, shf in existing if shf and ss == candidate)
                    if same_time < 2:
                        continue
                conflict = True
                break

        if not conflict:
            return candidate

    # Auch vor preferred_start probieren
    for offset in range(15, preferred_start - earliest + 15, 15):
        candidate = preferred_start - offset
        if candidate < earliest:
            break

        end = candidate + dauer
        conflict = False
        for s_start, s_end, s_hf in existing:
            if candidate < s_end and end > s_start:
                if halbfeld and s_hf and candidate == s_start:
                    same_time = sum(1 for ss, se, shf in existing if shf and ss == candidate)
                    if same_time < 2:
                        continue
                conflict = True
                break

        if not conflict:
            return candidate

    return None


def _book_slot(
    venue_slots: dict[tuple[str, str], list[tuple[int, int, bool]]],
    venue: str,
    datum_iso: str,
    start: int,
    dauer: int,
    halbfeld: bool,
) -> None:
    """Bucht einen Slot in der Venue-Belegung."""
    key = (venue, datum_iso)
    venue_slots.setdefault(key, []).append((start, start + dauer, halbfeld))

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
            "consecutive_penalty": round(plan.score.consecutive_penalty, 1),
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
