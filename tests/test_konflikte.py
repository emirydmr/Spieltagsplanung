"""Test Spielfeld-Kollisionserkennung."""
import requests

# 2 Staffeln mit Teams die das gleiche Spielfeld teilen
test = {
    "saison": "2025/26",
    "einteilung": {
        "total_teams": 8,
        "gruppen": [
            {
                "altersklasse": "C-Junioren",
                "spielklasse": "Qualistaffel",
                "topf": "Topf 1",
                "n_teams": 4,
                "staffeln": [{
                    "n_teams": 4,
                    "doppelrunde": True,
                    "max_distanz_km": 15.0,
                    "teams": [
                        {"mannschaft": "TSV Öhringen C1", "verein": "TSV Öhringen", "region": "Hohenlohe",
                         "lat": 49.20, "lon": 9.50, "adresse": "Sportpark, 74613 Öhringen", "wuensche_text": ""},
                        {"mannschaft": "TSV Crailsheim C1", "verein": "TSV Crailsheim", "region": "Hohenlohe",
                         "lat": 49.13, "lon": 10.07, "adresse": "Stadion, 74564 Crailsheim", "wuensche_text": ""},
                        {"mannschaft": "SV Westheim C1", "verein": "SV Westheim", "region": "Hohenlohe",
                         "lat": 49.08, "lon": 10.05, "adresse": "Sportplatz, 74538 Westheim", "wuensche_text": ""},
                        {"mannschaft": "FC Langenburg C1", "verein": "FC Langenburg", "region": "Hohenlohe",
                         "lat": 49.25, "lon": 9.85, "adresse": "Sportplatz, 74595 Langenburg", "wuensche_text": ""},
                    ]
                }],
                "score": {"total": 10, "distanz": 12.5, "region": 0, "balance": 0.1, "violations": 0},
                "merged": False,
            },
            {
                "altersklasse": "D-Junioren",
                "spielklasse": "Qualistaffel",
                "topf": "Topf 1",
                "n_teams": 4,
                "staffeln": [{
                    "n_teams": 4,
                    "doppelrunde": True,
                    "max_distanz_km": 10.0,
                    "teams": [
                        # TSV Öhringen D1 shares venue with TSV Öhringen C1!
                        {"mannschaft": "TSV Öhringen D1", "verein": "TSV Öhringen", "region": "Hohenlohe",
                         "lat": 49.20, "lon": 9.50, "adresse": "Sportpark, 74613 Öhringen", "wuensche_text": ""},
                        {"mannschaft": "TSV Crailsheim D1", "verein": "TSV Crailsheim", "region": "Hohenlohe",
                         "lat": 49.13, "lon": 10.07, "adresse": "Stadion, 74564 Crailsheim", "wuensche_text": ""},
                        {"mannschaft": "SV Westheim D1", "verein": "SV Westheim", "region": "Hohenlohe",
                         "lat": 49.08, "lon": 10.05, "adresse": "Sportplatz, 74538 Westheim", "wuensche_text": ""},
                        {"mannschaft": "FC Langenburg D1", "verein": "FC Langenburg", "region": "Hohenlohe",
                         "lat": 49.25, "lon": 9.85, "adresse": "Sportplatz, 74595 Langenburg", "wuensche_text": ""},
                    ]
                }],
                "score": {"total": 8, "distanz": 10.0, "region": 0, "balance": 0.0, "violations": 0},
                "merged": False,
            },
        ]
    }
}

resp = requests.post("http://127.0.0.1:8000/api/spielplan", json=test, timeout=120)
print(f"Status: {resp.status_code}")

if resp.status_code != 200:
    print(f"Error: {resp.text}")
else:
    data = resp.json()
    print(f"Staffeln: {data['total_staffeln']}")

    # Check for shared venues and their times
    for sp in data["spielplaene"]:
        print(f"\n{'='*60}")
        print(f"{sp['altersklasse']} {sp['topf']} - {sp['staffel_name']}")
        for st in sp["spieltage"][:3]:
            print(f"  Spieltag {st['nummer']}:")
            for s in st["spiele"]:
                datum = s.get("datum", "?")
                zeit = s.get("anstosszeit", "?")
                feld = s.get("spielfeld", "?")
                ort = feld.split(", ")[-1] if feld else "?"
                print(f"    {s['heim']:25s} vs {s['gast']:25s}  {datum} {zeit}  @{ort}")
