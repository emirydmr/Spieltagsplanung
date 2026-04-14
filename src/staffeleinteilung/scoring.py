"""Score-Berechnung für die Staffeleinteilung.

Score-Formel:
    TOTAL = w_distanz * distanz_score
          + w_region  * region_score
          + w_balance * balance_score
          + PENALTY   * constraint_violations

    Niedriger Score = bessere Einteilung.

Scores:
    - distanz_score:  Durchschnittliche paarweise Luftliniendistanz (km) aller
                      Mannschaften innerhalb einer Staffel, gemittelt über alle Staffeln.
    - region_score:   Anzahl der Mannschaften pro Staffel, die in der "falschen"
                      Region sind (= nicht die Mehrheitsregion der Staffel).
    - balance_score:  Standardabweichung der Staffelgrößen (0 = perfekt gleich groß).

Hard Constraints (Penalty = 10000):
    - Gleicher Verein doppelt in einer Staffel
    - Hohenlohe Süd (SHA/CR) mit Unterland gemischt (bei Topf 2 A/B/C-Junioren)
    - Staffelgröße außerhalb des erlaubten Bereichs
"""

import math
from dataclasses import dataclass

from src.common.models import Mannschaft, Staffel
from src.common.distanz import haversine_km

PENALTY = 10_000  # Hard-Constraint-Verletzung


@dataclass
class ScoreGewichte:
    """Gewichtung der einzelnen Score-Komponenten."""
    w_distanz: float = 1.0    # Fahrdistanz (km) - Hauptkriterium
    w_region: float = 50.0    # Regionale Fehlzuordnung
    w_balance: float = 20.0   # Staffelgrößen-Balance
    min_staffel_size: int = 5
    max_staffel_size: int = 11


@dataclass
class ScoreDetail:
    """Detaillierter Score-Breakdown für eine Einteilung."""
    distanz_score: float = 0.0
    region_score: float = 0.0
    balance_score: float = 0.0
    hard_violations: int = 0
    violation_details: list[str] | None = None
    total: float = 0.0

    def __str__(self) -> str:
        parts = [
            f"Total: {self.total:.1f}",
            f"  Distanz: {self.distanz_score:.1f} km (avg paarweise)",
            f"  Region: {self.region_score:.0f} Fehlzuordnungen",
            f"  Balance: {self.balance_score:.2f} (Stdabw Staffelgrößen)",
            f"  Hard Violations: {self.hard_violations}",
        ]
        if self.violation_details:
            for v in self.violation_details[:10]:
                parts.append(f"    - {v}")
        return "\n".join(parts)


def _avg_paarweise_distanz(mannschaften: list[Mannschaft]) -> float:
    """Berechnet die durchschnittliche paarweise Distanz in einer Staffel."""
    teams_mit_coords = [
        m for m in mannschaften
        if m.spielstaette and m.spielstaette.lat is not None
    ]
    n = len(teams_mit_coords)
    if n < 2:
        return 0.0

    total = 0.0
    paare = 0
    for i in range(n):
        for j in range(i + 1, n):
            a = teams_mit_coords[i].spielstaette
            b = teams_mit_coords[j].spielstaette
            total += haversine_km(a.lat, a.lon, b.lat, b.lon)
            paare += 1

    return total / paare if paare > 0 else 0.0


def _mehrheits_region(mannschaften: list[Mannschaft]) -> str:
    """Gibt die häufigste Region (bezirk_alt) in der Staffel zurück."""
    regionen: dict[str, int] = {}
    for m in mannschaften:
        r = m.bezirk_alt or "Unbekannt"
        regionen[r] = regionen.get(r, 0) + 1
    return max(regionen, key=regionen.get) if regionen else "Unbekannt"


def _region_violations(staffel: list[Mannschaft]) -> int:
    """Zählt Mannschaften die nicht zur Mehrheitsregion gehören."""
    if not staffel:
        return 0
    mehrheit = _mehrheits_region(staffel)
    return sum(1 for m in staffel if (m.bezirk_alt or "Unbekannt") != mehrheit)


