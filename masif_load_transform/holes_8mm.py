import adsk.core
import adsk.fusion
import adsk.cam
from pathlib import Path

from models import PartContext


def holes_8mm(ctx: PartContext, occurrence, slot_name: str):
    ctx.log(f"holes_8mm START for {slot_name}")

    holes = _detect_8mm_holes(occurrence, ctx, slot_name)
    ctx.log(f"holes_8mm detected {len(holes)} cylindrical faces")
    if not holes:
        ctx.log("holes_8mm: no holes; skipping setup/op creation")
        return

    setup = _create_setup(ctx, occurrence, slot_name, op_name="holes_8mm")
    _create_drill_op(ctx, setup, holes, slot_name)
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
    cam = _get_cam_product(ctx)

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


def _get_cam_product(ctx: PartContext):
    doc = ctx.app.activeDocument
    cam, prod = _find_cam_in_products(doc)
    if cam:
        _log_cam_info(ctx, cam, prod, "CAM product found")
        return cam

    ctx.log("CAM product not found; attempting to activate Manufacture workspace")
    ws = ctx.ui.workspaces.itemById("CAMEnvironment")
    if ws is None:
        ws = ctx.ui.workspaces.itemById("FusionCAMEnvironment")
    if ws:
        ws.activate()
    else:
        ctx.log("Manufacture workspace id not found")

    cam, prod = _find_cam_in_products(doc)
    assert cam, "Failed to get CAM product"
    _log_cam_info(ctx, cam, prod, "CAM product found after activation")
    return cam

    

def _find_cam_in_products(doc):
    for i in range(doc.products.count):
        prod = doc.products.item(i)
        if prod.productType == "CAMProductType":
            return adsk.cam.CAM.cast(prod), prod
    return None, None


def _log_cam_info(ctx: PartContext, cam, prod, prefix: str):
    prod_name = getattr(prod, "name", "")
    prod_type = getattr(prod, "productType", "")
    cam_type = getattr(cam, "objectType", "")
    ctx.log(f"{prefix}: productType={prod_type} name={prod_name} objectType={cam_type}")


def _create_drill_op(ctx: PartContext, setup, holes, slot_name: str):
    op = _apply_template_to_setup(ctx, setup, "masif_drill_8mm")
    op_name = f"{slot_name}_holes_8mm"
    op.displayName = op_name
    
    _set_drill_hole_faces(ctx, op, holes)

    ctx.log(f"Created drilling op from template: {op_name}")

    holeSelection: adsk.cam.CadObjectParameterValue = op.parameters.itemByName('holeFaces').value
    holeSelection.value = holes

    # Read back to confirm it stuck
    readback = holeSelection.value
    ctx.log(f"Drill op holeFaces set: count={len(readback)}")
    # op: adsk.cam.Operation = setup.operations.add(op)
    # Operation should already be within setup.
    return op


def _apply_template_to_setup(ctx: PartContext, setup, template_name: str):
    template_path = Path(ctx.config.template_dir) / f"{template_name}.f3dhsm-template"
    ctx.log(f"Template file: {template_path}")
    if not template_path.exists():
        raise RuntimeError(f"Template file not found: {template_path}")

    cam_template = adsk.cam.CAMTemplate.createFromFile(str(template_path))
    template_input = adsk.cam.CreateFromCAMTemplateInput.create()
    template_input.camTemplate = cam_template
    created_items = setup.createFromCAMTemplate2(template_input)
    assert len(created_items) == 1, f"Expected single operation from template: {created_items}"    
    ctx.log(f"Template applied: created_items count={len(created_items)}")
    op = created_items[0]
    ctx.log(f"Operation: item: name={op.name} objectType={op.objectType}")
    return op
