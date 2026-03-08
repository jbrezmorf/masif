import adsk.core

from feeds_speeds import drill_feed_speed_params
from models import PartContext


def holes_5mm(ctx: PartContext, occurrence, slot_name: str):
    ctx.log(f"holes_5mm START for {slot_name}")
    slot_name=f"{slot_name}_2_5mm"
    mark_depth_mm = 1.0
    tool_name = "4.5mm default drill"
    holes_exact, holes_shallow = _detect_lt_7_5mm_holes(occurrence, ctx, slot_name)
    ctx.log(f"holes_5mm detected exact={len(holes_exact)} shallow={len(holes_shallow)} cylindrical faces")
    if not holes_exact and not holes_shallow:
        ctx.log("holes_5mm: no holes; skipping setup/op creation")
        return

    setup = ctx.create_setup(occurrence, slot_name)
    tool_spec_full = dict(
        # Clearance Height: safe Z to move around without hitting stock/clamps
        clearanceHeight_mode="from wcs",
        clearanceHeight_value=f"{ctx.config.safe_z_mm} mm",

        # Retract Height: Z to pull up to between hole positions (above the part)
        retractHeight_mode="from wcs",
        retractHeight_value=f"{ctx.config.safe_z_mm} mm",

        # Feed Height: Z where the tool switches from rapid to feed before entering the hole
        feedHeight_mode="from wcs",
        feedHeight_value=f"{ctx.config.cycle_plane_z_mm} mm",

        # Top Height: the Z level considered the top of the drilling feature/entry surface
        topHeight_mode="from hole top",
        topHeight_offset="0 mm",

        # Bottom Height: the Z level considered the drilling depth limit (hole end + breakthrough)
        bottomHeight_mode="from hole bottom",
        bottomHeight_offset="-0.2 mm",

        # Cycle options
        drillTipThroughBottom=True,
    )
    tool_spec_full.update(drill_feed_speed_params(tool_diameter_mm=5.0))
    tool_spec_shallow = dict(tool_spec_full)
    tool_spec_shallow.update(dict(
        bottomHeight_mode="from hole top",
        bottomHeight_offset=f"-{mark_depth_mm:g} mm",
        drillTipThroughBottom=False,
    ))
    ctx.log(
        f"holes_5mm drilling spec: tool={tool_name} "
        f"exact_top={tool_spec_full['topHeight_mode']} shallow_mark_depth={mark_depth_mm:.3f} mm"
    )
    if holes_exact:
        ctx.add_op_drill(
            setup,
            holes_exact,
            slot_name,
            tool_name=tool_name,
            **tool_spec_full,
        )
    if holes_shallow:
        ctx.add_op_drill(
            setup,
            holes_shallow,
            slot_name,
            tool_name=tool_name,
            **tool_spec_shallow,
        )
    ctx.add_op_transverse(setup, 0.0, 0.0)
    ctx.generate_gcode(setup, slot_name)
    ctx.log(f"holes_5mm END for {slot_name}")


def _detect_lt_7_5mm_holes(occurrence, ctx: PartContext, slot_name: str):
    exact = []
    shallow = []
    bodies = occurrence.bRepBodies
    tol_cm = 0.02  # 0.2 mm tolerance in cm
    target_d_cm = 0.5  # 5 mm in cm
    max_d_cm = 0.55  # 7.5 mm in cm
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
                f"dir=({direction.x:.4f},{direction.y:.4f},{direction.z:.4f}) d={diam:.2f}"
                f"bb_min=({bb.minPoint.x:.4f},{bb.minPoint.y:.4f},{bb.minPoint.z:.4f}) "
                f"bb_max=({bb.maxPoint.x:.4f},{bb.maxPoint.y:.4f},{bb.maxPoint.z:.4f})",
            )

            if dot_z < 1.0 - z0_tol:
                continue
            if bb.maxPoint.z > z0_tol:
                continue
            if bb.maxPoint.z < -z0_tol - 0.1:   # milled 1mm
                continue
            ctx.log("top surface")
                
            if not ctx.is_in_top(bb, slot_name):
                continue
            ctx.log("active height")

            if abs(diam - target_d_cm) <= tol_cm:
                ctx.log("..add exact")
                exact.append(face)
            else:
                ctx.log("..add shallow")
                shallow.append(face)

    return exact, shallow
