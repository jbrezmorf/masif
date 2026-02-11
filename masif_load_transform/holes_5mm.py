import adsk.core
import adsk.cam

from models import PartContext


def holes_5mm(ctx: PartContext, occurrence, slot_name: str):
    ctx.log(f"holes_5mm START for {slot_name}")
    slot_name=f"{slot_name}_2_5mm"
    holes = _detect_lt_7_5mm_holes(occurrence, ctx, slot_name)
    ctx.log(f"holes_5mm detected {len(holes)} cylindrical faces")
    if not holes:
        ctx.log("holes_5mm: no holes; skipping setup/op creation")
        return

    setup = _create_setup(ctx, occurrence, slot_name)
    tool_spec = dict(
        clearanceHeight="5 mm",
        retractHeight="2 mm",
        feedHeight="1 mm",
        topHeight="0 mm",
        bottomHeight="-0.2 mm",
        drillTipThroughBottom="true",
        useTipAngle="true",
        label="holes_5mm",
    )
    ctx.add_op_drill(
        setup,
        holes,
        slot_name,
        tool_name="5mm Spot Drill",
        **tool_spec,
    )
    ctx.add_op_transverse(setup, 0.0, 0.0)
    ctx.generate_gcode(setup, slot_name)
    ctx.log(f"holes_5mm END for {slot_name}")


def _detect_lt_7_5mm_holes(occurrence, ctx: PartContext, slot_name: str):
    faces = []
    bodies = occurrence.bRepBodies
    tol_cm = 0.02  # 0.2 mm tolerance in cm
    max_d_cm = 0.75  # 7.5 mm in cm
    z0_tol = 0.01  # 0.1 mm in cm
    logged = 0
    for i in range(bodies.count):
        body = bodies.item(i)
        for face in body.faces:
            geom = face.geometry
            if geom.surfaceType != adsk.core.SurfaceTypes.CylinderSurfaceType:
                continue
            cyl = adsk.core.Cylinder.cast(geom)
            if not cyl:
                continue
            diam = 2.0 * cyl.radius
            if diam - max_d_cm > tol_cm:
                continue

            axis = cyl.axis
            origin = axis.origin if hasattr(axis, "origin") else adsk.core.Point3D.create(0, 0, 0)
            direction = axis.direction if hasattr(axis, "direction") else axis
            length = (direction.x * direction.x + direction.y * direction.y + direction.z * direction.z) ** 0.5
            if length == 0:
                continue
            dot_z = abs(direction.z) / length
            bb = face.boundingBox
            logged += 1
            ctx.log(
                f"holes_5mm face {logged}: origin=({origin.x:.4f},{origin.y:.4f},{origin.z:.4f}) "
                f"dir=({direction.x:.4f},{direction.y:.4f},{direction.z:.4f}) "
                f"bb_min=({bb.minPoint.x:.4f},{bb.minPoint.y:.4f},{bb.minPoint.z:.4f}) "
                f"bb_max=({bb.maxPoint.x:.4f},{bb.maxPoint.y:.4f},{bb.maxPoint.z:.4f})",
            )

            if dot_z < 1.0 - z0_tol:
                continue
            if bb.maxPoint.z > z0_tol:
                continue
            if bb.maxPoint.z < -z0_tol:
                continue

            if not ctx.is_in_top(bb, slot_name):
                continue
            ctx.log("..add")

            faces.append(face)

    return faces


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
