from typing import *
import sys
import attrs
import numpy as np
from functools import cached_property


from freecad import (Transform, mirror, rotate, translate, fuse, cut,
                     make_box, make_cylinder, make_ball, make_circle)
import FreeCAD
import Part

def normalize(v):
    """
    normalize a numpy vector.
    :param v:
    :return:
    """
    norm = np.linalg.norm(v)
    if norm == 0:
       return v
    return v / norm


###################################š

VecLike = Union[FreeCAD.Vector, Sequence[float]]
def fvec(v: VecLike) -> FreeCAD.Vector:
    if isinstance(v, FreeCAD.Vector):
        return v
    else:
        v = list(v)
        return FreeCAD.Vector(*v)

def vec_list(vec: FreeCAD.Vector):
    return [vec.x, vec.y, vec.z]


##########################


##########################š


def vector_origin():
    return FreeCAD.Vector(0, 0, 0)

def vector_z():
    return FreeCAD.Vector(0, 0, 1)

class BaseOp:
    def _apply(self, transform: Transform):
        return None

    def __matmul__(self, transform: Transform):
        return self._apply(transform)

    def expand(self):
        return [self]

@attrs.define
class ShapeOp(BaseOp):
    tool_shape: Part.Shape

    def _apply(self, transform: Transform):
        return self

    def _apply(self, transform:Transform):
        return ShapeOp(self.tool_shape @ transform)

    def copy(self):
        return ShapeOp(self.tool_shape.copy())


class NoneOp:

    def _apply(self, transform: Transform):
        return self

    def __matmul__(self, transform: Transform):
        return self

    def copy(self):
        return self

    def expand(self):
        return []

@attrs.define
class DrillOp(BaseOp):
    """
    Drill Operation bahaves like a Cylinder.
    Default start is at origin and drilling upward in Z axis.
    """
    radius = attrs.field(type=float)
    length = attrs.field(type=float)
    start = attrs.field(type=FreeCAD.Vector, default=attrs.Factory(vector_origin), converter=fvec)
    direction = attrs.field(type=FreeCAD.Vector, default=attrs.Factory(vector_z), converter=fvec)


    #def __repr__(self):
    #    return f"Drill(r={self.radius}): [{vec_list(self.start)}] -> [{vec_list(self.direction)}] * {self.length}"

    def _apply(self, transform: Transform):
        return DrillOp(
            self.radius,
            self.length,
            start = self.start @ transform,
            direction= self.direction @ transform.rotation(),
            )

    @cached_property
    def tool_shape(self):
        return  (Part.makeCylinder(self.radius, self.length)
                 @ rotate([0, 0, 1], self.direction)
                 @ translate(self.start))

    def copy(self):
        return DrillOp(self.radius, self.length, self.start, self.direction)



def mill_tool_cylinder(radius, length, can_end):
    # Create the milling tool (cylinder) at the start position
    start_cylinder = make_cylinder(radius, length)
    # Create the milling tool (cylinder) at the end position
    end_cylinder = make_cylinder(radius, length) @ translate(can_end)

    # Create profiles at the start and end positions
    # Side profiles (rectangle wires)
    rectangle_points = list(map(fvec, [
        (0, -radius, 0),
        (0, radius, 0),
        (0, radius, length),
        (0, -radius, length),
        (0, -radius, 0)
    ]))
    rectangle_wire_start = Part.makePolygon(rectangle_points)
    rectangle_wire_end = rectangle_wire_start.copy() @ translate(can_end)
    # Loft between the start and end rectangle wires to create the side sweep
    side_sweep = Part.makeLoft([rectangle_wire_start, rectangle_wire_end], True)

    components = [start_cylinder, end_cylinder, side_sweep]
    if abs(can_end.z) > 1e-6:
        # move no perpendicular to tool 'direction'
        # have to add top and bottom domes using loft

        # Top circle wires at the start and end positions
        top_circle_edge_start = Part.makeCircle(radius, fvec([0, 0, length]))
        top_circle_wire_start = Part.Wire([top_circle_edge_start])
        top_circle_wire_end = top_circle_wire_start.copy() @ translate(can_end)
        # Loft between the top circle wires
        top_sweep = Part.makeLoft([top_circle_wire_start, top_circle_wire_end], True)
        components.append(top_sweep)

        # Bottom circle wires at the start and end positions
        bottom_circle_edge_start = Part.makeCircle(radius)
        bottom_circle_wire_start = Part.Wire([bottom_circle_edge_start])
        bottom_circle_wire_end = bottom_circle_wire_start.copy() @ translate(can_end)
        # Loft between the bottom circle wires
        bottom_sweep = Part.makeLoft([bottom_circle_wire_start, bottom_circle_wire_end], True)
        components.append(bottom_sweep)
    return components



