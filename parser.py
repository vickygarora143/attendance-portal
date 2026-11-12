# -*- coding: utf-8 -*-
"""Biometric .xls parser — same logic used to build the October 2026 report."""
import re
import xlrd

from helpers import mmin


def parse_bio(path_or_fileobj):
    """Parse a biometric export (.xls, block format).

    Returns: dict emp_code -> {"name": str, "days": {day:int -> (status, in, out, tot)}}
    """
    wb = xlrd.open_workbook(filename=None, file_contents=path_or_fileobj.read())
    sh = wb.sheet_by_index(0)

    # day number -> column index (from header row 6)
    day_cols = {}
    for c in range(2, sh.ncols):
        m = re.match(r"(\d+)", str(sh.cell_value(6, c)).strip())
        if m:
            day_cols[int(m.group(1))] = c

    emp = {}
    r = 10
    while r < sh.nrows:
        if str(sh.cell_value(r, 0)).strip() == "Emp. Code:":
            # some device exports put the code in col 2, others in col 3
            code = str(sh.cell_value(r, 3)).strip() or str(sh.cell_value(r, 2)).strip()
            name = str(sh.cell_value(r, 13)).strip()
            days = {}
            for d, c in day_cols.items():
                st = str(sh.cell_value(r + 1, c)).strip()
                iv = str(sh.cell_value(r + 2, c)).strip()
                ov = str(sh.cell_value(r + 3, c)).strip()
                tv = str(sh.cell_value(r + 4, c)).strip()
                if st:                       # blank day columns skipped
                    days[d] = (st, iv, ov, tv)
            if code:
                emp[code] = {"name": name, "days": days}
            r += 6
        else:
            r += 1
    return emp


def derive_code(st, in_time, is_holiday, office):
    """Raw device status -> final attendance code (office rules applied)."""
    if st == "P":
        t = mmin(in_time)
        if t is None:
            return "P"
        if office.late_after < t < office.hd_from:
            return "L"
        if office.hd_from <= t < office.suspect_from:
            return "H"
        return "P"
    if st in ("HP", "\u00bdP"):
        return "H"                       # device half-day-present -> half day
    if st == "WOP":
        return "O"                       # worked on weekly-off -> comp-off present
    if st == "A":
        return "HO" if is_holiday else "A"
    if st == "WO":
        return "WO"
    return "-"
