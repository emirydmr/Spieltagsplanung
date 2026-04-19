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
    heim_wish_penalty: int = 0  # Wunsch-Strafe nur für Heim-Team
    gast_wish_penalty: int = 0  # Wunsch-Strafe nur für Gast-Team


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
    has_anstosszeit_wish: bool = False
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
_PENALTY_SPERRTAG     = 500  # Spiel auf Sperrtag (hart: verboten, weich: Strafe)
_PENALTY_WOCHENTAG    = 400  # Spiel nicht am Wunschwochentag (pro Team)
_BONUS_WOCHENTAG      = -100 # Bonus für Treffen des Wunschwochentags
_PENALTY_ANSTOSSZEIT  = 200  # Anstoßzeit > 30 min vom Wunsch entfernt
_FAIRNESS_WEIGHT      = 3    # Gewicht zur Minimierung der max. Wunsch-Last pro Team


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

    Löst pro Wochenend-Cluster (Fr+Sa+So derselben KW) separat, damit
    Verschiebungen zwischen Tagen korrekt gegen Venue-Konflikte abgewogen werden.

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

    # Gruppiere nach Wochenend-Cluster (ISO-Woche, damit Fr+Sa+So zusammen sind)
    # Alle Daten die ein Spiel erreichen kann bestimmen den Cluster
    from collections import defaultdict

    def _week_key(dt: date) -> tuple[int, int]:
        """(iso_year, iso_week) – Fr/Sa/So fallen in dieselbe Woche."""
        return dt.isocalendar()[:2]

    by_week: dict[tuple[int, int], list[_GameInfo]] = defaultdict(list)
    for g in all_games:
        # Cluster = die Wochen aller möglichen Optionen des Spiels
        weeks = set()
        for opt in g.options:
            weeks.add(_week_key(opt.date))
        # Spiel der frühesten Woche zuordnen (Primärdatum)
        primary_week = _week_key(g.spiel.datum)
        by_week[primary_week].append(g)

    total_changes = 0
    n_groups = len(by_week)

    print(f"[CP-SAT] {len(all_games)} Spiele in {n_groups} Wochen-Clustern")

    # Zeit pro Cluster proportional zum Gesamt-Limit (größere Cluster = mehr Zeit)
    total_games = len(all_games)
    for i, (wk, games) in enumerate(sorted(by_week.items())):
        # Proportionale Zeitverteilung: größere Cluster bekommen mehr
        cluster_limit = max(10, int(time_limit_seconds * len(games) / max(total_games, 1)))
        cluster_limit = min(cluster_limit, 180)  # Cap bei 180s pro Cluster

        print(f"[CP-SAT] Cluster {i+1}/{n_groups}: building model ({len(games)} games)...", flush=True)
        model = cp_model.CpModel()
        _build_model(model, games)
        changes = _solve_and_apply(model, games, cluster_limit)
        total_changes += changes

        if (i + 1) % 3 == 0 or i == n_groups - 1:
            print(f"[CP-SAT] Cluster {i+1}/{n_groups}: "
                  f"KW {wk[1]}/{wk[0]} ({len(games)} Spiele, {changes} Änd., {cluster_limit}s)")

    # ── Zweiter Pass: Repariere cross-date Konflikte ──────────
    repair_changes = _repair_cross_date_conflicts(plaene, wuensche, time_limit_seconds=60)
    total_changes += repair_changes

    # ── Dritter Pass: Globale Wunsch-Optimierung ──────────────
    wish_changes = _global_wish_optimization(plaene, wuensche, time_limit_seconds=240)
    total_changes += wish_changes

    # ── Vierter Pass: Greedy Per-Game Wunsch-Repair ───────────
    greedy_changes = _greedy_wish_repair(plaene, wuensche)
    total_changes += greedy_changes

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

        # Sperrtage per Team extrahieren: {iso_datum: prio}
        heim_sperrtage: dict[str, WunschPrio] = {}
        gast_sperrtage: dict[str, WunschPrio] = {}
        sperrtage: dict[str, WunschPrio] = {}  # merged (für HART-Ausschluss)
        for w in heim_w:
            if w.kategorie == WunschKategorie.SPERRTAG and w.datum:
                if heim_sperrtage.get(w.datum) != WunschPrio.HART:
                    heim_sperrtage[w.datum] = w.prioritaet
                if sperrtage.get(w.datum) != WunschPrio.HART:
                    sperrtage[w.datum] = w.prioritaet
        for w in gast_w:
            if w.kategorie == WunschKategorie.SPERRTAG and w.datum:
                if gast_sperrtage.get(w.datum) != WunschPrio.HART:
                    gast_sperrtage[w.datum] = w.prioritaet
                if sperrtage.get(w.datum) != WunschPrio.HART:
                    sperrtage[w.datum] = w.prioritaet

        # Wunschwochentage per Team extrahieren
        heim_wochentage: set[int] = set()
        gast_wochentage: set[int] = set()
        wunsch_wochentage: set[int] = set()  # merged (für Alternativtermine)
        for w in heim_w:
            if w.kategorie == WunschKategorie.WOCHENTAG and w.wochentag:
                wd_nr = _WOCHENTAG_MAP.get(w.wochentag.lower())
                if wd_nr is not None:
                    heim_wochentage.add(wd_nr)
                    wunsch_wochentage.add(wd_nr)
        for w in gast_w:
            if w.kategorie == WunschKategorie.WOCHENTAG and w.wochentag:
                wd_nr = _WOCHENTAG_MAP.get(w.wochentag.lower())
                if wd_nr is not None:
                    gast_wochentage.add(wd_nr)
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

            base_pen = {
                "primary": 0,
                "weekend": _PENALTY_ALT_WEEKEND,
                "weekday": _PENALTY_ALT_WEEKDAY,
            }[dt_type]

            # Per-Team Wunsch-Strafen berechnen
            heim_wish_pen = 0
            gast_wish_pen = 0

            # Weicher Sperrtag per Team
            if heim_sperrtage.get(dt_iso) == WunschPrio.WEICH:
                heim_wish_pen += _PENALTY_SPERRTAG
            if gast_sperrtage.get(dt_iso) == WunschPrio.WEICH:
                gast_wish_pen += _PENALTY_SPERRTAG

            # Wunschwochentag per Team (statt merged)
            if heim_wochentage:
                if dt.weekday() not in heim_wochentage:
                    heim_wish_pen += _PENALTY_WOCHENTAG
                else:
                    heim_wish_pen += _BONUS_WOCHENTAG

            if gast_wochentage:
                if dt.weekday() not in gast_wochentage:
                    gast_wish_pen += _PENALTY_WOCHENTAG
                else:
                    gast_wish_pen += _BONUS_WOCHENTAG

            total_pen = base_pen + heim_wish_pen + gast_wish_pen

            # Option A: Heim-Venue (kein Tausch)
            if g.heim_venue:
                g.options.append(_GameSlot(
                    date=dt,
                    earliest_min=earliest,
                    latest_min=latest,
                    venue=g.heim_venue,
                    venue_raw=g.heim_venue_raw,
                    is_swap=False,
                    penalty=total_pen,
                    heim_wish_penalty=heim_wish_pen,
                    gast_wish_penalty=gast_wish_pen,
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
                    penalty=total_pen + _PENALTY_SWAP,
                    heim_wish_penalty=heim_wish_pen,
                    gast_wish_penalty=gast_wish_pen,
                ))

        # Wunsch-Anstoßzeit überschreibt preferred_start
        if wunsch_zeit_min is not None:
            g.preferred_start = wunsch_zeit_min
            g.has_anstosszeit_wish = True


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
            if opt.penalty != 0:
                penalty_terms.append(opt.penalty * g.option_vars[oi])

        # Zeitabweichung in Slots
        pref_slot = to_slot(g.preferred_start)
        g_earliest = min(to_slot(opt.earliest_min) for opt in g.options)
        g_latest = max(to_slot(opt.latest_min) for opt in g.options)
        max_dev = max(abs(g_latest - pref_slot), abs(g_earliest - pref_slot), 1)
        dev = model.new_int_var(0, max_dev, f"d_{g.gid}")
        model.add_abs_equality(dev, g.start_var - pref_slot)
        penalty_terms.append(dev)

        # Anstoßzeit-Wunsch: starke Strafe wenn >30 min Abweichung
        if g.has_anstosszeit_wish and max_dev > 2:
            too_far = model.new_bool_var(f"tf_{g.gid}")
            # too_far=True ↔ Abweichung > 2 Slots (>30 min)
            model.add(dev > 2).only_enforce_if(too_far)
            model.add(dev <= 2).only_enforce_if(too_far.negated())
            penalty_terms.append(_PENALTY_ANSTOSSZEIT * too_far)

    # --- Fairness: minimiere maximale Wunsch-Last pro Team ---
    # Verhindert, dass ein Team alle Wunsch-Verletzungen abbekommt
    team_wish_cost: dict[str, list[tuple[int, object]]] = defaultdict(list)
    n_wish_games = 0
    n_wish_options_good = 0
    n_wish_options_bad = 0
    for g in games:
        has_wish = False
        for oi, opt in enumerate(g.options):
            hw = max(0, opt.heim_wish_penalty)
            gw = max(0, opt.gast_wish_penalty)
            if hw > 0 or gw > 0:
                has_wish = True
                n_wish_options_bad += 1
            elif opt.heim_wish_penalty < 0 or opt.gast_wish_penalty < 0:
                n_wish_options_good += 1
            if hw > 0:
                team_wish_cost[g.spiel.heim].append((hw, g.option_vars[oi]))
            if gw > 0:
                team_wish_cost[g.spiel.gast].append((gw, g.option_vars[oi]))
        if has_wish:
            n_wish_games += 1

    if n_wish_games > 0:
        print(f"[CP-SAT] Wish-Stats: {n_wish_games} games with wishes, "
              f"{n_wish_options_good} good options, {n_wish_options_bad} bad options, "
              f"{len(team_wish_cost)} teams affected", flush=True)

    if team_wish_cost:
        team_sum_vars = []
        team_ubs = []
        for team, entries in team_wish_cost.items():
            ub = sum(pen for pen, _ in entries)
            tv = model.new_int_var(0, ub, f"twp_{abs(hash(team)) % 100000}")
            model.add(tv == sum(pen * bv for pen, bv in entries))
            team_sum_vars.append(tv)
            team_ubs.append(ub)

        if team_sum_vars:
            overall_ub = max(team_ubs)
            max_team = model.new_int_var(0, overall_ub, "max_team_wp")
            for tv in team_sum_vars:
                model.add(max_team >= tv)
            penalty_terms.append(_FAIRNESS_WEIGHT * max_team)

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


