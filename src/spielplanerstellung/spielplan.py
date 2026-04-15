"""Spielplan-Generator: Kombiniert Schlüsselplan + Terminplan + SZ-Vergabe.

Erzeugt für jede Staffel einen konkreten Spielplan mit:
  - Spieltag-Nummer, Datum, Anstoßzeit
  - Paarungen (Heim vs. Gast)
  - Spielfreie Mannschaft (bei ungerader Staffelgröße)
"""

from dataclasses import dataclass, field
from datetime import date

from src.spielplanerstellung.schluesselplan import (
    get_paarungen_pro_spieltag, get_n_spieltage,
)
from src.spielplanerstellung.terminplan import find_terminplan, Terminplan
from src.spielplanerstellung.sz_vergabe import (
    vergebe_schluesselzahlen, SZZuordnung, SpielplanScore,
)
from src.spielplanerstellung.wuensche import Wunsch


@dataclass
class Spiel:
    """Ein einzelnes Spiel."""
    heim: str       # Mannschaftsname
    gast: str       # Mannschaftsname
    heim_verein: str = ""
    gast_verein: str = ""


@dataclass
class Spieltag:
    """Ein Spieltag mit allen Spielen."""
    nummer: int
    datum: date | None = None
    anstosszeit: str = ""
    spiele: list[Spiel] = field(default_factory=list)
    spielfrei: str | None = None   # Mannschaft die spielfrei hat


@dataclass
class StaffelSpielplan:
    """Kompletter Spielplan einer Staffel."""
    staffel_name: str
    altersklasse: str
    topf: str
    staffel_idx: int
    n_teams: int
    doppelrunde: bool
    sz_zuordnungen: list[SZZuordnung] = field(default_factory=list)
    spieltage: list[Spieltag] = field(default_factory=list)
    score: SpielplanScore | None = None


def generiere_spielplan(
    staffel_data: dict,
    altersklasse: str,
    topf: str,
    staffel_idx: int,
    region: str = "alle",
    wuensche: dict[str, list[Wunsch]] | None = None,
) -> StaffelSpielplan:
    """Generiert einen Spielplan für eine einzelne Staffel.

    Args:
        staffel_data: Dict aus der Einteilung (teams, n_teams, doppelrunde, ...)
        altersklasse: z.B. "C-Junioren"
        topf: z.B. "Topf 1"
        staffel_idx: Staffel-Index (0-basiert)
        region: "alle", "Unterland" oder "Hohenlohe"
        wuensche: Wünsche pro Mannschaft

    Returns:
        StaffelSpielplan
    """
    teams = staffel_data["teams"]
    n = staffel_data["n_teams"]
    doppelrunde = staffel_data.get("doppelrunde", False)

    staffelgroesse = n
    n_spieltage = get_n_spieltage(staffelgroesse)

    # 1. SZ-Vergabe (Optimierung)
    sz_zuordnungen, score = vergebe_schluesselzahlen(
        teams=teams,
        staffelgroesse=staffelgroesse,
        wuensche=wuensche,
    )

    # Build SZ→Team lookup
    sz_to_team = {z.sz: z for z in sz_zuordnungen}

    # 2. Terminplan finden
    terminplan = find_terminplan(altersklasse, n_spieltage, region)

    # 3. Paarungen pro Spieltag
    paarungen = get_paarungen_pro_spieltag(staffelgroesse)

    spieltage_list = []
    for spieltag_nr in sorted(paarungen.keys()):
        matches = paarungen[spieltag_nr]

        # Datum + Anstoßzeit
        datum = None
        anstosszeit = ""
        if terminplan and spieltag_nr in terminplan.spieltage:
            datum = terminplan.spieltage[spieltag_nr]
            # Nov-Feb → Winterzeit
            if datum and datum.month in (11, 12, 1, 2):
                anstosszeit = terminplan.anstosszeit_winter
            else:
                anstosszeit = terminplan.anstosszeit

        spiele = []
        spielfrei = None

        for h_sz, g_sz in matches:
            h_team = sz_to_team.get(h_sz)
            g_team = sz_to_team.get(g_sz)

            if h_team is None and g_team is not None:
                # h_sz = 1 (bye for odd staffels) → g_team hat spielfrei
                spielfrei = g_team.mannschaft
                continue
            elif g_team is None and h_team is not None:
                # g_sz = 1 → h_team hat spielfrei
                spielfrei = h_team.mannschaft
                continue
            elif h_team is None and g_team is None:
                continue

            spiele.append(Spiel(
                heim=h_team.mannschaft,
                gast=g_team.mannschaft,
                heim_verein=h_team.verein,
                gast_verein=g_team.verein,
            ))

        spieltage_list.append(Spieltag(
            nummer=spieltag_nr,
            datum=datum,
            anstosszeit=anstosszeit,
            spiele=spiele,
            spielfrei=spielfrei,
        ))

    # 4. Doppelrunde: Rückrunde anhängen (Heimrecht tauschen)
    if doppelrunde:
        rueckrunde = []
        for st in spieltage_list:
            rueck_spiele = [
                Spiel(
                    heim=s.gast,
                    gast=s.heim,
                    heim_verein=s.gast_verein,
                    gast_verein=s.heim_verein,
                )
                for s in st.spiele
            ]
            rueckrunde.append(Spieltag(
                nummer=st.nummer + n_spieltage,
                datum=None,  # Rückrunde-Termine nicht im Hinrunde-Plan
                anstosszeit=st.anstosszeit,
                spiele=rueck_spiele,
                spielfrei=st.spielfrei,
            ))
        spieltage_list.extend(rueckrunde)

    return StaffelSpielplan(
        staffel_name=f"Staffel {staffel_idx + 1}",
        altersklasse=altersklasse,
        topf=topf,
        staffel_idx=staffel_idx,
        n_teams=n,
        doppelrunde=doppelrunde,
        sz_zuordnungen=sz_zuordnungen,
        spieltage=spieltage_list,
        score=score,
    )


