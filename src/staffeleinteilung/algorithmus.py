"""Staffeleinteilungs-Algorithmus.

Ablauf:
    1. Mannschaften filtern (Altersklasse, Spielklasse, Topf)
    2. Regionenstaffeln überspringen (fix)
    3. Initiale Zuweisung: Geografie-basiertes Clustering (K-Means-artig auf Koordinaten)
    4. Hard-Constraint-Reparatur: Verein-Duplikate zwischen Staffeln tauschen
    5. Optimierung: Paarweise Swaps zwischen Staffeln wenn Score sich verbessert
"""

import math
import random
import time
import sys
from collections import defaultdict
from pathlib import Path

from src.common.models import Mannschaft
from src.staffeleinteilung.scoring import berechne_score, ScoreGewichte, ScoreDetail

_LOG_FILE = Path(__file__).resolve().parent.parent.parent / "output" / "einteilung_log.txt"


def _log(msg: str) -> None:
    """Gibt eine Nachricht auf stdout und in die Log-Datei aus."""
    print(msg, flush=True)
    try:
        _LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"[{time.strftime('%H:%M:%S')}] {msg}\n")
    except Exception:
        pass


def _hat_koordinaten(m: Mannschaft) -> bool:
    return m.spielstaette is not None and m.spielstaette.lat is not None


def _geo_center(mannschaften: list[Mannschaft]) -> tuple[float, float]:
    """Berechnet den geografischen Mittelpunkt einer Gruppe."""
    with_coords = [m for m in mannschaften if _hat_koordinaten(m)]
    if not with_coords:
        return (49.15, 9.4)  # Fallback: ungefähr Mitte Bezirk Franken
    lat = sum(m.spielstaette.lat for m in with_coords) / len(with_coords)
    lon = sum(m.spielstaette.lon for m in with_coords) / len(with_coords)
    return (lat, lon)


def _distanz_zu_punkt(m: Mannschaft, lat: float, lon: float) -> float:
    """Distanz einer Mannschaft zu einem Punkt."""
    if not _hat_koordinaten(m):
        return 999.0  # Hohe Default-Distanz
    dlat = m.spielstaette.lat - lat
    dlon = m.spielstaette.lon - lon
    return math.sqrt(dlat**2 + dlon**2)  # Euklidisch auf Grad (reicht für Sortierung)


