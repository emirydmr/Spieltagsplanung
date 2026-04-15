"""Test Wünsche-Integration in Spielplan-Generierung."""
import requests

test = {
    "saison": "2025/26",
    "einteilung": {
        "total_teams": 6,
        "gruppen": [{
            "altersklasse": "C-Junioren",
            "spielklasse": "Qualistaffel",
            "topf": "Topf 1",
            "n_teams": 6,
            "staffeln": [{
                "n_teams": 6,
                "doppelrunde": False,
                "max_distanz_km": 20.0,
                "teams": [
                    {"mannschaft": "TSV Ilshofen", "verein": "TSV Ilshofen", "region": "Hohenlohe",
                     "lat": 49.17, "lon": 9.92, "adresse": "Sportplatz, 74532 Ilshofen",
                     "wuensche_text": "Am 4. Oktober können wir nicht spielen (Vereinsfest)"},
                    {"mannschaft": "TSV Crailsheim", "verein": "TSV Crailsheim", "region": "Hohenlohe",
                     "lat": 49.13, "lon": 10.07, "adresse": "Stadion, 74564 Crailsheim",
                     "wuensche_text": ""},
                    {"mannschaft": "SV Westheim", "verein": "SV Westheim", "region": "Hohenlohe",
                     "lat": 49.08, "lon": 10.05, "adresse": "Sportplatz, 74538 Westheim",
                     "wuensche_text": "Wir spielen am liebsten samstags"},
                    {"mannschaft": "FC Langenburg", "verein": "FC Langenburg", "region": "Hohenlohe",
                     "lat": 49.25, "lon": 9.85, "adresse": "Sportplatz, 74595 Langenburg",
                     "wuensche_text": ""},
                    {"mannschaft": "TSG Schwäbisch Hall", "verein": "TSG Schwäbisch Hall", "region": "Hohenlohe",
                     "lat": 49.11, "lon": 9.74, "adresse": "Sportplatz, 74523 Schwäbisch Hall",
                     "wuensche_text": ""},
                    {"mannschaft": "TV Braunsbach", "verein": "TV Braunsbach", "region": "Hohenlohe",
                     "lat": 49.20, "lon": 9.79, "adresse": "Sportplatz, 74542 Braunsbach",
                     "wuensche_text": "Am 1. Spieltag bitte Heimspiel"},
                ]
            }],
            "score": {"total": 10, "distanz": 12.5, "region": 0, "balance": 0.1, "violations": 0},
            "merged": False,
        }]
    }
}

resp = requests.post("http://127.0.0.1:8000/api/spielplan", json=test, timeout=120)
print(f"Status: {resp.status_code}")

if resp.status_code != 200:
    print(f"Error: {resp.text}")
else:
    data = resp.json()
    print(f"Staffeln: {data['total_staffeln']}")
    print(f"Wünsche geparst: {data['wuensche_parsed']}")
    sp = data["spielplaene"][0]
    print(f"\n{sp['staffel_name']} - {sp['altersklasse']} - {sp['n_teams']} Teams")
    print(f"Score: {sp['score']}")
    print(f"\nSZ-Zuordnung:")
    for z in sp["sz_zuordnungen"]:
        print(f"  SZ {z['sz']}: {z['mannschaft']}")
    print(f"\nSpieltage:")
    for st in sp["spieltage"]:
        sf = f" [Spielfrei: {st['spielfrei']}]" if st.get("spielfrei") else ""
        print(f"  ST {st['nummer']}: {st['datum']} {st['anstosszeit']}{sf}")
        for s in st["spiele"]:
            print(f"    {s['heim']} vs {s['gast']}")
