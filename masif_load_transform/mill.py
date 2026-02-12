import adsk.core
import adsk.cam
import adsk.fusion

from models import PartContext


def mill(ctx: PartContext, occurrence, slot_name: str):
    ctx.log(f"mill START for {slot_name}")
    slot_name = f"{slot_name}_mill"
    faces = _detect_pocket_faces(occurrence, ctx, slot_name)
    ctx.log(f"mill detected {len(faces)} pocket faces")
    if not faces:
        ctx.log("mill: no pocket faces; skipping setup/op creation")
        return

    setup = _create_setup(ctx, occurrence, slot_name)
    #_, profiles = _build_pocket_profiles(ctx, occurrence, faces)
    tool_name = "8mm Flat Endmill"

    # _add_pocket_op(
    #     ctx,
    #     setup,
    #     faces,
    #     profiles,
    #     slot_name,
    #     op_name="mill_rough",
    #     tool_name=tool_name,
    #     stockToLeave="true",
    #     radialStockToLeave="0.3 mm",
    #     axialStockToLeave="0.2 mm",
    # )
    # _add_pocket_op(
    #     ctx,
    #     setup,
    #     faces,
    #     profiles,
    #     slot_name,
    #     op_name="mill_finish",
    #     tool_name=tool_name,
    #     stockToLeave="false",
    #     radialStockToLeave="0 mm",
    #     axialStockToLeave="0 mm",
    # )

    # ctx.add_op_transverse(setup, 0.0, 0.0)
    # ctx.generate_gcode(setup, slot_name)
    # ctx.log(f"mill END for {slot_name}")


def _detect_pocket_faces(occurrence, ctx: PartContext, slot_name: str):
    faces = []
    bodies = occurrence.bRepBodies
    target_z_cm = -0.1  # -1 mm in cm
    z_tol = 0.01  # 0.1 mm in cm
    normal_tol = 0.01
    logged = 0
    for i in range(bodies.count):
        body = bodies.item(i)
        for face in body.faces:
            geom = face.geometry
            if geom.surfaceType != adsk.core.SurfaceTypes.PlaneSurfaceType:
                continue
            plane = adsk.core.Plane.cast(geom)
            if not plane:
                continue
            normal = plane.normal
            nlen = normal.length
            if nlen == 0:
                continue
            dot_z = abs(normal.z) / nlen
            if dot_z < 1.0 - normal_tol:
                continue

            bb = face.boundingBox
            if abs(bb.minPoint.z - target_z_cm) > z_tol:
                continue
            if abs(bb.maxPoint.z - target_z_cm) > z_tol:
                continue

            logged += 1
            ctx.log(
                f"mill face {logged}: bb_min=({bb.minPoint.x:.4f},{bb.minPoint.y:.4f},{bb.minPoint.z:.4f}) "
                f"bb_max=({bb.maxPoint.x:.4f},{bb.maxPoint.y:.4f},{bb.maxPoint.z:.4f})",
            )

            if not ctx.is_in_top(bb, slot_name):
                continue

            faces.append(face)
    return faces


def _build_pocket_profiles(ctx: PartContext, occurrence, faces):
    if not faces:
        return None, []
    doc = ctx.app.activeDocument
    design = adsk.fusion.Design.cast(doc.products.itemByProductType("DesignProductType"))
    if not design:
        raise RuntimeError("No active Design document.")
    root = design.rootComponent
    sketch = root.sketches.add(faces[0])
    edge_col = adsk.core.ObjectCollection.create()
    # for face in faces:
    #     for loop in face.loops:
    #         if not loop.isOuter:
    #             continue
    #         for coe in loop.coEdges:
    #             edge_col.add(coe.edge)
    # if edge_col.count > 0:
    #     sketch.project(edge_col)
    # profiles = [sketch.profiles.item(i) for i in range(sketch.profiles.count)]
    # ctx.log(f"mill: pocket sketch profiles count={len(profiles)}")
    profiles = []
    return sketch, profiles


def _add_pocket_op(
    ctx: PartContext,
    setup,
    faces,
    profiles,
    slot_name: str,
    op_name: str,
    tool_name: str,
    **kw_args,
):
    tool = ctx._find_tool_by_full_name(tool_name)
    op_in: adsk.core.OperationInput = setup.operations.createInput("pocket2d")
    op_in.displayName = f"{slot_name}_{op_name}"
    op_in.tool = tool

    if not _set_pocket_geometry(ctx, op_in, profiles, faces):
        _log_op_params(ctx, op_in)
        raise RuntimeError("No compatible pocket geometry parameter found.")

    def set_expr(param_name: str, expr: str):
        prm = op_in.parameters.itemByName(param_name)
        if prm:
            prm.expression = expr

    for k, v in kw_args.items():
        try:
            set_expr(k, v)
        except RuntimeError as e:
            ctx.log(f"Invalid value: {k} = {v}.")
            raise e

    op = setup.operations.add(op_in)
    ctx.log(f"Created pocket op: {op_in.displayName}")
    return op


def _set_pocket_geometry(ctx: PartContext, op_in, profiles, faces) -> bool:
    profile_list = profiles or []
    face_list = faces or []
    candidates = [
        ("pocketSelection", profile_list),
        ("pockets", profile_list),
        ("pocketProfiles", profile_list),
        ("machiningBoundary", profile_list),
        ("machiningBoundaries", profile_list),
        ("pocketFaces", face_list),
        ("faces", face_list),
        ("selectedFaces", face_list),
    ]
    for name, items in candidates:
        if not items:
            continue
        p = op_in.parameters.itemByName(name)
        if not p:
            continue
        try:
            p.value.value = items
            ctx.log(f"mill: using geometry param '{name}' with {len(items)} items")
            return True
        except Exception as ex:
            ctx.log(f"mill: failed to set '{name}': {ex}")
    return False


def _log_op_params(ctx: PartContext, op_in):
    try:
        names = [op_in.parameters.item(i).name for i in range(op_in.parameters.count)]
        ctx.log(f"mill op params: {names}")
    except Exception:
        pass


def _create_setup(ctx: PartContext, occurrence, slot_name: str):
    cam = ctx._get_cam_product()

    setup_input: adsk.cam.SetupInput = cam.setups.createInput(adsk.cam.OperationTypes.MillingOperation)
    bodies = occurrence.bRepBodies
    body_count = bodies.count
    assert body_count > 0, "No bodies available for setup models"
    ctx.log(f"Setup models: occurrence.bRepBodies.count={body_count}")

    body_list = [b for b in bodies]
    setup_input.models = body_list
    setup_input.name = slot_name

    setup = cam.setups.add(setup_input)
    ctx.log(f"Created setup: {setup.name}")
    return setup
