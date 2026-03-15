from dataclasses import dataclass

# mill setting for large front pannel pockets

import adsk.core

from feeds_speeds import mill_feed_speed_params
from models import PartContext, linspace


@dataclass(frozen=True)
class PocketRegion:
    index: int
    faces_data: tuple
    chain_edges: tuple

    @property
    def faces(self):
        return list(self.faces_data)

    @property
    def chains(self):
        return [list(self.chain_edges)]

    def slot_name(self, base_slot_name: str) -> str:
        return f"{base_slot_name}_pocket_{self.index}"


@dataclass(frozen=True)
class PanelMillSpec:
    z_threshold_mm: float = -1.0
    z_depth_mm: float = -1.0
    stepdown_step_mm: float = 0.3

    def __post_init__(self):
        if self.z_threshold_mm > 0.0:
            raise RuntimeError("z_threshold_mm must be <= 0")
        if self.z_depth_mm >= 0.0:
            raise RuntimeError("z_depth_mm must be < 0")
        if self.stepdown_step_mm <= 0.0:
            raise RuntimeError("stepdown_step_mm must be > 0")

    @property
    def z_threshold_cm(self) -> float:
        return self.z_threshold_mm / 10.0

    @property
    def bottom_height_offset(self) -> str:
        return f"{self.z_depth_mm:g} mm"

    @property
    def contour_stepdowns_mm(self) -> list[float]:
        return linspace(0.0, self.z_depth_mm, 3, step=self.stepdown_step_mm)


