"""FastAPI Backend für die Spieltagsplanung.

Starten:
    python -m uvicorn src.api.server:app --reload --port 8000
"""

import sys
import tempfile
import shutil
from pathlib import Path

from fastapi import FastAPI, UploadFile, File, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from src.data_import.meldeliste_parser import parse_meldeliste, verknuepfe_koordinaten
from src.staffeleinteilung.algorithmus import gruppiere_mannschaften, einteilung_erstellen
from src.staffeleinteilung.scoring import ScoreGewichte
from src.common.distanz import haversine_km
from src.spielplanerstellung.wuensche_parser import parse_wuensche_llm
from src.spielplanerstellung.wuensche import Wunsch, WunschKategorie, WunschPrio, VereinsWuensche
from src.spielplanerstellung.spielplan import generiere_alle_spielplaene, spielplan_to_dict

app = FastAPI(title="Spieltagsplaner", version="1.0")

# Static files
UI_DIR = ROOT / "ui"
app.mount("/assets", StaticFiles(directory=str(UI_DIR / "assets")), name="assets")


# ─── Pages ─────────────────────────────────────────────────────

@app.get("/")
async def index():
    return FileResponse(str(UI_DIR / "index.html"))


@app.get("/app")
async def app_page():
    return FileResponse(str(UI_DIR / "app.html"))


# ─── API ───────────────────────────────────────────────────────

@app.post("/api/einteilung")
async def api_einteilung(
    file: UploadFile = File(...),
    w_distanz: float = 1.0,
    w_region: float = 50.0,
    w_balance: float = 20.0,
    max_staffel_size: int = 11,
):
    """Upload Meldeliste Excel → Staffeleinteilung berechnen."""
    if not file.filename.endswith((".xlsx", ".xls")):
        raise HTTPException(400, "Nur Excel-Dateien (.xlsx) erlaubt")

    # Save uploaded file to temp
    with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as tmp:
        shutil.copyfileobj(file.file, tmp)
        tmp_path = tmp.name

    try:
        mannschaften = parse_meldeliste(tmp_path)
        n_coords = verknuepfe_koordinaten(mannschaften)

        gewichte = ScoreGewichte(
            w_distanz=w_distanz,
            w_region=w_region,
            w_balance=w_balance,
            max_staffel_size=max_staffel_size,
        )

        gruppen = gruppiere_mannschaften(mannschaften)

        result = {
            "total_teams": len(mannschaften),
            "teams_mit_coords": n_coords,
            "gruppen": [],
        }

        for (ak, sk, topf), ms in sorted(gruppen.items()):
            topf_str = f"Topf {topf}" if topf > 0 else "fix"

            gruppe_data = {
                "altersklasse": ak,
                "spielklasse": sk,
                "topf": topf_str,
                "n_teams": len(ms),
                "staffeln": [],
                "score": None,
                "merged": False,
            }

            # Regionenstaffel: single staffel if small enough
            if topf == 0 and len(ms) <= max_staffel_size:
                gruppe_data["staffeln"] = [_staffel_to_dict(ms)]
                result["gruppen"].append(gruppe_data)
                continue

            if topf == 0 and len(ms) > max_staffel_size:
                gruppe_data["merged"] = True

            if len(ms) < 4:
                staffeln_list = [ms]
            else:
                staffeln_list, score = einteilung_erstellen(ms, gewichte)
                gruppe_data["score"] = {
                    "total": round(score.total, 1),
                    "distanz": round(score.distanz_score, 1),
                    "region": int(score.region_score),
                    "balance": round(score.balance_score, 2),
                    "violations": score.hard_violations,
                }

            for staffel in staffeln_list:
                gruppe_data["staffeln"].append(_staffel_to_dict(staffel))

            result["gruppen"].append(gruppe_data)

        return JSONResponse(result)

    except Exception as e:
        raise HTTPException(500, f"Fehler bei Verarbeitung: {str(e)}")
    finally:
        Path(tmp_path).unlink(missing_ok=True)


