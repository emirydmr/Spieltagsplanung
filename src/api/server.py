"""FastAPI Backend für die Spieltagsplanung.

Starten:
    python -m uvicorn src.api.server:app --reload --port 8000
"""

import sys
import tempfile
import shutil
import json
from datetime import datetime
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

# Verzeichnis für gespeicherte Spielpläne
SPIELPLAN_DIR = ROOT / "spielplan_logs"
SPIELPLAN_DIR.mkdir(exist_ok=True)

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
        result = {
            "spielplaene": [spielplan_to_dict(p) for p in plaene],
            "total_staffeln": len(plaene),
            "wuensche_parsed": len(wuensche),
        }

        # Spielplan persistent speichern
        _save_spielplan_log(result, saison)

        return JSONResponse(result)
    except Exception as e:
        raise HTTPException(500, f"Fehler bei Spielplan-Generierung: {str(e)}")


def _save_spielplan_log(result: dict, saison: str) -> Path:
    """Speichert das Spielplan-Ergebnis als JSON-Datei mit Metadaten."""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    total_konflikte = sum(
        p.get("score", {}).get("platz_konflikte", 0)
        for p in result.get("spielplaene", []) if p.get("score")
    )
    total_wunsch = sum(
        p.get("score", {}).get("wunsch_verletzungen", 0)
        for p in result.get("spielplaene", []) if p.get("score")
    )
    total_spiele = sum(
        len(s["spiele"])
        for p in result.get("spielplaene", []) for s in p["spieltage"]
    )
    log_entry = {
        "timestamp": datetime.now().isoformat(),
        "saison": saison,
        "total_staffeln": result.get("total_staffeln", 0),
        "total_spiele": total_spiele,
        "total_konflikte": total_konflikte,
        "total_wunsch_verletzungen": total_wunsch,
        "wuensche_parsed": result.get("wuensche_parsed", 0),
        "spielplaene": result.get("spielplaene", []),
    }

    filename = f"spielplan_{ts}.json"
    filepath = SPIELPLAN_DIR / filename
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(log_entry, f, ensure_ascii=False, indent=1)
    print(f"[LOG] Spielplan gespeichert: {filepath.name} "
          f"({total_spiele} Spiele, {total_konflikte} Platz-Konflikte, {total_wunsch} Wunsch-Verl.)")
    return filepath


@app.get("/api/spielplan/history")
async def api_spielplan_history():
    """Gibt eine Liste aller gespeicherten Spielpläne zurück (ohne Detaildaten)."""
    entries = []
    for fp in sorted(SPIELPLAN_DIR.glob("spielplan_*.json"), reverse=True):
        try:
            with open(fp, "r", encoding="utf-8") as f:
                data = json.load(f)
            entries.append({
                "filename": fp.name,
                "timestamp": data.get("timestamp", ""),
                "saison": data.get("saison", ""),
                "total_staffeln": data.get("total_staffeln", 0),
                "total_spiele": data.get("total_spiele", 0),
                "total_konflikte": data.get("total_konflikte", 0),
                "wuensche_parsed": data.get("wuensche_parsed", 0),
            })
        except (json.JSONDecodeError, KeyError):
            continue
    return JSONResponse({"history": entries})


@app.get("/api/spielplan/history/{filename}")
async def api_spielplan_load(filename: str):
    """Lädt einen bestimmten gespeicherten Spielplan."""
    filepath = SPIELPLAN_DIR / filename
    if not filepath.exists() or not filepath.name.startswith("spielplan_"):
        raise HTTPException(404, "Spielplan nicht gefunden")
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)
    return JSONResponse(data)


# ─── Manuelle Spielplan-Bearbeitung ────────────────────────────

