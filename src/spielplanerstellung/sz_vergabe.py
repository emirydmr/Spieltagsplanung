"""Schlüsselzahlen-Vergabe: Optimale Zuordnung von Teams zu SZ-Nummern.

Jedes Team in einer Staffel bekommt eine Schlüsselzahl (SZ).
Die SZ bestimmt über den Schlüsselplan das gesamte Heim/Auswärts-Muster.

Die Zuordnung wird optimiert nach:
  1. Heim/Auswärts-Gleichverteilung + keine langen Heim-/Auswärts-Serien
  2. Faire Auswärtskilometer-Verteilung
  3. Vereinswünsche (Sperrtage, Heimwünsche, Platzsharing)
  4. Miniminierung von Spielfeld-Doppelbelegungen

Algorithmus:
  - Kleine Staffeln (≤7 Teams): Exakte Lösung (alle Permutationen)
  - Größere: Simulated Annealing mit Multi-Start
"""

import itertools
import math
import random
from dataclasses import dataclass, field
from datetime import date

from src.spielplanerstellung.schluesselplan import (
    get_schluesselplan, get_paarungen_pro_spieltag, get_n_spieltage,
)
from src.spielplanerstellung.wuensche import Wunsch, WunschKategorie, WunschPrio
from src.common.distanz import haversine_km


# Wochentag-Name → date.weekday() (Montag=0 ... Sonntag=6)
WOCHENTAG_MAP = {
    "montag": 0, "dienstag": 1, "mittwoch": 2, "donnerstag": 3,
    "freitag": 4, "samstag": 5, "sonntag": 6,
    "mo": 0, "di": 1, "mi": 2, "do": 3, "fr": 4, "sa": 5, "so": 6,
}


@dataclass
class SZZuordnung:
    """Ergebnis: Team → Schlüsselzahl Zuordnung."""
    mannschaft: str
    verein: str
    sz: int
    region: str = ""
    lat: float | None = None
    lon: float | None = None
    adresse: str = ""


@dataclass
class SpielplanScore:
    """Score für eine Schlüsselzahlen-Zuordnung."""
    total: float = 0.0
    heim_balance: float = 0.0       # Wie gleichmäßig Heim verteilt ist
    consecutive_penalty: float = 0.0 # Aufeinanderfolgende Heim-/Auswärtsspiele
    distanz_fairness: float = 0.0   # Wie fair Auswärtskm verteilt sind
    wunsch_verletzungen: int = 0    # Anzahl verletzter Wünsche
    platz_konflikte: int = 0        # Doppelbelegungen am gleichen Tag
    wunsch_details: list = field(default_factory=list)  # Details pro Verletzung
    platz_konflikt_details: list = field(default_factory=list)  # Details pro Konflikt

    def berechne_total(self) -> float:
        self.total = (
            self.heim_balance * 10.0
            + self.consecutive_penalty * 25.0
            + self.distanz_fairness * 1.0
            + self.wunsch_verletzungen * 100.0
            + self.platz_konflikte * 50.0
        )
        return self.total