def _staffel_to_dict(mannschaften: list) -> dict:
    """Konvertiert eine Staffel (Liste von Mannschaft) in ein JSON-fähiges dict."""
    teams = []
    for m in sorted(mannschaften, key=lambda x: x.mannschaftsname):
        team = {
            "mannschaft": m.mannschaftsname,
            "verein": m.vereinsname,
            "verein_nr": m.verein_nr,
            "region": m.bezirk_alt or "?",
            "topf": m.topf,
            "wuensche_text": m.wuensche_text or "",
        }
        if m.spielstaette:
            team["spielstaette"] = m.spielstaette.name or ""
            team["adresse"] = m.spielstaette.adresse or ""
            team["lat"] = m.spielstaette.lat
            team["lon"] = m.spielstaette.lon
        teams.append(team)

    # Max pairwise distance
    max_dist = 0
    for i in range(len(mannschaften)):
        a = mannschaften[i]
        if not a.spielstaette or a.spielstaette.lat is None:
            continue
        for j in range(i + 1, len(mannschaften)):
            b = mannschaften[j]
            if not b.spielstaette or b.spielstaette.lat is None:
                continue
            d = haversine_km(
                a.spielstaette.lat, a.spielstaette.lon,
                b.spielstaette.lat, b.spielstaette.lon,
            )
            if d > max_dist:
                max_dist = d

    doppelrunde = len(mannschaften) < 5

    return {
        "n_teams": len(mannschaften),
        "teams": teams,
        "max_distanz_km": round(max_dist, 1),
        "doppelrunde": doppelrunde,
    }


# ─── Excel Export ──────────────────────────────────────────────

@app.post("/api/export")
async def api_export(request: Request):
    """Generiert eine Excel-Datei aus dem Einteilungsergebnis."""
    data = await request.json()
    gruppen = data.get("gruppen", [])
    if not gruppen:
        raise HTTPException(400, "Keine Gruppen vorhanden")

    wb = Workbook()

    # ── Styles ──
    header_font = Font(bold=True, color="FFFFFF", size=11)
    header_fill = PatternFill(start_color="C41230", end_color="C41230", fill_type="solid")
    staffel_font = Font(bold=True, size=11, color="C41230")
    thin_border = Border(
        bottom=Side(style="thin", color="E5E7EB"),
    )
    center = Alignment(horizontal="center")

    # ── Sheet 1: Übersicht ──
    ws_ueb = wb.active
    ws_ueb.title = "Übersicht"
    ueb_headers = ["Altersklasse", "Topf", "Teams", "Staffeln", "Ø Distanz (km)", "Probleme"]
    for ci, h in enumerate(ueb_headers, 1):
        cell = ws_ueb.cell(row=1, column=ci, value=h)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = center

    for ri, g in enumerate(gruppen, 2):
        ws_ueb.cell(row=ri, column=1, value=g["altersklasse"])
        ws_ueb.cell(row=ri, column=2, value=g["topf"])
        ws_ueb.cell(row=ri, column=3, value=g["n_teams"]).alignment = center
        ws_ueb.cell(row=ri, column=4, value=len(g["staffeln"])).alignment = center
        dist = g["score"]["distanz"] if g.get("score") else "-"
        ws_ueb.cell(row=ri, column=5, value=dist).alignment = center
        viol = g["score"]["violations"] if g.get("score") else 0
        ws_ueb.cell(row=ri, column=6, value=viol).alignment = center

    for col in ws_ueb.columns:
        ws_ueb.column_dimensions[col[0].column_letter].width = 18

    # ── Sheets per Altersklasse/Topf ──
    for g in gruppen:
        sheet_name = f"{g['altersklasse']} {g['topf']}"[:31]  # Excel max 31 chars
        ws = wb.create_sheet(title=sheet_name)

        row = 1
        for si, staffel in enumerate(g["staffeln"]):
            # Staffel header
            label = f"Staffel {si + 1}"
            if staffel.get("doppelrunde"):
                label += " (Doppelrunde)"
            label += f"  —  {staffel['n_teams']} Teams, Max. {staffel['max_distanz_km']} km"
            cell = ws.cell(row=row, column=1, value=label)
            cell.font = staffel_font
            ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=5)
            row += 1

            # Table headers
            team_headers = ["Nr.", "Mannschaft", "Verein", "Region", "Ort"]
            for ci, h in enumerate(team_headers, 1):
                cell = ws.cell(row=row, column=ci, value=h)
                cell.font = header_font
                cell.fill = header_fill
                cell.alignment = center
            row += 1

            # Team rows
            for ti, t in enumerate(staffel["teams"], 1):
                ws.cell(row=row, column=1, value=ti).alignment = center
                ws.cell(row=row, column=2, value=t["mannschaft"])
                ws.cell(row=row, column=3, value=t.get("verein", ""))
                ws.cell(row=row, column=4, value=t.get("region", ""))
                ort = t.get("adresse", "").split(", ")[-1] if t.get("adresse") else ""
                ws.cell(row=row, column=5, value=ort)
                for ci in range(1, 6):
                    ws.cell(row=row, column=ci).border = thin_border
                row += 1

            row += 1  # empty row between staffeln

        # Column widths
        ws.column_dimensions["A"].width = 6
        ws.column_dimensions["B"].width = 30
        ws.column_dimensions["C"].width = 30
        ws.column_dimensions["D"].width = 14
        ws.column_dimensions["E"].width = 22

    # Save to temp file
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx")
    wb.save(tmp.name)
    tmp.close()

    return FileResponse(
        tmp.name,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename="Staffeleinteilung.xlsx",
    )


