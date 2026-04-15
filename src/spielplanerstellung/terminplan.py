"""Rahmenterminkalender Hinrunde 2025/2026 – Bezirk Franken Jugend.

Definiert pro Altersklasse/Region:
  - Regelspieltag (Wochentag + Anstoßzeit)
  - Spieltag-Termine (Spieltag-Nr. → Datum)
"""

from dataclasses import dataclass
from datetime import date


@dataclass
class Terminplan:
    """Terminplan einer Altersklasse für die Hinrunde."""
    altersklasse: str
    region: str             # "alle", "Unterland", "Hohenlohe"
    regelspieltag: str      # z.B. "Samstag"
    anstosszeit: str        # z.B. "16:00"
    anstosszeit_winter: str # z.B. "14:30" (Nov-Feb)
    spieltage: dict[int, date]  # {spieltag_nr: datum}


# ── A-Junioren ──────────────────────────────────────────────

A_JUNIOREN_10 = Terminplan(
    altersklasse="A-Junioren",
    region="alle",
    regelspieltag="Samstag",
    anstosszeit="16:00",
    anstosszeit_winter="14:30",
    spieltage={
        1: date(2025, 9, 20),
        2: date(2025, 9, 27),
        3: date(2025, 10, 4),
        4: date(2025, 10, 11),
        5: date(2025, 10, 18),
        6: date(2025, 10, 25),
        # 2025-11-01 = Allerheiligen → spielfrei
        7: date(2025, 11, 8),
        8: date(2025, 11, 15),
        9: date(2025, 11, 22),
    },
)

A_JUNIOREN_8 = Terminplan(
    altersklasse="A-Junioren",
    region="alle",
    regelspieltag="Samstag",
    anstosszeit="16:00",
    anstosszeit_winter="14:30",
    spieltage={
        1: date(2025, 9, 20),
        2: date(2025, 9, 27),
        3: date(2025, 10, 4),
        4: date(2025, 10, 11),
        5: date(2025, 10, 18),
        6: date(2025, 10, 25),
        7: date(2025, 11, 8),
    },
)

# ── B-Junioren Regionenstaffel/Leistungsstaffel ─────────────

B_JUNIOREN_RST_10 = Terminplan(
    altersklasse="B-Junioren",
    region="alle",
    regelspieltag="Sonntag",
    anstosszeit="10:30",
    anstosszeit_winter="09:00",
    spieltage={
        1: date(2025, 9, 21),
        2: date(2025, 9, 28),
        3: date(2025, 10, 5),
        4: date(2025, 10, 12),
        5: date(2025, 10, 19),
        6: date(2025, 10, 26),
        # 2025-11-02 → spielfrei
        7: date(2025, 11, 9),
        8: date(2025, 11, 16),
        9: date(2025, 11, 30),  # Totensonntag → verschoben
    },
)

# ── B-Junioren Qualistaffel/Kreisstaffel ────────────────────

B_JUNIOREN_QST_10 = Terminplan(
    altersklasse="B-Junioren",
    region="alle",
    regelspieltag="Freitag",
    anstosszeit="19:00",
    anstosszeit_winter="17:30",
    spieltage={
        1: date(2025, 9, 19),
        2: date(2025, 9, 26),
        3: date(2025, 10, 1),   # Mi (wegen 03.10)
        4: date(2025, 10, 10),
        5: date(2025, 10, 17),
        6: date(2025, 10, 24),
        # 2025-10-31 → spielfrei
        7: date(2025, 11, 7),
        8: date(2025, 11, 14),
        9: date(2025, 11, 21),
    },
)

B_JUNIOREN_QST_8 = Terminplan(
    altersklasse="B-Junioren",
    region="alle",
    regelspieltag="Freitag",
    anstosszeit="19:00",
    anstosszeit_winter="17:30",
    spieltage={
        1: date(2025, 9, 19),
        2: date(2025, 9, 26),
        3: date(2025, 10, 10),
        4: date(2025, 10, 17),
        5: date(2025, 10, 24),
        6: date(2025, 11, 7),
        7: date(2025, 11, 14),
    },
)

# ── C-Junioren ──────────────────────────────────────────────

C_JUNIOREN_10 = Terminplan(
    altersklasse="C-Junioren",
    region="alle",
    regelspieltag="Samstag",
    anstosszeit="14:15",
    anstosszeit_winter="12:45",
    spieltage={
        1: date(2025, 9, 20),
        2: date(2025, 9, 27),
        3: date(2025, 10, 4),
        4: date(2025, 10, 11),
        5: date(2025, 10, 18),
        6: date(2025, 10, 25),
        7: date(2025, 11, 8),
        8: date(2025, 11, 15),
        9: date(2025, 11, 22),
    },
)

C_JUNIOREN_8 = Terminplan(
    altersklasse="C-Junioren",
    region="alle",
    regelspieltag="Samstag",
    anstosszeit="14:15",
    anstosszeit_winter="12:45",
    spieltage={
        1: date(2025, 9, 20),
        2: date(2025, 9, 27),
        3: date(2025, 10, 4),
        4: date(2025, 10, 11),
        5: date(2025, 10, 18),
        6: date(2025, 10, 25),
        7: date(2025, 11, 8),
    },
)

# ── D-Junioren ──────────────────────────────────────────────

D_JUNIOREN_UL_8 = Terminplan(
    altersklasse="D-Junioren",
    region="Unterland",
    regelspieltag="Samstag",
    anstosszeit="12:30",
    anstosszeit_winter="11:00",
    spieltage={
        1: date(2025, 9, 20),
        2: date(2025, 9, 27),
        3: date(2025, 10, 4),
        4: date(2025, 10, 11),
        5: date(2025, 10, 18),
        6: date(2025, 10, 25),
        7: date(2025, 11, 8),
    },
)

