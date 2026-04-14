"""Runner: Führt die Staffeleinteilung für eine Meldeliste durch.

Nutzung:
    python src/staffeleinteilung/run_einteilung.py raw_data/Meldeliste_Jugend_Hinrunde_24-25.xlsx
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from src.data_import.meldeliste_parser import parse_meldeliste, verknuepfe_koordinaten
from src.staffeleinteilung.algorithmus import gruppiere_mannschaften, einteilung_erstellen
from src.staffeleinteilung.scoring import ScoreGewichte


def main():
    if len(sys.argv) < 2:
        print("Nutzung: python run_einteilung.py <meldeliste.xlsx>")
        sys.exit(1)

    excel_path = sys.argv[1]
    print(f"Lade Meldeliste: {excel_path}\n")

    # 1. Daten laden
    mannschaften = parse_meldeliste(excel_path)
    n_coords = verknuepfe_koordinaten(mannschaften)
    print(f"  {len(mannschaften)} Mannschaften geladen, {n_coords} mit Koordinaten\n")

    # 2. Gruppieren
    gruppen = gruppiere_mannschaften(mannschaften)

    gewichte = ScoreGewichte()

    # 3. Pro Gruppe: Einteilung erstellen
    zusammenfassung = []  # (ak, sk, topf, n_teams, n_staffeln, sizes_str, score_total, violations)

    print("=" * 70)
    max_staffel_size = gewichte.max_staffel_size  # 12

    for (ak, sk, topf), ms in sorted(gruppen.items()):
        topf_str = f"Topf {topf}" if topf > 0 else "fix"
        print(f"\n{ak} | {sk} | {topf_str} | {len(ms)} Mannschaften")
        print("-" * 50)

        if topf == 0 and len(ms) <= max_staffel_size:
            # Regionenstaffel passt in eine Staffel -> fix anzeigen
            print(f"  (fixe Staffel, nicht optimiert)")
            for m in ms:
                print(f"    - {m.mannschaftsname} ({m.bezirk_alt})")
            zusammenfassung.append((ak, sk, topf_str, len(ms), 1, str(len(ms)), "-", 0))
            continue

        if topf == 0 and len(ms) > max_staffel_size:
            # Regionenstaffel zu groß -> splitten via Algorithmus
            print(f"  (Regionenstaffel zu groß, wird gesplittet)")

        if len(ms) < 4:
            dr = " [Doppelrunde]" if len(ms) < 5 else ""
            print(f"  (1 Staffel, {len(ms)} Teams){dr}")
            for m in ms:
                print(f"    - {m.mannschaftsname} ({m.bezirk_alt})")
            sizes_str = f"{len(ms)}(DR)" if len(ms) < 5 else str(len(ms))
            zusammenfassung.append((ak, sk, topf_str, len(ms), 1, sizes_str, "-", 0))
            continue

        staffeln, score = einteilung_erstellen(ms, gewichte)

        sizes = sorted([len(s) for s in staffeln], reverse=True)
        size_parts = []
        for s in sizes:
            if s < 5:
                size_parts.append(f"{s}(DR)")
            else:
                size_parts.append(str(s))
        sizes_str = "+".join(size_parts)

        # Ergebnis anzeigen
        for s_idx, staffel in enumerate(staffeln):
            regionen = {}
            for m in staffel:
                r = m.bezirk_alt or "?"
                regionen[r] = regionen.get(r, 0) + 1
            region_str = ", ".join(f"{r}:{n}" for r, n in sorted(regionen.items()))
            dr_tag = " [Doppelrunde]" if len(staffel) < 5 else ""
            print(f"\n  Staffel {s_idx + 1} ({len(staffel)} Teams, {region_str}){dr_tag}:")
            for m in sorted(staffel, key=lambda x: x.mannschaftsname):
                ort = ""
                if m.spielstaette and m.spielstaette.adresse:
                    parts = m.spielstaette.adresse.split(", ")
                    ort = parts[-1] if parts else ""
                print(f"    {m.mannschaftsname:<45} {m.bezirk_alt:<12} {ort}")

        print(f"\n  Score: {score}")
        zusammenfassung.append((ak, sk, topf_str, len(ms), len(staffeln), sizes_str,
                                f"{score.total:.1f}", score.hard_violations))

    # Zusammenfassung
    print("\n" + "=" * 70)
    print("\nZUSAMMENFASSUNG")
    print("=" * 70)
    header = f"{'Altersklasse':<16} {'Spielklasse':<18} {'Topf':<8} {'Teams':>5} {'Staffeln':>8} {'Größen':<20} {'Score':>8} {'Viol.':>5}"
    print(header)
    print("-" * len(header))
    for ak, sk, topf_str, n_teams, n_staffeln, sizes_str, score_str, viol in zusammenfassung:
        print(f"{ak:<16} {sk:<18} {topf_str:<8} {n_teams:>5} {n_staffeln:>8} {sizes_str:<20} {score_str:>8} {viol:>5}")
    print("-" * len(header))
    total_teams = sum(z[3] for z in zusammenfassung)
    total_staffeln = sum(z[4] for z in zusammenfassung)
    total_viol = sum(z[7] for z in zusammenfassung)
    print(f"{'GESAMT':<44} {total_teams:>5} {total_staffeln:>8} {'':<20} {'':>8} {total_viol:>5}")
    print(f"\nFertig.")


if __name__ == "__main__":
    main()
