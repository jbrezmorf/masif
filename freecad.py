
import sys
from typing import *
from pathlib import Path
# Get the directory of the current script
script_dir = Path(__file__).parent
import attrs

# Adjust the path according to where FreeCAD is installed
freecad_path = '/usr/lib/freecad-python3/lib'  # Set your FreeCAD installation path

if freecad_path not in sys.path:
    sys.path.append(freecad_path)
    sys.path.append(script_dir)

print(sys.path)
# Import FreeCAD modules
import FreeCAD
import Part



def fuse(shapes):
    assert len(shapes) > 0
    result = shapes[0]
    for s in shapes[1:]:
        result = result.fuse(s)
    return result


def make_cylinder(radius, length, axis=None, origin=None):
    """
    :return:
    """
    if origin is None:
        origin = [0, 0, 0]
    if axis is None:
        axis = [0, 0, 1]
    return Part.makeCylinder(radius, length) @ rotate([0, 0, 1], axis) @ translate(origin)

def make_box(dims, origin=None):
    """
    Make a box with one corner at origin and other corner at dims,
    parrallel with axes
    :param dims:
    :return:
    """
    if origin is None:
        origin = [0, 0, 0]
    return Part.makeBox(*dims) @ translate(origin)


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


def rotate(axis:VecLike, angle:Union[float, VecLike]) -> 'Transform':
    """
    1. rotate by 'angle' degrees around the 'axis' vector
    2. rotate from 'axis' vector to the 'angle' vector
    """
    axis = fvec(axis)
    if isinstance(angle, (float, int)):
        rot = FreeCAD.Rotation(axis, angle)
    else:
        target_axis = fvec(angle)
        rot = FreeCAD.Rotation(axis, target_axis)
    placement = FreeCAD.Placement(FreeCAD.Vector(0, 0, 0), rot)
    return Transform(placement)

def translate(pos: Union[FreeCAD.Vector, List[float]]) -> 'Transform':
    pos = fvec(pos)
    placement = FreeCAD.Placement(pos, FreeCAD.Rotation())
    return Transform(placement)

@attrs.define
class Transform:
    placement: FreeCAD.Placement

    def __matmul__(self, other: 'Transform'):
        """
        composition of transformations.
        obj @ self @ other == obj @ (self @ other)
        which implies:
        (self @ other) = other.mat @ self.mat
        :param other:
        :return:
        """
        return Transform(other.placement * self.placement)

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
