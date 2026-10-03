"""Write <folder>/index.csv for each folder in FOLDERS: one row per STL (file size, mesh stats, provenance).
Folders in XLSX also get <folder>/index.xlsx: the measured columns plus a summary sheet with Excel formulas.

size, format, triangles, extents, volume, watertight and sha256 are measured from the file.
units / source / changes / license are declared below by file name, not measured (only the PickNik file is
checked against its upstream blob id); a name that matches no rule is an error.
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

# native unit -> mm
SCALE = {"mm": 1, "m": 1000}

COLUMNS = ["file", "size_bytes", "size_MB", "stl_format", "triangles", "units", "scale_to_mm",
           "x_mm", "y_mm", "z_mm", "volume_cm3", "watertight", "sha256", "source", "changes", "license"]


def provenance(name, raw):
    """(units, source, changes, license)"""
    if name == PICKNIK:
        blob = hashlib.sha1(b"blob %d\0" % len(raw) + raw).hexdigest()
        assert blob == PICKNIK_BLOB, (name, blob)
        return "m", PICKNIK_SRC, "none", PICKNIK_LICENSE
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
    Sheet Summary: totals / min / max as formulas over Files, plus provenance notes.
    Every formula cell also stores its result, computed here, so viewers that do not calculate
    (Excel Protected View, pandas) show it; Excel recalculates on a normal (editable) open."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill

    shapes = []
    for r in recs:  # size class is read from the name; length is measured
        m = re.fullmatch(rf"peg_(.+)_{size}_{length}mm\.stl", r["file"])
        assert m, (r["file"], size, length)
        assert abs(r["z_mm"] - length) < 0.01, (r["file"], r["z_mm"], length)
        shapes.append(m[1])
    assert sorted(shapes) == sorted(PEG_SHAPES), shapes  # complete set, one file per shape
    # openpyxl writes floats as "%.16g"; round to that first so the stored results below are computed from
    # exactly the numbers Excel will read
    q = lambda v: None if v is None else float("%.16g" % v)
    recs = [dict(r, **{c: q(r[c]) for c in ("x_mm", "y_mm", "z_mm", "volume_cm3")}) for r in recs]
    title = f"FMB pegs, size {size}, length {length} mm"
    shared = {c: {r[c] for r in recs} for c in ("units", "source", "changes", "license")}
    assert all(len(v) == 1 for v in shared.values()), shared  # notes below state them once for all rows
    shared = {c: v.pop() for c, v in shared.items()}
    assert shared["units"] == "mm"  # the notes text says mm; units come from provenance(), not measured

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
    ws["A2"] = ("Measured from the STL files in this folder by make_index.py. index.csv has the same measurements "
                "(rounded) plus units, scale_to_mm, source, changes and license, which are in the Summary notes here.")
    ws["A2"].font = base
    head = ["file", "shape", "size_bytes", "size_MB", "stl_format", "triangles",
            "x_mm", "y_mm", "z_mm", "volume_cm3", "watertight", "sha256"]
    col = {h: chr(ord("A") + j) for j, h in enumerate(head)}
    fmt = {"size_bytes": "#,##0", "size_MB": "0.000", "triangles": "#,##0",
           "x_mm": "0.00", "y_mm": "0.00", "z_mm": "0.00", "volume_cm3": "0.0"}
    H = 4  # header row
    for h in head:
        c = ws[f"{col[h]}{H}"]
        c.value, c.font, c.fill = h, bold, head_fill
    first, last = H + 1, H + len(recs)
    for i, r in enumerate(recs, first):
        vals = dict(r, shape=re.fullmatch(r"peg_(.+)_[SML]_\d+mm\.stl", r["file"]).group(1))
        for h in head:
            if h == "size_MB":
                formula(ws, f"D{i}", f"C{i}/1000000", r["size_bytes"] / 1e6, base, fmt[h])
                continue
            c = ws[f"{col[h]}{i}"]
            c.value, c.font = vals[h], base
            if h in fmt:
                c.number_format = fmt[h]

    sizes = [r["size_bytes"] for r in recs]
    tris = [r["triangles"] for r in recs]
    vols = [r["volume_cm3"] for r in recs if r["volume_cm3"] is not None]
    assert vols, "no watertight part, volume statistics undefined"
    names = [r["file"] for r in recs]
    t = last + 1
    ws[f"A{t}"] = "Total"
    ws[f"A{t}"].font = bold
    formula(ws, f"C{t}", f"SUM(C{first}:C{last})", sum(sizes), bold, fmt["size_bytes"])
    formula(ws, f"D{t}", f"C{t}/1000000", sum(sizes) / 1e6, bold, fmt["size_MB"])
    formula(ws, f"F{t}", f"SUM(F{first}:F{last})", sum(tris), bold, fmt["triangles"])
    formula(ws, f"J{t}", f"SUM(J{first}:J{last})", sum(vols), bold, fmt["volume_cm3"])
    ws[f"K{t}"] = "(watertight parts)"
    ws[f"K{t}"].font = base
    for c, w in zip("ABCDEFGHIJKL", (32, 15, 12, 10, 11, 10, 9, 9, 9, 12, 16, 68)):
        ws.column_dimensions[c].width = w
    ws.freeze_panes = f"A{first}"

    s = wb.create_sheet("Summary")
    s["A1"] = f"Summary: {title}"
    s["A1"].font = Font(name="Arial", size=12, bold=True)
    for j, h in enumerate(("statistic", "value", "unit"), 1):
        c = s.cell(3, j, h)
        c.font, c.fill = bold, head_fill
    rng = lambda h: f"Files!{col[h]}{first}:{col[h]}{last}"
    A, C, F, G, H_, I, J, K = (rng(h) for h in ("file", "size_bytes", "triangles", "x_mm", "y_mm", "z_mm",
                                                "volume_cm3", "watertight"))
    rows = [
        ("files", f"COUNTA({A})", len(recs), "", "0"),
        ("watertight files", f"COUNTIF({K},TRUE)", sum(r["watertight"] for r in recs), "", "0"),
        ("total size", f"SUM({C})", sum(sizes), "bytes", "#,##0"),
        ("total size", f"SUM({C})/1000000", sum(sizes) / 1e6, "MB (1e6 bytes)", "0.000"),
        ("total triangles", f"SUM({F})", sum(tris), "", "#,##0"),
        ("total volume (watertight parts)", f"SUM({J})", sum(vols), "cm3", "0.0"),
        ("mean volume (watertight parts)", f"AVERAGE({J})", sum(vols) / len(vols), "cm3", "0.0"),
        ("min volume (watertight parts)", f"MIN({J})", min(vols), "cm3", "0.0"),
        ("max volume (watertight parts)", f"MAX({J})", max(vols), "cm3", "0.0"),
        ("largest volume part", f"INDEX({A},MATCH(MAX({J}),{J},0))",
         next(r["file"] for r in recs if r["volume_cm3"] == max(vols)), "", "@"),
        ("largest file", f"INDEX({A},MATCH(MAX({C}),{C},0))", names[sizes.index(max(sizes))], "", "@"),
        ("max x (footprint)", f"MAX({G})", max(r["x_mm"] for r in recs), "mm", "0.00"),
        ("max y (footprint)", f"MAX({H_})", max(r["y_mm"] for r in recs), "mm", "0.00"),
        ("min z (height)", f"MIN({I})", min(r["z_mm"] for r in recs), "mm", "0.00"),
        ("max z (height)", f"MAX({I})", max(r["z_mm"] for r in recs), "mm", "0.00"),
    ]
    for i, (label, f, result, unit, nf) in enumerate(rows, 4):
        s.cell(i, 1, label).font = base
        formula(s, f"B{i}", f, result, base, nf).alignment = Alignment(horizontal="right")
        s.cell(i, 3, unit).font = base
    n = 4 + len(rows) + 1
    notes = [
        ("Notes", None),
        ("units", "mm (STL coordinates, scale_to_mm = 1); "
                  "x/y/z = axis-aligned bounding box in the file's own orientation"),
        ("volume_cm3", "enclosed solid volume of the mesh, blank if not watertight; "
                       "printed mass also depends on infill and walls"),
        ("size_MB", "size_bytes / 1e6 (decimal MB, not MiB)"),
        ("sha256", "SHA-256 of the file bytes"),
        ("source", shared["source"]),
        ("changes", shared["changes"]),
        ("license", shared["license"]),
    ]
    for i, (k, v) in enumerate(notes, n):
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
