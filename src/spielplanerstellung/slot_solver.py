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

def _get_alternative_dates(primary: date) -> list[tuple[date, str]]:
    """Gibt alternative Spieltage in derselben KW zurück.

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


# ─── Solver ────────────────────────────────────────────────────

def solve_game_slots(
    plaene: list[StaffelSpielplan],
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

    _generate_options(all_games)

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

def _generate_options(games: list[_GameInfo]) -> None:
    """Erzeugt für jedes Spiel die möglichen (Datum, Venue, Zeitbereich)-Kandidaten."""
    for g in games:
        primary_date = g.spiel.datum
        alt_dates = _get_alternative_dates(primary_date)

        for dt, dt_type in alt_dates:
            earliest, latest = _time_range(dt)

            # Passt die Spieldauer überhaupt in den Zeitraum?
            if earliest + g.duration > latest + g.duration:
                continue

            date_pen = {
                "primary": 0,
                "weekend": _PENALTY_ALT_WEEKEND,
                "weekday": _PENALTY_ALT_WEEKDAY,
            }[dt_type]

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
