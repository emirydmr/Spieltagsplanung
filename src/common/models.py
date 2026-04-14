"""Datenmodelle für die Spieltagsplanung."""

from dataclasses import dataclass, field


@dataclass
class Spielstaette:
    name: str  # z.B. "Abstatt Kunstrasen"
    adresse: str  # z.B. "Kirschenwiesen, 74232 Abstatt-Zentrum"
    lat: float | None = None
    lon: float | None = None

    @property
    def adresse_key(self) -> str:
        """Normalisierte Adresse als Key (ohne Facility-Name)."""
        return self.adresse.strip().lower()


@dataclass
class Mannschaft:
    verein_nr: str
    vereinsname: str
    mannschaftsname: str
    altersklasse: str  # A-Junioren, B-Junioren, etc.
    spielklasse: str  # Regionenstaffel, Qualistaffel, etc.
    region: str  # Unterland, Hohenlohe, etc.
    bezirk_alt: str  # Unterland / Hohenlohe
    ms_nr: int  # 1, 2, 3 (1. Mannschaft, 2. Mannschaft, etc.)
    spielstaette: Spielstaette | None = None
    topf: int | None = None  # 1 oder 2


@dataclass
class Staffel:
    name: str
    altersklasse: str
    spielklasse: str
    mannschaften: list[Mannschaft] = field(default_factory=list)