@app.post("/api/spielplan/edit")
async def api_spielplan_edit(request: Request):
    """Wendet manuelle Änderungen auf Spielpläne an und berechnet Konflikte neu.

    Erwartet JSON mit:
      - spielplaene: aktueller Stand aller Spielpläne
      - edits: Liste von Änderungen [{staffel_idx, spieltag_nr, spiel_idx, field, value}]

    field kann sein: 'datum', 'anstosszeit', 'swap_teams'
    """
    data = await request.json()
    spielplaene = data.get("spielplaene", [])
    edits = data.get("edits", [])

    if not spielplaene:
        raise HTTPException(400, "Keine Spielpläne vorhanden")
    if not edits:
        raise HTTPException(400, "Keine Änderungen angegeben")

    for edit in edits:
        si = edit.get("staffel_idx")
        st_nr = edit.get("spieltag_nr")
        sp_idx = edit.get("spiel_idx")
        fld = edit.get("field", "")
        val = edit.get("value", "")

        # Staffel finden
        plan = None
        for p in spielplaene:
            if p["staffel_idx"] == si:
                plan = p
                break
        if plan is None:
            continue

        # Spieltag finden
        spieltag = None
        for st in plan["spieltage"]:
            if st["nummer"] == st_nr:
                spieltag = st
                break
        if spieltag is None:
            continue

        # Spiel finden
        if sp_idx < 0 or sp_idx >= len(spieltag["spiele"]):
            continue
        spiel = spieltag["spiele"][sp_idx]

        # Änderung anwenden
        if fld == "datum":
            spiel["datum"] = val
        elif fld == "anstosszeit":
            spiel["anstosszeit"] = val
        elif fld == "swap_teams":
            spiel["heim"], spiel["gast"] = spiel["gast"], spiel["heim"]
            # Spielfeld wechselt zum neuen Heim-Team
            if val:
                spiel["spielfeld"] = val

    # Konflikte neu berechnen
    _recalculate_konflikte(spielplaene)

    return JSONResponse({"spielplaene": spielplaene})


def _recalculate_konflikte(spielplaene: list[dict]) -> None:
    """Berechnet platz_konflikte für JSON-Spielpläne neu."""
    from collections import defaultdict

    _AK_HALBFELD = {"F-Junioren", "F-Juniorinnen", "E-Junioren", "E-Juniorinnen",
                     "D-Junioren", "D-Juniorinnen", "Bambini"}
    _AK_DAUER = {
        "Bambini": 40, "F-Junioren": 40, "F-Juniorinnen": 40,
        "E-Junioren": 50, "E-Juniorinnen": 50,
        "D-Junioren": 60, "D-Juniorinnen": 60,
        "C-Junioren": 70, "C-Juniorinnen": 70,
        "B-Junioren": 80, "B-Juniorinnen": 80,
        "A-Junioren": 90, "A-Juniorinnen": 90,
    }

    belegung: dict[tuple[str, str], list[tuple[int, int, bool]]] = defaultdict(list)

    for plan in spielplaene:
        ak = plan.get("altersklasse", "")
        halbfeld = ak in _AK_HALBFELD
        dauer = _AK_DAUER.get(ak, 80)
        for st in plan.get("spieltage", []):
            for spiel in st.get("spiele", []):
                feld = (spiel.get("spielfeld") or "").strip().lower()
                datum = spiel.get("datum") or ""
                if not feld or not datum:
                    continue
                key = (feld, datum)
                zeit_str = spiel.get("anstosszeit", "") or ""
                parts = zeit_str.replace(":", ".").split(".")
                if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
                    start = int(parts[0]) * 60 + int(parts[1])
                else:
                    start = 720
                belegung[key].append((start, start + dauer, halbfeld))

    # Konflikte zählen pro (feld, datum)
    remaining: dict[tuple[str, str], int] = {}
    for key, entries in belegung.items():
        entries.sort()
        konflikte = 0
        for i in range(len(entries)):
            for j in range(i + 1, len(entries)):
                s_i, e_i, hf_i = entries[i]
                s_j, e_j, hf_j = entries[j]
                if s_j < e_i:
                    if hf_i and hf_j and s_i == s_j:
                        continue
                    konflikte += 1
        remaining[key] = konflikte

    # Verteile auf Spielpläne
    for plan in spielplaene:
        if not plan.get("score"):
            continue
        plan["score"]["platz_konflikte"] = 0
        ak = plan.get("altersklasse", "")
        for st in plan.get("spieltage", []):
            for spiel in st.get("spiele", []):
                feld = (spiel.get("spielfeld") or "").strip().lower()
                datum = spiel.get("datum") or ""
                if not feld or not datum:
                    continue
                key = (feld, datum)
                if remaining.get(key, 0) > 0:
                    plan["score"]["platz_konflikte"] += 1
                    remaining[key] -= 1


# ─── Spielplan Excel Export ────────────────────────────────────

