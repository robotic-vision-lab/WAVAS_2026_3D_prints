# WAVAS 2026 3D prints

`final_stl/` holds the STL files to print. [`final_stl/index.csv`](final_stl/index.csv) has one row per file.

## Before printing

STL files carry no unit. Check the `units` column:

- `mm` — load as is.
- `m` — the coordinates are metres. Import as metres or scale by `scale_to_mm` (×1000) in the slicer.
  This applies to `picknik_ur5_realsense_camera_adapter_rev2.STL`.

## index.csv columns

| column | meaning |
|---|---|
| `file` | file name inside `final_stl/` |
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

Regenerate with `python make_index.py` (needs `trimesh`; tested with Python 3.14.0, trimesh 5.1.0, numpy 2.5.1).

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
