"""Spielplan-Generator: Kombiniert Schlüsselplan + Terminplan + SZ-Vergabe.

Erzeugt für jede Staffel einen konkreten Spielplan mit:
  - Spieltag-Nummer, Datum, Anstoßzeit
  - Paarungen (Heim vs. Gast) mit eigener Zeit + Spielfeld
  - Spielfreie Mannschaft (bei ungerader Staffelgröße)
  - Spielfeld-Kollisionserkennung und -auflösung
  - Spieltag-Reordering: Permutiert die Zuordnung Spieltag->Datum,
    um Cross-Staffel Venue-Kollisionen vorab zu minimieren
"""

import itertools
import math
import random
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date

from src.spielplanerstellung.schluesselplan import (
    get_paarungen_pro_spieltag, get_n_spieltage,
)
from src.spielplanerstellung.terminplan import find_terminplan, Terminplan
from src.spielplanerstellung.sz_vergabe import (
    vergebe_schluesselzahlen, SZZuordnung, SpielplanScore,
)
from src.spielplanerstellung.wuensche import Wunsch


@dataclass
class Spiel:
    """Ein einzelnes Spiel."""
    heim: str       # Mannschaftsname
    gast: str       # Mannschaftsname
    heim_verein: str = ""
    gast_verein: str = ""
    datum: date | None = None
    anstosszeit: str = ""
    spielfeld: str = ""   # Adresse des Heimspielfelds


@dataclass
class Spieltag:
    """Ein Spieltag mit allen Spielen."""
    nummer: int
    datum: date | None = None
    anstosszeit: str = ""
    spiele: list[Spiel] = field(default_factory=list)
    spielfrei: str | None = None   # Mannschaft die spielfrei hat


@dataclass
class StaffelSpielplan:
    """Kompletter Spielplan einer Staffel."""
    staffel_name: str
    altersklasse: str
    topf: str
    staffel_idx: int
    n_teams: int
    doppelrunde: bool
    sz_zuordnungen: list[SZZuordnung] = field(default_factory=list)
    spieltage: list[Spieltag] = field(default_factory=list)
    score: SpielplanScore | None = None


def generiere_spielplan(
    staffel_data: dict,
    altersklasse: str,
    topf: str,
    staffel_idx: int,
    region: str = "alle",
    wuensche: dict[str, list[Wunsch]] | None = None,
    sperrtage: set["date"] | None = None,
) -> StaffelSpielplan:
    """Generiert einen Spielplan für eine einzelne Staffel.

    Args:
        staffel_data: Dict aus der Einteilung (teams, n_teams, doppelrunde, ...)
        altersklasse: z.B. "C-Junioren"
        topf: z.B. "Topf 1"
        staffel_idx: Staffel-Index (0-basiert)
        region: "alle", "Unterland" oder "Hohenlohe"
        wuensche: Wünsche pro Mannschaft
        sperrtage: Optionale Menge von Daten die komplett gesperrt sind

    Returns:
        StaffelSpielplan
    """
    teams = staffel_data["teams"]
    n = staffel_data["n_teams"]
    doppelrunde = staffel_data.get("doppelrunde", False)

    staffelgroesse = n
    n_spieltage = get_n_spieltage(staffelgroesse)

    # 2. Terminplan finden (VOR SZ-Vergabe, damit Daten für Wünsche-Prüfung da sind)
    terminplan = find_terminplan(altersklasse, n_spieltage, region)

    # Sperrtage aus Terminplan entfernen
    if terminplan and sperrtage:
        filtered = {nr: dt for nr, dt in terminplan.spieltage.items() if dt not in sperrtage}
        removed = len(terminplan.spieltage) - len(filtered)
        if removed > 0:
            terminplan.spieltage = filtered
            print(f"[Sperrtage] {altersklasse}: {removed} Termine gesperrt")

    # Spieltag-Daten für Wünsche-Scoring extrahieren
    spieltag_dates: dict[int, "date"] = {}
    if terminplan:
        for st_nr, dt in terminplan.spieltage.items():
            if dt:
                spieltag_dates[st_nr] = dt

    # 1. SZ-Vergabe (Optimierung mit Daten + Wünschen)
    sz_zuordnungen, score = vergebe_schluesselzahlen(
        teams=teams,
        staffelgroesse=staffelgroesse,
        wuensche=wuensche,
        spieltag_dates=spieltag_dates if spieltag_dates else None,
    )

    # Build SZ->Team lookup
    sz_to_team = {z.sz: z for z in sz_zuordnungen}

    # 3. Paarungen pro Spieltag
    paarungen = get_paarungen_pro_spieltag(staffelgroesse)

    spieltage_list = []
    for spieltag_nr in sorted(paarungen.keys()):
        matches = paarungen[spieltag_nr]

        # Datum + Anstoßzeit
        datum = None
        anstosszeit = ""
        if terminplan and spieltag_nr in terminplan.spieltage:
            datum = terminplan.spieltage[spieltag_nr]
            # Nov-Feb -> Winterzeit
            if datum and datum.month in (11, 12, 1, 2):
                anstosszeit = terminplan.anstosszeit_winter
            else:
                anstosszeit = terminplan.anstosszeit

        spiele = []
        spielfrei = None

        for h_sz, g_sz in matches:
            h_team = sz_to_team.get(h_sz)
            g_team = sz_to_team.get(g_sz)

            if h_team is None and g_team is not None:
                # h_sz = 1 (bye for odd staffels) -> g_team hat spielfrei
                spielfrei = g_team.mannschaft
                continue
            elif g_team is None and h_team is not None:
                # g_sz = 1 -> h_team hat spielfrei
                spielfrei = h_team.mannschaft
                continue
            elif h_team is None and g_team is None:
                continue

            spiele.append(Spiel(
                heim=h_team.mannschaft,
                gast=g_team.mannschaft,
                heim_verein=h_team.verein,
                gast_verein=g_team.verein,
                datum=datum,
                anstosszeit=anstosszeit,
                spielfeld=h_team.adresse or "",
            ))

        spieltage_list.append(Spieltag(
            nummer=spieltag_nr,
            datum=datum,
            anstosszeit=anstosszeit,
            spiele=spiele,
            spielfrei=spielfrei,
        ))

    # 4. Doppelrunde: Rückrunde anhängen (Heimrecht tauschen)
    if doppelrunde:
        rueckrunde = []
        for st in spieltage_list:
            rueck_spiele = [
                Spiel(
                    heim=s.gast,
                    gast=s.heim,
                    heim_verein=s.gast_verein,
                    gast_verein=s.heim_verein,
                    datum=None,  # Rückrunde-Termine nicht im Hinrunde-Plan
                    anstosszeit=s.anstosszeit,
                    spielfeld=_find_adresse(sz_zuordnungen, s.gast),
                )
                for s in st.spiele
            ]
            rueckrunde.append(Spieltag(
                nummer=st.nummer + n_spieltage,
                datum=None,  # Rückrunde-Termine nicht im Hinrunde-Plan
                anstosszeit=st.anstosszeit,
                spiele=rueck_spiele,
                spielfrei=st.spielfrei,
            ))
        spieltage_list.extend(rueckrunde)

    return StaffelSpielplan(
        staffel_name=staffel_data.get("staffel_name", f"Staffel {staffel_idx + 1}"),
        altersklasse=altersklasse,
        topf=topf,
        staffel_idx=staffel_idx,
        n_teams=n,
        doppelrunde=doppelrunde,
        sz_zuordnungen=sz_zuordnungen,
        spieltage=spieltage_list,
        score=score,
    )