@app.post("/api/spielplan/export")
async def api_spielplan_export(request: Request):
    """Generiert eine Excel-Datei aus den Spielplänen."""
    data = await request.json()
    spielplaene = data.get("spielplaene", [])
    if not spielplaene:
        raise HTTPException(400, "Keine Spielpläne vorhanden")

    wb = Workbook()

    # ── Styles ──
    header_font = Font(bold=True, color="FFFFFF", size=11)
    header_fill = PatternFill(start_color="C41230", end_color="C41230", fill_type="solid")
    spieltag_font = Font(bold=True, size=11, color="C41230")
    thin_border = Border(bottom=Side(style="thin", color="E5E7EB"))
    center = Alignment(horizontal="center")
    wrap = Alignment(wrap_text=True, vertical="center")

    # ── Sheet 1: Übersicht ──
    ws_ueb = wb.active
    ws_ueb.title = "Übersicht"
    ueb_headers = ["Altersklasse", "Topf", "Staffel", "Teams", "Spieltage",
                    "Spiele", "Konflikte", "Doppelrunde"]
    for ci, h in enumerate(ueb_headers, 1):
        cell = ws_ueb.cell(row=1, column=ci, value=h)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = center

    for ri, p in enumerate(spielplaene, 2):
        n_spiele = sum(len(st["spiele"]) for st in p["spieltage"])
        konflikte = p.get("score", {}).get("platz_konflikte", 0) if p.get("score") else 0
        ws_ueb.cell(row=ri, column=1, value=p["altersklasse"])
        ws_ueb.cell(row=ri, column=2, value=p["topf"])
        ws_ueb.cell(row=ri, column=3, value=p["staffel_name"])
        ws_ueb.cell(row=ri, column=4, value=p["n_teams"]).alignment = center
        ws_ueb.cell(row=ri, column=5, value=len(p["spieltage"])).alignment = center
        ws_ueb.cell(row=ri, column=6, value=n_spiele).alignment = center
        c = ws_ueb.cell(row=ri, column=7, value=konflikte)
        c.alignment = center
        if konflikte > 0:
            c.font = Font(bold=True, color="DC2626")
        ws_ueb.cell(row=ri, column=8, value="Ja" if p.get("doppelrunde") else "Nein").alignment = center

    for col in ws_ueb.columns:
        ws_ueb.column_dimensions[col[0].column_letter].width = 16

    # ── Sheets per Spielplan ──
    for p in spielplaene:
        sheet_name = f"{p['altersklasse']} {p['staffel_name']}"[:31]
        ws = wb.create_sheet(title=sheet_name)

        row = 1
        for st in p["spieltage"]:
            # Spieltag header
            datum_str = ""
            if st.get("datum"):
                try:
                    from datetime import date as _date
                    dt = _date.fromisoformat(st["datum"])
                    wochentage = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]
                    datum_str = f"{wochentage[dt.weekday()]}, {dt.strftime('%d.%m.%Y')}"
                except (ValueError, IndexError):
                    datum_str = st["datum"]

            label = f"Spieltag {st['nummer']}  —  {datum_str}"
            cell = ws.cell(row=row, column=1, value=label)
            cell.font = spieltag_font
            ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=5)
            row += 1

            # Table headers
            sp_headers = ["Zeit", "Heim", "Gast", "Spielort", "Datum"]
            for ci, h in enumerate(sp_headers, 1):
                cell = ws.cell(row=row, column=ci, value=h)
                cell.font = header_font
                cell.fill = header_fill
                cell.alignment = center
            row += 1

            # Spiele
            for spiel in st["spiele"]:
                datum_spiel = ""
                if spiel.get("datum"):
                    try:
                        dt2 = _date.fromisoformat(spiel["datum"])
                        datum_spiel = dt2.strftime("%d.%m.%Y")
                    except ValueError:
                        datum_spiel = spiel["datum"]

                ws.cell(row=row, column=1, value=spiel.get("anstosszeit", "")).alignment = center
                ws.cell(row=row, column=2, value=spiel.get("heim", ""))
                ws.cell(row=row, column=3, value=spiel.get("gast", ""))
                ws.cell(row=row, column=4, value=spiel.get("spielfeld", ""))
                ws.cell(row=row, column=5, value=datum_spiel).alignment = center
                for ci in range(1, 6):
                    ws.cell(row=row, column=ci).border = thin_border
                row += 1

            # Spielfrei
            if st.get("spielfrei"):
                ws.cell(row=row, column=1, value=f"Spielfrei: {st['spielfrei']}")
                ws.cell(row=row, column=1).font = Font(italic=True, color="888888")
                row += 1

            row += 1  # empty row

        # Column widths
        ws.column_dimensions["A"].width = 10
        ws.column_dimensions["B"].width = 28
        ws.column_dimensions["C"].width = 28
        ws.column_dimensions["D"].width = 36
        ws.column_dimensions["E"].width = 14

    # Save to temp file
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx")
    wb.save(tmp.name)
    tmp.close()

    return FileResponse(
        tmp.name,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename="Spielplaene.xlsx",
    )


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