# ─── 6. Iterative Wunsch-Verbesserung ─────────────────────────


def _find_wish_violations(
    all_games: list[_GameInfo],
    wuensche: dict[str, list[Wunsch]],
) -> tuple[set[int], list[tuple[str, date]]]:
    """Identifiziert Spiele mit Wunsch-Verletzungen.

    Returns:
        (violation_gids, target_slots) – target_slots sind (venue, ziel_datum)-Paare.
    """
    violation_gids: set[int] = set()
    target_slots: list[tuple[str, date]] = []

    for g in all_games:
        if not g.spiel.datum:
            continue

        heim_w = wuensche.get(g.spiel.heim, [])
        gast_w = wuensche.get(g.spiel.gast, [])

        # Sammle alle gewünschten Wochentage (Heim + Gast)
        all_wished_wds: set[int] = set()
        for w in heim_w + gast_w:
            if w.kategorie == WunschKategorie.WOCHENTAG and w.wochentag:
                wd = _WOCHENTAG_MAP.get(w.wochentag.strip().lower())
                if wd is not None:
                    all_wished_wds.add(wd)

        if all_wished_wds and g.spiel.datum.weekday() not in all_wished_wds:
            # Spiel auf keinem der gewünschten Tage → Verletzung
            ref = g.spieltag.datum if g.spieltag.datum else g.spiel.datum
            erreichbar = False
            for target_wd in all_wished_wds:
                diff = target_wd - ref.weekday()
                if diff > 3:
                    diff -= 7
                elif diff < -3:
                    diff += 7
                if abs(diff) <= 3:
                    erreichbar = True
                    # Ziel-Datum berechnen
                    target_diff = target_wd - g.spiel.datum.weekday()
                    if target_diff > 3:
                        target_diff -= 7
                    elif target_diff < -3:
                        target_diff += 7
                    target_date = g.spiel.datum + timedelta(days=target_diff)
                    if g.heim_venue:
                        target_slots.append((g.heim_venue, target_date))
            if erreichbar:
                violation_gids.add(g.gid)

        for w in heim_w + gast_w:
            if w.kategorie == WunschKategorie.ANSTOSSZEIT and w.uhrzeit:
                parts = w.uhrzeit.replace(":", ".").split(".")
                if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
                    wunsch_min = int(parts[0]) * 60 + int(parts[1])
                else:
                    continue
                zeit = _parse_time(g.spiel.anstosszeit)
                actual_min = zeit[0] * 60 + zeit[1] if zeit else 720
                # Auf Wochentagen ist frühester Anstoß 17:30 – Wünsche vor 17:30
                # sind dort physisch unmöglich und werden nicht als Verletzung gezählt
                if g.spiel.datum.weekday() < 5 and wunsch_min < 17 * 60 + 30:
                    continue
                if abs(actual_min - wunsch_min) > 30:
                    violation_gids.add(g.gid)

    return violation_gids, target_slots


