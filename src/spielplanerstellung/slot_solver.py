"""CP-SAT-basierte Slot-Vergabe für konfliktfreie Spielplanung.

Ersetzt die greedy-inkrementelle Methode durch einen Constraint-Solver
(Google OR-Tools CP-SAT), der global optimale Lösungen findet.

Kernidee:
  - Jedes Spiel kann auf alternative Tage innerhalb derselben KW ausweichen
  - Wochentag-Spiele frühestens 17:30
  - Cumulative-Constraint pro (Venue, Datum) mit Kapazität 2
    → Halbfeld-Spiele (Demand 1): 2 parallel OK
    → Großfeld-Spiele (Demand 2): blockieren das Feld komplett
  - Minimiert: Zeitabweichung + Datums-Abweichung + H/A-Tausch-Penalties
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field as dc_field
from datetime import date, timedelta

from ortools.sat.python import cp_model

from src.spielplanerstellung.spielplan import (
    StaffelSpielplan, Spieltag, Spiel,
    _find_adresse, _get_spieldauer_min, _ist_halbfeld,
    _parse_time, _format_time,
)
from src.spielplanerstellung.wuensche import (
    Wunsch, WunschKategorie, WunschPrio,
)


# ─── Datenstrukturen ──────────────────────────────────────────


@dataclass
class _GameSlot:
    """Eine mögliche Slot-Option für ein Spiel."""
    date: date
    earliest_min: int   # frühester Anstoß (Minuten ab Mitternacht)
    latest_min: int     # spätester Anstoß
    venue: str          # normalisierter Venue-Key
    venue_raw: str      # originale Adresse (für Zuweisung)
    is_swap: bool       # True = Heim/Auswärts getauscht
    penalty: int        # Strafpunkte für diese Option


@dataclass
class _GameInfo:
    """Ein zu planendes Spiel mit allen CP-SAT-Variablen."""
    gid: int
    spiel: Spiel
    plan: StaffelSpielplan
    spieltag: Spieltag
    duration: int
    halbfeld: bool
    heim_venue: str
    heim_venue_raw: str
    gast_venue: str
    gast_venue_raw: str
    preferred_start: int
    options: list[_GameSlot] = dc_field(default_factory=list)
    # CP-SAT Variablen (werden in _build_model gesetzt)
    option_vars: list = dc_field(default_factory=list)
    start_var: object = None


# ─── Alternative Termine ───────────────────────────────────────

def _get_alternative_dates(primary: date, wunsch_wochentage: set[int] | None = None) -> list[tuple[date, str]]:
    """Gibt alternative Spieltage in derselben KW zurück.

    Wenn wunsch_wochentage angegeben, wird auch der gewünschte Wochentag
    als Alternative hinzugefügt (falls nicht schon enthalten).

    Returns:
        [(datum, typ)] wobei typ ∈ {'primary', 'weekend', 'weekday'}
    """
    wd = primary.weekday()  # 0=Mo … 6=So
    result = [(primary, "primary")]

    if wd == 5:      # Samstag
        result.append((primary - timedelta(days=1), "weekday"))   # Freitag
        result.append((primary + timedelta(days=1), "weekend"))   # Sonntag
    elif wd == 6:    # Sonntag
        result.append((primary - timedelta(days=1), "weekend"))   # Samstag
        result.append((primary - timedelta(days=2), "weekday"))   # Freitag
    elif wd == 4:    # Freitag
        result.append((primary + timedelta(days=1), "weekend"))   # Samstag
        result.append((primary + timedelta(days=2), "weekend"))   # Sonntag
    else:            # Mo–Do
        if wd > 0:
            result.append((primary - timedelta(days=1), "weekday"))
        result.append((primary + timedelta(days=1), "weekday"))
        # Samstag derselben Woche
        days_to_sat = 5 - wd
        result.append((primary + timedelta(days=days_to_sat), "weekend"))

    # Wunsch-Wochentage als Extra-Optionen (wenn nicht schon enthalten)
    if wunsch_wochentage:
        existing_wds = {dt.weekday() for dt, _ in result}
        for target_wd in wunsch_wochentage:
            if target_wd in existing_wds:
                continue
            # Berechne nächsten Tag mit diesem Wochentag in derselben KW (±3 Tage)
            diff = target_wd - wd
            if diff > 3:
                diff -= 7
            elif diff < -3:
                diff += 7
            candidate = primary + timedelta(days=diff)
            dt_type = "weekend" if target_wd >= 5 else "weekday"
            result.append((candidate, dt_type))

    return result


def _time_range(dt: date) -> tuple[int, int]:
    """Erlaubter Anstoßzeitraum [earliest, latest] in Minuten.

    Wochentag (Mo-Fr):  17:30 – 20:00
    Samstag:            09:00 – 19:30  (Winter: bis 17:00)
    Sonntag:            09:00 – 18:00  (Winter: bis 16:00)
    """
    wd = dt.weekday()
    is_winter = dt.month in (11, 12, 1, 2)

    if wd < 5:   # Wochentag
        return (17 * 60 + 30, 20 * 60)
    elif wd == 5:  # Samstag
        return (9 * 60, 17 * 60 if is_winter else 19 * 60 + 30)
    else:          # Sonntag
        return (9 * 60, 16 * 60 if is_winter else 18 * 60)


# ─── Penalties ─────────────────────────────────────────────────

# Strafgewichte – höher = unerwünschter
_PENALTY_ALT_WEEKEND  = 10   # Ausweichen auf anderes WE-Datum
_PENALTY_ALT_WEEKDAY  = 30   # Ausweichen auf Wochentag
_PENALTY_SWAP         = 20   # Heim/Auswärts-Tausch
_PENALTY_TIME_PER_15  = 1    # je 15 min Abweichung von Wunschzeit
_PENALTY_SPERRTAG     = 200  # Spiel auf Sperrtag (hart: verboten, weich: Strafe)
_PENALTY_WOCHENTAG    = 50   # Spiel nicht am Wunschwochentag (pro Team)


# ─── Solver ────────────────────────────────────────────────────

# Wochentag-Name → date.weekday()
_WOCHENTAG_MAP = {
    "montag": 0, "dienstag": 1, "mittwoch": 2, "donnerstag": 3,
    "freitag": 4, "samstag": 5, "sonntag": 6,
    "mo": 0, "di": 1, "mi": 2, "do": 3, "fr": 4, "sa": 5, "so": 6,
}


def solve_game_slots(
    plaene: list[StaffelSpielplan],
    wuensche: dict[str, list[Wunsch]] | None = None,
    time_limit_seconds: int = 120,
) -> int:
    """Weist allen Spielen konfliktfreie Slots zu (CP-SAT).

    Löst pro Primärdatum separat (kleinere Teilprobleme → schneller).

    Returns:
        Anzahl geänderter Spiele.
    """
    import time as _time
    t0 = _time.time()

    all_games = _collect_games(plaene)
    if not all_games:
        return 0

    _generate_options(all_games, wuensche=wuensche)

    # Nur Spiele mit gültigen Optionen
    all_games = [g for g in all_games if g.options]

    # Gruppiere nach Primärdatum (Spiele am selben Tag konkurrieren)
    from collections import defaultdict
    by_date: dict[date, list[_GameInfo]] = defaultdict(list)
    for g in all_games:
        by_date[g.spiel.datum].append(g)

    total_changes = 0
    n_groups = len(by_date)

    print(f"[CP-SAT] {len(all_games)} Spiele in {n_groups} Datumsgruppen")

    # Zeit pro Gruppe proportional zum Gesamt-Limit
    per_group_limit = max(5, time_limit_seconds // max(n_groups, 1))

    for i, (dt, games) in enumerate(sorted(by_date.items())):
        model = cp_model.CpModel()
        _build_model(model, games)
        changes = _solve_and_apply(model, games, per_group_limit)
        total_changes += changes

        if (i + 1) % 5 == 0 or i == n_groups - 1:
            print(f"[CP-SAT] Gruppe {i+1}/{n_groups}: "
                  f"{dt} ({len(games)} Spiele, {changes} Änderungen)")

    # ── Zweiter Pass: Repariere cross-date Konflikte ──────────
    repair_changes = _repair_cross_date_conflicts(plaene, wuensche, time_limit_seconds=30)
    total_changes += repair_changes

    print(f"[CP-SAT] Fertig in {_time.time() - t0:.1f}s, "
          f"{total_changes} Spiele geändert")

    return total_changes


# ─── 1. Spiele sammeln ────────────────────────────────────────

def _collect_games(plaene: list[StaffelSpielplan]) -> list[_GameInfo]:
    """Extrahiert alle Spiele aus allen Staffel-Spielplänen."""
    games: list[_GameInfo] = []
    gid = 0

    for plan in plaene:
        dauer = _get_spieldauer_min(plan.altersklasse)
        halbfeld = _ist_halbfeld(plan.altersklasse)

        for st in plan.spieltage:
            for spiel in st.spiele:
                if not spiel.datum:
                    continue

                heim_raw = (spiel.spielfeld or "").strip()
                heim_venue = heim_raw.lower()
                gast_raw = _find_adresse(plan.sz_zuordnungen, spiel.gast).strip()
                gast_venue = gast_raw.lower()

                pref = _parse_time(spiel.anstosszeit)
                pref_min = pref[0] * 60 + pref[1] if pref else 600

                games.append(_GameInfo(
                    gid=gid,
                    spiel=spiel,
                    plan=plan,
                    spieltag=st,
                    duration=dauer,
                    halbfeld=halbfeld,
                    heim_venue=heim_venue,
                    heim_venue_raw=heim_raw,
                    gast_venue=gast_venue,
                    gast_venue_raw=gast_raw,
                    preferred_start=pref_min,
                ))
                gid += 1

    return games


# ─── 2. Optionen pro Spiel ────────────────────────────────────

def _generate_options(
    games: list[_GameInfo],
    wuensche: dict[str, list[Wunsch]] | None = None,
) -> None:
    """Erzeugt für jedes Spiel die möglichen (Datum, Venue, Zeitbereich)-Kandidaten.

    Berücksichtigt Vereinswünsche:
      - SPERRTAG/HART: Option wird komplett ausgeschlossen
      - SPERRTAG/WEICH: Hohe Strafe
      - WOCHENTAG: Strafe wenn Datum nicht am Wunschwochentag
    """
    wuensche = wuensche or {}

    for g in games:
        primary_date = g.spiel.datum

        # Wünsche für Heim- und Gast-Team sammeln
        heim_w = wuensche.get(g.spiel.heim, [])
        gast_w = wuensche.get(g.spiel.gast, [])

        # Sperrtage extrahieren: {iso_datum: prio}
        sperrtage: dict[str, WunschPrio] = {}
        for w in heim_w + gast_w:
            if w.kategorie == WunschKategorie.SPERRTAG and w.datum:
                existing = sperrtage.get(w.datum)
                # HART überschreibt WEICH
                if existing != WunschPrio.HART:
                    sperrtage[w.datum] = w.prioritaet

        # Wunschwochentage extrahieren (Heim- UND Gast-Team)
        wunsch_wochentage: set[int] = set()
        for w in heim_w + gast_w:
            if w.kategorie == WunschKategorie.WOCHENTAG and w.wochentag:
                wd_nr = _WOCHENTAG_MAP.get(w.wochentag.lower())
                if wd_nr is not None:
                    wunsch_wochentage.add(wd_nr)

        # Alternative Termine inkl. Wunsch-Wochentage
        alt_dates = _get_alternative_dates(primary_date, wunsch_wochentage or None)

        # Wunsch-Anstoßzeit extrahieren (Heim- UND Gast-Team)
        wunsch_zeit_min: int | None = None
        for w in heim_w + gast_w:
            if w.kategorie == WunschKategorie.ANSTOSSZEIT and w.uhrzeit:
                parts = w.uhrzeit.replace(":", ".").split(".")
                if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
                    wunsch_zeit_min = int(parts[0]) * 60 + int(parts[1])
                    break

        for dt, dt_type in alt_dates:
            earliest, latest = _time_range(dt)

            # Passt die Spieldauer überhaupt in den Zeitraum?
            if earliest + g.duration > latest + g.duration:
                continue

            # --- Wünsche-Prüfung pro Datum ---
            dt_iso = dt.isoformat()
            sperr_prio = sperrtage.get(dt_iso)

            if sperr_prio == WunschPrio.HART:
                # Harter Sperrtag → Datum komplett ausschließen
                continue

            date_pen = {
                "primary": 0,
                "weekend": _PENALTY_ALT_WEEKEND,
                "weekday": _PENALTY_ALT_WEEKDAY,
            }[dt_type]

            # Weicher Sperrtag → hohe Strafe
            if sperr_prio == WunschPrio.WEICH:
                date_pen += _PENALTY_SPERRTAG

            # Wunschwochentag nicht getroffen → Strafe
            if wunsch_wochentage and dt.weekday() not in wunsch_wochentage:
                date_pen += _PENALTY_WOCHENTAG

            # Option A: Heim-Venue (kein Tausch)
            if g.heim_venue:
                g.options.append(_GameSlot(
                    date=dt,
                    earliest_min=earliest,
                    latest_min=latest,
                    venue=g.heim_venue,
                    venue_raw=g.heim_venue_raw,
                    is_swap=False,
                    penalty=date_pen,
                ))

            # Option B: Gast-Venue (H/A-Tausch)
            if g.gast_venue and g.gast_venue != g.heim_venue:
                g.options.append(_GameSlot(
                    date=dt,
                    earliest_min=earliest,
                    latest_min=latest,
                    venue=g.gast_venue,
                    venue_raw=g.gast_venue_raw,
                    is_swap=True,
                    penalty=date_pen + _PENALTY_SWAP,
                ))

        # Wunsch-Anstoßzeit überschreibt preferred_start
        if wunsch_zeit_min is not None:
            g.preferred_start = wunsch_zeit_min


# ─── 3. CP-SAT Modell ─────────────────────────────────────────

# Zeitdiskretisierung: 15-Minuten-Raster
_SLOT_STEP = 15


def _build_model(model: cp_model.CpModel, games: list[_GameInfo]) -> None:
    """Baut das CP-SAT-Modell mit diskretisierten 15-Min-Slots."""

    # Diskretisierte Einheiten (1 Einheit = 15 Min)
    def to_slot(minutes: int) -> int:
        return minutes // _SLOT_STEP

    def from_slot(slot: int) -> int:
        return slot * _SLOT_STEP

    # --- Variablen pro Spiel ---
    for g in games:
        g_earliest = min(to_slot(opt.earliest_min) for opt in g.options)
        g_latest = max(to_slot(opt.latest_min) for opt in g.options)
        dur_slots = max(1, (g.duration + _SLOT_STEP - 1) // _SLOT_STEP)

        g.start_var = model.new_int_var(g_earliest, g_latest, f"s_{g.gid}")
        g._dur_slots = dur_slots

        g.option_vars = []
        for oi, opt in enumerate(g.options):
            bv = model.new_bool_var(f"o_{g.gid}_{oi}")
            g.option_vars.append(bv)

            model.add(g.start_var >= to_slot(opt.earliest_min)).only_enforce_if(bv)
            model.add(g.start_var <= to_slot(opt.latest_min)).only_enforce_if(bv)

        model.add_exactly_one(g.option_vars)

    # --- Venue-NoOverlap via Cumulative ---
    venue_date_intervals: dict[tuple[str, str], list[tuple]] = defaultdict(list)

    for g in games:
        dur_slots = g._dur_slots
        for oi, opt in enumerate(g.options):
            interval = model.new_optional_fixed_size_interval_var(
                g.start_var,
                dur_slots,
                g.option_vars[oi],
                f"iv_{g.gid}_{oi}",
            )
            demand = 1 if g.halbfeld else 2
            key = (opt.venue, opt.date.isoformat())
            venue_date_intervals[key].append((interval, demand))

    for key, entries in venue_date_intervals.items():
        if len(entries) < 2:
            continue
        intervals = [e[0] for e in entries]
        demands = [e[1] for e in entries]
        model.add_cumulative(intervals, demands, 2)

    # --- Zielfunktion ---
    penalty_terms = []

    for g in games:
        for oi, opt in enumerate(g.options):
            if opt.penalty > 0:
                penalty_terms.append(opt.penalty * g.option_vars[oi])

        # Zeitabweichung in Slots
        pref_slot = to_slot(g.preferred_start)
        g_earliest = min(to_slot(opt.earliest_min) for opt in g.options)
        g_latest = max(to_slot(opt.latest_min) for opt in g.options)
        max_dev = max(abs(g_latest - pref_slot), abs(g_earliest - pref_slot), 1)
        dev = model.new_int_var(0, max_dev, f"d_{g.gid}")
        model.add_abs_equality(dev, g.start_var - pref_slot)
        penalty_terms.append(dev)

    if penalty_terms:
        model.minimize(sum(penalty_terms))


# ─── 4. Lösen & Anwenden ──────────────────────────────────────

def _solve_and_apply(
    model: cp_model.CpModel,
    games: list[_GameInfo],
    time_limit: int,
) -> int:
    """Löst das Modell und schreibt die Ergebnisse zurück in die Spiel-Objekte."""

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit
    solver.parameters.num_workers = 8

    status = solver.solve(model)

    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return 0

    changes = 0

    for g in games:
        # Gewählte Option finden
        chosen_oi = None
        for oi, bv in enumerate(g.option_vars):
            if solver.value(bv):
                chosen_oi = oi
                break

        if chosen_oi is None:
            continue

        opt = g.options[chosen_oi]
        new_start_slot = solver.value(g.start_var)
        new_start = new_start_slot * _SLOT_STEP
        new_time = _format_time(new_start // 60, new_start % 60)

        changed = False

        # Datum aktualisieren (pro Spiel, nicht pro Spieltag)
        if opt.date != g.spiel.datum:
            g.spiel.datum = opt.date
            changed = True

        # Anstoßzeit aktualisieren
        if g.spiel.anstosszeit != new_time:
            g.spiel.anstosszeit = new_time
            changed = True

        # H/A-Tausch
        if opt.is_swap:
            g.spiel.heim, g.spiel.gast = g.spiel.gast, g.spiel.heim
            g.spiel.heim_verein, g.spiel.gast_verein = (
                g.spiel.gast_verein, g.spiel.heim_verein
            )
            g.spiel.spielfeld = opt.venue_raw
            changed = True

        if changed:
            changes += 1

    return changes


# ─── 5. Reparatur-Pass für cross-date Konflikte ───────────────


def _repair_cross_date_conflicts(
    plaene: list[StaffelSpielplan],
    wuensche: dict[str, list[Wunsch]] | None = None,
    time_limit_seconds: int = 30,
) -> int:
    """Zweiter CP-SAT-Pass: löst Konflikte, die durch date-shifting entstanden.

    Nach Pass 1 können Spiele, die auf alternative Tage verschoben wurden,
    mit Spielen kollidieren, die für diesen Tag separat gelöst wurden.
    Dieser Pass gruppiert nach tatsächlichem Datum und re-optimiert nur Gruppen
    mit Konflikten.
    """
    # Baue aktuelle Belegung: (venue, datum) → [games]
    all_games = _collect_games(plaene)
    if not all_games:
        return 0

    # Finde Konflikte auf aktuellem Stand
    belegung: dict[tuple[str, str], list[_GameInfo]] = defaultdict(list)
    for g in all_games:
        if not g.spiel.spielfeld or not g.spiel.datum:
            continue
        venue = g.spiel.spielfeld.strip().lower()
        dt_iso = g.spiel.datum.isoformat()
        belegung[(venue, dt_iso)].append(g)

    # Prüfe welche (venue, datum) Konflikte haben
    conflict_dates: set[date] = set()
    for (venue, dt_iso), games in belegung.items():
        if len(games) < 2:
            continue
        entries = []
        for g in games:
            zeit = _parse_time(g.spiel.anstosszeit)
            start = zeit[0] * 60 + zeit[1] if zeit else 720
            entries.append((start, start + g.duration, g.halbfeld))
        entries.sort()
        for i in range(len(entries)):
            for j in range(i + 1, len(entries)):
                s_i, e_i, hf_i = entries[i]
                s_j, e_j, hf_j = entries[j]
                if s_j < e_i:
                    if hf_i and hf_j and s_i == s_j:
                        continue
                    conflict_dates.add(date.fromisoformat(dt_iso))

    if not conflict_dates:
        return 0

    print(f"[CP-SAT] Reparatur-Pass: {len(conflict_dates)} Datumgruppen mit Konflikten")

    # Sammle alle Spiele an Konflikttagen (nicht nur die kollidierenden)
    conflict_games = [g for g in all_games if g.spiel.datum in conflict_dates]
    _generate_options(conflict_games, wuensche=wuensche)
    conflict_games = [g for g in conflict_games if g.options]

    if not conflict_games:
        return 0

    # Löse global (alle Konflikttage zusammen – sollte klein sein)
    model = cp_model.CpModel()
    _build_model(model, conflict_games)
    changes = _solve_and_apply(model, conflict_games, time_limit_seconds)
    print(f"[CP-SAT] Reparatur: {changes} Spiele angepasst")
    return changes
