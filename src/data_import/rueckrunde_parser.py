"""Parser für die Rückrunde-Einteilungs-Excel.

Liest die vom Spielleiter vorgegebenen Staffelzuordnungen
aus dem Excel „Einteilungen Rückrunde 25-26 Junioren und Juniorinnen.xlsx".

Format pro Sheet (= Altersklasse):
    - Staffel-Header in Spalten 0, 5, 10 (5er-Blöcke)
    - Darunter: Rang, Mannschaftsname, Punkte, Quotient
    - Mehrere Staffel-Blöcke vertikal und horizontal

Die Mannschaften werden gegen die Meldeliste abgeglichen,
um Spielstätten-/Wünsche-Daten anzureichern.
"""

import re
from dataclasses import dataclass

import openpyxl

from src.common.models import Mannschaft


# Pattern für Staffel-Header-Erkennung
_STAFFEL_HEADER_RE = re.compile(
    r"^([A-E]-Junior(?:en|innen))\s+"
    r"(Leistungsstaffel|Kreisstaffel|Bezirksstaffel)\s*"
    r"(\d+)?\s*(\(Doppelrunde\))?",
    re.IGNORECASE,
)

# Pattern für Rang-Zelle ("1.", "2.", "10." etc.)
_RANG_RE = re.compile(r"^(\d{1,2})\.\s*$")

# Suffixe die beim Matching entfernt werden
_STRIP_SUFFIXES = re.compile(r"\s*\((?:flex|DR)\)\s*$|\s*zg\.\s*$", re.IGNORECASE)


@dataclass
class RueckrundeTeam:
    """Ein Team in einer Rückrunde-Staffel."""
    rang: int
    name: str  # Mannschaftsname aus dem Rückrunde-Excel
    punkte: float | None = None
    quotient: float | None = None
    ist_flex: bool = False
    mannschaft: Mannschaft | None = None  # Verknüpft nach Matching


@dataclass
class RueckrundeStaffel:
    """Eine Staffel aus der Rückrunde-Einteilung."""
    name: str  # z.B. "A-Junioren Leistungsstaffel 1"
    altersklasse: str  # z.B. "A-Junioren"
    staffeltyp: str  # "Leistungsstaffel", "Kreisstaffel", "Bezirksstaffel"
    nummer: int
    doppelrunde: bool = False
    teams: list[RueckrundeTeam] | None = None

    def __post_init__(self):
        if self.teams is None:
            self.teams = []


def _normalize_name(name: str) -> str:
    """Normalisiert einen Mannschaftsnamen für das Matching."""
    name = _STRIP_SUFFIXES.sub("", name).strip()
    # Mehrfach-Leerzeichen → einfach
    name = re.sub(r"\s+", " ", name)
    return name.lower()