def create_arc(radius, start_point, start_tangent_vector, end_tangent_vector, invert = False):
    """
    Creates an arc given the radius, start point, start tangent vector, and end tangent vector.
    The arc is constructed using the specified radius and the tangent vectors, selecting the arc
    with angle less than Pi (the shorter arc).

    Parameters:
    radius (float): Radius of the arc.
    start_point (Vector): Starting point of the arc.
    start_tangent_vector (Vector): Tangent vector at the starting point.
    end_tangent_vector (Vector): Tangent vector at the end point.

    Returns:
    Part.Edge: The arc as a shape.
    end_point (Vector): The calculated end point of the arc.
    """

    # Normalize tangent vectors
    T1 = fvec(start_tangent_vector).normalize()
    T2 = fvec(end_tangent_vector).normalize()


    # Z-axis vector
    Z_axis = FreeCAD.Vector(0, 0, 1)

    # Compute sign based on the direction of T1.cross(T2) relative to Z-axis
    cross_T1_T2 = T1.cross(T2)
    TT_dot_Z = cross_T1_T2.dot(Z_axis)
    #assert abs(abs(TT_dot_Z) - 1) < 1e-6, "Arc and its tangent vectors must lay in XY plane."
    if TT_dot_Z >= 0:
        sign = -1
    else:
        sign = 1

    # Compute arc center
    C = start_point.add(T1.cross(Z_axis).multiply(sign * radius))

    # Compute end point
    end_point = C.add(Z_axis.cross(T2.multiply(sign)).multiply(radius))

    # Compute mid point for Part.Arc
    # The mid point is halfway along the arc, which can be approximated by averaging the start and end vectors from the center
    #mid_vector = (start_point.sub(C)).add(end_point.sub(C)).normalize().multiply(radius)
    #mid_point = C.add(mid_vector)
    mid_vector = ((start_point.sub(C)).add(end_point.sub(C))).multiply(0.5).normalize().multiply(radius)
    mid_point = C.add(mid_vector)
    # Create the arc
    if invert:
        arc = Part.Arc(end_point, mid_point, start_point).toShape()
    else:
        arc = Part.Arc(start_point, mid_point, end_point).toShape()

    return arc, end_point


def create_capsule(radius, length, can_end):
    """
    Creates a capsule-shaped solid by revolving a wire composed of two circular arcs and a line.

    Parameters:
    R (float): Radius of the cylinder and hemispherical ends.
    L (float): Length of the cylinder between the centers of the hemispherical ends.
    axis (FreeCAD.Vector): Axis of revolution (default is X-axis).

    Returns:
    Part.Shape: The resulting capsule-shaped solid.
    """
    R = radius
    L = fvec(can_end).Length
    rotation_axis = can_end.normalize()
    assert abs(abs(rotation_axis.dot(fvec([1, 0, 0]))) - 1) < 1e-6

    # Define the rotation axis and origin
    origin = fvec([0, 0, 0])

    # Construct the profile in XY plane

    normal = fvec([1, 0, 0])
    # Points defining the profile in the YZ-plane
    p1 = fvec([0, R, 0])  # Bottom center point of the lower hemisphere
    #p2 = fvec([0, -R, 0])  # Bottom center point of the lower hemisphere
    left_arc, p2 = create_arc(R, p1, [-1, 0, 0], [0, -1, 0])
    p3 = fvec([L + R, 0, 0])  # End point of the line segment (start of upper arc)
    bot_line = Part.makeLine(p2, p3)
    right_arc, p4 = create_arc(R, p3, [0, 1, 0], [-1, 0, 0])
    top_line = Part.makeLine(p4, p1)

    # Combine all edges into a wire
    edges = [left_arc, bot_line, right_arc, top_line]
    wire = Part.Wire(edges)

    # Ensure the wire is closed
    #if not wire.isClosed():
    #    print("Wire is not closed. Closing the wire.")
    #    wire = Part.Wire(wire.Edges + [Part.makeLine(wire.Edges[-1].Vertexes[1], wire.Edges[0].Vertexes[0])])

    # Create a face from the wire (required for solid revolution)
    face = Part.Face(wire)

    # Revolve the face around the specified axis to create the solid
    solid = face.revolve(origin, rotation_axis, 360) @ translate([0, 0, -radius + length])

    return [solid]


