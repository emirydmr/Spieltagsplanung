"""Schlüsselpläne (Round-Robin-Paarungstabellen) nach DFBnet 1-L Schema.

Für jede geradzahlige Staffelgröße (4, 6, 8, 10, 12, 14, 16) ist eine
Tabelle hinterlegt, die pro Schlüsseltag die Paarungen (Heim-SZ, Gast-SZ) enthält.

Ungerade Staffelgrößen (5, 7, 9, 11) nutzen den nächsthöheren geraden Plan:
SZ 1 wird nicht vergeben -> Team gegen SZ 1 hat spielfrei.

Schlüsseltag-Reihenfolge: Im DFBnet gilt "1-L", d.h. Schlüsseltag 1 ist der
LETZTE Spieltag. Umrechnung: spieltag = n_schluesseltage - schluesseltag + 1
"""

# Format: {staffelgroesse: {schluesseltag: [(heim_sz, gast_sz), ...]}}
SCHLUESSELPLAENE: dict[int, dict[int, list[tuple[int, int]]]] = {
    4: {
        3: [(1, 3), (4, 2)],
        2: [(1, 2), (3, 4)],
        1: [(2, 3), (4, 1)],
    },
    6: {
        5: [(1, 5), (3, 2), (6, 4)],
        4: [(2, 6), (4, 1), (5, 3)],
        3: [(1, 3), (4, 2), (6, 5)],
        2: [(1, 2), (3, 6), (5, 4)],
        1: [(2, 5), (4, 3), (6, 1)],
    },
    8: {
        7: [(1, 7), (3, 4), (5, 2), (8, 6)],
        6: [(2, 3), (4, 8), (6, 1), (7, 5)],
        5: [(1, 5), (3, 7), (6, 4), (8, 2)],
        4: [(2, 6), (4, 1), (5, 3), (7, 8)],
        3: [(1, 3), (4, 2), (6, 7), (8, 5)],
        2: [(1, 2), (3, 8), (5, 6), (7, 4)],
        1: [(2, 7), (4, 5), (6, 3), (8, 1)],
    },
    10: {
        9: [(1, 9), (3, 6), (5, 4), (7, 2), (10, 8)],
        8: [(2, 5), (4, 3), (6, 10), (8, 1), (9, 7)],
        7: [(1, 7), (3, 2), (5, 9), (8, 6), (10, 4)],
        6: [(2, 10), (4, 8), (6, 1), (7, 5), (9, 3)],
        5: [(1, 5), (3, 7), (6, 4), (8, 2), (10, 9)],
        4: [(2, 6), (4, 1), (5, 3), (7, 10), (9, 8)],
        3: [(1, 3), (4, 2), (6, 9), (8, 7), (10, 5)],
        2: [(1, 2), (3, 10), (5, 8), (7, 6), (9, 4)],
        1: [(2, 9), (4, 7), (6, 5), (8, 3), (10, 1)],
    },
    12: {
        11: [(1, 11), (3, 8), (5, 6), (7, 4), (9, 2), (12, 10)],
        10: [(2, 7), (4, 5), (6, 3), (8, 12), (10, 1), (11, 9)],
        9: [(1, 9), (3, 4), (5, 2), (7, 11), (10, 8), (12, 6)],
        8: [(2, 3), (4, 12), (6, 10), (8, 1), (9, 7), (11, 5)],
        7: [(1, 7), (3, 11), (5, 9), (8, 6), (10, 4), (12, 2)],
        6: [(2, 10), (4, 8), (6, 1), (7, 5), (9, 3), (11, 12)],
        5: [(1, 5), (3, 7), (6, 4), (8, 2), (10, 11), (12, 9)],
        4: [(2, 6), (4, 1), (5, 3), (7, 12), (9, 10), (11, 8)],
        3: [(1, 3), (4, 2), (6, 11), (8, 9), (10, 7), (12, 5)],
        2: [(1, 2), (3, 12), (5, 10), (7, 8), (9, 6), (11, 4)],
        1: [(2, 11), (4, 9), (6, 7), (8, 5), (10, 3), (12, 1)],
    },
    14: {
        13: [(1, 13), (3, 10), (5, 8), (7, 6), (9, 4), (11, 2), (14, 12)],
        12: [(2, 9), (4, 7), (6, 5), (8, 3), (10, 14), (12, 1), (13, 11)],
        11: [(1, 11), (3, 6), (5, 4), (7, 2), (9, 13), (12, 10), (14, 8)],
        10: [(2, 5), (4, 3), (6, 14), (8, 12), (10, 1), (11, 9), (13, 7)],
        9: [(1, 9), (3, 2), (5, 13), (7, 11), (10, 8), (12, 6), (14, 4)],
        8: [(2, 14), (4, 12), (6, 10), (8, 1), (9, 7), (11, 5), (13, 3)],
        7: [(1, 7), (3, 11), (5, 9), (8, 6), (10, 4), (12, 2), (14, 13)],
        6: [(2, 10), (4, 8), (6, 1), (7, 5), (9, 3), (11, 14), (13, 12)],
        5: [(1, 5), (3, 7), (6, 4), (8, 2), (10, 13), (12, 11), (14, 9)],
        4: [(2, 6), (4, 1), (5, 3), (7, 14), (9, 12), (11, 10), (13, 8)],
        3: [(1, 3), (4, 2), (6, 13), (8, 11), (10, 9), (12, 7), (14, 5)],
        2: [(1, 2), (3, 14), (5, 12), (7, 10), (9, 8), (11, 6), (13, 4)],
        1: [(2, 13), (4, 11), (6, 9), (8, 7), (10, 5), (12, 3), (14, 1)],
    },
    16: {
        15: [(1, 15), (3, 12), (5, 10), (7, 8), (9, 6), (11, 4), (13, 2), (16, 14)],
        14: [(2, 11), (4, 9), (6, 7), (8, 5), (10, 3), (12, 16), (14, 1), (15, 13)],
        13: [(1, 13), (3, 8), (5, 6), (7, 4), (9, 2), (11, 15), (14, 12), (16, 10)],
        12: [(2, 7), (4, 5), (6, 3), (8, 16), (10, 14), (12, 1), (13, 11), (15, 9)],
        11: [(1, 11), (3, 4), (5, 2), (7, 15), (9, 13), (12, 10), (14, 8), (16, 6)],
        10: [(2, 3), (4, 16), (6, 14), (8, 12), (10, 1), (11, 9), (13, 7), (15, 5)],
        9: [(1, 9), (3, 15), (5, 13), (7, 11), (10, 8), (12, 6), (14, 4), (16, 2)],
        8: [(2, 14), (4, 12), (6, 10), (8, 1), (9, 7), (11, 5), (13, 3), (15, 16)],
        7: [(1, 7), (3, 11), (5, 9), (8, 6), (10, 4), (12, 2), (14, 15), (16, 13)],
        6: [(2, 10), (4, 8), (6, 1), (7, 5), (9, 3), (11, 16), (13, 14), (15, 12)],
        5: [(1, 5), (3, 7), (6, 4), (8, 2), (10, 15), (12, 13), (14, 11), (16, 9)],
        4: [(2, 6), (4, 1), (5, 3), (7, 16), (9, 14), (11, 12), (13, 10), (15, 8)],
        3: [(1, 3), (4, 2), (6, 15), (8, 13), (10, 11), (12, 9), (14, 7), (16, 5)],
        2: [(1, 2), (3, 16), (5, 14), (7, 12), (9, 10), (11, 8), (13, 6), (15, 4)],
        1: [(2, 15), (4, 13), (6, 11), (8, 9), (10, 7), (12, 5), (14, 3), (16, 1)],
    },
}