def bestimme_staffelanzahl(
    n_mannschaften: int,
    min_size: int = 5,
    max_size: int = 12,
    target_size: int = 8,
) -> int:
    """Bestimmt die optimale Anzahl Staffeln.

    Versucht möglichst nah an target_size zu kommen,
    ohne min/max zu verletzen.
    """
    if n_mannschaften <= max_size:
        return 1

    # Verschiedene Staffelanzahlen durchprobieren
    best_n = max(1, round(n_mannschaften / target_size))
    best_diff = float("inf")

    for n_staffeln in range(max(1, n_mannschaften // max_size), n_mannschaften // min_size + 2):
        if n_staffeln < 1:
            continue
        avg = n_mannschaften / n_staffeln
        if min_size <= avg <= max_size:
            diff = abs(avg - target_size)
            if diff < best_diff:
                best_diff = diff
                best_n = n_staffeln

    return best_n


def _initiale_zuweisung_geo(
    mannschaften: list[Mannschaft],
    n_staffeln: int,
) -> list[list[Mannschaft]]:
    """Initiale Zuweisung: Sortiere nach Längengrad, teile in n gleichgroße Gruppen.

    Einfachster Geo-Split: West nach Ost sortieren, dann aufteilen.
    Funktioniert gut für den Bezirk Franken (längliche West-Ost-Ausdehnung).
    """
    # Sortiere nach Längengrad (West -> Ost)
    sortiert = sorted(
        mannschaften,
        key=lambda m: (m.spielstaette.lon if _hat_koordinaten(m) else 9.4)
    )

    staffeln: list[list[Mannschaft]] = [[] for _ in range(n_staffeln)]
    chunk_size = len(sortiert) / n_staffeln

    for i, m in enumerate(sortiert):
        staffel_idx = min(int(i / chunk_size), n_staffeln - 1)
        staffeln[staffel_idx].append(m)

    return staffeln


def _repariere_verein_duplikate(staffeln: list[list[Mannschaft]]) -> int:
    """Repariert Verein-Duplikate durch Tausch zwischen Staffeln.

    Returns:
        Anzahl der durchgeführten Swaps
    """
    swaps = 0
    max_iterations = 100

    for _ in range(max_iterations):
        found_swap = False

        for s_idx, staffel in enumerate(staffeln):
            # Finde Verein-Duplikate
            verein_count: dict[str, list[int]] = defaultdict(list)
            for t_idx, m in enumerate(staffel):
                verein_count[m.verein_nr].append(t_idx)

            for vnr, indices in verein_count.items():
                if len(indices) <= 1:
                    continue

                # Versuche die überzähligen Mannschaften in andere Staffeln zu tauschen
                for dup_idx in indices[1:]:
                    dup_team = staffel[dup_idx]
                    best_swap = None
                    best_improvement = 0

                    for other_idx, other_staffel in enumerate(staffeln):
                        if other_idx == s_idx:
                            continue
                        # Prüfe ob der Verein in der Ziel-Staffel noch nicht existiert
                        other_vereine = {m.verein_nr for m in other_staffel}
                        if vnr in other_vereine:
                            continue

                        # Finde den besten Tauschpartner in der Ziel-Staffel
                        for cand_idx, candidate in enumerate(other_staffel):
                            # Candidate darf in unserer Staffel keinen Duplikat erzeugen
                            our_vereine = {m.verein_nr for m in staffel} - {vnr}
                            if candidate.verein_nr in our_vereine:
                                # Würde neues Duplikat erzeugen
                                if sum(1 for m in staffel if m.verein_nr == candidate.verein_nr) > 0:
                                    continue

                            best_swap = (other_idx, cand_idx)
                            break  # Erster gültiger Tausch reicht

                    if best_swap:
                        other_idx, cand_idx = best_swap
                        # Tausch durchführen
                        staffeln[s_idx][dup_idx], staffeln[other_idx][cand_idx] = (
                            staffeln[other_idx][cand_idx],
                            staffeln[s_idx][dup_idx],
                        )
                        swaps += 1
                        found_swap = True
                        break  # Staffel nochmal prüfen

                if found_swap:
                    break

        if not found_swap:
            break

    return swaps


def _optimiere_swaps(
    staffeln: list[list[Mannschaft]],
    gewichte: ScoreGewichte,
    max_ohne_verbesserung: int = 300,
) -> int:
    """Optimiert durch paarweisen Tausch von Mannschaften zwischen Staffeln.

    Läuft bis keine Verbesserung mehr gefunden wird (max_ohne_verbesserung
    aufeinanderfolgende Versuche ohne Erfolg = Konvergenz).

    Returns:
        Anzahl akzeptierter Swaps
    """
    akzeptiert = 0
    seit_letzter_verbesserung = 0
    iterationen = 0
    start_time = time.time()
    aktueller_score = berechne_score(staffeln, gewichte).total
    n_teams = sum(len(s) for s in staffeln)

    _log(f"      Swap-Optimierung: {n_teams} Teams, {len(staffeln)} Staffeln, "
         f"max {max_ohne_verbesserung} ohne Verbesserung")

    while seit_letzter_verbesserung < max_ohne_verbesserung:
        iterationen += 1

        # Fortschritt alle 500 Iterationen loggen
        if iterationen % 500 == 0:
            elapsed = time.time() - start_time
            _log(f"      ... Iteration {iterationen}, Score={aktueller_score:.1f}, "
                 f"Swaps={akzeptiert}, Stagnation={seit_letzter_verbesserung}/{max_ohne_verbesserung}, "
                 f"Zeit={elapsed:.1f}s")

        # Wähle zwei verschiedene Staffeln
        if len(staffeln) < 2:
            break
        s1, s2 = random.sample(range(len(staffeln)), 2)
        if not staffeln[s1] or not staffeln[s2]:
            seit_letzter_verbesserung += 1
            continue

        # Wähle je eine zufällige Mannschaft
        t1 = random.randint(0, len(staffeln[s1]) - 1)
        t2 = random.randint(0, len(staffeln[s2]) - 1)

        # Tausch durchführen
        staffeln[s1][t1], staffeln[s2][t2] = staffeln[s2][t2], staffeln[s1][t1]

        neuer_score = berechne_score(staffeln, gewichte).total

        if neuer_score < aktueller_score:
            aktueller_score = neuer_score
            akzeptiert += 1
            seit_letzter_verbesserung = 0
        else:
            # Tausch rückgängig
            staffeln[s1][t1], staffeln[s2][t2] = staffeln[s2][t2], staffeln[s1][t1]
            seit_letzter_verbesserung += 1

    elapsed = time.time() - start_time
    _log(f"      Fertig: {iterationen} Iterationen, {akzeptiert} Swaps, {elapsed:.1f}s")
    return akzeptiert


def einteilung_erstellen(
    mannschaften: list[Mannschaft],
    gewichte: ScoreGewichte | None = None,
    target_staffel_size: int = 8,
    seed: int | None = 42,
) -> tuple[list[list[Mannschaft]], ScoreDetail]:
    """Erstellt eine optimierte Staffeleinteilung für eine Gruppe von Mannschaften.

    Args:
        mannschaften: Alle Mannschaften EINER Altersklasse/Spielklasse/Topf-Kombination
        gewichte: Score-Gewichtung
        target_staffel_size: Ziel-Staffelgröße
        seed: Random seed für Reproduzierbarkeit

    Returns:
        (staffeln, score_detail)
    """
    if seed is not None:
        random.seed(seed)

    if gewichte is None:
        gewichte = ScoreGewichte()

    n = len(mannschaften)
    if n == 0:
        return [], ScoreDetail()

    # 1. Staffelanzahl bestimmen
    n_staffeln = bestimme_staffelanzahl(
        n, gewichte.min_staffel_size, gewichte.max_staffel_size, target_staffel_size
    )

    if n_staffeln <= 1:
        staffeln = [list(mannschaften)]
        return staffeln, berechne_score(staffeln, gewichte)

    # 2. Initiale geografische Zuweisung
    staffeln = _initiale_zuweisung_geo(mannschaften, n_staffeln)

    score_initial = berechne_score(staffeln, gewichte)
    _log(f"    Initial ({n_staffeln} Staffeln): Score={score_initial.total:.1f} "
          f"(Distanz={score_initial.distanz_score:.1f}km, "
          f"Region={score_initial.region_score:.0f}, "
          f"Violations={score_initial.hard_violations})")

    # 3. Hard-Constraint-Reparatur: Verein-Duplikate
    n_swaps = _repariere_verein_duplikate(staffeln)
    if n_swaps > 0:
        score_nach_repair = berechne_score(staffeln, gewichte)
        _log(f"    Nach Duplikat-Reparatur ({n_swaps} Swaps): Score={score_nach_repair.total:.1f}")

    # 4. Optimierung durch zufällige Swaps (bis Konvergenz)
    n_optim = _optimiere_swaps(staffeln, gewichte, max_ohne_verbesserung=n * 30)
    score_final = berechne_score(staffeln, gewichte)
    _log(f"    Nach Optimierung ({n_optim} Swaps): Score={score_final.total:.1f} "
          f"(Distanz={score_final.distanz_score:.1f}km, "
          f"Region={score_final.region_score:.0f}, "
          f"Violations={score_final.hard_violations})")

    return staffeln, score_final


def gruppiere_mannschaften(
    alle_mannschaften: list[Mannschaft],
    min_topf2_size: int = 5,
) -> dict[tuple[str, str, int], list[Mannschaft]]:
    """Gruppiert Mannschaften nach (Altersklasse, Spielklasse_grob, Topf).

    Regionenstaffeln werden als eigene Gruppe mit key (..., 0) markiert.
    Bei Juniorinnen: Topf 2 wird in Topf 1 gemergt wenn zu wenig Teams.
    """
    gruppen: dict[tuple[str, str, int], list[Mannschaft]] = defaultdict(list)

    for m in alle_mannschaften:
        sk = m.spielklasse.lower() if m.spielklasse else ""
        if "regionenstaffel" in sk or "verbandsstaffel" in sk or "landesstaffel" in sk:
            gruppen[(m.altersklasse, "Regionenstaffel", 0)].append(m)
        else:
            gruppen[(m.altersklasse, "Qualistaffel", m.topf or 2)].append(m)

    # Juniorinnen: Topf 2 und kleine Regionenstaffeln in Topf 1 mergen
    keys_to_merge = []
    for (ak, sk, topf), ms in list(gruppen.items()):
        if "juniorinnen" not in ak.lower():
            continue
        topf1_key = (ak, "Qualistaffel", 1)
        if topf1_key not in gruppen:
            continue
        # Topf 2 mit zu wenig Teams
        if sk == "Qualistaffel" and topf == 2 and len(ms) < min_topf2_size:
            keys_to_merge.append(((ak, sk, topf), topf1_key))
        # Regionenstaffel mit zu wenig Teams
        if sk == "Regionenstaffel" and len(ms) < min_topf2_size:
            keys_to_merge.append(((ak, sk, topf), topf1_key))

    for src_key, dst_key in keys_to_merge:
        label = "Regionenstaffel" if src_key[1] == "Regionenstaffel" else "Topf 2"
        print(f"  [Merge] {src_key[0]} {label} ({len(gruppen[src_key])} Teams) -> Topf 1 gemergt")
        gruppen[dst_key].extend(gruppen[src_key])
        del gruppen[src_key]

    return gruppen
