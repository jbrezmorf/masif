import adsk.core
import adsk.cam
import time
from pathlib import Path

#from models import PartContext


def holes_8mm(ctx: PartContext, occurrence, slot_name: str):
    ctx.log(f"holes_8mm START for {slot_name}")

    holes = _detect_8mm_holes(occurrence, ctx, slot_name)
    ctx.log(f"holes_8mm detected {len(holes)} cylindrical faces")
    if not holes:
        ctx.log("holes_8mm: no holes; skipping setup/op creation")
        return

    setup = _create_setup(ctx, occurrence, slot_name, op_name="holes_8mm")
    tool_spec = dict(
        # Heights: set in mm explicitly to avoid unit surprises
        clearanceHeight="5 mm",
        retractHeight="2 mm",
        feedHeight="1 mm",
        topHeight="0 mm",

        # Bottom: drill through slightly (tweak if you want)
        bottomHeight="-0.2 mm",

        # Drill cycle options (names vary by post; set only if they exist)
        drillTipThroughBottom="true",   # common flag
        useTipAngle="true",             # sometimes used for point compensation
        label="holes_8mm",
        #tool_type="drill",
        #diameter_mm=8.0,
        #diameter_tolerance_mm=0.2,
    )
    ctx.add_op_drill(
        setup,
        holes,
        slot_name,
        tool_name="8mm Flat Endmill",
        **tool_spec,
    )
    ctx.add_op_transverse(setup, 0.0, 0.0)
    generate_gcode(ctx, setup, occurrence, slot_name)
    ctx.log(f"holes_8mm END for {slot_name}")


def generate_gcode(ctx: PartContext, setup, occurrence, slot_name: str):
    op_name = "holes_8mm"
    ctx.log(f"holes_8mm G-code START for {slot_name} setup={getattr(setup, 'name', '?')}")

    output_dir = ctx.config.ncdir
    output_dir.mkdir(parents=True, exist_ok=True)
    file_stem = _build_gcode_stem(ctx, slot_name)

    post_config = Path(ctx.config.template_dir) / "uccnc.cps"
    if not post_config.exists():
        raise RuntimeError(f"Post config not found: {post_config}")
    ctx.log(f"holes_8mm G-code: using post config: {post_config}")

    units = adsk.cam.PostOutputUnitOptions.MillimetersOutput
    output_file = str(output_dir / file_stem)
    ctx.log(
        f"Post settings: output_dir={output_dir} file_stem={file_stem} "
        f"post_config={post_config} units={units}"
    )

    post_input = _create_post_input(ctx, output_file, post_config, output_dir, units)
    post_input.programName = file_stem
    post_input.isOpenInEditor = False

    _generate_toolpaths(ctx, setup)

    targets = adsk.core.ObjectCollection.create()
    targets.add(setup)
    cam = ctx._get_cam_product()

    try:
        ok = cam.postProcess(targets, post_input)
        ctx.log(f"holes_8mm G-code: postProcess ok={ok}")
    except Exception as ex:
        ctx.log(f"holes_8mm G-code: postProcess failed: {ex}")
        return

    ctx.log(f"holes_8mm G-code END for {slot_name}")


def _build_gcode_stem(ctx: PartContext, slot_name: str) -> str:
    return f"{Path(ctx.config.step_path).stem}_{slot_name}"


def _generate_toolpaths(ctx: PartContext, setup):
    cam = ctx._get_cam_product()

    ops = getattr(setup, "operations", None)
    targets = adsk.core.ObjectCollection.create()
    if ops and getattr(ops, "count", 0) > 0:
        for i in range(ops.count):
            targets.add(ops.item(i))
        ctx.log(f"holes_8mm G-code: generating toolpaths for {ops.count} operations")
        future = cam.generateToolpath(targets)
    else:
        ctx.log("holes_8mm G-code: generating toolpaths for setup")
        future = cam.generateToolpath(setup)

    # Don't use hasattr on properties like isGenerationCompleted (getter may throw)
    if not future or getattr(future, "objectType", "") != "adsk::cam::GenerateToolpathFuture":
        # Some older calls can return bool; treat False as failure.
        if isinstance(future, bool) and not future:
            raise RuntimeError("Toolpath generation failed (bool False)")
        return

    start = time.time()

    # Give Fusion a chance to actually start the generation
    adsk.doEvents()
    time.sleep(0.05)

    while True:
        adsk.doEvents()

        # Tolerate the transient "Generation not started" state
        try:
            done = future.isGenerationCompleted
        except RuntimeError as ex:
            if "Generation not started" in str(ex):
                done = False
            else:
                raise

        if done:
            # These can also throw in some builds; guard them too
            try:
                if getattr(future, "hasError", False):
                    raise RuntimeError(getattr(future, "errorMessage", "Toolpath generation failed"))
            except RuntimeError:
                # If even hasError/errorMessage are flaky, just break and let post reveal issues
                pass
            break

        if time.time() - start > 300:
            raise RuntimeError("Toolpath generation timeout (300s)")

        time.sleep(0.05)


def _create_post_input(ctx: PartContext, output_file: str, post_config: str, output_dir: Path, units):
    assert units is not None, "PostProcessInput units must be set"
    return adsk.cam.PostProcessInput.create(
        output_file,
        str(post_config),
        str(output_dir),
        units,
    )




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