@attrs.define
class MillOp(BaseOp):
    """
    Mill Operation bahaves like a Cylinder fused over a path.
    Default start is at origin and drilling upward in Z axis.
    """
    radius = attrs.field(type=float)
    length = attrs.field(type=float)    # Active length of the tool.
    direction = attrs.field(type=FreeCAD.Vector, converter=fvec)
    # Direction of the tool while moving
    start = attrs.field(type=FreeCAD.Vector, converter=fvec)
    # Start point of move
    end = attrs.field(type=FreeCAD.Vector, converter=fvec)
    r_fillet = attrs.field(type=float, default=None)
    tool_shape_fn = attrs.field(type=Callable, default=mill_tool_cylinder)

    #def __repr__(self):
    #    return f"Mill(r={self.radius}, l={self.length}): ^[{vec_list(self.direction)}], [{vec_list(self.start)}] -> [{vec_list(self.end)}]"

    @classmethod
    def ball(cls, radius, width, direction, start, end):
        assert width <= 2.0 * radius
        dz = radius - np.sqrt(radius ** 2.0 - (width / 2.0) ** 2)
        return cls(radius, dz, direction=direction, start=start, end=end, tool_shape_fn=create_capsule) #mill_tool_ball)

    def _apply(self, transform: Transform):
        return MillOp(
            self.radius,
            self.length,
            self.direction  @ transform.rotation(),
            start = self.start @ transform,
            end = self.end @ transform,
            r_fillet=self.r_fillet,
            tool_shape_fn=self.tool_shape_fn
            )

    @property
    def tool_shape(self):
        radius, length = self.radius, self.length
        direction, start, end = map(np.array, [self.direction, self.start, self.end])

        # Normalize the direction vector
        direction = normalize(direction)

        # Ratation to canonical position.
        # direction -> Z axis
        # XYmovment_vec -> X axis
        dir_rot = rotate(direction, [0, 0, 1])
        move_vec = vec_list(fvec(end - start) @ dir_rot)
        xy_move_vec = move_vec.copy()
        xy_move_vec[2] = 0
        move_rot = rotate(xy_move_vec, [1, 0, 0])
        can_rot = dir_rot @ move_rot
        can_end = fvec(move_vec) @ move_rot
        assert abs(can_end.y) < 1e-6, f"Canonical end points: {vec_list(can_end)}"
        components = self.tool_shape_fn(radius, length, can_end)

        fused_shape = fuse(components) @ can_rot.inverse() @ translate(start)
        if self.r_fillet is not None:
            if fused_shape.check():
                print("Shape has errors:", fused_shape.check())
            fused_shape = fused_shape.removeSplitter()
            #fused_shape = fused_shape.clean()
            # Or
            #fused_shape = Part.refineShape(fused_shape, True, True)
            for i, edge in enumerate(fused_shape.Edges):
                try:
                    fused_shape = fused_shape.makeFillet(self.r_fillet, [edge])
                except Part.OCCError:
                    # Handle or log the edge that cannot be filleted
                    pass
        return fused_shape

    def copy(self):
        return MillOp(self.radius, self.length, self.direction, self.start, self.end, self.r_fillet, self.tool_shape_fn)




CNCOperation = Union[DrillOp, MillOp, 'OperationList']

class OperationList(BaseOp):
    def __init__(self, *ops):
        self._ops: List[CNCOperation] = ops

    def __iter__(self):
        return iter(self._ops)

    def _apply(self, transform):
        return OperationList(*[x._apply(transform) for x in self._ops])

    def expand(self):
        """
        Return plain list of operation tree.
        :return:
        """
        ops = []
        for o in self._ops:
            ops.extend(o.expand())
        return ops
