"""Stress-Test: 20 Staffeln, 4 AKs, viele Venue-Konflikte."""
import time
from datetime import date
from src.spielplanerstellung.spielplan import (
    StaffelSpielplan, Spieltag, Spiel,
)
from src.spielplanerstellung.sz_vergabe import SZZuordnung, SpielplanScore
from src.spielplanerstellung.slot_solver import solve_game_slots

# 5 Venues, 4 AKs, 5 Staffeln pro AK = 20 Staffeln
# Pro Staffel: 4 Spiele pro Spieltag, 3 Spieltage = 60 Spiele pro Staffel
VENUES = [
    "Sportplatz Musterstadt",
    "Sportanlage Neustadt",
    "FC-Platz Waldheim",
    "SV-Stadion Bergdorf",
    "TSV-Arena Steinbach",
]
AKS = ["E-Junioren", "D-Junioren", "C-Junioren", "A-Junioren"]
DATUM_MAP = {
    1: date(2025, 9, 20),
    2: date(2025, 9, 27),
    3: date(2025, 10, 4),
}
ZEITEN = {
    "E-Junioren": "11:15",
    "D-Junioren": "12:30",
    "C-Junioren": "14:15",
    "A-Junioren": "16:00",
}

alle_plaene = []
idx = 0
for ak in AKS:
    for si in range(5):
        sz_list = []
        spieltage_list = []
        teams = [f"Team_{ak}_{si}_{t}" for t in range(8)]
        for i, t in enumerate(teams):
            venue = VENUES[i % len(VENUES)]
            sz_list.append(SZZuordnung(mannschaft=t, verein=t, sz=i+1, adresse=venue))

        for st_nr in range(1, 4):
            datum = DATUM_MAP[st_nr]
            zeit = ZEITEN[ak]
            spiele = []
            for g in range(4):
                h = teams[g * 2]
                a = teams[g * 2 + 1]
                h_venue = VENUES[(g * 2) % len(VENUES)]
                spiele.append(Spiel(
                    heim=h, gast=a,
                    heim_verein=h, gast_verein=a,
                    datum=datum, anstosszeit=zeit, spielfeld=h_venue,
                ))
            spieltage_list.append(Spieltag(
                nummer=st_nr, datum=datum, anstosszeit=zeit,
                spiele=spiele, spielfrei=None,
            ))

        plan = StaffelSpielplan(
            staffel_name=f"Staffel {idx}", altersklasse=ak, topf="Topf 1",
            staffel_idx=idx, n_teams=8, doppelrunde=False,
            sz_zuordnungen=sz_list, spieltage=spieltage_list,
            score=SpielplanScore(),
        )
        alle_plaene.append(plan)
        idx += 1

total_games = sum(len(s.spiele) for p in alle_plaene for s in p.spieltage)
print(f"Staffeln: {len(alle_plaene)}, Spiele: {total_games}")
print()

t0 = time.time()
changes = solve_game_slots(alle_plaene, time_limit_seconds=60)
elapsed = time.time() - t0
print(f"CP-SAT: {changes} Spiele geaendert in {elapsed:.1f}s")

# Zaehle verbleibende Konflikte
from collections import defaultdict
belegung = defaultdict(list)
for p in alle_plaene:
    from src.spielplanerstellung.spielplan import _get_spieldauer_min, _ist_halbfeld, _parse_time
    dauer = _get_spieldauer_min(p.altersklasse)
    hf = _ist_halbfeld(p.altersklasse)
    for st in p.spieltage:
        for s in st.spiele:
            if not s.spielfeld or not s.datum:
                continue
            key = (s.spielfeld.strip().lower(), s.datum.isoformat())
            zeit = _parse_time(s.anstosszeit)
            start = zeit[0]*60 + zeit[1] if zeit else 720
            belegung[key].append((start, start+dauer, hf))

konflikte = 0
for key, entries in belegung.items():
    entries.sort()
    for i in range(len(entries)):
        for j in range(i+1, len(entries)):
            si, ei, hfi = entries[i]
            sj, ej, hfj = entries[j]
            if sj < ei:
                if hfi and hfj and si == sj:
                    same = sum(1 for ss, se, shf in entries if shf and ss == si)
                    if same <= 2:
                        continue
                konflikte += 1

print(f"Verbleibende Konflikte: {konflikte}")
