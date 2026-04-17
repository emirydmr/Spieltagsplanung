from src.spielplanerstellung.slot_solver import _get_alternative_dates, _time_range
from datetime import date

# Test: Samstag 20.09.2025
d = date(2025, 9, 20)
alts = _get_alternative_dates(d)
for dt, typ in alts:
    earliest, latest = _time_range(dt)
    day_name = dt.strftime("%A")
    print(f"  {dt} ({day_name:>10}) typ={typ:>10}  {earliest//60:02d}:{earliest%60:02d} - {latest//60:02d}:{latest%60:02d}")

print()

# Test: Dienstag 16.09.2025
d2 = date(2025, 9, 16)
alts2 = _get_alternative_dates(d2)
for dt, typ in alts2:
    earliest, latest = _time_range(dt)
    day_name = dt.strftime("%A")
    print(f"  {dt} ({day_name:>10}) typ={typ:>10}  {earliest//60:02d}:{earliest%60:02d} - {latest//60:02d}:{latest%60:02d}")