def _safe_float(val) -> float | None:
    """Konvertiert einen Wert zu float, oder None."""
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def parse_rueckrunde_einteilung(excel_path: str) -> list[RueckrundeStaffel]:
    """Parst die Rückrunde-Einteilung aus dem Excel.

    Args:
        excel_path: Pfad zur Einteilungs-Excel-Datei

    Returns:
        Liste von RueckrundeStaffel mit zugeordneten Teams
    """
    wb = openpyxl.load_workbook(excel_path, data_only=True, read_only=True)
    staffeln: list[RueckrundeStaffel] = []

    for sheet_name in wb.sheetnames:
        # Nur Altersklassen-Sheets verarbeiten
        if not re.match(r"[A-E]-Junior", sheet_name):
            continue

        ws = wb[sheet_name]
        rows = list(ws.iter_rows(values_only=True))

        # Finde alle Staffel-Header mit Position
        headers: list[tuple[int, int, RueckrundeStaffel]] = []  # (row, col, staffel)

        for ri, row in enumerate(rows):
            for col_offset in (0, 5, 10):
                if col_offset >= len(row):
                    continue
                cell = row[col_offset]
                if not cell or not isinstance(cell, str):
                    continue
                m = _STAFFEL_HEADER_RE.match(cell.strip())
                if m:
                    ak = m.group(1)
                    typ = m.group(2)
                    nr_str = m.group(3)
                    nr = int(nr_str) if nr_str else 1
                    dr = bool(m.group(4))

                    staffel = RueckrundeStaffel(
                        name=cell.strip().replace(" (Doppelrunde)", ""),
                        altersklasse=ak,
                        staffeltyp=typ,
                        nummer=nr,
                        doppelrunde=dr or "(Doppelrunde)" in cell,
                    )
                    headers.append((ri, col_offset, staffel))

        # Für jeden Header: Teams aus den Zeilen darunter lesen
        for hi, (header_row, col_offset, staffel) in enumerate(headers):
            # Bestimme die letzte Zeile dieses Blocks:
            # - Nächster Header auf gleicher col_offset
            # - Oder Ende des Sheets
            next_header_row = len(rows)
            for hj in range(hi + 1, len(headers)):
                if headers[hj][1] == col_offset and headers[hj][0] > header_row:
                    next_header_row = headers[hj][0]
                    break

            # Teams lesen (Header+1 überspringen = Spaltenüberschriften "Punkte", "Q")
            for ri in range(header_row + 1, min(next_header_row, len(rows))):
                row = rows[ri]
                if col_offset >= len(row):
                    continue

                rang_cell = row[col_offset]
                name_cell = row[col_offset + 1] if col_offset + 1 < len(row) else None

                # Prüfe auf Rang-Pattern
                if rang_cell is None or name_cell is None:
                    continue

                rang_str = str(rang_cell).strip()
                rang_match = _RANG_RE.match(rang_str)

                # Auch "1" ohne Punkt akzeptieren
                if not rang_match:
                    try:
                        r = int(rang_str)
                        if 1 <= r <= 20:
                            rang_match = True
                            rang_val = r
                    except (ValueError, TypeError):
                        continue
                else:
                    rang_val = int(rang_match.group(1))

                if not rang_match:
                    continue

                name = str(name_cell).strip()
                if not name or name.lower() in ("punkte", "q", "sl:", ""):
                    continue

                # Punkte und Quotient
                punkte = _safe_float(row[col_offset + 2] if col_offset + 2 < len(row) else None)
                quotient = _safe_float(row[col_offset + 3] if col_offset + 3 < len(row) else None)

                ist_flex = "(flex)" in name.lower()

                team = RueckrundeTeam(
                    rang=rang_val,
                    name=name,
                    punkte=punkte,
                    quotient=quotient,
                    ist_flex=ist_flex,
                )
                staffel.teams.append(team)

            staffeln.append(staffel)

    wb.close()
    return staffeln


def match_teams_gegen_meldeliste(
    staffeln: list[RueckrundeStaffel],
    mannschaften: list[Mannschaft],
) -> tuple[int, int]:
    """Verknüpft Rückrunde-Teams mit Mannschaften aus der Meldeliste.

    Setzt team.mannschaft auf das passende Mannschaft-Objekt.

    Returns:
        (matched, unmatched) Anzahl
    """
    # Index: normalisierter Name → Mannschaft
    name_index: dict[str, Mannschaft] = {}
    for m in mannschaften:
        key = _normalize_name(m.mannschaftsname)
        name_index[key] = m

    matched = 0
    unmatched = 0

    for staffel in staffeln:
        for team in staffel.teams:
            norm = _normalize_name(team.name)

            # 1. Exakter Match
            if norm in name_index:
                team.mannschaft = name_index[norm]
                matched += 1
                continue

            # 2. Substring-Match: Rückrunde-Name enthält Meldeliste-Name oder umgekehrt
            found = False
            for key, m in name_index.items():
                if norm in key or key in norm:
                    team.mannschaft = m
                    matched += 1
                    found = True
                    break

            if not found:
                # 3. Wort-basierter Match: mind. 2 signifikante Wörter übereinstimmend
                norm_words = set(w for w in norm.split() if len(w) > 2)
                best_score = 0
                best_match = None
                for key, m in name_index.items():
                    key_words = set(w for w in key.split() if len(w) > 2)
                    common = norm_words & key_words
                    if len(common) > best_score and len(common) >= 2:
                        best_score = len(common)
                        best_match = m

                if best_match:
                    team.mannschaft = best_match
                    matched += 1
                else:
                    unmatched += 1

    return matched, unmatched


