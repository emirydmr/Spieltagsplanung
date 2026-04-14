"""FastAPI Backend für die Spieltagsplanung.

Starten:
    python -m uvicorn src.api.server:app --reload --port 8000
"""

import sys
import tempfile
import shutil
from pathlib import Path

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from src.data_import.meldeliste_parser import parse_meldeliste, verknuepfe_koordinaten
from src.staffeleinteilung.algorithmus import gruppiere_mannschaften, einteilung_erstellen
from src.staffeleinteilung.scoring import ScoreGewichte
from src.common.distanz import haversine_km

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
