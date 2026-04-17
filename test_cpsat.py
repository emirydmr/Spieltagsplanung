"""Schnelltest CP-SAT Solver mit Mini-Daten."""
from datetime import date
from src.spielplanerstellung.spielplan import (
    StaffelSpielplan, Spieltag, Spiel,
)
from src.spielplanerstellung.sz_vergabe import SZZuordnung, SpielplanScore
from src.spielplanerstellung.slot_solver import solve_game_slots

# Simuliere 3 Staffeln die am selben Samstag am selben Sportplatz spielen
VENUE = "Sportplatz Musterstadt, Hauptstr. 1"
DATUM = date(2025, 9, 20)  # Samstag

def make_plan(ak, zeit, teams):
    sz_list = [
        SZZuordnung(mannschaft=t, verein=t.split()[0], sz=i+1, adresse=VENUE)
        for i, t in enumerate(teams)
    ]
    # Jeweils 1 Spieltag mit 1 Spiel
    spiele = [Spiel(
        heim=teams[0], gast=teams[1],
        heim_verein=teams[0].split()[0], gast_verein=teams[1].split()[0],
        datum=DATUM, anstosszeit=zeit, spielfeld=VENUE,
    )]
    spieltage = [Spieltag(nummer=1, datum=DATUM, anstosszeit=zeit, spiele=spiele)]
    return StaffelSpielplan(
        staffel_name="Test", altersklasse=ak, topf="Topf 1",
        staffel_idx=0, n_teams=2, doppelrunde=False,
        sz_zuordnungen=sz_list, spieltage=spieltage,
        score=SpielplanScore(),
    )

# 3 Spiele am selben Ort, selbe Zeit → MUSS Konflikte loesen
plaene = [
    make_plan("E-Junioren", "11:15", ["FC Adler E1", "SV Falke E1"]),
    make_plan("D-Junioren", "11:15", ["FC Adler D1", "SV Falke D1"]),
    make_plan("C-Junioren", "11:15", ["FC Adler C1", "SV Falke C1"]),
    make_plan("A-Junioren", "11:15", ["FC Adler A1", "SV Falke A1"]),
]

print(f"VOR CP-SAT: Alle 4 Spiele um 11:15 am selben Ort")
print()

changes = solve_game_slots(plaene, time_limit_seconds=30)
print(f"CP-SAT: {changes} Spiele geaendert")
print()

for p in plaene:
    for st in p.spieltage:
        for s in st.spiele:
            print(f"  {p.altersklasse:15s}  {s.datum}  {s.anstosszeit:5s}  {s.heim} vs {s.gast}  @ {s.spielfeld[:40]}")
