from typing import *
import sys
import attrs
import numpy as np
from functools import cached_property

import FreeCAD
import Part
from freecad import Transform, rotate, translate, fuse, make_box, make_cylinder


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


@attrs.define
class DrillOp:
    """
    Drill Operation bahaves like a Cylinder.
    Default start is at origin and drilling upward in Z axis.
    """
    radius = attrs.field(type=float)
    length = attrs.field(type=float)
    start = attrs.field(type=FreeCAD.Vector, default=attrs.Factory(vector_origin), converter=fvec)
    direction = attrs.field(type=FreeCAD.Vector, default=attrs.Factory(vector_z), converter=fvec)


    def __repr__(self):
        return f"Drill(r={self.radius}): [{vec_list(self.start)}] -> [{vec_list(self.direction)}] * {self.length}"

    def _apply(self, transform: Transform):
        return DrillOp(
            self.radius,
            self.length,
            start = self.start @ transform,
            direction= self.direction @ transform.rotation(),
            )

    def __matmul__(self, transform: Transform):
        return self._apply(transform)

    @cached_property
    def tool_shape(self):
        return  (Part.makeCylinder(self.radius, self.length)
                 @ rotate([0, 0, 1], self.direction)
                 @ translate(self.start))

    def copy(self):
        return DrillOp(self.radius, self.length, self.start, self.direction)

    def expand(self):
        return [self]


@attrs.define
class MillOp:
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

    def __repr__(self):
        return f"Mill(r={self.radius}, l={self.length}): ^[{vec_list(self.direction)}], [{vec_list(self.start)}] -> [{vec_list(self.end)}]"

    def _apply(self, transform: Transform):
        return MillOp(
            self.radius,
            self.length,
            self.direction  @ transform.rotation(),
            start = self.start @ transform,
            end = self.end @ transform
            )

    def __matmul__(self, transform: Transform):
        return self._apply(transform)

    @cached_property
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
            ( 0, -radius, 0)
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

        return fuse(components) @ can_rot.inverse() @ translate(start)

    def copy(self):
        return MillOp(self.radius, self.length, self.direction, self.start, self.end)

    def expand(self):
        return [self]


CNCOperation = Union[DrillOp, MillOp, 'OperationList']

class OperationList:
    def __init__(self, *ops):
        self._ops: List[CNCOperation] = ops

    def __iter__(self):
        return iter(self._ops)

    def _apply(self, transform):
        return OperationList(*[x._apply(transform) for x in self._ops])

    def __matmul__(self, transform: Transform):
        return self._apply(transform)


    def expand(self):
        """
        Return plain list of operation tree.
        :return:
        """
        ops = []
        for o in self._ops:
            ops.extend(o.expand())
        return ops
