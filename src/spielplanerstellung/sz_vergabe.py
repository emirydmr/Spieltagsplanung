"""Schlüsselzahlen-Vergabe: Optimale Zuordnung von Teams zu SZ-Nummern.

Jedes Team in einer Staffel bekommt eine Schlüsselzahl (SZ).
Die SZ bestimmt über den Schlüsselplan das gesamte Heim/Auswärts-Muster.

Die Zuordnung wird optimiert nach:
  1. Heim/Auswärts-Gleichverteilung
  2. Faire Auswärtskilometer-Verteilung
  3. Vereinswünsche (Sperrtage, Heimwünsche, Platzsharing)
  4. Jüngere AK spielen früher als ältere am gleichen Tag (weich)
"""

import itertools
import random
from dataclasses import dataclass, field

from src.spielplanerstellung.schluesselplan import (
    get_schluesselplan, get_paarungen_pro_spieltag, get_n_spieltage,
)
from src.spielplanerstellung.wuensche import Wunsch, WunschKategorie, WunschPrio
from src.common.distanz import haversine_km


@dataclass
class SZZuordnung:
    """Ergebnis: Team → Schlüsselzahl Zuordnung."""
    mannschaft: str
    verein: str
    sz: int
    region: str = ""
    lat: float | None = None
    lon: float | None = None


@dataclass
class SpielplanScore:
    """Score für eine Schlüsselzahlen-Zuordnung."""
    total: float = 0.0
    heim_balance: float = 0.0       # Wie gleichmäßig Heim verteilt ist
    distanz_fairness: float = 0.0   # Wie fair Auswärtskm verteilt sind
    wunsch_verletzungen: int = 0    # Anzahl verletzter Wünsche
    platz_konflikte: int = 0        # Doppelbelegungen am gleichen Tag

    def berechne_total(self) -> float:
        self.total = (
            self.heim_balance * 10.0
            + self.distanz_fairness * 1.0
            + self.wunsch_verletzungen * 100.0
            + self.platz_konflikte * 500.0
        )
        return self.total


def _score_zuordnung(
    teams: list[dict],
    sz_mapping: dict[int, dict],  # {sz: team_dict}
    staffelgroesse: int,
    wuensche: dict[str, list[Wunsch]] | None = None,
    platz_belegung: dict[str, list[tuple[str, int]]] | None = None,
) -> SpielplanScore:
    """Bewertet eine SZ-Zuordnung.

    Args:
        teams: Liste der Team-Dicts
        sz_mapping: {sz_nummer: team_dict}
        staffelgroesse: Staffelgröße (für Schlüsselplan)
        wuensche: {mannschaftsname: [Wunsch, ...]}
        platz_belegung: {adresse: [(mannschaft, sz), ...]} für Platzsharing
    """
    score = SpielplanScore()
    paarungen = get_paarungen_pro_spieltag(staffelgroesse)
    n_spieltage = len(paarungen)

    # ── 1. Heim/Auswärts-Balance ──
    # Zähle Heimspiele pro Team
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

    # Ideale Verteilung: jedes Team ~gleich viele Heim/Auswärts
    if heim_counts:
        vals = list(heim_counts.values())
        avg = sum(vals) / len(vals) if vals else 0
        score.heim_balance = sum((v - avg) ** 2 for v in vals)

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
                # Auswärtsteam fährt die Strecke
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
                if w.kategorie == WunschKategorie.SPERRTAG and w.datum:
                    # Check if team has a home game on blocked date
                    # (simplified: any game on that date is bad)
                    for st, matches in paarungen.items():
                        for h, g in matches:
                            if (h == sz or g == sz):
                                penalty = 2 if w.prioritaet == WunschPrio.HART else 1
                                score.wunsch_verletzungen += penalty

    # ── 4. Platz-Konflikte ──
    if platz_belegung:
        for adresse, belegungen in platz_belegung.items():
            # Check: gleicher Spieltag, gleicher Platz → Konflikt
            for spieltag, matches in paarungen.items():
                heim_at_platz = []
                for h_sz, g_sz in matches:
                    h_team = sz_mapping.get(h_sz)
                    if h_team and h_team.get("adresse", "").lower() == adresse.lower():
                        heim_at_platz.append(h_team["mannschaft"])
                if len(heim_at_platz) > 1:
                    score.platz_konflikte += len(heim_at_platz) - 1

    score.berechne_total()
    return score


def vergebe_schluesselzahlen(
    teams: list[dict],
    staffelgroesse: int,
    wuensche: dict[str, list[Wunsch]] | None = None,
    platz_belegung: dict[str, list[tuple[str, int]]] | None = None,
    max_permutations: int = 50_000,
) -> tuple[list[SZZuordnung], SpielplanScore]:
    """Findet die optimale SZ-Zuordnung für eine Staffel.

    Für kleine Staffeln (≤8): probiert alle Permutationen.
    Für größere: verwendet Zufallsoptimierung.

    Args:
        teams: Liste von Team-Dicts (mannschaft, verein, region, lat, lon, adresse)
        staffelgroesse: Größe der Staffel
        wuensche: Optional: Wünsche pro Mannschaft
        platz_belegung: Optional: Platzbelegungsinfo
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
            score = _score_zuordnung(teams, mapping, staffelgroesse, wuensche, platz_belegung)
            if best_score is None or score.total < best_score.total:
                best_score = score
                best_mapping = mapping.copy()
    else:
        # Zufallsoptimierung mit Swap-Hill-Climbing
        current_perm = list(available_sz)
        random.shuffle(current_perm)
        current_mapping = {current_perm[i]: teams[i] for i in range(n)}
        current_score = _score_zuordnung(teams, current_mapping, staffelgroesse, wuensche, platz_belegung)
        best_score = current_score
        best_mapping = current_mapping.copy()

        no_improve = 0
        for _ in range(max_permutations):
            # Random swap
            i, j = random.sample(range(n), 2)
            new_perm = list(current_perm)
            new_perm[i], new_perm[j] = new_perm[j], new_perm[i]
            new_mapping = {new_perm[k]: teams[k] for k in range(n)}
            new_score = _score_zuordnung(teams, new_mapping, staffelgroesse, wuensche, platz_belegung)

            if new_score.total < current_score.total:
                current_perm = new_perm
                current_mapping = new_mapping
                current_score = new_score
                no_improve = 0
                if new_score.total < best_score.total:
                    best_score = new_score
                    best_mapping = new_mapping.copy()
            else:
                no_improve += 1
                if no_improve > n * 100:
                    # Restart
                    random.shuffle(current_perm)
                    current_mapping = {current_perm[k]: teams[k] for k in range(n)}
                    current_score = _score_zuordnung(teams, current_mapping, staffelgroesse, wuensche, platz_belegung)
                    no_improve = 0

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
        ))

    return zuordnungen, best_score