# ─── Vereinswünsche LLM Parsing ───────────────────────────────

@app.post("/api/wuensche/parse")
async def api_parse_wuensche(request: Request):
    """Freitext-Wünsche per LLM in strukturierte Flags umwandeln."""
    data = await request.json()
    freitext = data.get("text", "")
    mannschaft = data.get("mannschaft", "")
    verein = data.get("verein", "")
    provider = data.get("provider", "ollama")
    model = data.get("model", "llama3")
    api_base = data.get("api_base")
    api_key = data.get("api_key")

    if not freitext.strip():
        raise HTTPException(400, "Kein Text angegeben")

    try:
        result = parse_wuensche_llm(
            freitext=freitext,
            mannschaft=mannschaft,
            verein=verein,
            provider=provider,
            model=model,
            api_base=api_base,
            api_key=api_key,
        )
        return JSONResponse({
            "mannschaft": result.mannschaft,
            "verein": result.verein,
            "wuensche": [
                {
                    "kategorie": w.kategorie.value,
                    "prioritaet": w.prioritaet.value,
                    "beschreibung": w.beschreibung,
                    "datum": w.datum,
                    "wochentag": w.wochentag,
                    "uhrzeit": w.uhrzeit,
                    "bezug_mannschaft": w.bezug_mannschaft,
                }
                for w in result.wuensche
            ],
        })
    except Exception as e:
        raise HTTPException(500, f"LLM-Fehler: {str(e)}")


# ─── Spielplan-Generierung ─────────────────────────────────────

@app.post("/api/spielplan")
async def api_spielplan(request: Request):
    """Generiert Spielpläne für alle Staffeln aus der Einteilung."""
    data = await request.json()
    einteilung = data.get("einteilung")
    saison = data.get("saison", "")
    if not einteilung or not einteilung.get("gruppen"):
        raise HTTPException(400, "Keine Einteilung vorhanden")

    try:
        # Wünsche regelbasiert parsen (schnell, kein LLM)
        wuensche = _parse_wuensche_fast(einteilung, saison)

        plaene = generiere_alle_spielplaene(
            einteilung, wuensche=wuensche if wuensche else None,
        )
        # Count resolved changes (staggered times + H/A swaps)
        resolved = sum(1 for p in plaene for st in p.spieltage for s in st.spiele if s.spielfeld)
        return JSONResponse({
            "spielplaene": [spielplan_to_dict(p) for p in plaene],
            "total_staffeln": len(plaene),
            "wuensche_parsed": len(wuensche),
        })
    except Exception as e:
        raise HTTPException(500, f"Fehler bei Spielplan-Generierung: {str(e)}")


# ─── Schneller Wünsche-Parser (Regex, kein LLM) ───────────────

import re as _re

_WOCHENTAGE = {
    "montag": "Montag", "dienstag": "Dienstag", "mittwoch": "Mittwoch",
    "donnerstag": "Donnerstag", "freitag": "Freitag", "samstag": "Samstag",
    "sonntag": "Sonntag",
}

_SPERR_PATTERN = _re.compile(
    r"(?:nicht|kein|gesperrt|fällt aus|keine? (?:spiel|platz))"
    r".*?(\d{1,2})[./](\d{1,2})(?:[./](\d{2,4}))?",
    _re.IGNORECASE,
)

_DATUM_PATTERN = _re.compile(
    r"(\d{1,2})[./](\d{1,2})(?:[./](\d{2,4}))?",
)

_ZEIT_PATTERN = _re.compile(
    r"(\d{1,2})[:.:](\d{2})\s*(?:uhr)?",
    _re.IGNORECASE,
)

_HEIM_KEYWORDS = _re.compile(
    r"heim|heimspiel|zu\s*hause",
    _re.IGNORECASE,
)

_AUSW_KEYWORDS = _re.compile(
    r"auswärts|ausw[aä]rts",
    _re.IGNORECASE,
)

