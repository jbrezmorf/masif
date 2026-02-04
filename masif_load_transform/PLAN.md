# Plan

## Goal
- Build a Fusion 360 Python workflow to load a model, generate four aligned manufacturing copies, run three CAM operations per copy, and export G-code files following the specified naming convention.

## Assumptions
- Script runs inside Fusion 360 (no external execution).
- Units are consistent with Fusion internal cm context; the alignment targets origin at top-left with Z- into the part.
- Tooling is limited to three tools: 8mm drill, 5mm drill, and a mill (coarse/fine templates).

## Steps
1. Define core data models (dataclasses) for configuration, model metadata, and operation outputs.
2. Implement model import and 4x transform alignment (top/bottom, left/right), ensuring the part extends to X+, Y+, Z- with top-left at origin.
3. Implement `copy_process` orchestration to loop copies and call `holes_8mm`, `mill`, `holes_5mm`, then export G-code with the required naming.
4. Add separate module for `holes_8mm` using detection by diameter and a template-driven drill operation; document how to create/locate the template.
5. Implement `mill` to detect horizontal faces at Z = -0.1 cm and run coarse + fine milling templates.
6. Implement `holes_5mm` to detect holes ≤ 0.5 cm, drilling full-depth for 0.5 cm and spotting 1 mm for smaller holes.
7. Implement common G-code export function and logging hooks (tools.Logger) for each step.
8. Add minimal usage documentation and configuration guidance (paths, templates, tool names, naming scheme).

## Deliverables
- New/updated modules per function (`holes_8mm.py`, `mill.py`, `holes_5mm.py`, orchestration module).
- Shared dataclasses for config and part context.
- G-code export utility with filename convention: `<basename>_<L/R><top/bot>_<op name>`.
- Short instructions on creating and referencing Fusion CAM templates.