def _score_zuordnung(
    teams: list[dict],
    sz_mapping: dict[int, dict],  # {sz: team_dict}
    staffelgroesse: int,
    wuensche: dict[str, list[Wunsch]] | None = None,
    spieltag_dates: dict[int, date] | None = None,
) -> SpielplanScore:
    """Bewertet eine SZ-Zuordnung.

    Args:
        teams: Liste der Team-Dicts
        sz_mapping: {sz_nummer: team_dict}
        staffelgroesse: Staffelgröße (für Schlüsselplan)
        wuensche: {mannschaftsname: [Wunsch, ...]}
        spieltag_dates: {spieltag_nr: datum} für datumbasierte Wunsch-Prüfung
    """
    score = SpielplanScore()
    paarungen = get_paarungen_pro_spieltag(staffelgroesse)
    sorted_spieltage = sorted(paarungen.keys())

    # ── Pre-compute: Team-Rolle pro Spieltag ──
    # {spieltag_nr: {sz: "heim"|"gast"|"frei"}}
    team_rolle: dict[int, dict[int, str]] = {}
    for spieltag, matches in paarungen.items():
        team_rolle[spieltag] = {}
        for h_sz, g_sz in matches:
            team_rolle[spieltag][h_sz] = "heim"
            team_rolle[spieltag][g_sz] = "gast"

    # ── 1. Heim/Auswärts-Balance ──
    heim_counts: dict[str, int] = {t["mannschaft"]: 0 for t in teams}
    ausw_counts: dict[str, int] = {t["mannschaft"]: 0 for t in teams}

    for spieltag, matches in paarungen.items():
        for h_sz, g_sz in matches:
            h_team = sz_mapping.get(h_sz)
            g_team = sz_mapping.get(g_sz)
            if h_team:
                heim_counts[h_team["mannschaft"]] = heim_counts.get(h_team["mannschaft"], 0) + 1
            if g_team:
                ausw_counts[g_team["mannschaft"]] = ausw_counts.get(g_team["mannschaft"], 0) + 1

    if heim_counts:
        vals = list(heim_counts.values())
        avg = sum(vals) / len(vals) if vals else 0
        score.heim_balance = sum((v - avg) ** 2 for v in vals)

    # ── 1b. Consecutive Home/Away penalty ──
    # 3+ Heim- oder Auswärtsspiele hintereinander sind unerwünscht
    for sz, team in sz_mapping.items():
        consecutive = 0
        last_role = None
        for st_nr in sorted_spieltage:
            rolle = team_rolle.get(st_nr, {}).get(sz)
            if rolle is None:
                # spielfrei unterbricht Serien
                last_role = None
                consecutive = 0
                continue
            if rolle == last_role:
                consecutive += 1
                if consecutive >= 2:  # 3+ gleiche Rolle
                    score.consecutive_penalty += (consecutive - 1)
            else:
                consecutive = 0
            last_role = rolle

    # ── 2. Auswärtskilometer-Fairness ──
    ausw_km: dict[str, float] = {t["mannschaft"]: 0.0 for t in teams}
    for spieltag, matches in paarungen.items():
        for h_sz, g_sz in matches:
            h_team = sz_mapping.get(h_sz)
            g_team = sz_mapping.get(g_sz)
            if not h_team or not g_team:
                continue
            h_lat = h_team.get("lat")
            g_lat = g_team.get("lat")
            if h_lat is not None and g_lat is not None:
                d = haversine_km(h_lat, h_team["lon"], g_lat, g_team["lon"])
                ausw_km[g_team["mannschaft"]] = ausw_km.get(g_team["mannschaft"], 0) + d

    if ausw_km:
        vals = list(ausw_km.values())
        avg = sum(vals) / len(vals) if vals else 0
        score.distanz_fairness = sum((v - avg) ** 2 for v in vals) ** 0.5

    # ── 3. Wünsche ──
    if wuensche:
        for sz, team in sz_mapping.items():
            m_name = team["mannschaft"]
            team_w = wuensche.get(m_name, [])
            for w in team_w:
                penalty = 2 if w.prioritaet == WunschPrio.HART else 1

                if w.kategorie == WunschKategorie.SPERRTAG:
                    score.wunsch_verletzungen += _check_sperrtag(
                        w, sz, paarungen, spieltag_dates, penalty)

                elif w.kategorie == WunschKategorie.HEIMWUNSCH:
                    score.wunsch_verletzungen += _check_heimwunsch(
                        w, sz, paarungen, team_rolle, spieltag_dates, penalty, want_heim=True)

                elif w.kategorie == WunschKategorie.AUSWAERTSWUNSCH:
                    score.wunsch_verletzungen += _check_heimwunsch(
                        w, sz, paarungen, team_rolle, spieltag_dates, penalty, want_heim=False)

                elif w.kategorie == WunschKategorie.WOCHENTAG:
                    score.wunsch_verletzungen += _check_wochentag(
                        w, sz, paarungen, team_rolle, spieltag_dates, penalty)

    # ── 4. Platz-Konflikte (gleichzeitig Heim am selben Ort) ──
    # 2 am gleichen Ort → leicht lösbar (gestaffelte Zeiten)
    # 3+ → immer schwieriger, daher exponentiell
    for spieltag, matches in paarungen.items():
        heim_at_platz: dict[str, list[str]] = {}
        for h_sz, g_sz in matches:
            h_team = sz_mapping.get(h_sz)
            if h_team:
                addr = h_team.get("adresse", "").strip().lower()
                if addr:
                    heim_at_platz.setdefault(addr, []).append(h_team["mannschaft"])
        for addr, teams_at in heim_at_platz.items():
            extra = len(teams_at) - 1
            if extra >= 1:
                # 2 = 1 conflict, 3 = 3 conflicts, 4 = 6 etc. (triangular)
                score.platz_konflikte += extra * (extra + 1) // 2

    score.berechne_total()
    return score


