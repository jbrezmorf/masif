import adsk.core
import adsk.fusion

from models import PartContext
from tools import mat_translation, mat_rotation, compose, bbox_dims_xyz


def load_and_split(ctx: PartContext):
    """
    Uses the preloaded original occurrence and creates 4 transformed
    "Paste New" component copies with names:
      top_right, bottom_right, top_left, bottom_left

    Returns:
        dict[str, adsk.fusion.Occurrence]  # slot_name -> created occurrence
    """
    app = ctx.app
    shift_z_after_rot_y_cm = ctx.config.shift_z_after_rot_y_cm

    doc = app.activeDocument
    design = adsk.fusion.Design.cast(doc.products.itemByProductType("DesignProductType"))
    if not design:
        raise RuntimeError("No active Design document.")

    root = design.rootComponent
    occs = root.occurrences

    ctx.log("=== load_and_split START ===")

    base_occ = ctx.original_occurrence
    if base_occ is None:
        raise RuntimeError("original_occurrence is not loaded")
    base_comp = base_occ.component
    ctx.log(f"Imported component name (raw): {base_comp.name}")

    # Measure dims from bounding box (current placement)
    bb = base_occ.boundingBox
    dims = ctx.dimensions
    thick, width, height = dims.x, dims.y, dims.z
    _, _, _, minp, maxp = bbox_dims_xyz(bb)

    ctx.log(f"BoundingBox min = ({minp.x:.6f}, {minp.y:.6f}, {minp.z:.6f})")
    ctx.log(f"BoundingBox max = ({maxp.x:.6f}, {maxp.y:.6f}, {maxp.z:.6f})")
    ctx.log(f"Dimensions (X,Y,Z) = thick={thick:.6f}  width={width:.6f}  height={height:.6f}")

    # Shift so minZ -> 0 (world Z)
    shift_to_zero_z = -minp.z
    base_shift = mat_translation(0, 0, shift_to_zero_z)
    ctx.log(f"Shift-to-zero: dz = {shift_to_zero_z:.6f} (so minZ -> 0)")

    # Apply shift to base occurrence for confirmation
    base_occ.transform = compose(base_occ.transform, base_shift)

    # Verify
    bb2 = base_occ.boundingBox
    _, _, _, minp2, _ = bbox_dims_xyz(bb2)
    ctx.log(f"After applying base shift to base_occ, minZ = {minp2.z:.9f}")

    # Axes
    AX_Y = adsk.core.Vector3D.create(0, 1, 0)
    AX_Z = adsk.core.Vector3D.create(0, 0, 1)

    # Raw slot transforms (without base shift)
    tr_top_right_raw = compose(
        mat_rotation(270, AX_Y),
        mat_translation(0, 0, shift_z_after_rot_y_cm),
        mat_translation(height, 0, 0),
    )

    tr_bottom_right_raw = compose(
        mat_rotation(270, AX_Y),
        mat_translation(0, 0, shift_z_after_rot_y_cm),
        mat_rotation(180, AX_Z),
        mat_translation(0, width, 0),
    )

    tr_top_left_raw = compose(
        mat_rotation(90, AX_Y),
        mat_rotation(180, AX_Z),
        mat_translation(height, 0, 0),
        mat_translation(0, width, 0),
    )

    tr_bottom_left_raw = compose(
        mat_rotation(90, AX_Y),
    )

    # Apply base shift to all slot transforms (key fix)
    tr_top_right = compose(base_shift, tr_top_right_raw)
    tr_bottom_right = compose(base_shift, tr_bottom_right_raw)
    tr_top_left = compose(base_shift, tr_top_left_raw)
    tr_bottom_left = compose(base_shift, tr_bottom_left_raw)

    def add_named_copy(slot_name: str, tr: adsk.core.Matrix3D):
        new_occ = occs.addNewComponentCopy(base_comp, tr)
        if not new_occ:
            raise RuntimeError(f"addNewComponentCopy failed for slot {slot_name}")
        try:
            new_occ.component.name = slot_name
        except:
            pass
        ctx.log(f"Created slot: {slot_name}")
        return new_occ

    created = {
        "top_right": add_named_copy("top_right", tr_top_right),
        "bottom_right": add_named_copy("bottom_right", tr_bottom_right),
        "top_left": add_named_copy("top_left", tr_top_left),
        "bottom_left": add_named_copy("bottom_left", tr_bottom_left),
    }

    if ctx.config.delete_base_import_occurrence:
        try:
            base_occ.deleteMe()
            ctx.log("Deleted original imported occurrence (kept only 4 slots).")
        except:
            ctx.log("WARNING: Could not delete original imported occurrence.")

    ctx.log("=== load_and_split END ===")
    return created
