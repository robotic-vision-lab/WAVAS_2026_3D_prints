"""Write <folder>/index.csv for each folder in FOLDERS: one row per STL (file size, mesh stats, provenance).
Folders in XLSX also get <folder>/index.xlsx: the measured columns plus a summary sheet with Excel formulas.

size, format, triangles, extents, volume, watertight and sha256 are measured from the file.
units / source / changes / license are declared below by file name, not measured (the two PickNik files are
pinned to their git blob ids, so a different file under the same name fails); a name that matches no rule is
an error.
STL carries no unit; `units` is what one native coordinate means, x/y/z/volume are converted to mm / cm3.
size_MB = size_bytes / 1e6.
"""
import csv
import hashlib
import io
import re
import struct
import zipfile
from datetime import datetime
from pathlib import Path
from xml.sax.saxutils import escape

import trimesh

ROOT = Path(__file__).parent
FOLDERS = ["final_stl", "pegs_M_150mm"]
# folder -> (size class, length mm) of the pegs it must hold; such folders also get index.xlsx
XLSX = {"pegs_M_150mm": ("M", 150)}
# FMB peg shapes, as named by ../convert.py (SHAPES); a size/length folder must hold one peg of each
PEG_SHAPES = {"arch", "circle", "double_square", "ellipse", "hexagon", "rectangle", "square_round", "star",
              "three_prong"}

FMB_SRC = "FMB (Luo et al.), {step}, listed at https://functional-manipulation-benchmark.github.io/files/"
# cadquery exportStl(tolerance=0.01, angularTolerance=0.05), relative=True by default
FMB_CHANGES = ("STEP solid tessellated to STL (linear deflection 0.01 relative to edge size, angular 0.05 rad); "
               "translated so XY bbox centre = origin and min z = 0; not rotated")
FMB_LICENSE = "CC BY 4.0, https://creativecommons.org/licenses/by/4.0/"

PICKNIK = "picknik_ur5_realsense_camera_adapter_rev2.STL"
PICKNIK_SRC = ("https://github.com/PickNikRobotics/picknik_accessories @3b0912d, "
               "descriptions/brackets/ur_realsense_camera_adapter/")
PICKNIK_BLOB = "86c14ab1a4116fd975e24196015ebc383e6aebf4"  # git blob id of the file upstream at 3b0912d
PICKNIK_LICENSE = "BSD-3-Clause, Copyright (c) 2024 PickNik Inc., see LICENSE.picknik.txt"

# D455 variant, made from PICKNIK by make_d455_variant.py (kept with the lab's mount files, not in this repo).
# The changes text was measured by hand from the two meshes (sections and boolean differences; those measuring
# scripts are not kept), not taken from the generator's comments, which understate the changes. It is pinned to
# this exact file, and nothing here re-checks that it is true.
PICKNIK_D455 = "picknik_adapter_D455_mm.STL"
PICKNIK_D455_BLOB = "899089f699122d1cc4c9f272ed4b313ef9281bff"
PICKNIK_D455_CHANGES = (
    f"made from {PICKNIK} by make_d455_variant.py (not in this repo): scaled from m to mm; a 6 mm thick cross "
    "bar, 112 mm across in x, joined onto the tilted camera platform over y = -66 to -90 (mid-plane), where it "
    "squares off the platform's tapered end; the last ~7 mm of the tip, with the 3.4 mm hole, keeps its "
    "original taper; two 4.4 mm holes, perpendicular to the platform, at x = -47.5 / +47.5 and y = -80 on the "
    "platform mid-plane, for the D455's two rear M4 screws (95 mm apart). Material is only added, none "
    "removed: besides the bar it fills the original two M3 holes and the 15 mm hole, makes the two ~24 mm "
    "windows about 2 mm shorter at their outer edge, and fills up to about 1 mm of the bottom countersink of "
    "the 3.4 mm hole at x = 0, y = -92 on the side toward the bar (the hole itself is unchanged)")
PICKNIK_D455_LICENSE = "BSD-3-Clause, Copyright (c) 2024 PickNik Inc. (modified), see LICENSE.picknik.txt"