def _check_sperrtag(
    w: Wunsch, sz: int,
    paarungen: dict, spieltag_dates: dict[int, date] | None,
    penalty: int,
) -> int:
    """Prüft ob Team an einem Sperrtag spielen muss."""
    if not spieltag_dates or not w.datum:
        return 0
    try:
        sperr_date = date.fromisoformat(w.datum)
    except (ValueError, TypeError):
        return 0
    for st_nr, dt in spieltag_dates.items():
        if dt == sperr_date:
            # Spielt das Team an diesem Spieltag?
            if st_nr in paarungen:
                for h, g in paarungen[st_nr]:
                    if h == sz or g == sz:
                        return penalty
    return 0


def _check_heimwunsch(
    w: Wunsch, sz: int,
    paarungen: dict, team_rolle: dict,
    spieltag_dates: dict[int, date] | None,
    penalty: int, want_heim: bool,
) -> int:
    """Prüft ob Team am gewünschten Datum Heim/Auswärts hat."""
    if not spieltag_dates or not w.datum:
        return 0
    try:
        wunsch_date = date.fromisoformat(w.datum)
    except (ValueError, TypeError):
        return 0
    for st_nr, dt in spieltag_dates.items():
        if dt == wunsch_date:
            rolle = team_rolle.get(st_nr, {}).get(sz)
            if rolle is None:
                return 0  # spielfrei → kein Verstoß
            if want_heim and rolle != "heim":
                return penalty
            if not want_heim and rolle != "gast":
                return penalty
    return 0


def _check_wochentag(
    w: Wunsch, sz: int,
    paarungen: dict, team_rolle: dict,
    spieltag_dates: dict[int, date] | None,
    penalty: int,
) -> int:
    """Prüft ob Spieltage am bevorzugten Wochentag liegen."""
    if not spieltag_dates or not w.wochentag:
        return 0
    gewuenscht = WOCHENTAG_MAP.get(w.wochentag.strip().lower())
    if gewuenscht is None:
        return 0
    violations = 0
    for st_nr, dt in spieltag_dates.items():
        # Team spielt an diesem Spieltag?
        rolle = team_rolle.get(st_nr, {}).get(sz)
        if rolle is None:
            continue
        if dt.weekday() != gewuenscht:
            violations += penalty
    return violations