_PLATZ_KEYWORDS = _re.compile(
    r"platz.*(?:teil|shar|gemeinsam|gleichzeitig)|gleich(?:en?)\s*platz",
    _re.IGNORECASE,
)


def _saison_start_year(saison: str) -> int | None:
    """Extrahiert das Startjahr aus z.B. '2025/26' → 2025."""
    if not saison:
        return None
    try:
        return int(saison.split("/")[0])
    except (ValueError, IndexError):
        return None


def _resolve_year(month: int, saison: str) -> int:
    """Bestimmt das Jahr für einen Monat (Aug-Dez → Startjahr, Jan-Jul → Startjahr+1)."""
    start = _saison_start_year(saison)
    if start is None:
        from datetime import datetime
        now = datetime.now()
        start = now.year if now.month >= 8 else now.year - 1
    return start if month >= 8 else start + 1


def _parse_wuensche_fast(
    einteilung: dict,
    saison: str,
) -> dict[str, list[Wunsch]]:
    """Parst Wünsche-Freitext regelbasiert (schnell, ohne LLM).

    Erkennt: Sperrtage, Wochentag-Präferenzen, Uhrzeiten, Heim/Auswärts-Wünsche.
    """
    result: dict[str, list[Wunsch]] = {}

    for gruppe in einteilung.get("gruppen", []):
        for staffel in gruppe.get("staffeln", []):
            for team in staffel.get("teams", []):
                text = team.get("wuensche_text", "").strip()
                if not text:
                    continue

                mannschaft = team.get("mannschaft", "")
                wuensche: list[Wunsch] = []

                # Normalisiere: _x000D_ (Excel-Zeilenumbruch) → Leerzeichen
                text_clean = text.replace("_x000D_", " ").replace("\r", " ").replace("\n", " ")

                # ── Sperrtage ──
                for m in _SPERR_PATTERN.finditer(text_clean):
                    day, month = int(m.group(1)), int(m.group(2))
                    year_str = m.group(3)
                    if year_str:
                        year = int(year_str) if len(year_str) == 4 else 2000 + int(year_str)
                    else:
                        year = _resolve_year(month, saison)
                    try:
                        from datetime import date
                        datum = date(year, month, day)
                        wuensche.append(Wunsch(
                            kategorie=WunschKategorie.SPERRTAG,
                            prioritaet=WunschPrio.HART,
                            beschreibung=f"Gesperrt am {datum.strftime('%d.%m.%Y')}",
                            datum=datum.isoformat(),
                            original_text=text,
                        ))
                    except ValueError:
                        pass

                # ── Wochentag-Präferenz ──
                text_lower = text_clean.lower()
                for wt_key, wt_name in _WOCHENTAGE.items():
                    if wt_key in text_lower:
                        wuensche.append(Wunsch(
                            kategorie=WunschKategorie.WOCHENTAG,
                            prioritaet=WunschPrio.WEICH,
                            beschreibung=f"Bevorzugt {wt_name}",
                            wochentag=wt_name,
                            original_text=text,
                        ))

                # ── Uhrzeit ──
                zeit_match = _ZEIT_PATTERN.search(text_clean)
                if zeit_match:
                    h, m = int(zeit_match.group(1)), int(zeit_match.group(2))
                    if 8 <= h <= 21:
                        wuensche.append(Wunsch(
                            kategorie=WunschKategorie.ANSTOSSZEIT,
                            prioritaet=WunschPrio.WEICH,
                            beschreibung=f"Anstoß {h:02d}:{m:02d}",
                            uhrzeit=f"{h:02d}:{m:02d}",
                            original_text=text,
                        ))

                # ── Heim/Auswärts-Beziehung ──
                if _HEIM_KEYWORDS.search(text_clean) and _AUSW_KEYWORDS.search(text_clean):
                    # "Wenn Heim, dann andere Auswärts" → Platzsharing-Hinweis
                    wuensche.append(Wunsch(
                        kategorie=WunschKategorie.PLATZSHARING,
                        prioritaet=WunschPrio.WEICH,
                        beschreibung="Heim/Auswärts-Abstimmung gewünscht",
                        original_text=text,
                    ))

                # ── Fallback: wenn nichts erkannt, als Sonstiges speichern ──
                if not wuensche:
                    wuensche.append(Wunsch(
                        kategorie=WunschKategorie.SONSTIGES,
                        prioritaet=WunschPrio.WEICH,
                        beschreibung=text_clean[:200],
                        original_text=text,
                    ))

                result[mannschaft] = wuensche

    return result