# native unit -> mm
SCALE = {"mm": 1, "m": 1000}

COLUMNS = ["file", "size_bytes", "size_MB", "stl_format", "triangles", "units", "scale_to_mm",
           "x_mm", "y_mm", "z_mm", "volume_cm3", "watertight", "sha256", "source", "changes", "license"]


def provenance(name, raw):
    """(units, source, changes, license)"""
    blob = hashlib.sha1(b"blob %d\0" % len(raw) + raw).hexdigest()
    if name == PICKNIK:
        assert blob == PICKNIK_BLOB, (name, blob)
        return "m", PICKNIK_SRC, "none", PICKNIK_LICENSE
    if name == PICKNIK_D455:
        assert blob == PICKNIK_D455_BLOB, (name, blob)
        return "mm", PICKNIK_SRC, PICKNIK_D455_CHANGES, PICKNIK_D455_LICENSE
    if name == "peg_fixture.stl":
        step = "peg fixture.step"
    elif name.startswith("board_"):
        step = "peg_board.step"
    elif name.startswith("peg_"):
        step = "peg.step"
    else:
        raise KeyError(f"{name}: no provenance declared in make_index.py")
    return "mm", FMB_SRC.format(step=step), FMB_CHANGES, FMB_LICENSE


def triangles(path, raw):
    """(format, n_triangles) read off the bytes, independent of the mesh loader."""
    (n,) = struct.unpack_from("<I", raw, 80)
    if len(raw) == 84 + 50 * n:
        return "binary", n
    assert raw.lstrip().startswith(b"solid"), path
    return "ascii", raw.count(b"facet normal")


def measure(p):
    """One record per STL, unrounded; csv and xlsx format it."""
    raw = p.read_bytes()
    fmt, n = triangles(p, raw)
    m = trimesh.load(p, force="mesh")
    assert len(m.faces) == n, (p.name, len(m.faces), n)

    unit, src, changes, lic = provenance(p.name, raw)
    k = SCALE[unit]
    ext = m.extents * k
    assert 10 < ext.max() < 500, (p.name, unit, ext)  # catches m <-> mm mix-ups (not cm)
    return dict(
        file=p.name, size_bytes=len(raw), stl_format=fmt, triangles=n, units=unit, scale_to_mm=k,
        x_mm=float(ext[0]), y_mm=float(ext[1]), z_mm=float(ext[2]),
        volume_cm3=float(m.volume) * k**3 / 1000 if m.is_watertight else None,
        watertight=bool(m.is_watertight), sha256=hashlib.sha256(raw).hexdigest(),
        source=src, changes=changes, license=lic,
    )