def get_schluesselplan(staffelgroesse: int) -> dict[int, list[tuple[int, int]]]:
    """Gibt den Schlüsselplan für eine Staffelgröße zurück.

    Ungerade Größen (5,7,9,11) nutzen den nächsthöheren geraden Plan.
    """
    if staffelgroesse in SCHLUESSELPLAENE:
        return SCHLUESSELPLAENE[staffelgroesse]

    # Ungerade -> nächsthöhere gerade Größe
    even_size = staffelgroesse + 1
    if even_size in SCHLUESSELPLAENE:
        return SCHLUESSELPLAENE[even_size]

    raise ValueError(f"Kein Schlüsselplan für Staffelgröße {staffelgroesse}")


def get_n_spieltage(staffelgroesse: int) -> int:
    """Anzahl Spieltage für Einfachrunde."""
    plan = get_schluesselplan(staffelgroesse)
    return len(plan)


def schluesseltag_to_spieltag(schluesseltag: int, n_spieltage: int) -> int:
    """Wandelt Schlüsseltag -> Spieltag (1-L Umrechnung)."""
    return n_spieltage - schluesseltag + 1


def get_paarungen_pro_spieltag(
    staffelgroesse: int,
) -> dict[int, list[tuple[int, int]]]:
    """Gibt Paarungen sortiert nach Spieltag (nicht Schlüsseltag) zurück.

    Returns:
        {spieltag: [(heim_sz, gast_sz), ...]}
    """
    plan = get_schluesselplan(staffelgroesse)
    n_st = len(plan)
    result = {}
    for stag, paarungen in plan.items():
        spieltag = schluesseltag_to_spieltag(stag, n_st)
        result[spieltag] = paarungen
    return dict(sorted(result.items()))


def get_heimspiele_pro_sz(staffelgroesse: int) -> dict[int, list[int]]:
    """Gibt für jede SZ die Spieltage zurück, an denen sie Heim hat.

    Returns:
        {sz: [spieltag, ...]}
    """
    paarungen = get_paarungen_pro_spieltag(staffelgroesse)
    heim: dict[int, list[int]] = {}
    for spieltag, matches in paarungen.items():
        for h, g in matches:
            heim.setdefault(h, []).append(spieltag)
    return heim