def _find_adresse(sz_zuordnungen: list[SZZuordnung], mannschaft: str) -> str:
    """Findet die Adresse eines Teams anhand des Namens."""
    for z in sz_zuordnungen:
        if z.mannschaft == mannschaft:
            return z.adresse or ""
    return ""


def generiere_alle_spielplaene(
    einteilung_data: dict,
    wuensche: dict[str, list[Wunsch]] | None = None,
    sperrtage: set["date"] | None = None,
) -> list[StaffelSpielplan]:
    """Generiert Spielpläne für alle Staffeln aus der Einteilung.

    Ansatz: Inkrementelle Slot-Vergabe, jüngste AK zuerst.
      1. Alle Spielpläne generieren (SZ-Vergabe, Paarungen, Daten)
      2. Alle Anstoßzeiten löschen
      3. AK für AK (jüngste zuerst) jedem Spiel einen freien Slot zuweisen
      4. Bei Konflikt: nächsten freien Slot oder H/A-Tausch
      5. Garantie: Jedes Spiel bekommt eine Uhrzeit, keine Überlappungen

    Args:
        einteilung_data: Das JSON-Result von /api/einteilung
        wuensche: Wünsche pro Mannschaftsname
        sperrtage: Optionale Menge von Daten die komplett gesperrt sind

    Returns:
        Liste von StaffelSpielplan
    """
    alle_plaene = []

    for gruppe in einteilung_data.get("gruppen", []):
        ak = gruppe["altersklasse"]
        topf = gruppe["topf"]

        # Region bestimmen (für Terminplan-Lookup)
        region = "alle"
        if ak in ("D-Junioren", "E-Junioren"):
            regions = [t.get("region", "") for s in gruppe["staffeln"] for t in s["teams"]]
            hl_count = sum(1 for r in regions if "Hohenlohe" in r)
            ul_count = sum(1 for r in regions if "Unterland" in r)
            region = "Hohenlohe" if hl_count > ul_count else "Unterland"

        for si, staffel in enumerate(gruppe["staffeln"]):
            plan = generiere_spielplan(
                staffel_data=staffel,
                altersklasse=ak,
                topf=topf,
                staffel_idx=si,
                region=region,
                wuensche=wuensche,
                sperrtage=sperrtage,
            )
            alle_plaene.append(plan)

    # Cross-Staffel SZ-Optimierung: Swappt Teams innerhalb Staffeln
    # um Venue-Kollisionen zwischen Staffeln zu reduzieren
    _optimiere_sz_cross_staffel(alle_plaene)

    # Spieltag-Reordering: Cross-Staffel Venue-Kollisionen minimieren
    saved = _optimiere_spieltag_reihenfolge(alle_plaene)
    if saved > 0:
        print(f"[Reorder] Gesamt: {saved} Venue-Kollisionen eingespart")

    # CP-SAT Slot-Vergabe: globale Optimierung, konfliktfrei
    from src.spielplanerstellung.slot_solver import solve_game_slots
    solve_game_slots(alle_plaene, wuensche=wuensche, time_limit_seconds=600)

    # Zähle verbleibende Konflikte (sollte 0 oder nahe 0 sein)
    _update_platz_konflikte(alle_plaene)

    # Wunsch-Verletzungen nach CP-SAT neu berechnen (basierend auf tatsächlichem spiel.datum)
    if wuensche:
        _update_wunsch_verletzungen(alle_plaene, wuensche)

    return alle_plaene


