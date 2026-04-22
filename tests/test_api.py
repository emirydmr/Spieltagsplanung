"""Quick API tests for edit + export endpoints."""
import requests
import json

SERVER = "http://127.0.0.1:8000"

mock_spielplaene = [{
    "staffel_idx": 0,
    "altersklasse": "C-Junioren",
    "staffel_name": "Staffel 1",
    "topf": "Topf 1",
    "n_teams": 6,
    "doppelrunde": False,
    "sz_zuordnungen": [],
    "score": {
        "total": 10, "heim_balance": 0, "consecutive_penalty": 0,
        "distanz_fairness": 0, "wunsch_verletzungen": 0, "platz_konflikte": 0,
    },
    "spieltage": [{
        "nummer": 1,
        "datum": "2025-09-20",
        "anstosszeit": "10:00",
        "spiele": [
            {"heim": "Team A", "gast": "Team B", "datum": "2025-09-20",
             "anstosszeit": "10:00", "spielfeld": "Platz 1, Stadt"},
            {"heim": "Team C", "gast": "Team D", "datum": "2025-09-20",
             "anstosszeit": "12:00", "spielfeld": "Platz 2, Stadt"},
        ],
        "spielfrei": None,
    }],
}]

# Test 1: Edit datum
print("Test 1: Edit datum")
edits = [{"staffel_idx": 0, "spieltag_nr": 1, "spiel_idx": 0, "field": "datum", "value": "2025-09-21"}]
resp = requests.post(f"{SERVER}/api/spielplan/edit", json={"spielplaene": mock_spielplaene, "edits": edits})
assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
result = resp.json()
assert result["spielplaene"][0]["spieltage"][0]["spiele"][0]["datum"] == "2025-09-21"
print("  OK: datum changed to 2025-09-21")

# Test 2: Edit anstosszeit
print("Test 2: Edit anstosszeit")
edits2 = [{"staffel_idx": 0, "spieltag_nr": 1, "spiel_idx": 0, "field": "anstosszeit", "value": "14:30"}]
resp2 = requests.post(f"{SERVER}/api/spielplan/edit", json={"spielplaene": mock_spielplaene, "edits": edits2})
assert resp2.status_code == 200
result2 = resp2.json()
assert result2["spielplaene"][0]["spieltage"][0]["spiele"][0]["anstosszeit"] == "14:30"
print("  OK: zeit changed to 14:30")

# Test 3: Swap teams
print("Test 3: Swap teams")
edits3 = [{"staffel_idx": 0, "spieltag_nr": 1, "spiel_idx": 1, "field": "swap_teams", "value": ""}]
resp3 = requests.post(f"{SERVER}/api/spielplan/edit", json={"spielplaene": mock_spielplaene, "edits": edits3})
assert resp3.status_code == 200
result3 = resp3.json()
s = result3["spielplaene"][0]["spieltage"][0]["spiele"][1]
assert s["heim"] == "Team D" and s["gast"] == "Team C", f"Got: {s['heim']} vs {s['gast']}"
print(f"  OK: swapped to {s['heim']} vs {s['gast']}")

# Test 4: Excel export
print("Test 4: Excel export")
resp4 = requests.post(f"{SERVER}/api/spielplan/export", json={"spielplaene": mock_spielplaene})
assert resp4.status_code == 200, f"Expected 200, got {resp4.status_code}: {resp4.text[:200]}"
assert "spreadsheet" in resp4.headers.get("content-type", "")
print(f"  OK: Excel file {len(resp4.content)} bytes")

print()
print("All API tests passed!")
