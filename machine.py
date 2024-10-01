from typing import *
import sys

import attrs
import numpy as np
from functools import cached_property
# Adjust the path according to where FreeCAD is installed
freecad_path = '/usr/lib/freecad-python3/lib'  # Set your FreeCAD installation path

if freecad_path not in sys.path:
    sys.path.append(freecad_path)

import FreeCAD
import Part


VecLike = Union[FreeCAD.Vector, Sequence[float]]
def to_vec(v: VecLike) -> FreeCAD.Vector:
    if isinstance(v, FreeCAD.Vector):
        return v
    else:
        v = list(v)
        return FreeCAD.Vector(*v)

def vec_list(vec: FreeCAD.Vector):
    return [vec.x, vec.y, vec.z]


##########################

def rotate(axis:VecLike, angle:Union[float, VecLike]) -> 'Transform':
    """
    1. rotate by 'angle' degrees around the 'axis' vector
    2. rotate from 'axis' vector to the 'angle' vector
    """
    axis = to_vec(axis)
    if isinstance(angle, (float, int)):
        rot = FreeCAD.Rotation(axis, angle)
    else:
        target_axis = to_vec(angle)
        rot = FreeCAD.Rotation(axis, target_axis)
    placement = FreeCAD.Placement(FreeCAD.Vector(0, 0, 0), rot)
    return Transform(placement)

def translate(pos: Union[FreeCAD.Vector, List[float]]) -> 'Transform':
    pos = to_vec(pos)
    placement = FreeCAD.Placement(pos, FreeCAD.Rotation())
    return Transform(placement)

@attrs.define
class Transform:
    placement: FreeCAD.Placement

    def __matmul__(self, other: 'Transform'):
        return Transform(self.placement.multiply(other.placement))

    def __rmatmul__(self, shape: Union[Part.Shape, FreeCAD.Vector]):
        """
        Apply the stored transform to the right-hand operand (shape or vector).
        """
        if isinstance(shape, Part.Shape):

            # Apply the placement transform to the shape
            mat = self.placement.toMatrix()
            transformed_shape = shape.transformGeometry(mat)
            return transformed_shape
        elif isinstance(shape, FreeCAD.Vector):
            return self.placement.multVec(shape)
        else:
            raise TypeError(f"The right operand must be of type `Part.Shape` not {type(shape)}.")


    def inverse(self) -> 'Transform':
        return Transform(self.placement.inverse())

    def rotation(self) -> 'Transform':
        """
        Taking just the rotation part of the placement.
        :return:
        """
        rot = self.placement.Rotation
        return Transform(FreeCAD.Placement(FreeCAD.Vector(0, 0, 0), rot))


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
    start = attrs.field(type=FreeCAD.Vector, default=attrs.Factory(vector_origin), converter=to_vec)
    direction = attrs.field(type=FreeCAD.Vector, default=attrs.Factory(vector_z), converter=to_vec)


    def __repr__(self):
        return f"Drill(r={self.radius}): [{vec_list(self.start)}] -> [{vec_list(self.direction)}] * {self.length}"

    def apply(self, transform: Transform):
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

CNCOperation = Union[DrillOp]

class OperationList:
    def __init__(self, *ops):
        self._ops: List[CNCOperation] = ops

    def __iter__(self):
        return iter(self._ops)

    def apply(self, transform):
        return OperationList(*[x.apply(transform) for x in self._ops])