def _rebuild_spieltage(plan: StaffelSpielplan) -> None:
    """Baut Spieltage aus den aktuellen sz_zuordnungen neu auf.

    Wird nach Cross-Staffel SZ-Swaps aufgerufen, um die Spiel-Objekte
    mit den neuen Paarungen konsistent zu machen. Behält Daten und Zeiten bei.
    """
    sz_to_team = {z.sz: z for z in plan.sz_zuordnungen}
    paarungen = get_paarungen_pro_spieltag(plan.n_teams)
    n_spieltage = get_n_spieltage(plan.n_teams)

    # Vorhandene Daten/Zeiten übernehmen
    old_data = {st.nummer: (st.datum, st.anstosszeit) for st in plan.spieltage}

    new_spieltage = []
    for spieltag_nr in sorted(paarungen.keys()):
        matches = paarungen[spieltag_nr]
        datum, anstosszeit = old_data.get(spieltag_nr, (None, ""))

        spiele = []
        spielfrei = None

        for h_sz, g_sz in matches:
            h_team = sz_to_team.get(h_sz)
            g_team = sz_to_team.get(g_sz)

            if h_team is None and g_team is not None:
                spielfrei = g_team.mannschaft
                continue
            elif g_team is None and h_team is not None:
                spielfrei = h_team.mannschaft
                continue
            elif h_team is None and g_team is None:
                continue

            spiele.append(Spiel(
                heim=h_team.mannschaft,
                gast=g_team.mannschaft,
                heim_verein=h_team.verein,
                gast_verein=g_team.verein,
                datum=datum,
                anstosszeit=anstosszeit,
                spielfeld=h_team.adresse or "",
            ))

        new_spieltage.append(Spieltag(
            nummer=spieltag_nr,
            datum=datum,
            anstosszeit=anstosszeit,
            spiele=spiele,
            spielfrei=spielfrei,
        ))

    if plan.doppelrunde:
        for st in list(new_spieltage):
            rueck = [
                Spiel(
                    heim=s.gast, gast=s.heim,
                    heim_verein=s.gast_verein, gast_verein=s.heim_verein,
                    datum=None, anstosszeit=s.anstosszeit,
                    spielfeld=_find_adresse(plan.sz_zuordnungen, s.gast),
                )
                for s in st.spiele
            ]
            new_spieltage.append(Spieltag(
                nummer=st.nummer + n_spieltage,
                datum=None, anstosszeit=st.anstosszeit,
                spiele=rueck, spielfrei=st.spielfrei,
            ))

    plan.spieltage = new_spieltage


def _optimiere_sz_cross_staffel(
    alle_plaene: list[StaffelSpielplan],
    max_rounds: int = 5,
) -> int:
    """Optimiert SZ-Zuordnungen staffelübergreifend.

    Swappt Paare von Teams innerhalb derselben Staffel, sodass deren
    Heimspiel-Daten sich weniger mit anderen Staffeln überschneiden.

    Paarungen bleiben korrekt (Schlüsselplan unverändert) – nur welches
    Team welche SZ bekommt ändert sich. Beispiel:
      - Team A (Venue X) war SZ 3 -> Heim an Spieltag 1,3,5
      - Team B (Venue Y) war SZ 5 -> Heim an Spieltag 2,4,6
      - Nach Swap: A ist SZ 5 (Heim an 2,4,6), B ist SZ 3 (Heim an 1,3,5)
      - Wenn Venue X an Spieltag 1 Konflikte hatte, sind die jetzt weg

    Returns: Gesamtzahl akzeptierter Swaps.
    """
    n_plans = len(alle_plaene)

    # Spieltag -> Datum pro Plan
    plan_st_dates: list[dict[int, date]] = []
    for plan in alle_plaene:
        plan_st_dates.append({st.nummer: st.datum for st in plan.spieltage if st.datum})

    # SZ -> Heim-Spieltage (gecached pro Staffelgröße)
    _heim_cache: dict[int, dict[int, frozenset]] = {}

    def heim_spieltage(n_teams: int) -> dict[int, frozenset]:
        if n_teams not in _heim_cache:
            paarungen = get_paarungen_pro_spieltag(n_teams)
            h: dict[int, set] = defaultdict(set)
            for st_nr, matches in paarungen.items():
                for h_sz, _g_sz in matches:
                    h[h_sz].add(st_nr)
            _heim_cache[n_teams] = {sz: frozenset(sts) for sz, sts in h.items()}
        return _heim_cache[n_teams]

    # SZ -> Mannschaft pro Plan (veränderbar)
    plan_sz_team: list[dict[int, str]] = []
    # Mannschaft -> Venue pro Plan (fix)
    team_venue: list[dict[str, str]] = []
    for plan in alle_plaene:
        plan_sz_team.append({z.sz: z.mannschaft for z in plan.sz_zuordnungen})
        team_venue.append({
            z.mannschaft: (z.adresse or "").strip().lower()
            for z in plan.sz_zuordnungen
        })

    def plan_home_vds(pi: int) -> set[tuple[str, str]]:
        """Alle (venue, date_iso) Heimspiel-Paare für Plan pi."""
        hs = heim_spieltage(alle_plaene[pi].n_teams)
        dates = plan_st_dates[pi]
        vds: set[tuple[str, str]] = set()
        for sz, mannschaft in plan_sz_team[pi].items():
            venue = team_venue[pi].get(mannschaft, "")
            if not venue:
                continue
            for st_nr in hs.get(sz, frozenset()):
                dt = dates.get(st_nr)
                if dt:
                    vds.add((venue, dt.isoformat()))
        return vds

    # Globale Venue-Belegung: (venue, date) -> {plan_idx: count}
    global_usage: dict[tuple[str, str], dict[int, int]] = defaultdict(
        lambda: defaultdict(int)
    )
    for pi in range(n_plans):
        for vd in plan_home_vds(pi):
            global_usage[vd][pi] += 1

    def total_conflicts() -> int:
        return sum(
            max(0, sum(1 for c in pcs.values() if c > 0) - 1)
            for pcs in global_usage.values()
        )

    initial = total_conflicts()
    if initial == 0:
        return 0

    total_swaps = 0
    last_round = 0

    for round_nr in range(max_rounds):
        round_swaps = 0
        last_round = round_nr

        for pi in range(n_plans):
            plan = alle_plaene[pi]
            hs = heim_spieltage(plan.n_teams)
            dates = plan_st_dates[pi]
            sz_team = plan_sz_team[pi]
            tv = team_venue[pi]
            szs = sorted(sz_team.keys())
            if len(szs) < 2:
                continue

            def plan_conflicts(st_map: dict[int, str]) -> int:
                c = 0
                for sz, mann in st_map.items():
                    venue = tv.get(mann, "")
                    if not venue:
                        continue
                    for st_nr in hs.get(sz, frozenset()):
                        dt = dates.get(st_nr)
                        if dt:
                            vd = (venue, dt.isoformat())
                            others = sum(
                                1 for p, cnt in global_usage.get(vd, {}).items()
                                if p != pi and cnt > 0
                            )
                            if others > 0:
                                c += 1
                return c

            current_c = plan_conflicts(sz_team)
            if current_c == 0:
                continue

            best_swap = None
            best_c = current_c

            for i in range(len(szs)):
                for j in range(i + 1, len(szs)):
                    sa, sb = szs[i], szs[j]
                    # Gleiche Venue -> Swap ändert nichts
                    if tv.get(sz_team[sa], "") == tv.get(sz_team[sb], ""):
                        continue
                    trial = dict(sz_team)
                    trial[sa], trial[sb] = trial[sb], trial[sa]
                    tc = plan_conflicts(trial)
                    if tc < best_c:
                        best_c = tc
                        best_swap = (sa, sb)

            if best_swap:
                sa, sb = best_swap
                # Global usage aktualisieren
                for vd in plan_home_vds(pi):
                    global_usage[vd][pi] -= 1
                    if global_usage[vd][pi] <= 0:
                        del global_usage[vd][pi]
                # Swap anwenden
                sz_team[sa], sz_team[sb] = sz_team[sb], sz_team[sa]
                # Neue Einträge
                for vd in plan_home_vds(pi):
                    global_usage[vd][pi] += 1

                round_swaps += 1
                total_swaps += 1

        if round_swaps == 0:
            break

    if total_swaps == 0:
        return 0

    final = total_conflicts()
    print(f"[Cross-SZ] {initial} -> {final} Kollisionen "
          f"({total_swaps} SZ-Swaps in {last_round + 1} Runden)")

    # Geänderte Pläne aktualisieren: SZ-Zuordnungen + Spieltage neu aufbauen
    modified = 0
    for pi, plan in enumerate(alle_plaene):
        new_sz_team = plan_sz_team[pi]
        old_sz_team = {z.sz: z.mannschaft for z in plan.sz_zuordnungen}
        if new_sz_team != old_sz_team:
            modified += 1
            mannschaft_info = {z.mannschaft: z for z in plan.sz_zuordnungen}
            new_zuordnungen = []
            for sz in sorted(new_sz_team.keys()):
                mannschaft = new_sz_team[sz]
                orig = mannschaft_info[mannschaft]
                new_zuordnungen.append(SZZuordnung(
                    mannschaft=orig.mannschaft, verein=orig.verein, sz=sz,
                    region=orig.region, lat=orig.lat, lon=orig.lon,
                    adresse=orig.adresse,
                ))
            plan.sz_zuordnungen = new_zuordnungen
            _rebuild_spieltage(plan)

    print(f"[Cross-SZ] {modified} Staffeln neu aufgebaut")
    return total_swaps


