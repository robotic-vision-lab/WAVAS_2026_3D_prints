# WAVAS 2026 3D prints

| folder | contents | index |
|---|---|---|
| `final_stl/` | board L, size-L 100 mm pegs in 8 shapes (no circle), peg fixture, PickNik camera adapter | [`index.csv`](final_stl/index.csv) |
| `pegs_M_150mm/` | the 9 FMB pegs (all 9 shapes) in size M, length 150 mm | [`index.csv`](pegs_M_150mm/index.csv), [`index.xlsx`](pegs_M_150mm/index.xlsx) |

Each `index.csv` has one row per STL in its folder. `index.xlsx` has two sheets:

- `Files`: the measured columns of `index.csv` unrounded, plus a `shape` column taken from the file name.
  Units (mm, `scale_to_mm` = 1), source, changes and license are the same for all 9 files and are listed once in
  the `Summary` notes.
- `Summary`: totals, min / max, the largest part, and those notes.

`size_MB`, the totals and the `Summary` statistics are Excel formulas, and the file also stores their results.
Excel Protected View (how a downloaded file usually opens) and openpyxl / pandas show the stored results; a normal
Excel open recalculates them. Use `index.csv` for scripts.

## Before printing

STL files carry no unit. Check the `units` column:

- `mm` — load as is.
- `m` — the coordinates are metres. Import as metres or scale by `scale_to_mm` (×1000) in the slicer.
  This applies to `picknik_ur5_realsense_camera_adapter_rev2.STL`.

## index.csv columns

| column | meaning |
|---|---|
| `file` | file name inside the folder |
| `size_bytes` | exact file size |
| `size_MB` | `size_bytes / 1e6` (decimal megabytes, not MiB) |
| `stl_format` | `binary` or `ascii` |
| `triangles` | facet count read from the file |
| `units` | what one native coordinate means (declared in `make_index.py`, not stored in the STL) |
| `scale_to_mm` | factor that turns native coordinates into millimetres |
| `x_mm`, `y_mm`, `z_mm` | axis-aligned bounding box in the file's own orientation, in mm |
| `volume_cm3` | enclosed volume; empty if the mesh is not watertight |
| `watertight` | every edge shared by exactly two facets |
| `sha256` | SHA-256 of the file bytes |
| `source`, `changes`, `license` | where the part comes from, what was changed, and its license |

Regenerate every index with `python make_index.py` (needs `trimesh` and `openpyxl`; tested with Python 3.14.0,
trimesh 5.1.0, numpy 2.5.1, openpyxl 3.1.5). A re-run reproduces both `index.csv` and `index.xlsx` byte for byte.

## Sources and licenses

- **Board, pegs, peg fixture** — from the CAD files of
  [FMB: A Functional Manipulation Benchmark for Generalizable Robotic Learning](https://functional-manipulation-benchmark.github.io/)
  (Jianlan Luo, Charles Xu, Fangchen Liu, Liam Tan, Zipeng Lin, Jeffrey Wu, Pieter Abbeel, Sergey Levine),
  licensed [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).
  Changes: each STEP solid was tessellated to its own STL and translated so that the XY bounding-box centre is at the
  origin and the lowest point is at z = 0.
- **`picknik_ur5_realsense_camera_adapter_rev2.STL`** — unmodified from
  [PickNikRobotics/picknik_accessories](https://github.com/PickNikRobotics/picknik_accessories) (commit `3b0912d`),
  BSD-3-Clause, Copyright (c) 2024 PickNik Inc. License text: [`final_stl/LICENSE.picknik.txt`](final_stl/LICENSE.picknik.txt).
