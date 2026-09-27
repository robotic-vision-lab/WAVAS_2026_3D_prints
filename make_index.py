"""Write final_stl/index.csv: one row per STL in final_stl/ (file size, mesh stats, provenance).

size, format, triangles, extents, volume, watertight and sha256 are measured from the file.
units / source / changes / license are declared below by file name, not measured (only the PickNik file is
checked against its upstream blob id); a name that matches no rule is an error.
STL carries no unit; `units` is what one native coordinate means, x/y/z/volume are converted to mm / cm3.
size_MB = size_bytes / 1e6.
"""
import csv
import hashlib
import struct
from pathlib import Path

import trimesh

DIR = Path(__file__).parent / "final_stl"

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


def main():
    rows = []
    for p in sorted(DIR.iterdir(), key=lambda p: p.name.lower()):
        if p.suffix.lower() != ".stl":
            continue
        raw = p.read_bytes()
        fmt, n = triangles(p, raw)
        m = trimesh.load(p, force="mesh")
        assert len(m.faces) == n, (p.name, len(m.faces), n)

        unit, src, changes, lic = provenance(p.name, raw)
        k = SCALE[unit]
        ext = m.extents * k
        assert 10 < ext.max() < 500, (p.name, unit, ext)  # a printable part, not a unit mix-up
        rows.append([
            p.name,
            len(raw),
            f"{len(raw) / 1e6:.3f}",
            fmt,
            n,
            unit,
            k,
            *(f"{v:.2f}" for v in ext),
            f"{m.volume * k**3 / 1000:.1f}" if m.is_watertight else "",
            m.is_watertight,
            hashlib.sha256(raw).hexdigest(),
            src,
            changes,
            lic,
        ])

    with open(DIR / "index.csv", "w", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["file", "size_bytes", "size_MB", "stl_format", "triangles", "units", "scale_to_mm",
                    "x_mm", "y_mm", "z_mm", "volume_cm3", "watertight", "sha256", "source", "changes", "license"])
        w.writerows(rows)
    print(f"{len(rows)} files, {sum(r[1] for r in rows)} bytes -> {DIR / 'index.csv'}")


if __name__ == "__main__":
    main()
