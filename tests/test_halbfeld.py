"""Test AK-spezifische Spieldauer + Halbfeld-Logik bei Kollisionen."""
from datetime import date
from src.spielplanerstellung.spielplan import (
    Spiel, StaffelSpielplan, SpielplanScore,
    resolve_spielfeld_konflikte, _get_spieldauer_min,
)

# Szenario 1: Zwei D-Junioren Halbfeld-Spiele am gleichen Spielfeld + Tag + Zeit
# → Sollte KEINEN Konflikt geben (2 Halbfeld = 1 Großfeld)
plan_d1 = StaffelSpielplan(
    staffel_name="D1-S1", altersklasse="D-Junioren", topf="Topf 1",
    staffel_idx=0, n_teams=4, doppelrunde=False,
    spieltage=[type('ST', (), {
        'nummer': 1, 'datum': date(2025, 9, 20), 'anstosszeit': '12:30',
        'spiele': [
            Spiel(heim="Team A", gast="Team B", datum=date(2025, 9, 20),
                  anstosszeit="12:30", spielfeld="Sportpark, 74613 Öhringen"),
        ], 'spielfrei': None
    })()],
)

plan_d2 = StaffelSpielplan(
    staffel_name="D2-S1", altersklasse="D-Junioren", topf="Topf 2",
    staffel_idx=0, n_teams=4, doppelrunde=False,
    spieltage=[type('ST', (), {
        'nummer': 1, 'datum': date(2025, 9, 20), 'anstosszeit': '12:30',
        'spiele': [
            Spiel(heim="Team C", gast="Team D", datum=date(2025, 9, 20),
                  anstosszeit="12:30", spielfeld="Sportpark, 74613 Öhringen"),
        ], 'spielfrei': None
    })()],
)

# Szenario 2: C-Junioren Großfeld + D-Junioren Halbfeld am gleichen Feld + Zeit
# → C braucht Großfeld → D muss verschoben werden
plan_c = StaffelSpielplan(
    staffel_name="C-S1", altersklasse="C-Junioren", topf="Topf 1",
    staffel_idx=0, n_teams=4, doppelrunde=False,
    spieltage=[type('ST', (), {
        'nummer': 1, 'datum': date(2025, 9, 20), 'anstosszeit': '14:15',
        'spiele': [
            Spiel(heim="Team E", gast="Team F", datum=date(2025, 9, 20),
                  anstosszeit="14:15", spielfeld="Sportpark, 74613 Öhringen"),
        ], 'spielfrei': None
    })()],
)

plan_d3 = StaffelSpielplan(
    staffel_name="D3-S1", altersklasse="D-Junioren", topf="Topf 1",
    staffel_idx=0, n_teams=4, doppelrunde=False,
    spieltage=[type('ST', (), {
        'nummer': 1, 'datum': date(2025, 9, 20), 'anstosszeit': '14:15',
        'spiele': [
            Spiel(heim="Team G", gast="Team H", datum=date(2025, 9, 20),
                  anstosszeit="14:15", spielfeld="Sportpark, 74613 Öhringen"),
        ], 'spielfrei': None
    })()],
)

# Szenario 3: Drei D-Junioren Halbfeld am gleichen Feld → 3. muss warten
plan_d4 = StaffelSpielplan(
    staffel_name="D4-S1", altersklasse="D-Junioren", topf="Topf 1",
    staffel_idx=0, n_teams=4, doppelrunde=False,
    spieltage=[type('ST', (), {
        'nummer': 1, 'datum': date(2025, 9, 20), 'anstosszeit': '12:30',
        'spiele': [
            Spiel(heim="Team I", gast="Team J", datum=date(2025, 9, 20),
                  anstosszeit="12:30", spielfeld="Sportpark, 74613 Öhringen"),
        ], 'spielfrei': None
    })()],
)

print("=== Test 1: Zwei D-Junioren Halbfeld parallel ===")
n = resolve_spielfeld_konflikte([plan_d1, plan_d2])
t1 = plan_d1.spieltage[0].spiele[0].anstosszeit
t2 = plan_d2.spieltage[0].spiele[0].anstosszeit
print(f"  Konflikte behoben: {n}")
print(f"  Team A vs B: {t1}")
print(f"  Team C vs D: {t2}")
assert n == 0 and t1 == "12:30" and t2 == "12:30", "FAIL: 2 Halbfeld sollten parallel sein!"
print("  ✓ OK\n")

print("=== Test 2: C-Junioren Großfeld blockiert D-Junioren ===")
n = resolve_spielfeld_konflikte([plan_c, plan_d3])
tc = plan_c.spieltage[0].spiele[0].anstosszeit
td = plan_d3.spieltage[0].spiele[0].anstosszeit
print(f"  Konflikte behoben: {n}")
print(f"  C: Team E vs F: {tc}")
print(f"  D: Team G vs H: {td}")
d_start_expected = 14*60 + 15 + _get_spieldauer_min("C-Junioren")
print(f"  D erwartet nach C-Dauer ({_get_spieldauer_min('C-Junioren')}min): {d_start_expected//60}:{d_start_expected%60:02d}")
assert n >= 1, "FAIL: D sollte verschoben sein!"
print("  ✓ OK\n")

print("=== Test 3: Drei D-Halbfeld → 3. muss warten ===")
# Reset times for clean test
plan_d1.spieltage[0].spiele[0].anstosszeit = "12:30"
plan_d2.spieltage[0].spiele[0].anstosszeit = "12:30"
plan_d4.spieltage[0].spiele[0].anstosszeit = "12:30"
n = resolve_spielfeld_konflikte([plan_d1, plan_d2, plan_d4])
t1 = plan_d1.spieltage[0].spiele[0].anstosszeit
t2 = plan_d2.spieltage[0].spiele[0].anstosszeit
t4 = plan_d4.spieltage[0].spiele[0].anstosszeit
print(f"  Konflikte behoben: {n}")
print(f"  Team A vs B: {t1}")
print(f"  Team C vs D: {t2}")
print(f"  Team I vs J: {t4}")
assert t1 == "12:30" and t2 == "12:30", "FAIL: erste 2 Halbfeld sollten parallel sein!"
assert t4 != "12:30", f"FAIL: 3. Halbfeld sollte verschoben sein, ist aber {t4}!"
print("  ✓ OK\n")

print("Alle Tests bestanden!")
