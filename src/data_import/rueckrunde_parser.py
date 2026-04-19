"""Parser für Einteilungs-Excel (Hinrunde und Rückrunde).

Liest die vom Spielleiter vorgegebenen Staffelzuordnungen
aus den Einteilungs-Excel-Dateien.

Unterstützte Formate:
    - Rückrunde: Leistungsstaffel, Kreisstaffel, Bezirksstaffel
    - Hinrunde: Qualistaffel, Regionenstaffel, Quali Bezirksstaffel

Die Mannschaften werden gegen die Meldeliste abgeglichen,
um Spielstätten-/Wünsche-Daten anzureichern.
"""

import re
from dataclasses import dataclass

import openpyxl

from src.common.models import Mannschaft


# Pattern für Staffel-Header-Erkennung (Hinrunde + Rückrunde)
_STAFFEL_HEADER_RE = re.compile(
    r"^([A-E]-Junior(?:en|innen))\s+"
    r"(Leistungsstaffel|Kreisstaffel|Bezirksstaffel"
    r"|Qualistaffel|Quali\s*Bezirksstaffel"
    r"|Regionenstaffel(?:\s+\w+)?)\s*"
    r"(\d+)?\s*(?:\(.*\))?",
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


def _name_words(name: str) -> set[str]:
    """Extrahiert signifikante Wörter für Fuzzy-Matching.

    Splittet auf Leerzeichen, /, - und entfernt Abkürzungspunkte.
    """
    # Punkte am Wortende entfernen (Abkürzungen wie "Markelsh.")
    clean = re.sub(r"\.(?=\s|/|-|$)", "", name)
    # Split auf Leerzeichen, / und -
    parts = re.split(r"[\s/\-]+", clean)
    return set(w for w in parts if len(w) > 2)


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
        # Beide Formate: "A-Junioren" (25-26) und "Einteilung A-Junioren" (24-25)
        if not re.search(r"[A-E]-Junior|Juniorinnen", sheet_name, re.IGNORECASE):
            continue

        ws = wb[sheet_name]
        rows = list(ws.iter_rows(values_only=True))

        # Finde alle Staffel-Header mit Position
        headers: list[tuple[int, int, RueckrundeStaffel]] = []  # (row, col, staffel)

        for ri, row in enumerate(rows):
            # Alle Spalten scannen (24-25 B-Junioren hat Staffel 2 bei col 6 statt 5)
            for col_offset in range(min(len(row), 20)):
                cell = row[col_offset]
                if not cell or not isinstance(cell, str):
                    continue
                m = _STAFFEL_HEADER_RE.match(cell.strip())
                if m:
                    ak = m.group(1)
                    typ = m.group(2)
                    nr_str = m.group(3)
                    nr = int(nr_str) if nr_str else 1
                    dr = "(Doppelrunde)" in cell or "(DR)" in cell

                    staffel = RueckrundeStaffel(
                        name=cell.strip(),
                        altersklasse=ak,
                        staffeltyp=typ,
                        nummer=nr,
                        doppelrunde=dr,
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
    Matching berücksichtigt die Altersklasse der Staffel.

    Returns:
        (matched, unmatched) Anzahl
    """
    # Index: (normalisierter Name, altersklasse) → Mannschaft
    ak_name_index: dict[tuple[str, str], Mannschaft] = {}
    # Fallback-Index ohne AK (für Juniorinnen etc.)
    name_index: dict[str, list[Mannschaft]] = {}
    for m in mannschaften:
        key = _normalize_name(m.mannschaftsname)
        ak_key = _normalize_ak(m.altersklasse)
        ak_name_index[(key, ak_key)] = m
        if key not in name_index:
            name_index[key] = []
        name_index[key].append(m)

    for staffel in staffeln:
        staffel_ak = _normalize_ak(staffel.altersklasse)

        for team in staffel.teams:
            norm = _normalize_name(team.name)

            # 1. Exakter Match mit AK
            ak_match = ak_name_index.get((norm, staffel_ak))
            if ak_match:
                team.mannschaft = ak_match
                continue

            # 2. Exakter Name ohne AK (Fallback)
            if norm in name_index:
                team.mannschaft = name_index[norm][0]
                continue

            # 3. Substring-Match mit AK-Präferenz
            found = False
            for (key, ak), m in ak_name_index.items():
                if ak == staffel_ak and (norm in key or key in norm):
                    team.mannschaft = m
                    found = True
                    break

            if not found:
                # 4. Substring-Match ohne AK
                for key, ml in name_index.items():
                    if norm in key or key in norm:
                        team.mannschaft = ml[0]
                        found = True
                        break

            if not found:
                # 5. Wort-basierter Match mit AK-Präferenz
                norm_words = _name_words(norm)
                best_score = 0
                best_match = None
                for (key, ak), m in ak_name_index.items():
                    key_words = _name_words(key)
                    # Exakte Wort-Überlappung
                    common = norm_words & key_words
                    # Abkürzungs-Match: "Markelsh" startswith "Markelsheim"[:8]
                    for nw in norm_words - common:
                        for kw in key_words - common:
                            if len(nw) >= 4 and len(kw) >= 4:
                                if nw.startswith(kw[:4]) or kw.startswith(nw[:4]):
                                    common.add(nw)
                                    break
                    score = len(common)
                    # Bonus für passende AK
                    if ak == staffel_ak:
                        score += 0.5
                    if score > best_score and len(common) >= 2:
                        best_score = score
                        best_match = m

                if best_match:
                    team.mannschaft = best_match

    # Unique matched Meldeliste-Teams zählen
    matched_set: set[int] = set()
    unmatched = 0
    for staffel in staffeln:
        for team in staffel.teams:
            if team.mannschaft:
                matched_set.add(id(team.mannschaft))
            else:
                unmatched += 1

    return len(matched_set), unmatched


def _normalize_ak(ak: str) -> str:
    """Normalisiert Altersklasse für Matching."""
    return ak.strip().lower()


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
    t = typ.lower()
    if "leistung" in t or "regionenstaffel" in t:
        return "Leistungsstaffel"
    elif "bezirk" in t:
        return "Bezirksstaffel"
    elif "quali" in t:
        return "Qualistaffel"
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