D_JUNIOREN_UL_6 = Terminplan(
    altersklasse="D-Junioren",
    region="Unterland",
    regelspieltag="Samstag",
    anstosszeit="12:30",
    anstosszeit_winter="11:00",
    spieltage={
        1: date(2025, 9, 20),
        2: date(2025, 9, 27),
        3: date(2025, 10, 4),
        4: date(2025, 10, 11),
        5: date(2025, 10, 18),
    },
)

D_JUNIOREN_HL_8 = Terminplan(
    altersklasse="D-Junioren",
    region="Hohenlohe",
    regelspieltag="Mittwoch",
    anstosszeit="18:00",
    anstosszeit_winter="16:30",
    spieltage={
        1: date(2025, 9, 17),
        2: date(2025, 9, 24),
        3: date(2025, 10, 1),
        4: date(2025, 10, 8),
        5: date(2025, 10, 15),
        6: date(2025, 10, 22),
        7: date(2025, 11, 5),
    },
)

D_JUNIOREN_HL_6 = Terminplan(
    altersklasse="D-Junioren",
    region="Hohenlohe",
    regelspieltag="Mittwoch",
    anstosszeit="18:00",
    anstosszeit_winter="16:30",
    spieltage={
        1: date(2025, 9, 24),
        2: date(2025, 10, 1),
        3: date(2025, 10, 8),
        4: date(2025, 10, 15),
        5: date(2025, 10, 22),
    },
)

# ── E-Junioren ──────────────────────────────────────────────

E_JUNIOREN_UL = Terminplan(
    altersklasse="E-Junioren",
    region="Unterland",
    regelspieltag="Samstag",
    anstosszeit="11:15",
    anstosszeit_winter="09:45",
    spieltage={
        1: date(2025, 9, 20),
        2: date(2025, 9, 27),
        3: date(2025, 10, 4),
        4: date(2025, 10, 11),
        5: date(2025, 10, 18),
        6: date(2025, 10, 25),
        7: date(2025, 11, 8),
    },
)

E_JUNIOREN_HL = Terminplan(
    altersklasse="E-Junioren",
    region="Hohenlohe",
    regelspieltag="Dienstag",
    anstosszeit="18:00",
    anstosszeit_winter="16:30",
    spieltage={
        1: date(2025, 9, 16),
        2: date(2025, 9, 23),
        3: date(2025, 9, 30),
        4: date(2025, 10, 7),
        5: date(2025, 10, 14),
        6: date(2025, 10, 21),
        7: date(2025, 10, 28),
    },
)

# ── Juniorinnen ─────────────────────────────────────────────

B_JUNIORINNEN_8 = Terminplan(
    altersklasse="B-Juniorinnen",
    region="alle",
    regelspieltag="Freitag",
    anstosszeit="18:30",
    anstosszeit_winter="17:00",
    spieltage={
        1: date(2025, 9, 19),
        2: date(2025, 9, 26),
        3: date(2025, 10, 10),
        4: date(2025, 10, 17),
        5: date(2025, 10, 24),
        6: date(2025, 11, 7),
        7: date(2025, 11, 14),
    },
)

C_JUNIORINNEN_8 = Terminplan(
    altersklasse="C-Juniorinnen",
    region="alle",
    regelspieltag="Samstag",
    anstosszeit="14:15",
    anstosszeit_winter="12:45",
    spieltage={
        1: date(2025, 9, 20),
        2: date(2025, 9, 27),
        3: date(2025, 10, 4),
        4: date(2025, 10, 11),
        5: date(2025, 10, 18),
        6: date(2025, 10, 25),
        7: date(2025, 11, 8),
    },
)

D_JUNIORINNEN_6 = Terminplan(
    altersklasse="D-Juniorinnen",
    region="alle",
    regelspieltag="Freitag",
    anstosszeit="18:00",
    anstosszeit_winter="16:30",
    spieltage={
        1: date(2025, 9, 19),
        2: date(2025, 9, 26),
        3: date(2025, 10, 10),
        4: date(2025, 10, 17),
        5: date(2025, 10, 24),
    },
)


# ── Lookup ──────────────────────────────────────────────────

# Alle Terminpläne nach (Altersklasse, Region, n_spieltage)
_ALLE_PLAENE = [
    A_JUNIOREN_10, A_JUNIOREN_8,
    B_JUNIOREN_RST_10, B_JUNIOREN_QST_10, B_JUNIOREN_QST_8,
    C_JUNIOREN_10, C_JUNIOREN_8,
    D_JUNIOREN_UL_8, D_JUNIOREN_UL_6,
    D_JUNIOREN_HL_8, D_JUNIOREN_HL_6,
    E_JUNIOREN_UL, E_JUNIOREN_HL,
    B_JUNIORINNEN_8, C_JUNIORINNEN_8, D_JUNIORINNEN_6,
]


def find_terminplan(altersklasse: str, n_spieltage: int, region: str = "alle") -> Terminplan | None:
    """Findet den passenden Terminplan.

    Args:
        altersklasse: z.B. "C-Junioren"
        n_spieltage: Anzahl benötigter Spieltage
        region: "alle", "Unterland" oder "Hohenlohe"
    """
    for tp in _ALLE_PLAENE:
        if tp.altersklasse != altersklasse:
            continue
        if tp.region != "alle" and tp.region != region:
            continue
        if len(tp.spieltage) >= n_spieltage:
            return tp
    return None


# ── Altersklasse-Reihenfolge (jünger zuerst) ───────────────

AK_REIHENFOLGE = [
    "E-Junioren",
    "D-Juniorinnen",
    "D-Junioren",
    "C-Juniorinnen",
    "C-Junioren",
    "B-Juniorinnen",
    "B-Junioren",
    "A-Junioren",
]