def _optimiere_spieltag_reihenfolge(
    alle_plaene: list[StaffelSpielplan],
    max_passes: int = 3,
) -> int:
    """Permutiert pro Staffel die Zuordnung Spieltag -> Kalenderdatum.

    Paarungen (wer gegen wen) bleiben gleich – nur WANN sie stattfinden ändert sich.
    Minimiert die Anzahl an (Venue, Datum)-Kollisionen zwischen verschiedenen Staffeln,
    damit der nachfolgende CP-SAT Slot-Solver weniger Konflikte auflösen muss.

    Algorithmus:
      - Pro Staffel: alle Permutationen der Spieltag-Daten durchprobieren (≤9! = 362.880)
      - Scoring: Anzahl (Venue, Datum)-Paare, die schon von anderen Staffeln belegt sind
      - Mehrere Durchläufe, da Umordnung einer Staffel neue Optionen für andere öffnet
      - Für >9 Spieltage: Simulated Annealing statt Brute-Force

    Returns: Gesamtzahl eingesparter Kollisionen.
    """
    total_saved = 0

    for _pass in range(max_passes):
        pass_saved = 0

        for plan_idx, plan in enumerate(alle_plaene):
            # Nur Hinrunde-Spieltage (Rückrunde hat datum=None)
            hinrunde_st = [st for st in plan.spieltage if st.datum is not None]
            if len(hinrunde_st) <= 1:
                continue

            n = len(hinrunde_st)
            dates = [st.datum for st in hinrunde_st]

            # Anstoßzeiten extrahieren (Sommer/Winter)
            summer_time = winter_time = hinrunde_st[0].anstosszeit
            for st in hinrunde_st:
                if st.datum.month in (11, 12, 1, 2):
                    winter_time = st.anstosszeit
                else:
                    summer_time = st.anstosszeit

            # Heim-Venues pro Spieltag (Index in hinrunde_st)
            heim_venues_per_st: list[list[str]] = []
            for st in hinrunde_st:
                venues = []
                for spiel in st.spiele:
                    if spiel.spielfeld:
                        venues.append(spiel.spielfeld.strip().lower())
                heim_venues_per_st.append(venues)

            # Venue-Belegung aller ANDEREN Pläne: (venue, date_iso) -> Anzahl
            other_usage: dict[tuple[str, str], int] = defaultdict(int)
            for i, other in enumerate(alle_plaene):
                if i == plan_idx:
                    continue
                for st in other.spieltage:
                    if not st.datum:
                        continue
                    for spiel in st.spiele:
                        if spiel.spielfeld:
                            key = (spiel.spielfeld.strip().lower(), st.datum.isoformat())
                            other_usage[key] += 1

            # Scoring: Kosten-Matrix [spieltag_i][date_j] -> Kollisionen
            # wenn Spieltag i auf Datum j gelegt wird
            date_isos = [d.isoformat() for d in dates]
            cost_matrix: list[list[int]] = []
            for i in range(n):
                row = []
                for j in range(n):
                    c = sum(other_usage.get((v, date_isos[j]), 0)
                            for v in heim_venues_per_st[i])
                    row.append(c)
                cost_matrix.append(row)

            current_score = sum(cost_matrix[i][i] for i in range(n))
            if current_score == 0:
                continue

            best_perm = list(range(n))
            best_score = current_score

            if math.factorial(n) <= 500_000:  # ≤9 Spieltage -> Brute-Force
                for perm in itertools.permutations(range(n)):
                    s = sum(cost_matrix[i][perm[i]] for i in range(n))
                    if s < best_score:
                        best_score = s
                        best_perm = list(perm)
                    if best_score == 0:
                        break
            else:  # >9 Spieltage -> Simulated Annealing
                cur_perm = list(range(n))
                cur_s = current_score
                for step in range(50_000):
                    t = 10.0 * (0.001 ** (step / 49_999))
                    i, j = random.sample(range(n), 2)
                    new_perm = list(cur_perm)
                    new_perm[i], new_perm[j] = new_perm[j], new_perm[i]
                    new_s = sum(cost_matrix[k][new_perm[k]] for k in range(n))
                    delta = new_s - cur_s
                    if delta < 0 or random.random() < math.exp(-delta / max(t, 1e-10)):
                        cur_perm = new_perm
                        cur_s = new_s
                        if cur_s < best_score:
                            best_score = cur_s
                            best_perm = list(cur_perm)
                    if best_score == 0:
                        break

            if best_score < current_score:
                # Permutation anwenden: Daten + Anstoßzeiten reassignen
                new_dates = [dates[best_perm[i]] for i in range(n)]
                for i, st in enumerate(hinrunde_st):
                    new_dt = new_dates[i]
                    new_zeit = (winter_time if new_dt.month in (11, 12, 1, 2)
                                else summer_time)
                    st.datum = new_dt
                    st.anstosszeit = new_zeit
                    for spiel in st.spiele:
                        spiel.datum = new_dt
                        spiel.anstosszeit = new_zeit

                saved = current_score - best_score
                pass_saved += saved
                total_saved += saved
                print(f"[Reorder] {plan.altersklasse} {plan.staffel_name}: "
                      f"{current_score} -> {best_score} Kollisionen (-{saved})")

        if pass_saved == 0:
            break
        print(f"[Reorder] Pass {_pass + 1}: {pass_saved} Kollisionen eingespart")

    return total_saved


