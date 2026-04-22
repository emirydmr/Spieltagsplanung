"""Test: CP-SAT mit Wuenschen (Sperrtag + Wochentag)."""
from datetime import date
from src.spielplanerstellung.spielplan import StaffelSpielplan, Spieltag, Spiel
from src.spielplanerstellung.sz_vergabe import SZZuordnung, SpielplanScore
from src.spielplanerstellung.slot_solver import solve_game_slots
from src.spielplanerstellung.wuensche import Wunsch, WunschKategorie, WunschPrio

VENUE = "Sportplatz Musterstadt"
DATUM = date(2025, 9, 20)  # Samstag

sz = [
    SZZuordnung(mannschaft="Team A", verein="FC A", sz=1, adresse=VENUE),
    SZZuordnung(mannschaft="Team B", verein="FC B", sz=2, adresse=VENUE),
    SZZuordnung(mannschaft="Team C", verein="FC C", sz=3, adresse="Platz 2"),
    SZZuordnung(mannschaft="Team D", verein="FC D", sz=4, adresse="Platz 2"),
]

spiele = [
    Spiel(heim="Team A", gast="Team B", datum=DATUM, anstosszeit="14:15", spielfeld=VENUE),
    Spiel(heim="Team C", gast="Team D", datum=DATUM, anstosszeit="14:15", spielfeld="Platz 2"),
]

plaene = [StaffelSpielplan(
    staffel_name="Test", altersklasse="C-Junioren", topf="T1",
    staffel_idx=0, n_teams=4, doppelrunde=False,
    sz_zuordnungen=sz, spieltage=[Spieltag(nummer=1, datum=DATUM, anstosszeit="14:15", spiele=spiele)],
    score=SpielplanScore(),
)]

# Wuensche: Team A hat harten Sperrtag am 20.09.
wuensche = {
    "Team A": [
        Wunsch(
            kategorie=WunschKategorie.SPERRTAG,
            prioritaet=WunschPrio.HART,
            beschreibung="Sperrtag 20.09.",
            datum="2025-09-20",
            original_text="20.09. gesperrt",
        ),
    ],
    "Team C": [
        Wunsch(
            kategorie=WunschKategorie.WOCHENTAG,
            prioritaet=WunschPrio.WEICH,
            beschreibung="Bevorzugt Sonntag",
            wochentag="Sonntag",
            original_text="Wir spielen lieber sonntags",
        ),
    ],
}

print("VOR CP-SAT:")
for s in spiele:
    print(f"  {s.datum} {s.anstosszeit} {s.heim} vs {s.gast} @ {s.spielfeld}")

changes = solve_game_slots(plaene, wuensche=wuensche, time_limit_seconds=10)

print(f"\nNACH CP-SAT ({changes} Aenderungen):")
for p in plaene:
    for st in p.spieltage:
        for s in st.spiele:
            print(f"  {s.datum} {s.anstosszeit} {s.heim} vs {s.gast} @ {s.spielfeld}")

# Pruefe Sperrtag: Team A darf NICHT am 20.09. spielen
sperrtag_ok = True
for p in plaene:
    for st in p.spieltage:
        for s in st.spiele:
            if ("Team A" in (s.heim, s.gast)) and s.datum == date(2025, 9, 20):
                print("\n!!! FEHLER: Team A spielt trotz Sperrtag am 20.09. !!!")
                sperrtag_ok = False

if sperrtag_ok:
    print("\nOK: Team A spielt NICHT am 20.09. (Sperrtag respektiert)")