def generiere_alle_spielplaene(
    einteilung_data: dict,
    wuensche: dict[str, list[Wunsch]] | None = None,
) -> list[StaffelSpielplan]:
    """Generiert Spielpläne für alle Staffeln aus der Einteilung.

    Args:
        einteilung_data: Das JSON-Result von /api/einteilung
        wuensche: Wünsche pro Mannschaftsname

    Returns:
        Liste von StaffelSpielplan
    """
    alle_plaene = []

    for gruppe in einteilung_data.get("gruppen", []):
        ak = gruppe["altersklasse"]
        topf = gruppe["topf"]

        # Region bestimmen (für Terminplan-Lookup)
        region = "alle"
        if ak in ("D-Junioren", "E-Junioren"):
            # Schaue welche Region die meisten Teams haben
            regions = [t.get("region", "") for s in gruppe["staffeln"] for t in s["teams"]]
            hl_count = sum(1 for r in regions if "Hohenlohe" in r)
            ul_count = sum(1 for r in regions if "Unterland" in r)
            region = "Hohenlohe" if hl_count > ul_count else "Unterland"

        for si, staffel in enumerate(gruppe["staffeln"]):
            plan = generiere_spielplan(
                staffel_data=staffel,
                altersklasse=ak,
                topf=topf,
                staffel_idx=si,
                region=region,
                wuensche=wuensche,
            )
            alle_plaene.append(plan)

    return alle_plaene


def spielplan_to_dict(plan: StaffelSpielplan) -> dict:
    """Konvertiert einen Spielplan in ein JSON-fähiges Dict."""
    return {
        "staffel_name": plan.staffel_name,
        "altersklasse": plan.altersklasse,
        "topf": plan.topf,
        "staffel_idx": plan.staffel_idx,
        "n_teams": plan.n_teams,
        "doppelrunde": plan.doppelrunde,
        "sz_zuordnungen": [
            {"mannschaft": z.mannschaft, "verein": z.verein, "sz": z.sz, "region": z.region}
            for z in plan.sz_zuordnungen
        ],
        "score": {
            "total": round(plan.score.total, 1),
            "heim_balance": round(plan.score.heim_balance, 2),
            "distanz_fairness": round(plan.score.distanz_fairness, 1),
            "wunsch_verletzungen": plan.score.wunsch_verletzungen,
            "platz_konflikte": plan.score.platz_konflikte,
        } if plan.score else None,
        "spieltage": [
            {
                "nummer": st.nummer,
                "datum": st.datum.isoformat() if st.datum else None,
                "anstosszeit": st.anstosszeit,
                "spiele": [
                    {"heim": s.heim, "gast": s.gast}
                    for s in st.spiele
                ],
                "spielfrei": st.spielfrei,
            }
            for st in plan.spieltage
        ],
    }