def mill(ctx: PartContext, occurrence, slot_name: str, spec: PanelMillSpec = PanelMillSpec()):
    ctx.log(f"mill START for {slot_name}")
    slot_name = f"{slot_name}_1_mill"
    faces = _detect_pocket_faces(occurrence, ctx, slot_name, spec)
    ctx.log(f"mill detected {len(faces)} pocket faces")
    if not faces:
        ctx.log("mill: no pocket faces; skipping setup/op creation")
        return

    setup = ctx.create_setup(occurrence, slot_name)
    pockets = build_pocket_regions(faces, ctx)
    ctx.log(f"mill grouped {len(pockets)} pockets")
    tool_diameter_mm = 8.0
    rough_stock_clearance_mm = 0.2
    rough_radial_stock_mm = tool_diameter_mm - rough_stock_clearance_mm
    tool_name = "8mm Flat Endmill"
    contour_stepdowns_mm = spec.contour_stepdowns_mm
    final_depth_mm = spec.z_depth_mm
    ctx.log(
        f"mill depth spec: z_threshold_mm={spec.z_threshold_mm:g} "
        f"z_depth_mm={spec.z_depth_mm:g} "
        f"stepdown_step_mm={spec.stepdown_step_mm:g} "
        f"contour_depths_mm={contour_stepdowns_mm}",
    )

    # Minimal, stable 2D Pocket params (tune feeds elsewhere if needed)
    base_spec = dict(
        # Heights (same system as your drill: *_mode/_offset)
        clearanceHeight_mode="from wcs",
        clearanceHeight_value=f"{ctx.config.safe_z_mm} mm",

        retractHeight_mode="from wcs",
        retractHeight_value=f"{ctx.config.safe_z_mm} mm",

        feedHeight_mode="from wcs",
        feedHeight_value=f"{ctx.config.cycle_plane_z_mm} mm",

        topHeight_mode="from stock top",
        topHeight_offset="0 mm",


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
    base_spec.update(mill_feed_speed_params(tool_diameter_mm=tool_diameter_mm, flutes=2))

    contour_spec = dict(
        (k, v) for k, v in base_spec.items() if k != "doFinishingPasses"
    )
    contour_spec.update(dict(
        compensationType="computer",
        useStockToLeave=False,
        stockToLeave="0 mm",
        verticalStockToLeave="0 mm",
        topHeight_mode="from stock top",
        topHeight_offset="0 mm",
    ))

    pocket_spec = dict(
        base_spec,
        bottomHeight_mode="from stock top",
        bottomHeight_offset=spec.bottom_height_offset,
        useStockToLeave=True,
        stockToLeave=f"{rough_radial_stock_mm:g} mm",
        verticalStockToLeave="0 mm",
        doFinishingPasses=False,
    )
    ctx.log(f"mill tuning: rough_radial_stock_mm={rough_radial_stock_mm:g}")

    for pocket in pockets:
        ctx.log(f"mill pocket {pocket.index}: sequencing full milling cycle")
        ctx.add_op_mill_contour_first(
            setup,
            pocket_chains=pocket.chains,
            slot_name=pocket.slot_name(slot_name),
            tool_name=tool_name,
            contour_stepdowns_mm=contour_stepdowns_mm,
            contour_spec=contour_spec,
            pocket_spec=pocket_spec,
            final_depth_mm=final_depth_mm,
            pocket_faces=pocket.faces,
        )

    ctx.add_op_transverse(setup, 0.0, 0.0)
    ctx.generate_gcode(setup, slot_name)
    ctx.log(f"mill END for {slot_name}")

def _detect_pocket_faces(occurrence, ctx: PartContext, slot_name: str, spec: PanelMillSpec):
    faces = []
    bodies = occurrence.bRepBodies
    z_tol = 0.01  # 0.1 mm in cm
    normal_tol = 0.01
    logged = 0
    threshold_cm = spec.z_threshold_cm
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

            plane_z = plane.origin.z
            if plane_z > z_tol:
                continue

            bb = face.boundingBox
            if not ctx.is_in_top(bb, slot_name):
                continue

            if plane_z >= threshold_cm:
                continue

            depth_cm = -plane_z
            logged += 1
            ctx.log(
                f"mill face {logged}: plane_z={plane_z:.4f} "
                f"bb_min=({bb.minPoint.x:.4f},{bb.minPoint.y:.4f},{bb.minPoint.z:.4f}) "
                f"bb_max=({bb.maxPoint.x:.4f},{bb.maxPoint.y:.4f},{bb.maxPoint.z:.4f}) "
                f"depth_mm={depth_cm * 10.0:.3f}",
            )

            faces.append(face)
    return faces


def build_pocket_regions(pocket_faces, ctx: PartContext):
    if not pocket_faces:
        return []

    components = _group_connected_faces(pocket_faces)
    ordered_components = sorted(components, key=_component_sort_key)
    pockets = []

    for index, component_faces in enumerate(ordered_components, start=1):
        chain_edges = tuple(_build_outer_boundary_loop(component_faces))
        bb = _component_bbox(component_faces)
        ctx.log(
            f"mill pocket {index}: "
            f"bb_min=({bb.minPoint.x:.4f},{bb.minPoint.y:.4f},{bb.minPoint.z:.4f}) "
            f"bb_max=({bb.maxPoint.x:.4f},{bb.maxPoint.y:.4f},{bb.maxPoint.z:.4f}) "
            f"faces={len(component_faces)} edges={len(chain_edges)}",
        )
        pockets.append(PocketRegion(index=index, faces_data=tuple(component_faces), chain_edges=chain_edges))

    return pockets


def _group_connected_faces(pocket_faces):
    edge_to_face_ids = {}
    for face_id, face in enumerate(pocket_faces):
        for edge in face.edges:
            edge_to_face_ids.setdefault(edge.entityToken, []).append(face_id)

    adjacency = {face_id: set() for face_id in range(len(pocket_faces))}
    for face_ids in edge_to_face_ids.values():
        if len(face_ids) < 2:
            continue
        for face_id in face_ids:
            adjacency[face_id].update(other_id for other_id in face_ids if other_id != face_id)

    components = []
    seen = set()
    for face_id, face in enumerate(pocket_faces):
        if face_id in seen:
            continue
        stack = [face_id]
        component_ids = []
        seen.add(face_id)
        while stack:
            current = stack.pop()
            component_ids.append(current)
            for other_id in adjacency[current]:
                if other_id in seen:
                    continue
                seen.add(other_id)
                stack.append(other_id)
        components.append([pocket_faces[i] for i in component_ids])

    return components


def _component_sort_key(component_faces):
    bb = _component_bbox(component_faces)
    return (round(bb.minPoint.x, 6), round(bb.minPoint.y, 6))


def _component_bbox(component_faces):
    min_x = min(face.boundingBox.minPoint.x for face in component_faces)
    min_y = min(face.boundingBox.minPoint.y for face in component_faces)
    min_z = min(face.boundingBox.minPoint.z for face in component_faces)
    max_x = max(face.boundingBox.maxPoint.x for face in component_faces)
    max_y = max(face.boundingBox.maxPoint.y for face in component_faces)
    max_z = max(face.boundingBox.maxPoint.z for face in component_faces)
    return adsk.core.BoundingBox3D.create(
        adsk.core.Point3D.create(min_x, min_y, min_z),
        adsk.core.Point3D.create(max_x, max_y, max_z),
    )


def _build_outer_boundary_loop(component_faces):
    edge_counts = {}
    token_to_edge = {}

    for face in component_faces:
        outer = next((loop for loop in face.loops if loop.isOuter), None)
        if not outer:
            raise RuntimeError("Pocket component face has no outer loop")
        for coe in outer.coEdges:
            edge = coe.edge
            edge_token = edge.entityToken
            token_to_edge[edge_token] = edge
            edge_counts[edge_token] = edge_counts.get(edge_token, 0) + 1

    boundary_edges = [token_to_edge[token] for token, count in edge_counts.items() if count == 1]
    if not boundary_edges:
        raise RuntimeError("Pocket component has no boundary edges")

    vertex_to_edges = {}
    edge_endpoints = {}
    for edge in boundary_edges:
        start_token = edge.startVertex.entityToken
        end_token = edge.endVertex.entityToken
        edge_endpoints[edge.entityToken] = (start_token, end_token)
        vertex_to_edges.setdefault(start_token, []).append(edge)
        vertex_to_edges.setdefault(end_token, []).append(edge)

    start_edge = boundary_edges[0]
    used_edges = {start_edge.entityToken}
    loop_edges = [start_edge]
    start_vertex, current_vertex = edge_endpoints[start_edge.entityToken]

    while current_vertex != start_vertex:
        incident_edges = vertex_to_edges.get(current_vertex, [])
        next_edge = next(
            (edge for edge in incident_edges if edge.entityToken not in used_edges),
            None,
        )
        if next_edge is None:
            raise RuntimeError("Pocket boundary stopped before closing")
        used_edges.add(next_edge.entityToken)
        loop_edges.append(next_edge)
        edge_start, edge_end = edge_endpoints[next_edge.entityToken]
        current_vertex = edge_end if edge_start == current_vertex else edge_start

    if len(used_edges) != len(boundary_edges):
        raise RuntimeError("Pocket component produced more than one boundary loop")

    return loop_edges


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