def _check_hard_constraints(
    staffeln: list[list[Mannschaft]],
    gewichte: ScoreGewichte,
) -> tuple[int, list[str]]:
    """Prüft Hard Constraints und gibt die Anzahl der Verletzungen zurück."""
    violations = 0
    details = []

    for idx, staffel in enumerate(staffeln):
        # HC-4: Keine zwei Mannschaften desselben Vereins im gleichen Topf
        vereine: dict[str, list[str]] = {}
        for m in staffel:
            if m.verein_nr not in vereine:
                vereine[m.verein_nr] = []
            vereine[m.verein_nr].append(m.mannschaftsname)
        for vnr, names in vereine.items():
            if len(names) > 1:
                violations += len(names) - 1
                details.append(
                    f"Staffel {idx+1}: Verein {vnr} hat {len(names)} Mannschaften: {names}"
                )

        # HC-5: Hohenlohe Süd nicht mit Unterland
        has_unterland = any(m.bezirk_alt == "Unterland" for m in staffel)
        has_hohenlohe_sued = any(
            m.bezirk_alt == "Hohenlohe" and m.region and "SHA" in m.region.upper()
            for m in staffel
        )
        # Einfachere Erkennung: Bezirk neu == 12 ist SHA/CR-Bereich
        # Oder SRG enthält "Schwäbisch Hall" / "Crailsheim"
        # Für jetzt: check über region-feld
        if has_unterland and has_hohenlohe_sued:
            violations += 1
            details.append(f"Staffel {idx+1}: Unterland mit Hohenlohe Süd gemischt")

        # HC-1: Staffelgröße im Bereich
        # Bei nur einer Staffel und zu wenig Teams insgesamt -> unvermeidbar, keine Violation
        total_teams = sum(len(s) for s in staffeln)
        size = len(staffel)
        if size < gewichte.min_staffel_size and not (len(staffeln) == 1 and total_teams < gewichte.min_staffel_size):
            violations += 1
            details.append(f"Staffel {idx+1}: Zu klein ({size} < {gewichte.min_staffel_size})")
        if size > gewichte.max_staffel_size:
            violations += 1
            details.append(f"Staffel {idx+1}: Zu groß ({size} > {gewichte.max_staffel_size})")

    return violations, details


def berechne_score(
    staffeln: list[list[Mannschaft]],
    gewichte: ScoreGewichte | None = None,
) -> ScoreDetail:
    """Berechnet den Gesamtscore einer Staffeleinteilung.

    Args:
        staffeln: Liste von Listen von Mannschaften (jede innere Liste = eine Staffel)
        gewichte: Score-Gewichtung (default: Standardgewichte)

    Returns:
        ScoreDetail mit Breakdown aller Komponenten
    """
    if gewichte is None:
        gewichte = ScoreGewichte()

    detail = ScoreDetail(violation_details=[])

    if not staffeln:
        return detail

    # Distanz-Score: Durchschnitt der avg. paarweisen Distanzen aller Staffeln
    distanz_scores = [_avg_paarweise_distanz(s) for s in staffeln]
    detail.distanz_score = sum(distanz_scores) / len(distanz_scores) if distanz_scores else 0.0

    # Region-Score: Summe aller Fehlzuordnungen
    detail.region_score = sum(_region_violations(s) for s in staffeln)

    # Balance-Score: Standardabweichung der Staffelgrößen
    sizes = [len(s) for s in staffeln]
    if len(sizes) > 1:
        avg_size = sum(sizes) / len(sizes)
        variance = sum((s - avg_size) ** 2 for s in sizes) / len(sizes)
        detail.balance_score = math.sqrt(variance)
    else:
        detail.balance_score = 0.0

    # Hard Constraints
    detail.hard_violations, detail.violation_details = _check_hard_constraints(
        staffeln, gewichte
    )

    # Gesamtscore
    detail.total = (
        gewichte.w_distanz * detail.distanz_score
        + gewichte.w_region * detail.region_score
        + gewichte.w_balance * detail.balance_score
        + PENALTY * detail.hard_violations
    )

    return detail