def _iterative_wish_improvement(
    plaene: list[StaffelSpielplan],
    wuensche: dict[str, list[Wunsch]] | None = None,
    iterations: int = 5,
    time_limit_per_iter: int = 60,
) -> int:
    """Legacy – ersetzt durch _global_wish_optimization + _greedy_wish_repair."""
    return 0


def _global_wish_optimization(
    plaene: list[StaffelSpielplan],
    wuensche: dict[str, list[Wunsch]] | None = None,
    time_limit_seconds: int = 120,
) -> int:
    """Globale Wunsch-Optimierung: löst ALLE Wunsch-Verletzungen in einem Modell.

    Statt in kleine Sub-Probleme aufzuteilen (was die globale Sicht bricht),
    wird ein einziges CP-SAT mit allen verletzten Spielen + deren Venue-Nachbarn
    gebaut. Hintergrund-Spiele werden fixiert, Pool-Spiele sind frei.
    """
    if not wuensche:
        return 0

    import time as _time
    t0 = _time.time()
    total_changes = 0

    for iteration in range(3):  # Max 3 Runden
        all_games = _collect_games(plaene)
        if not all_games:
            break

        # 1. Verletzungen identifizieren
        violation_gids, target_slots = _find_wish_violations(all_games, wuensche)
        if not violation_gids:
            print(f"[CP-SAT] Wunsch-Opt {iteration+1}: Keine Verletzungen → fertig")
            break

        games_by_gid = {g.gid: g for g in all_games}

        # 2. Pool = alle verletzten Spiele + alle Spiele an denselben Venues/Weeks
        #    Wir brauchen genug Kontext, damit der Solver verschieben kann.
        def _week_key(dt: date) -> tuple[int, int]:
            return dt.isocalendar()[:2]

        # Index: (venue, week) → {gid}
        venue_week_gids: dict[tuple[str, tuple[int, int]], set[int]] = defaultdict(set)
        for g in all_games:
            if g.spiel.datum and g.heim_venue:
                wk = _week_key(g.spiel.datum)
                venue_week_gids[(g.heim_venue, wk)].add(g.gid)

        # Sammle alle Venue+Week-Keys die berührt werden
        needed_keys: set[tuple[str, tuple[int, int]]] = set()

        # a) Aktuelle Venue+Week der verletzten Spiele
        for gid in violation_gids:
            g = games_by_gid[gid]
            if g.spiel.datum and g.heim_venue:
                needed_keys.add((g.heim_venue, _week_key(g.spiel.datum)))

        # b) Ziel-Venue+Week (wohin die Spiele verschoben werden sollen)
        for venue, target_date in target_slots:
            needed_keys.add((venue, _week_key(target_date)))

        # Sammle alle GIDs in den needed_keys
        pool_gids: set[int] = set()
        for key in needed_keys:
            pool_gids.update(venue_week_gids.get(key, set()))
        pool_gids.update(violation_gids)

        pool = [g for g in all_games if g.gid in pool_gids]
        background = [g for g in all_games if g.gid not in pool_gids]

        # 3. Optionen für Pool-Spiele generieren
        _generate_options(pool, wuensche=wuensche)
        pool = [g for g in pool if g.options]

        # 4. Hintergrund-Spiele fixieren (nur relevante – die an Pool-Venues+Dates)
        pool_venue_dates: set[tuple[str, str]] = set()
        for g in pool:
            for opt in g.options:
                pool_venue_dates.add((opt.venue, opt.date.isoformat()))

        fixed_bg = []
        for g in background:
            if not g.spiel.datum or not g.heim_venue:
                continue
            if (g.heim_venue, g.spiel.datum.isoformat()) not in pool_venue_dates:
                continue
            zeit = _parse_time(g.spiel.anstosszeit)
            start = zeit[0] * 60 + zeit[1] if zeit else 720
            g.options = [_GameSlot(
                date=g.spiel.datum,
                earliest_min=start,
                latest_min=start,
                venue=g.heim_venue,
                venue_raw=g.heim_venue_raw,
                is_swap=False,
                penalty=0,
            )]
            fixed_bg.append(g)

        all_model_games = pool + fixed_bg

        if len(all_model_games) < 2:
            break

        # 5. Einen großen CP-SAT solve
        print(f"[CP-SAT] Wunsch-Opt {iteration+1}: {len(violation_gids)} Verletzungen, "
              f"{len(pool)} Pool + {len(fixed_bg)} fixierte BG = {len(all_model_games)} Spiele",
              flush=True)

        model = cp_model.CpModel()
        _build_model(model, all_model_games)
        changes = _solve_and_apply(model, all_model_games, time_limit_seconds)
        total_changes += changes

        elapsed = _time.time() - t0
        print(f"[CP-SAT] Wunsch-Opt {iteration+1}: {changes} Änd. ({elapsed:.1f}s)", flush=True)

        if changes == 0:
            break

    return total_changes