def write_csv(path, recs):
    with open(path, "w", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(COLUMNS)
        for r in recs:
            w.writerow([
                r["file"], r["size_bytes"], f"{r['size_bytes'] / 1e6:.3f}", r["stl_format"], r["triangles"],
                r["units"], r["scale_to_mm"], *(f"{r[c]:.2f}" for c in ("x_mm", "y_mm", "z_mm")),
                "" if r["volume_cm3"] is None else f"{r['volume_cm3']:.1f}",
                r["watertight"], r["sha256"], r["source"], r["changes"], r["license"],
            ])


def write_xlsx(path, size, length, recs):
    """Sheet Files: one row per STL, measured values unrounded (display-formatted only).
    Sheet Summary: statistics as formulas over Files (all files, the pegs, the board), plus provenance notes.
    Every formula cell also stores its result, computed here, so viewers that do not calculate
    (Excel Protected View, pandas) show it; Excel recalculates on a normal (editable) open."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill

    board_name = f"board_{size}.stl"
    part, shape = {}, {}
    for r in recs:  # size class is read from the name; peg length is measured
        if r["file"] == board_name:
            part[r["file"]], shape[r["file"]] = "board", None
            continue
        m = re.fullmatch(rf"peg_(.+)_{size}_{length}mm\.stl", r["file"])
        assert m, (r["file"], size, length)
        assert abs(r["z_mm"] - length) < 0.01, (r["file"], r["z_mm"], length)
        part[r["file"]], shape[r["file"]] = "peg", m[1]
    assert sorted(s for s in shape.values() if s) == sorted(PEG_SHAPES), shape  # complete set, one peg per shape
    # openpyxl writes floats as "%.16g"; round to that first so the stored results below are computed from
    # exactly the numbers Excel will read
    q = lambda v: None if v is None else float("%.16g" % v)
    recs = [dict(r, **{c: q(r[c]) for c in ("x_mm", "y_mm", "z_mm", "volume_cm3")}) for r in recs]
    pegs = [r for r in recs if part[r["file"]] == "peg"]
    board = next((r for r in recs if part[r["file"]] == "board"), None)
    title = f"FMB size {size}: {len(pegs)} pegs, length {length} mm" + (f", and {board_name}" if board else "")
    shared = {c: {r[c] for r in recs} for c in ("units", "changes", "license")}
    assert all(len(v) == 1 for v in shared.values()), shared  # notes below state them once for all rows
    shared = {c: v.pop() for c, v in shared.items()}
    assert shared["units"] == "mm"  # the notes text says mm; units come from provenance(), not measured
    source = {p: {r["source"] for r in recs if part[r["file"]] == p} for p in ("peg", "board")}
    assert all(len(v) <= 1 for v in source.values()), source

    wb = Workbook()
    base = Font(name="Arial", size=10)
    bold = Font(name="Arial", size=10, bold=True)
    head_fill = PatternFill("solid", start_color="D9D9D9")
    cached = {}  # (sheet, cell) -> (formula, result)

    def formula(ws, ref, f, result, font, number_format):
        c = ws[ref]
        c.value, c.font, c.number_format = "=" + f, font, number_format
        cached[(ws.title, ref)] = (f, result)
        return c

    ws = wb.active
    ws.title = "Files"
    ws["A1"] = title
    ws["A1"].font = Font(name="Arial", size=12, bold=True)
    ws["A2"] = ("Measured from the STL files in this folder by make_index.py (part and shape are read from the file "
                "name). index.csv has the same measurements (rounded) plus units, scale_to_mm, source, changes and "
                "license, which are in the Summary notes here.")
    ws["A2"].font = base
    head = ["file", "part", "shape", "size_bytes", "size_MB", "stl_format", "triangles",
            "x_mm", "y_mm", "z_mm", "volume_cm3", "watertight", "sha256"]
    col = {h: chr(ord("A") + j) for j, h in enumerate(head)}
    fmt = {"size_bytes": "#,##0", "size_MB": "0.000", "triangles": "#,##0",
           "x_mm": "0.00", "y_mm": "0.00", "z_mm": "0.00", "volume_cm3": "0.0"}
    H = 4  # header row
    for h in head:
        c = ws[f"{col[h]}{H}"]
        c.value, c.font, c.fill = h, bold, head_fill
    first, last = H + 1, H + len(recs)
    row = {}
    for i, r in enumerate(recs, first):
        row[r["file"]] = i
        vals = dict(r, part=part[r["file"]], shape=shape[r["file"]])
        for h in head:
            if h == "size_MB":
                formula(ws, f"{col[h]}{i}", f"{col['size_bytes']}{i}/1000000", r["size_bytes"] / 1e6, base, fmt[h])
                continue
            c = ws[f"{col[h]}{i}"]
            c.value, c.font = vals[h], base
            if h in fmt:
                c.number_format = fmt[h]
    prow = sorted(row[r["file"]] for r in pegs)
    assert prow == list(range(prow[0], prow[-1] + 1)), prow  # pegs are one block of rows, so one range covers them

    sizes = [r["size_bytes"] for r in recs]
    tris = [r["triangles"] for r in recs]
    vols = [r["volume_cm3"] for r in recs if r["volume_cm3"] is not None]
    pvols = [r["volume_cm3"] for r in pegs if r["volume_cm3"] is not None]
    assert pvols, "no watertight peg, volume statistics undefined"
    t = last + 1
    ws[f"A{t}"] = "Total"
    ws[f"A{t}"].font = bold
    for h, result in (("size_bytes", sum(sizes)), ("triangles", sum(tris)), ("volume_cm3", sum(vols))):
        formula(ws, f"{col[h]}{t}", f"SUM({col[h]}{first}:{col[h]}{last})", result, bold, fmt[h])
    formula(ws, f"{col['size_MB']}{t}", f"{col['size_bytes']}{t}/1000000", sum(sizes) / 1e6, bold, fmt["size_MB"])
    ws[f"{col['watertight']}{t}"] = "(watertight parts)"
    ws[f"{col['watertight']}{t}"].font = base
    for h, w in zip(head, (32, 7, 15, 12, 10, 11, 10, 9, 9, 9, 12, 16, 68)):
        ws.column_dimensions[col[h]].width = w
    ws.freeze_panes = f"A{first}"

    s = wb.create_sheet("Summary")
    s["A1"] = f"Summary: {title}"
    s["A1"].font = Font(name="Arial", size=12, bold=True)
    for j, h in enumerate(("statistic", "value", "unit"), 1):
        c = s.cell(3, j, h)
        c.font, c.fill = bold, head_fill
    A = lambda h: f"Files!{col[h]}{first}:{col[h]}{last}"  # all files
    P = lambda h: f"Files!{col[h]}{prow[0]}:{col[h]}{prow[-1]}"  # pegs only
    first_max = lambda rs, k: next(r["file"] for r in rs if r[k] == max(x[k] for x in rs if x[k] is not None))
    rows = [
        ("All files",),
        ("files", f"COUNTA({A('file')})", len(recs), "", "0"),
        ("watertight files", f"COUNTIF({A('watertight')},TRUE)", sum(r["watertight"] for r in recs), "", "0"),
        ("total size", f"SUM({A('size_bytes')})", sum(sizes), "bytes", "#,##0"),
        ("total size", f"SUM({A('size_bytes')})/1000000", sum(sizes) / 1e6, "MB (1e6 bytes)", "0.000"),
        ("total triangles", f"SUM({A('triangles')})", sum(tris), "", "#,##0"),
        ("total volume (watertight parts)", f"SUM({A('volume_cm3')})", sum(vols), "cm3", "0.0"),
        ("largest file", f"INDEX({A('file')},MATCH(MAX({A('size_bytes')}),{A('size_bytes')},0))",
         first_max(recs, "size_bytes"), "", "General"),
        ("Pegs",),
        ("pegs", f"COUNTA({P('file')})", len(pegs), "", "0"),
        ("total volume (watertight pegs)", f"SUM({P('volume_cm3')})", sum(pvols), "cm3", "0.0"),
        ("mean volume (watertight pegs)", f"AVERAGE({P('volume_cm3')})", sum(pvols) / len(pvols), "cm3", "0.0"),
        ("min volume (watertight pegs)", f"MIN({P('volume_cm3')})", min(pvols), "cm3", "0.0"),
        ("max volume (watertight pegs)", f"MAX({P('volume_cm3')})", max(pvols), "cm3", "0.0"),
        ("largest volume peg", f"INDEX({P('file')},MATCH(MAX({P('volume_cm3')}),{P('volume_cm3')},0))",
         first_max(pegs, "volume_cm3"), "", "General"),
        ("max x (footprint)", f"MAX({P('x_mm')})", max(r["x_mm"] for r in pegs), "mm", "0.00"),
        ("max y (footprint)", f"MAX({P('y_mm')})", max(r["y_mm"] for r in pegs), "mm", "0.00"),
        ("min z (length)", f"MIN({P('z_mm')})", min(r["z_mm"] for r in pegs), "mm", "0.00"),
        ("max z (length)", f"MAX({P('z_mm')})", max(r["z_mm"] for r in pegs), "mm", "0.00"),
    ]
    if board:
        b = row[board["file"]]
        rows += [("Board",), ("file", f"Files!{col['file']}{b}", board["file"], "", "General")]
        rows += [(f"{a} (bounding box)", f"Files!{col[a + '_mm']}{b}", board[a + "_mm"], "mm", "0.00") for a in "xyz"]
        if board["volume_cm3"] is not None:
            rows.append(("volume", f"Files!{col['volume_cm3']}{b}", board["volume_cm3"], "cm3", "0.0"))
    i = 4
    for entry in rows:
        if len(entry) == 1:  # section heading
            i += i > 4
            s.cell(i, 1, entry[0]).font = bold
        else:
            label, f, result, unit, nf = entry
            s.cell(i, 1, label).font = base
            formula(s, f"B{i}", f, result, base, nf).alignment = Alignment(horizontal="right")
            s.cell(i, 3, unit).font = base
        i += 1
    notes = [
        ("Notes", None),
        ("units", "mm (STL coordinates, scale_to_mm = 1); "
                  "x/y/z = axis-aligned bounding box in the file's own orientation"),
        ("volume_cm3", "enclosed solid volume of the mesh, blank if not watertight; "
                       "printed mass also depends on infill and walls"),
        ("size_MB", "size_bytes / 1e6 (decimal MB, not MiB)"),
        ("sha256", "SHA-256 of the file bytes"),
    ]
    notes += [({"peg": "source, pegs", "board": "source, board"}[p], v.pop()) for p, v in source.items() if v]
    notes += [("changes", shared["changes"]), ("license", shared["license"])]
    for i, (k, v) in enumerate(notes, i + 1):
        s.cell(i, 1, k).font = bold if v is None else base
        if v is not None:
            s.cell(i, 2, v).font = base
    s.column_dimensions["A"].width = 30
    s.column_dimensions["B"].width = 34
    s.column_dimensions["C"].width = 16

    wb.calculation.fullCalcOnLoad = True
    # Fixed timestamps and stored (uncompressed) zip entries so a re-run is byte-identical.
    epoch = datetime(1980, 1, 1)  # earliest date a zip entry can carry
    wb.properties.creator = "make_index.py"
    wb.properties.created = epoch
    sheet_xml = {w.title: f"xl/worksheets/sheet{i}.xml" for i, w in enumerate(wb.worksheets, 1)}
    buf = io.BytesIO()
    wb.save(buf)
    with zipfile.ZipFile(buf) as zin, zipfile.ZipFile(path, "w", zipfile.ZIP_STORED) as zout:
        for info in zin.infolist():
            data = zin.read(info.filename)
            if info.filename == "docProps/core.xml":  # openpyxl stamps "modified" with the save time
                data, k = re.subn(rb"(<dcterms:modified[^>]*>)[^<]*", rb"\g<1>1980-01-01T00:00:00Z", data)
                assert k == 1, data
            for (sheet, ref), (f, result) in cached.items():
                if sheet_xml[sheet] != info.filename:
                    continue
                # openpyxl writes <c r="D5" s="5"><f>C5/1000000</f><v></v></c>; fill in the result
                t, v = (' t="str"', escape(result)) if isinstance(result, str) else ("", repr(result))
                pat = rf'(<c r="{ref}"(?: s="\d+")?)(><f>{re.escape(escape(f))}</f>)<v></v>'
                data, k = re.subn(pat.encode(), lambda m: m[1] + t.encode() + m[2] + f"<v>{v}</v>".encode(), data)
                assert k == 1, (sheet, ref, f)
            zi = zipfile.ZipInfo(info.filename, date_time=epoch.timetuple()[:6])
            zi.create_system = 0
            zout.writestr(zi, data)


def main():
    for folder in FOLDERS:
        d = ROOT / folder
        recs = [measure(p) for p in sorted(d.iterdir(), key=lambda p: p.name.lower()) if p.suffix.lower() == ".stl"]
        write_csv(d / "index.csv", recs)
        out = [d / "index.csv"]
        if folder in XLSX:
            write_xlsx(d / "index.xlsx", *XLSX[folder], recs)
            out.append(d / "index.xlsx")
        print(f"{folder}: {len(recs)} files, {sum(r['size_bytes'] for r in recs)} bytes -> "
              + ", ".join(p.name for p in out))


if __name__ == "__main__":
    main()