def _update_platz_konflikte(plaene: list[StaffelSpielplan]) -> None:
    """Zählt verbleibende Spielfeld-Konflikte nach der Auflösung und aktualisiert Scores."""
    from collections import defaultdict
    # (start, end, halbfeld, game_name, zeit, staffel_info, ort)
    belegung: dict[tuple[str, str], list[tuple[int, int, bool, str, str, str, str]]] = defaultdict(list)

    for plan in plaene:
        halbfeld = _ist_halbfeld(plan.altersklasse)
        dauer = _get_spieldauer_min(plan.altersklasse)
        staffel_info = f"{plan.altersklasse} {plan.staffel_name}"
        for st in plan.spieltage:
            for spiel in st.spiele:
                if not spiel.spielfeld or not spiel.datum:
                    continue
                key = (spiel.spielfeld.strip().lower(), spiel.datum.isoformat())
                zeit = _parse_time(spiel.anstosszeit)
                start = zeit[0] * 60 + zeit[1] if zeit else 720
                game_name = f"{spiel.heim} vs {spiel.gast}"
                ort = spiel.spielfeld.split(", ")[-1] if ", " in spiel.spielfeld else spiel.spielfeld
                belegung[key].append((start, start + dauer, halbfeld,
                                      game_name, spiel.anstosszeit or "?",
                                      staffel_info, ort))

    # Build per-game conflict details: game_name -> [detail_dict, ...]
    game_conflicts: dict[str, list[dict]] = defaultdict(list)
    for (feld, datum), entries in belegung.items():
        entries.sort()
        for i in range(len(entries)):
            for j in range(i + 1, len(entries)):
                s_i, e_i, hf_i, name_i, zeit_i, staffel_i, ort_i = entries[i]
                s_j, e_j, hf_j, name_j, zeit_j, staffel_j, ort_j = entries[j]
                if s_j < e_i:
                    if hf_i and hf_j and s_i == s_j:
                        continue
                    # Register conflict for both games
                    game_conflicts[name_i].append({
                        "datum": datum,
                        "ort": ort_i,
                        "spiel": name_i,
                        "grund": f"Zeitüberlappung mit {name_j} ({zeit_j}, {staffel_j})",
                    })
                    game_conflicts[name_j].append({
                        "datum": datum,
                        "ort": ort_j,
                        "spiel": name_j,
                        "grund": f"Zeitüberlappung mit {name_i} ({zeit_i}, {staffel_i})",
                    })

    for plan in plaene:
        if not plan.score:
            continue
        plan.score.platz_konflikte = 0
        plan.score.platz_konflikt_details = []
        for st in plan.spieltage:
            for spiel in st.spiele:
                game_name = f"{spiel.heim} vs {spiel.gast}"
                conflicts = game_conflicts.get(game_name, [])
                if conflicts:
                    plan.score.platz_konflikte += 1
                    plan.score.platz_konflikt_details.extend(conflicts)
        plan.score.berechne_total()


