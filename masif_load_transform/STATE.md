Project State Summary (as of last interaction)

Overview
- Fusion 360 Python script that imports a STEP model, creates 4 transformed copies, and runs CAM operations per copy.
- Primary entry: masif_load_transform.py (scripts are reloaded on import to avoid stale module issues).
- Logging: centralized via PartContext.log (Logger uses TextCommands + file).
- Log file is deleted at start of each run and named after the STEP stem.

Key Modules
- masif_load_transform.py
  - Builds JobConfig, creates PartContext (which loads STEP immediately), then calls load_and_split and processing pipeline.
  - process_all -> copy_process -> holes_8mm / mill / holes_5mm.
- models.py
  - JobConfig (paths, shift, delete_base_import_occurrence).
  - PartContext: constructor loads STEP; stores original_occurrence.
  - dimensions is a cached_property derived from original_occurrence bounding box (returns a Point3D diff).
  - is_in_top(bb, slot_name) handles top/bottom filtering using part height.
- split.py
  - Uses ctx.original_occurrence (already imported in PartContext.load).
  - Computes base shift to minZ=0, creates 4 transformed copies named:
    top_right, bottom_right, top_left, bottom_left.
  - Deletes the original imported occurrence (configurable).
- holes_8mm.py
  - Detects cylindrical faces of ~8mm diameter (0.8 cm), checks axis alignment to Z.
  - Filters by Z=0 plane and ctx.is_in_top(bb, slot_name).
  - Logs each detected face origin/direction/bbox.
  - Creates CAM setup per slot and drilling operation (if CAM product present).
  - G-code generation is a placeholder.
- mill.py / holes_5mm.py
  - Stub implementations (only logging).

Known Behaviors/Constraints
- PartContext.load imports STEP into the active design and sets original_occurrence.
- All operations assume Fusion 360 context; no external code execution.
- Units are treated as centimeters in geometry contexts (8mm = 0.8 cm).
- CAM product may not be available; holes_8mm skips setup if CAM is not loaded.

Open Work
- Implement holes_5mm detection and operation logic.
- Implement mill detection at Z = -0.1 cm and coarse/fine operations.
- Implement actual G-code generation + filename convention.
- Confirm PartDimensions type/usage (dimensions currently returns a Point3D diff).

User Preferences/Constraints
- Do not ask questions; proceed with best-effort assumptions.
- Avoid generic try/except blocks that hide errors.
