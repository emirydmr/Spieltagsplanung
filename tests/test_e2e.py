"""End-to-End Test: Meldeliste laden → Einteilung → Spielplan mit CP-SAT."""
import time
import requests

SERVER = "http://127.0.0.1:8000"
MELDELISTE = r"raw_data\Meldeliste_Junioren_Hinrunde_25-26.xlsx"

# 1. Einteilung erstellen
print("1. Einteilung erstellen ...")
t0 = time.time()
with open(MELDELISTE, "rb") as f:
    resp = requests.post(f"{SERVER}/api/einteilung", files={"file": f})
if resp.status_code != 200:
    print(f"   FEHLER: {resp.status_code} {resp.text[:200]}")
    exit(1)

einteilung = resp.json()
n_gruppen = len(einteilung.get("gruppen", []))
n_staffeln = sum(len(g["staffeln"]) for g in einteilung["gruppen"])
n_teams = sum(s["n_teams"] for g in einteilung["gruppen"] for s in g["staffeln"])
print(f"   {n_gruppen} Gruppen, {n_staffeln} Staffeln, {n_teams} Teams in {time.time()-t0:.1f}s")

# 2. Spielplan erstellen (mit CP-SAT)
print()
print("2. Spielplan erstellen (CP-SAT) ...")
t0 = time.time()
resp2 = requests.post(
    f"{SERVER}/api/spielplan",
    json={"einteilung": einteilung, "saison": "Hinrunde 25/26"},
    timeout=600,  # 10 min timeout
)
elapsed = time.time() - t0

if resp2.status_code != 200:
    print(f"   FEHLER: {resp2.status_code} {resp2.text[:500]}")
    exit(1)

result = resp2.json()
n_plaene = result.get("total_staffeln", 0)
wuensche = result.get("wuensche_parsed", 0)
plaene = result.get("spielplaene", [])

# Konflikte zaehlen
total_konflikte = sum(
    p.get("score", {}).get("platz_konflikte", 0)
    for p in plaene if p.get("score")
)
total_spiele = sum(
    len(s["spiele"])
    for p in plaene for s in p["spieltage"]
)

print(f"   {n_plaene} Spielplaene, {total_spiele} Spiele, "
      f"{wuensche} Wuensche in {elapsed:.1f}s")
print(f"   >>> KONFLIKTE: {total_konflikte} <<<")

# Top-5 Staffeln mit meisten Konflikten
staffeln_mit_konflikten = [
    (p["altersklasse"], p["staffel_name"], p["score"]["platz_konflikte"])
    for p in plaene if p.get("score") and p["score"]["platz_konflikte"] > 0
]
staffeln_mit_konflikten.sort(key=lambda x: -x[2])
if staffeln_mit_konflikten:
    print()
    print("   Top Staffeln mit Konflikten:")
    for ak, sn, k in staffeln_mit_konflikten[:10]:
        print(f"     {ak} {sn}: {k}")

# 3. History pruefen
print()
print("3. Spielplan-History pruefen ...")
resp3 = requests.get(f"{SERVER}/api/spielplan/history")
if resp3.status_code == 200:
    history = resp3.json().get("history", [])
    print(f"   {len(history)} gespeicherte(r) Spielplan/Spielplaene")
    for h in history[:3]:
        print(f"     {h['timestamp']}  {h['total_spiele']} Spiele, "
              f"{h['total_konflikte']} Konflikte, {h['wuensche_parsed']} Wuensche")
else:
    print(f"   FEHLER: {resp3.status_code}")