def _update_wunsch_verletzungen(
    plaene: list[StaffelSpielplan],
    wuensche: dict[str, list[Wunsch]],
) -> None:
    """Berechnet Wunsch-Verletzungen neu basierend auf tatsächlichen Spiel-Daten nach CP-SAT.

    Wochentag-Wünsche: Zählt nur Spiele als Verletzung, bei denen der bevorzugte
    Tag innerhalb derselben KW erreichbar war (±3 Tage vom Spieltag-Datum).
    """
    from src.spielplanerstellung.wuensche import WunschKategorie, WunschPrio
    from datetime import timedelta

    _WT_MAP = {
        "montag": 0, "dienstag": 1, "mittwoch": 2, "donnerstag": 3,
        "freitag": 4, "samstag": 5, "sonntag": 6,
        "mo": 0, "di": 1, "mi": 2, "do": 3, "fr": 4, "sa": 5, "so": 6,
    }
    _WT_NAMES = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]

    for plan in plaene:
        if not plan.score:
            continue

        # (datum, rolle, heim, gast, anstosszeit, spieltag_datum)
        team_games: dict[str, list[tuple[date, str, str, str, str, date | None]]] = {}
        for st in plan.spieltage:
            for spiel in st.spiele:
                if not spiel.datum:
                    continue
                team_games.setdefault(spiel.heim, []).append(
                    (spiel.datum, "heim", spiel.heim, spiel.gast, spiel.anstosszeit, st.datum))
                team_games.setdefault(spiel.gast, []).append(
                    (spiel.datum, "gast", spiel.heim, spiel.gast, spiel.anstosszeit, st.datum))

        violations = 0
        details: list[dict] = []

        for mannschaft, games in team_games.items():
            team_w = wuensche.get(mannschaft, [])

            # Sammle ALLE gewünschten Wochentage dieses Teams
            gewuenschte_wochentage: set[int] = set()
            for w in team_w:
                if w.kategorie == WunschKategorie.WOCHENTAG and w.wochentag:
                    wd_nr = _WT_MAP.get(w.wochentag.strip().lower())
                    if wd_nr is not None:
                        gewuenschte_wochentage.add(wd_nr)

            for w in team_w:
                pen = 2 if w.prioritaet == WunschPrio.HART else 1

                if w.kategorie == WunschKategorie.SPERRTAG and w.datum:
                    try:
                        sperr = date.fromisoformat(w.datum)
                    except (ValueError, TypeError):
                        continue
                    for g_datum, rolle, heim, gast, zeit, st_datum in games:
                        if g_datum == sperr:
                            violations += pen
                            details.append({
                                "team": mannschaft,
                                "typ": "Sperrtag",
                                "datum": g_datum.isoformat(),
                                "spiel": f"{heim} vs {gast}",
                                "grund": f"Spiel am {sperr.strftime('%d.%m.%Y')} trotz Sperrtag",
                            })
                            break

                elif w.kategorie == WunschKategorie.WOCHENTAG and w.wochentag:
                    # Skip: Wochentag violations werden unten gesammelt gezählt
                    pass

                elif w.kategorie == WunschKategorie.ANSTOSSZEIT and w.uhrzeit:
                    parts = w.uhrzeit.replace(":", ".").split(".")
                    if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
                        wunsch_min = int(parts[0]) * 60 + int(parts[1])
                    else:
                        continue
                    for g_datum, rolle, heim, gast, anstosszeit, st_datum in games:
                        # Auf Wochentagen ist frühester Anstoß 17:30 – Wünsche vor 17:30
                        # sind dort physisch unmöglich und werden nicht als Verletzung gezählt
                        if g_datum.weekday() < 5 and wunsch_min < 17 * 60 + 30:
                            continue
                        zeit_parts = (anstosszeit or "").replace(":", ".").split(".")
                        if len(zeit_parts) == 2 and zeit_parts[0].isdigit() and zeit_parts[1].isdigit():
                            actual_min = int(zeit_parts[0]) * 60 + int(zeit_parts[1])
                        else:
                            continue
                        diff = abs(actual_min - wunsch_min)
                        if diff > 30:
                            violations += pen
                            details.append({
                                "team": mannschaft,
                                "typ": "Anstoßzeit",
                                "datum": g_datum.isoformat(),
                                "spiel": f"{heim} vs {gast}",
                                "grund": f"Anstoß {anstosszeit} statt gewünscht {w.uhrzeit}",
                            })

                elif w.kategorie == WunschKategorie.HEIMWUNSCH and w.datum:
                    try:
                        wunsch_date = date.fromisoformat(w.datum)
                    except (ValueError, TypeError):
                        continue
                    for g_datum, rolle, heim, gast, zeit, st_datum in games:
                        if g_datum == wunsch_date and rolle != "heim":
                            violations += pen
                            details.append({
                                "team": mannschaft,
                                "typ": "Heimwunsch",
                                "datum": g_datum.isoformat(),
                                "spiel": f"{heim} vs {gast}",
                                "grund": f"Auswärts statt Heim am {wunsch_date.strftime('%d.%m.%Y')}",
                            })

                elif w.kategorie == WunschKategorie.AUSWAERTSWUNSCH and w.datum:
                    try:
                        wunsch_date = date.fromisoformat(w.datum)
                    except (ValueError, TypeError):
                        continue
                    for g_datum, rolle, heim, gast, zeit, st_datum in games:
                        if g_datum == wunsch_date and rolle != "gast":
                            violations += pen
                            details.append({
                                "team": mannschaft,
                                "typ": "Auswärtswunsch",
                                "datum": g_datum.isoformat(),
                                "spiel": f"{heim} vs {gast}",
                                "grund": f"Heim statt Auswärts am {wunsch_date.strftime('%d.%m.%Y')}",
                            })

            # ── Wochentag-Verletzungen: einmal pro Spiel, unabhängig von Anzahl Wochentag-Wünsche ──
            if gewuenschte_wochentage:
                wunsch_str = " oder ".join(
                    _WT_NAMES[wd] for wd in sorted(gewuenschte_wochentage)
                )
                for g_datum, rolle, heim, gast, zeit, st_datum in games:
                    if g_datum.weekday() in gewuenschte_wochentage:
                        continue  # Spiel ist auf einem der gewünschten Tage

                    # Prüfe ob mindestens einer der gewünschten Tage erreichbar war (±2 Tage)
                    ref = st_datum or g_datum
                    erreichbar = False
                    for target_wd in gewuenschte_wochentage:
                        diff = target_wd - ref.weekday()
                        if diff > 3:
                            diff -= 7
                        elif diff < -3:
                            diff += 7
                        if abs(diff) <= 2:
                            erreichbar = True
                            break

                    if erreichbar:
                        violations += 1
                        details.append({
                            "team": mannschaft,
                            "typ": "Wochentag",
                            "datum": g_datum.isoformat(),
                            "spiel": f"{heim} vs {gast}",
                            "grund": f"Spiel am {_WT_NAMES[g_datum.weekday()]} {g_datum.strftime('%d.%m.')} statt {wunsch_str}",
                        })

        plan.score.wunsch_verletzungen = violations
        plan.score.wunsch_details = details
        plan.score.berechne_total()


# ─── Inkrementelle Slot-Vergabe ────────────────────────────────