def _greedy_wish_repair(
    plaene: list[StaffelSpielplan],
    wuensche: dict[str, list[Wunsch]] | None = None,
) -> int:
    """Greedy Per-Game Repair: Versucht jedes noch verletzte Spiel einzeln zu verschieben.

    Für jedes verletzte Spiel:
    1. Berechne Ziel-Datum (gewünschter Wochentag)
    2. Prüfe ob der Slot am Ziel-Datum frei ist (kein Venue-Konflikt)
    3. Falls ja: verschiebe das Spiel
    Falls nein: baue Mini-CP-SAT mit dem Spiel + allen Spielen am Ziel-Venue/-Datum

    Behandelt sowohl WOCHENTAG- als auch ANSTOSSZEIT-Verletzungen.
    """
    if not wuensche:
        return 0

    import time as _time
    t0 = _time.time()

    all_games = _collect_games(plaene)
    if not all_games:
        return 0

    violation_gids, _ = _find_wish_violations(all_games, wuensche)
    if not violation_gids:
        return 0

    # Aktuelle Venue-Belegung bauen
    venue_date_games: dict[tuple[str, str], list[_GameInfo]] = defaultdict(list)
    for g in all_games:
        if g.spiel.datum and g.heim_venue:
            venue_date_games[(g.heim_venue, g.spiel.datum.isoformat())].append(g)

    games_by_gid = {g.gid: g for g in all_games}
    total_changes = 0

    # Sortiere: Spiele mit höchster Wunsch-Dringlichkeit zuerst
    violation_list = sorted(violation_gids)

    for gid in violation_list:
        g = games_by_gid[gid]
        if not g.spiel.datum or not g.heim_venue:
            continue

        # Welchen Wochentag will das Team?
        heim_w = wuensche.get(g.spiel.heim, [])
        gast_w = wuensche.get(g.spiel.gast, [])
        target_wds: set[int] = set()
        for w in heim_w + gast_w:
            if w.kategorie == WunschKategorie.WOCHENTAG and w.wochentag:
                wd = _WOCHENTAG_MAP.get(w.wochentag.strip().lower())
                if wd is not None:
                    target_wds.add(wd)

        # --- WOCHENTAG-Verletzung: Spiel auf anderen Tag verschieben ---
        wochentag_fixed = False
        if target_wds and g.spiel.datum.weekday() not in target_wds:
            for target_wd in target_wds:
                diff = target_wd - g.spiel.datum.weekday()
                if diff > 3:
                    diff -= 7
                elif diff < -3:
                    diff += 7
                target_date = g.spiel.datum + timedelta(days=diff)

                earliest, latest = _time_range(target_date)
                if earliest > latest:
                    continue

                # Prüfe Venue-Belegung am Ziel-Datum
                target_key = (g.heim_venue, target_date.isoformat())
                blocking_games = venue_date_games.get(target_key, [])

                mini_games = [g]
                for bg in blocking_games:
                    if bg.gid != g.gid:
                        mini_games.append(bg)

                g.options = [_GameSlot(
                    date=target_date,
                    earliest_min=earliest,
                    latest_min=latest,
                    venue=g.heim_venue,
                    venue_raw=g.heim_venue_raw,
                    is_swap=False,
                    penalty=0,
                )]

                for bg in blocking_games:
                    if bg.gid == g.gid:
                        continue
                    zeit = _parse_time(bg.spiel.anstosszeit)
                    start = zeit[0] * 60 + zeit[1] if zeit else 720
                    bg.options = [_GameSlot(
                        date=bg.spiel.datum,
                        earliest_min=start,
                        latest_min=start,
                        venue=bg.heim_venue,
                        venue_raw=bg.heim_venue_raw,
                        is_swap=False,
                        penalty=0,
                    )]

                model = cp_model.CpModel()
                _build_model(model, mini_games)
                changes = _solve_and_apply(model, mini_games, 5)

                if changes > 0:
                    total_changes += changes
                    old_key = (g.heim_venue, g.spiel.datum.isoformat())
                    if g in venue_date_games.get(old_key, []):
                        venue_date_games[old_key].remove(g)
                    venue_date_games[target_key].append(g)
                    wochentag_fixed = True
                    break

        if wochentag_fixed:
            continue

        # --- ANSTOSSZEIT-Verletzung: Zeitslots am selben Venue/Datum umordnen ---
        wunsch_zeit_min: int | None = None
        for w in heim_w + gast_w:
            if w.kategorie == WunschKategorie.ANSTOSSZEIT and w.uhrzeit:
                parts = w.uhrzeit.replace(":", ".").split(".")
                if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
                    wunsch_zeit_min = int(parts[0]) * 60 + int(parts[1])
                    break

        if wunsch_zeit_min is None:
            continue

        # Auf Wochentagen: Wunsch vor 17:30 ist physisch unmöglich
        if g.spiel.datum.weekday() < 5 and wunsch_zeit_min < 17 * 60 + 30:
            continue

        zeit = _parse_time(g.spiel.anstosszeit)
        actual_min = zeit[0] * 60 + zeit[1] if zeit else 720
        if abs(actual_min - wunsch_zeit_min) <= 30:
            continue  # Schon nah genug

        # Baue Mini-CP-SAT mit allen Spielen am selben Venue + Datum
        current_key = (g.heim_venue, g.spiel.datum.isoformat())
        same_slot_games = venue_date_games.get(current_key, [])

        mini_games = []
        earliest, latest = _time_range(g.spiel.datum)
        for sg in same_slot_games:
            sg.has_anstosszeit_wish = False  # Reset
            sg.options = [_GameSlot(
                date=sg.spiel.datum,
                earliest_min=earliest,
                latest_min=latest,
                venue=sg.heim_venue,
                venue_raw=sg.heim_venue_raw,
                is_swap=False,
                penalty=0,
            )]
            # Wunsch-Anstoßzeit setzen
            sg_heim_w = wuensche.get(sg.spiel.heim, [])
            sg_gast_w = wuensche.get(sg.spiel.gast, [])
            for w in sg_heim_w + sg_gast_w:
                if w.kategorie == WunschKategorie.ANSTOSSZEIT and w.uhrzeit:
                    parts = w.uhrzeit.replace(":", ".").split(".")
                    if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
                        sg.preferred_start = int(parts[0]) * 60 + int(parts[1])
                        sg.has_anstosszeit_wish = True
                        break
            mini_games.append(sg)

        if len(mini_games) < 2:
            # Nur ein Spiel am Slot – einfach direkt verschieben
            g.spiel.anstosszeit = _format_time(wunsch_zeit_min // 60, wunsch_zeit_min % 60)
            total_changes += 1
            continue

        model = cp_model.CpModel()
        _build_model(model, mini_games)
        changes = _solve_and_apply(model, mini_games, 5)
        if changes > 0:
            total_changes += changes

    if total_changes > 0:
        print(f"[CP-SAT] Greedy Repair: {total_changes} Spiele angepasst ({_time.time()-t0:.1f}s)",
              flush=True)

    return total_changes
