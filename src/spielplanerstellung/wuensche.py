"""Vereinswünsche – Kategorien und strukturierte Flags.

Wünsche von Vereinen (Freitext) werden per LLM in strukturierte
Flags umgewandelt, die der Spielplan-Algorithmus berücksichtigen kann.
"""

from dataclasses import dataclass, field
from enum import Enum


class WunschKategorie(str, Enum):
    """Kategorien für Vereinswünsche."""
    SPERRTAG = "sperrtag"                # "Am 12.10. können wir nicht spielen"
    HEIMWUNSCH = "heimwunsch"            # "Am 20.09. möchten wir Heimspiel"
    AUSWAERTSWUNSCH = "auswaertswunsch"  # "Am 20.09. bitte auswärts"
    WOCHENTAG = "wochentag"              # "Wir spielen am liebsten samstags"
    ANSTOSSZEIT = "anstosszeit"          # "Anstoß bitte 14:00"
    PLATZSHARING = "platzsharing"        # "Teilen Platz mit C-Junioren 1."
    GLEICHZEITIG = "gleichzeitig"        # "Sollen gleichzeitig wie B-Junioren spielen"
    ABWECHSELND = "abwechselnd"          # "Abwechselnd Heim mit C-Junioren 1."
    REIHENFOLGE = "reihenfolge"          # "Bitte erst Auswärts, dann Heim am Anfang"
    SONSTIGES = "sonstiges"              # Alles andere


class WunschPrio(str, Enum):
    """Priorität eines Wunsches."""
    HART = "hart"      # Muss berücksichtigt werden
    WEICH = "weich"    # Sollte berücksichtigt werden, wenn möglich


@dataclass
class Wunsch:
    """Ein einzelner strukturierter Vereinswunsch."""
    kategorie: WunschKategorie
    prioritaet: WunschPrio
    beschreibung: str              # Kurze Zusammenfassung
    datum: str | None = None       # ISO-Datum wenn relevant (z.B. "2025-10-04")
    wochentag: str | None = None   # z.B. "Samstag"
    uhrzeit: str | None = None     # z.B. "14:00"
    bezug_mannschaft: str | None = None  # Auf welche andere Mannschaft bezogen
    original_text: str = ""        # Originaltext des Wunsches


@dataclass
class VereinsWuensche:
    """Alle Wünsche eines Vereins / einer Mannschaft."""
    mannschaft: str          # z.B. "TSV Öhringen 2"
    verein: str              # z.B. "TSV Öhringen"
    wuensche: list[Wunsch] = field(default_factory=list)

    @property
    def sperrtage(self) -> list[Wunsch]:
        return [w for w in self.wuensche if w.kategorie == WunschKategorie.SPERRTAG]

    @property
    def heimwuensche(self) -> list[Wunsch]:
        return [w for w in self.wuensche if w.kategorie == WunschKategorie.HEIMWUNSCH]

    @property
    def platzsharing(self) -> list[Wunsch]:
        return [w for w in self.wuensche if w.kategorie == WunschKategorie.PLATZSHARING]

    @property
    def harte_wuensche(self) -> list[Wunsch]:
        return [w for w in self.wuensche if w.prioritaet == WunschPrio.HART]