# AK-Reihenfolge: jüngste zuerst (bekommen die Wunschzeiten)
_AK_ORDER: dict[str, int] = {
    "F-Junioren": 0, "F-Juniorinnen": 1,
    "E-Junioren": 2, "E-Juniorinnen": 3,
    "D-Junioren": 4, "D-Juniorinnen": 5,
    "C-Junioren": 6, "C-Juniorinnen": 7,
    "B-Junioren": 8, "B-Juniorinnen": 9,
    "A-Junioren": 10, "A-Juniorinnen": 11,
}

# Frühester / spätester Anstoß (Sommer vs. Winter)
_EARLIEST_SUMMER = 9 * 60           # 09:00
_LATEST_SUMMER = 19 * 60 + 30       # 19:30
_EARLIEST_WINTER = 9 * 60           # 09:00
_LATEST_WINTER = 17 * 60            # 17:00


def _assign_slots_incremental(plaene: list[StaffelSpielplan]) -> None:
    """Weist allen Spielen konfliktfrei Anstoßzeiten zu.

    Vorgehen:
      1. Sammle alle Spiele aller Staffeln
      2. Sortiere: jüngste AK zuerst -> bekommen ihre Wunschzeit
      3. Für jedes Spiel: finde an (spielfeld, datum) den ersten freien Slot
      4. Falls kein Slot frei: tausche Heim/Auswärts und probiere Gast-Venue
      5. Fallback: nächster freier Slot (auch nach Standardzeiten)
    """
    # Globale Belegung: (venue_lower, datum_iso) -> [(start_min, end_min, halbfeld)]
    venue_slots: dict[tuple[str, str], list[tuple[int, int, bool]]] = {}

    # Sammle alle Spiele mit Metadaten
    all_games: list[tuple[int, StaffelSpielplan, Spieltag, Spiel]] = []
    for plan in plaene:
        ak_order = _AK_ORDER.get(plan.altersklasse, 99)
        for st in plan.spieltage:
            for spiel in st.spiele:
                all_games.append((ak_order, plan, st, spiel))

    # Sortiere: jüngste AK zuerst
    all_games.sort(key=lambda x: x[0])

    for _, plan, st, spiel in all_games:
        if not spiel.datum:
            # Kein Datum (z.B. Rückrunde) -> Standardzeit behalten
            continue

        ak = plan.altersklasse
        dauer = _get_spieldauer_min(ak)
        halbfeld = _ist_halbfeld(ak)

        # Winter oder Sommer?
        is_winter = spiel.datum.month in (11, 12, 1, 2)
        earliest = _EARLIEST_WINTER if is_winter else _EARLIEST_SUMMER
        latest = _LATEST_WINTER if is_winter else _LATEST_SUMMER

        # Gewünschte Startzeit (aus Terminplan)
        preferred = _parse_time(spiel.anstosszeit)
        preferred_min = preferred[0] * 60 + preferred[1] if preferred else (earliest + 60)

        # Versuche zuerst am Heim-Venue
        venue = spiel.spielfeld.strip().lower() if spiel.spielfeld else ""
        datum_iso = spiel.datum.isoformat()

        if venue:
            slot = _find_free_slot(
                venue_slots, venue, datum_iso, preferred_min, dauer, halbfeld, earliest, latest
            )
            if slot is not None:
                _book_slot(venue_slots, venue, datum_iso, slot, dauer, halbfeld)
                spiel.anstosszeit = _format_time(slot // 60, slot % 60)
                continue

        # Heim-Venue voll -> versuche H/A-Tausch
        gast_addr = _find_adresse(plan.sz_zuordnungen, spiel.gast)
        gast_venue = gast_addr.strip().lower() if gast_addr else ""

        if gast_venue and gast_venue != venue:
            slot = _find_free_slot(
                venue_slots, gast_venue, datum_iso, preferred_min, dauer, halbfeld, earliest, latest
            )
            if slot is not None:
                # Tausche Heim/Auswärts
                spiel.heim, spiel.gast = spiel.gast, spiel.heim
                spiel.heim_verein, spiel.gast_verein = spiel.gast_verein, spiel.heim_verein
                spiel.spielfeld = gast_addr
                _book_slot(venue_slots, gast_venue, datum_iso, slot, dauer, halbfeld)
                spiel.anstosszeit = _format_time(slot // 60, slot % 60)
                continue

        # Fallback: forciere am Heim-Venue (auch spätere Zeiten)
        if venue:
            slot = _find_free_slot(
                venue_slots, venue, datum_iso, earliest, dauer, halbfeld, earliest, 23 * 60
            )
            if slot is not None:
                _book_slot(venue_slots, venue, datum_iso, slot, dauer, halbfeld)
                spiel.anstosszeit = _format_time(slot // 60, slot % 60)
                continue

        # Absoluter Fallback: behalte Standardzeit (kann Konflikt geben)
        if preferred:
            _book_slot(venue_slots, venue or "__unknown__", datum_iso, preferred_min, dauer, halbfeld)


def _find_free_slot(
    venue_slots: dict[tuple[str, str], list[tuple[int, int, bool]]],
    venue: str,
    datum_iso: str,
    preferred_start: int,
    dauer: int,
    halbfeld: bool,
    earliest: int,
    latest: int,
) -> int | None:
    """Findet den nächsten freien Slot ab preferred_start.

    Gibt die Startzeit in Minuten zurück, oder None wenn nichts passt.
    """
    key = (venue, datum_iso)
    existing = venue_slots.get(key, [])

    # Versuche preferred_start zuerst, dann in 15-Min-Schritten aufwärts
    for offset in range(0, latest - earliest + dauer, 15):
        candidate = preferred_start + offset
        if candidate < earliest:
            continue
        if candidate + dauer > latest + dauer:  # Spiel darf bis latest + dauer_min laufen
            break

        end = candidate + dauer

        conflict = False
        for s_start, s_end, s_hf in existing:
            # Überlappung?
            if candidate < s_end and end > s_start:
                # Halbfeld: 2 gleichzeitig OK wenn gleiche Startzeit
                if halbfeld and s_hf and candidate == s_start:
                    # Zähle wie viele schon zu dieser Zeit laufen
                    same_time = sum(1 for ss, se, shf in existing if shf and ss == candidate)
                    if same_time < 2:
                        continue
                conflict = True
                break

        if not conflict:
            return candidate

    # Auch vor preferred_start probieren
    for offset in range(15, preferred_start - earliest + 15, 15):
        candidate = preferred_start - offset
        if candidate < earliest:
            break

        end = candidate + dauer
        conflict = False
        for s_start, s_end, s_hf in existing:
            if candidate < s_end and end > s_start:
                if halbfeld and s_hf and candidate == s_start:
                    same_time = sum(1 for ss, se, shf in existing if shf and ss == candidate)
                    if same_time < 2:
                        continue
                conflict = True
                break

        if not conflict:
            return candidate

    return None


def _book_slot(
    venue_slots: dict[tuple[str, str], list[tuple[int, int, bool]]],
    venue: str,
    datum_iso: str,
    start: int,
    dauer: int,
    halbfeld: bool,
) -> None:
    """Bucht einen Slot in der Venue-Belegung."""
    key = (venue, datum_iso)
    venue_slots.setdefault(key, []).append((start, start + dauer, halbfeld))

# Offizielle Spielzeiten WFV Jugendfußball + Puffer
# Spielzeit = 2 × Halbzeit + Halbzeitpause + Nachspielzeit + Wechselpuffer
# Halbfeld-AK (D und jünger): 2 Spiele passen gleichzeitig auf 1 Großfeld
AK_SPIELDAUER: dict[str, dict] = {
    "A-Junioren":   {"halbzeit": 45, "pause": 15, "puffer": 20, "halbfeld": False},  # 2×45 + 15 + 20 = 125 min
    "A-Juniorinnen": {"halbzeit": 45, "pause": 15, "puffer": 20, "halbfeld": False},
    "B-Junioren":   {"halbzeit": 40, "pause": 15, "puffer": 15, "halbfeld": False},  # 2×40 + 15 + 15 = 110 min
    "B-Juniorinnen": {"halbzeit": 40, "pause": 15, "puffer": 15, "halbfeld": False},
    "C-Junioren":   {"halbzeit": 35, "pause": 15, "puffer": 15, "halbfeld": False},  # 2×35 + 15 + 15 = 100 min
    "C-Juniorinnen": {"halbzeit": 35, "pause": 15, "puffer": 15, "halbfeld": False},
    "D-Junioren":   {"halbzeit": 25, "pause": 10, "puffer": 15, "halbfeld": True},   # 2×25 + 10 + 15 =  75 min
    "D-Juniorinnen": {"halbzeit": 25, "pause": 10, "puffer": 15, "halbfeld": True},
    "E-Junioren":   {"halbzeit": 20, "pause": 10, "puffer": 10, "halbfeld": True},   # 2×20 + 10 + 10 =  60 min
    "E-Juniorinnen": {"halbzeit": 20, "pause": 10, "puffer": 10, "halbfeld": True},
    "F-Junioren":   {"halbzeit": 15, "pause":  5, "puffer": 10, "halbfeld": True},   # 2×15 +  5 + 10 =  45 min
    "F-Juniorinnen": {"halbzeit": 15, "pause":  5, "puffer": 10, "halbfeld": True},
}

_DEFAULT_DAUER = {"halbzeit": 35, "pause": 15, "puffer": 15, "halbfeld": False}


def _get_spieldauer_min(altersklasse: str) -> int:
    """Gibt die gesamte Blockdauer (inkl. Puffer) in Minuten für eine AK zurück."""
    d = AK_SPIELDAUER.get(altersklasse, _DEFAULT_DAUER)
    return 2 * d["halbzeit"] + d["pause"] + d["puffer"]


def _ist_halbfeld(altersklasse: str) -> bool:
    """Prüft ob die AK auf Halbfeld spielt (D-Jugend und jünger)."""
    d = AK_SPIELDAUER.get(altersklasse, _DEFAULT_DAUER)
    return d["halbfeld"]


def _parse_time(zeit_str: str) -> tuple[int, int] | None:
    """Parst "14:15" -> (14, 15). Gibt None zurück bei leerem/ungültigem String."""
    if not zeit_str or ":" not in zeit_str:
        return None
    try:
        parts = zeit_str.strip().split(":")
        return (int(parts[0]), int(parts[1]))
    except (ValueError, IndexError):
        return None


def _format_time(h: int, m: int) -> str:
    """Formatiert (14, 15) -> "14:15"."""
    return f"{h:02d}:{m:02d}"


def spielplan_to_dict(plan: StaffelSpielplan) -> dict:
    """Konvertiert einen Spielplan in ein JSON-fähiges Dict."""
    return {
        "staffel_name": plan.staffel_name,
        "altersklasse": plan.altersklasse,
        "topf": plan.topf,
        "staffel_idx": plan.staffel_idx,
        "n_teams": plan.n_teams,
        "doppelrunde": plan.doppelrunde,
        "sz_zuordnungen": [
            {"mannschaft": z.mannschaft, "verein": z.verein, "sz": z.sz, "region": z.region}
            for z in plan.sz_zuordnungen
        ],
        "score": {
            "total": round(plan.score.total, 1),
            "heim_balance": round(plan.score.heim_balance, 2),
            "consecutive_penalty": round(plan.score.consecutive_penalty, 1),
            "distanz_fairness": round(plan.score.distanz_fairness, 1),
            "wunsch_verletzungen": plan.score.wunsch_verletzungen,
            "platz_konflikte": plan.score.platz_konflikte,
            "wunsch_details": plan.score.wunsch_details,
            "platz_konflikt_details": plan.score.platz_konflikt_details,
        } if plan.score else None,
        "spieltage": [
            {
                "nummer": st.nummer,
                "datum": st.datum.isoformat() if st.datum else None,
                "anstosszeit": st.anstosszeit,
                "spiele": [
                    {
                        "heim": s.heim,
                        "gast": s.gast,
                        "datum": s.datum.isoformat() if s.datum else None,
                        "anstosszeit": s.anstosszeit,
                        "spielfeld": s.spielfeld,
                    }
                    for s in st.spiele
                ],
                "spielfrei": st.spielfrei,
            }
            for st in plan.spieltage
        ],
    }