def staffeln_to_einteilung_result(
    staffeln: list[RueckrundeStaffel],
    total_teams_meldeliste: int,
    teams_mit_coords: int,
) -> dict:
    """Konvertiert Rückrunde-Staffeln in das API-Ergebnis-Format.

    Gleiche Struktur wie /api/einteilung damit die UI und
    Spielplan-Pipeline unverändert funktionieren.
    """
    from src.common.distanz import haversine_km

    # Gruppiere Staffeln nach (Altersklasse, Staffeltyp)
    gruppen_map: dict[tuple[str, str], list[RueckrundeStaffel]] = {}
    for s in staffeln:
        key = (s.altersklasse, s.staffeltyp)
        if key not in gruppen_map:
            gruppen_map[key] = []
        gruppen_map[key].append(s)

    gruppen = []
    for (ak, typ), staffel_list in sorted(gruppen_map.items()):
        topf_str = _staffeltyp_to_topf(typ)

        # Alle Teams über alle Staffeln dieser Gruppe
        n_teams = sum(len(s.teams) for s in staffel_list)

        gruppe_data = {
            "altersklasse": ak,
            "spielklasse": typ,
            "topf": topf_str,
            "n_teams": n_teams,
            "staffeln": [],
            "score": None,
            "merged": False,
            "rueckrunde": True,
        }

        for s in sorted(staffel_list, key=lambda x: x.nummer):
            staffel_dict = _staffel_to_dict(s)
            gruppe_data["staffeln"].append(staffel_dict)

        gruppen.append(gruppe_data)

    return {
        "total_teams": total_teams_meldeliste,
        "teams_mit_coords": teams_mit_coords,
        "rueckrunde": True,
        "gruppen": gruppen,
    }


def _staffeltyp_to_topf(typ: str) -> str:
    """Mappt Staffeltyp auf Topf-String für die API."""
    if "Leistung" in typ:
        return "Leistungsstaffel"
    elif "Bezirk" in typ:
        return "Bezirksstaffel"
    else:
        return "Kreisstaffel"


def _staffel_to_dict(staffel: RueckrundeStaffel) -> dict:
    """Konvertiert eine RueckrundeStaffel in ein JSON-Dict."""
    from src.common.distanz import haversine_km

    teams = []
    for t in staffel.teams:
        team_dict = {
            "mannschaft": t.name,
            "rang_hinrunde": t.rang,
            "punkte_hinrunde": t.punkte,
            "quotient_hinrunde": t.quotient,
            "ist_flex": t.ist_flex,
            "verein": "",
            "verein_nr": "",
            "region": "?",
            "topf": None,
            "wuensche_text": "",
        }

        if t.mannschaft:
            team_dict["mannschaft"] = t.mannschaft.mannschaftsname
            team_dict["verein"] = t.mannschaft.vereinsname
            team_dict["verein_nr"] = t.mannschaft.verein_nr
            team_dict["region"] = t.mannschaft.bezirk_alt or "?"
            team_dict["topf"] = t.mannschaft.topf
            team_dict["wuensche_text"] = t.mannschaft.wuensche_text or ""
            if t.mannschaft.spielstaette:
                team_dict["spielstaette"] = t.mannschaft.spielstaette.name or ""
                team_dict["adresse"] = t.mannschaft.spielstaette.adresse or ""
                team_dict["lat"] = t.mannschaft.spielstaette.lat
                team_dict["lon"] = t.mannschaft.spielstaette.lon

        teams.append(team_dict)

    # Max paarweise Distanz
    max_dist = 0.0
    mannschaften_mit_coords = [
        t.mannschaft for t in staffel.teams
        if t.mannschaft and t.mannschaft.spielstaette and t.mannschaft.spielstaette.lat is not None
    ]
    for i in range(len(mannschaften_mit_coords)):
        a = mannschaften_mit_coords[i].spielstaette
        for j in range(i + 1, len(mannschaften_mit_coords)):
            b = mannschaften_mit_coords[j].spielstaette
            d = haversine_km(a.lat, a.lon, b.lat, b.lon)
            if d > max_dist:
                max_dist = d

    return {
        "staffel_name": staffel.name,
        "n_teams": len(staffel.teams),
        "teams": teams,
        "max_distanz_km": round(max_dist, 1),
        "doppelrunde": staffel.doppelrunde or len(staffel.teams) < 5,
    }
