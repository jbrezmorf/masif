import adsk.core

from feeds_speeds import mill_feed_speed_params
from models import PartContext


def mill(ctx: PartContext, occurrence, slot_name: str):
    ctx.log(f"mill START for {slot_name}")
    slot_name = f"{slot_name}_1_mill"
    faces = _detect_pocket_faces(occurrence, ctx, slot_name)
    ctx.log(f"mill detected {len(faces)} pocket faces")
    if not faces:
        ctx.log("mill: no pocket faces; skipping setup/op creation")
        return

    setup = ctx.create_setup(occurrence, slot_name)
    chains = build_pocket_chains(faces)
    tool_name = "8mm Flat Endmill"

    # Minimal, stable 2D Pocket params (tune feeds elsewhere if needed)
    pocket_spec = dict(
        # Heights (same system as your drill: *_mode/_offset)
        clearanceHeight_mode="from retract height",
        clearanceHeight_offset="8 mm",

        retractHeight_mode="from stock top",
        retractHeight_offset="2.5 mm",

        feedHeight_mode="from stock top",
        feedHeight_offset="1.5 mm",

        topHeight_mode="from stock top",
        topHeight_offset="0 mm",

        # Bottom of pocket plane (your faces are at -1mm from stock top)
        # Either drive to "from selection" with offset 0, or directly set bottomHeight_value.
        # Start with selection-based, because you already have pocket bottom faces.
        bottomHeight_mode="from stock top",
        bottomHeight_offset="-1 mm",


        # Linking / ramp stuff that causes your warnings
        entry_verticalRadius="0.2 mm",
        rampAngle="2 deg",
        rampClearanceHeight="0.5 mm",
        rightCompensation = False,

        # IMPORTANT for “don’t mill outside”: keep cutter comp in computer
        # (If your post/strategy uses different token, your logger will show it.)
        compensationType="computer",

        # Stock to leave (roughing style)
        useStockToLeave=False,
        stockToLeave="0 mm",
        verticalStockToLeave="0 mm",

        doFinishingPasses=True,
        finishingStepover="0.3 mm",
        numberOfFinishingStepovers="1",
        leadsForAllFinishingPasses=True,

        useStockContours=False,
    )
    pocket_spec.update(mill_feed_speed_params(tool_diameter_mm=8.0, flutes=2))
    print(pocket_spec)
    ctx.add_op_pocket2d(
        setup,
        pocket_chains=chains,
        slot_name=slot_name,
        tool_name=tool_name,
        **pocket_spec,
    )

    ctx.add_op_transverse(setup, 0.0, 0.0)
    ctx.generate_gcode(setup, slot_name)
    ctx.log(f"mill END for {slot_name}")

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


def build_pocket_chains(pocket_faces):
    """
    pocket_faces: list[BRepFace] for all pockets (4 faces per pocket).
    Returns: list[list[BRepEdge]] ordered closed chains (one per pocket).
    """
    if not pocket_faces:
        return []

    # 1) Count edges across all faces; keep only edges referenced once => outer boundaries
    edge_counts = {}
    token_to_edge = {}

    for f in pocket_faces:
        outer = next((loop for loop in f.loops if loop.isOuter), None)
        if not outer:
            continue

        for coe in outer.coEdges:
            e = coe.edge
            tok = e.entityToken
            token_to_edge[tok] = e
            edge_counts[tok] = edge_counts.get(tok, 0) + 1

    boundary_edges = [token_to_edge[tok] for tok, c in edge_counts.items() if c == 1]
    if not boundary_edges:
        return []

    # 2) Build vertex -> incident boundary edges
    v_to_edges = {}          # vertexToken -> list[BRepEdge]
    endpoints = {}           # edgeToken -> (v1, v2)
    for e in boundary_edges:
        v1 = e.startVertex.entityToken
        v2 = e.endVertex.entityToken
        endpoints[e.entityToken] = (v1, v2)
        v_to_edges.setdefault(v1, []).append(e)
        v_to_edges.setdefault(v2, []).append(e)

    # 3) Walk cycles (each cycle == one pocket boundary)
    used_edges = set()
    loops = []

    for e0 in boundary_edges:
        if e0.entityToken in used_edges:
            continue

        # start a new loop with e0
        loop_edges = []
        used_edges.add(e0.entityToken)
        loop_edges.append(e0)

        v_start, v_curr = endpoints[e0.entityToken]   # traverse from v_start -> v_curr

        while True:
            if v_curr == v_start:
                break

            inc = v_to_edges.get(v_curr, [])
            if len(inc) < 2:
                raise RuntimeError("Boundary is not a closed chain (vertex degree < 2).")

            # pick the next edge: at v_curr there are typically 2 edges; choose the unused one
            nxt = None
            for cand in inc:
                if cand.entityToken not in used_edges:
                    nxt = cand
                    break

            if nxt is None:
                # no unused outgoing edge: either we closed properly or graph is weird
                if v_curr != v_start:
                    raise RuntimeError("Stopped before closing loop (graph has a branch or merged pockets).")
                break

            used_edges.add(nxt.entityToken)
            loop_edges.append(nxt)

            a, b = endpoints[nxt.entityToken]
            v_curr = b if a == v_curr else a

        loops.append(loop_edges)

    return loops


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