def vergebe_schluesselzahlen(
    teams: list[dict],
    staffelgroesse: int,
    wuensche: dict[str, list[Wunsch]] | None = None,
    spieltag_dates: dict[int, date] | None = None,
    max_permutations: int = 5_040,  # 7! = 5040 → Brute-Force bis 7 Teams
) -> tuple[list[SZZuordnung], SpielplanScore]:
    """Findet die optimale SZ-Zuordnung für eine Staffel.

    Algorithmus:
      - Kleine Staffeln (≤7 Teams): Exakte Lösung (alle Permutationen)
      - Größere: Simulated Annealing mit Multi-Start
        - Temperatur sinkt exponentiell, erlaubt anfangs schlechtere Lösungen
        - Mehrere unabhängige Starts → beste Lösung gewinnt

    Args:
        teams: Liste von Team-Dicts (mannschaft, verein, region, lat, lon, adresse)
        staffelgroesse: Größe der Staffel
        wuensche: Optional: Wünsche pro Mannschaft
        spieltag_dates: Optional: {spieltag_nr: datum} für datumsbasierte Wunsch-Prüfung
        max_permutations: Max. Permutationen für Brute-Force

    Returns:
        (zuordnungen, score)
    """
    n = len(teams)

    # Verfügbare SZ: für ungerade Staffeln ist SZ 1 = spielfrei
    if n % 2 != 0:
        available_sz = list(range(2, n + 2))  # z.B. 5 Teams → SZ 2-6
    else:
        available_sz = list(range(1, n + 1))  # z.B. 8 Teams → SZ 1-8

    n_perms = 1
    for i in range(1, n + 1):
        n_perms *= i

    best_score: SpielplanScore | None = None
    best_mapping: dict[int, dict] | None = None

    if n_perms <= max_permutations:
        # Brute force: alle Permutationen
        for perm in itertools.permutations(available_sz):
            mapping = {perm[i]: teams[i] for i in range(n)}
            score = _score_zuordnung(teams, mapping, staffelgroesse, wuensche, spieltag_dates)
            if best_score is None or score.total < best_score.total:
                best_score = score
                best_mapping = mapping.copy()
    else:
        # Simulated Annealing with Multi-Start
        n_restarts = max(3, min(8, 40_000 // (n * 500)))
        iters_per_run = min(8_000, n * 800)
        t_start = 500.0
        t_end = 0.1

        for _run in range(n_restarts):
            current_perm = list(available_sz)
            random.shuffle(current_perm)
            current_mapping = {current_perm[i]: teams[i] for i in range(n)}
            current_score = _score_zuordnung(teams, current_mapping, staffelgroesse, wuensche, spieltag_dates)

            run_best_score = current_score
            run_best_mapping = current_mapping.copy()

            for step in range(iters_per_run):
                # Temperature: exponential cooling
                t = t_start * ((t_end / t_start) ** (step / max(1, iters_per_run - 1)))

                # Neighborhood: swap two random SZ assignments
                i, j = random.sample(range(n), 2)
                new_perm = list(current_perm)
                new_perm[i], new_perm[j] = new_perm[j], new_perm[i]
                new_mapping = {new_perm[k]: teams[k] for k in range(n)}
                new_score = _score_zuordnung(teams, new_mapping, staffelgroesse, wuensche, spieltag_dates)

                delta = new_score.total - current_score.total

                # Accept better solutions always; worse with probability e^(-delta/T)
                if delta < 0 or random.random() < math.exp(-delta / max(t, 1e-10)):
                    current_perm = new_perm
                    current_mapping = new_mapping
                    current_score = new_score

                    if current_score.total < run_best_score.total:
                        run_best_score = current_score
                        run_best_mapping = current_mapping.copy()

            # Keep global best across all restarts
            if best_score is None or run_best_score.total < best_score.total:
                best_score = run_best_score
                best_mapping = run_best_mapping.copy()

    # Convert best mapping to SZZuordnung list
    zuordnungen = []
    for sz, team in sorted(best_mapping.items()):
        zuordnungen.append(SZZuordnung(
            mannschaft=team["mannschaft"],
            verein=team.get("verein", ""),
            sz=sz,
            region=team.get("region", ""),
            lat=team.get("lat"),
            lon=team.get("lon"),
            adresse=team.get("adresse", ""),
        ))

    return zuordnungen, best_score
