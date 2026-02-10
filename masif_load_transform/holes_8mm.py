import adsk.core
import adsk.cam

from models import PartContext


def holes_8mm(ctx: PartContext, occurrence, slot_name: str):
    ctx.log(f"holes_8mm START for {slot_name}")

    holes = _detect_8mm_holes(occurrence, ctx, slot_name)
    ctx.log(f"holes_8mm detected {len(holes)} cylindrical faces")
    if not holes:
        ctx.log("holes_8mm: no holes; skipping setup/op creation")
        return

    setup = _create_setup(ctx, occurrence, slot_name, op_name="holes_8mm")
    ctx._create_drill_op(setup, holes, slot_name)
    generate_gcode(ctx, occurrence, slot_name)
    ctx.log(f"holes_8mm END for {slot_name}")


def generate_gcode(ctx: PartContext, occurrence, slot_name: str):
    # Intentionally empty placeholder for future G-code export.
    ctx.log(f"holes_8mm G-code TODO for {slot_name}")


def _detect_8mm_holes(occurrence, ctx: PartContext, slot_name: str):
    faces = []
    bodies = occurrence.bRepBodies
    tol_cm = 0.02  # 0.2 mm tolerance in cm
    target_d_cm = 0.8  # 8 mm in cm
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
            if abs(diam - target_d_cm) > tol_cm:
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
                f"holes_8mm face {logged}: origin=({origin.x:.4f},{origin.y:.4f},{origin.z:.4f}) "
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




def _create_setup(ctx: PartContext, occurrence, slot_name: str, op_name: str):
    cam = ctx._get_cam_product()

    setup_input: adsk.cam.SetupInput = cam.setups.createInput(adsk.cam.OperationTypes.MillingOperation)
    bodies = occurrence.bRepBodies
    body_count = bodies.count
    assert body_count > 0, "No bodies available for setup models"
    ctx.log(f"Setup models: occurrence.bRepBodies.count={body_count}")


    #setup_input.models = bodies 
    # From some version .models is const vector reference; we must modify it instead
    body_list = [b for b in bodies]
    setup_input.models = body_list 
    setup_input.name = f"{slot_name}_{op_name}"
    # input.stockMode = adsk.cam.SetupStockModes.RelativeBoxStock
    # input.parameters.itemByName('job_stockOffsetMode').expression = "'keep'"

    setup = cam.setups.add(setup_input)
    ctx.log(f"Created setup: {setup.name}")
    return setup
