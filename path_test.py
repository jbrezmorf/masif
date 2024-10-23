import numpy as np
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
from FreeCAD import Vector
import math

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
    T1 = start_tangent_vector.normalize()
    T2 = end_tangent_vector.normalize()

    # Z-axis vector
    Z_axis = Vector(0, 0, 1)

    # Compute sign based on the direction of T1.cross(T2) relative to Z-axis
    cross_T1_T2 = T1.cross(T2)
    if cross_T1_T2.dot(Z_axis) >= 0:
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

def create_path_wire(A, B, L, R, H):
    """
    Creates the wire representing the path of the mill operation.

    Parameters:
    A (Vector): Starting point.
    B (Vector): Ending point.
    L (float): Parametric length for path division.
    R (float): Radius for circular transitions.
    H (float): Vertical length to move downwards.

    Returns:
    Part.Wire: The wire representing the path.
    """
    # Compute the unit vector from A to B
    D_vec = B.sub(A)
    L_AB = D_vec.Length
    D = D_vec.normalize()

    # Compute parametric points along AB
    t1 = 0.5 - L
    t2 = 0.5 + L
    P1 = A
    P2 = A + D * (L_AB * t1)
    P10 = B
    P9 = A + D * (L_AB * t2)

    edges = []

    # Edge from P1 to P2
    edge1 = Part.LineSegment(P1, P2).toShape()
    edges.append(edge1)

    # First arc from P2 to P3
    # Start tangent vector T1 (along AB)
    T1 = D
    # End tangent vector T2 (downwards)
    T2 = Vector(0, -1, 0)

    arc1, P3 = create_arc(R, P2, T1, T2)
    edges.append(arc1)
    arc_last, P8 = create_arc(R, P9, -T1, T2)

    # Line downwards from P3 to P4
    P4 = P3.add(Vector(0, -H, 0))
    edge2 = Part.LineSegment(P3, P4).toShape()
    edges.append(edge2)

    # Second arc from P4 to P5
    # Start tangent vector T3 (downwards)
    T3 = Vector(0, -1, 0)
    # End tangent vector T4 (horizontal right)
    T4 = Vector(1, 0, 0)

    arc2, P5 = create_arc(R, P4, T3, T4)
    edges.append(arc2)

    # Horizontal line from P5 to P6
    # Compute horizontal length
    total_horizontal_length = P8.x - P3.x -2 * R
    assert total_horizontal_length > 10, f"Too small handle_width={total_horizontal_length}"
    P6 = P5.add(Vector(total_horizontal_length, 0, 0))
    edge3 = Part.LineSegment(P5, P6).toShape()
    edges.append(edge3)

    # Third arc from P6 to P7
    # Start tangent vector T5 (horizontal right)
    T5 = Vector(1, 0, 0)
    # End tangent vector T6 (upwards)
    T6 = Vector(0, 1, 0)

    arc3, P7 = create_arc(R, P6, T5, T6)
    edges.append(arc3)

    edge4 = Part.LineSegment(P7, P8).toShape()
    edges.append(edge4)
    edges.append(arc_last)  #P8, P9


    # Edge from P8 to B (should be minimal or zero if P8 == B)
    # For completeness, we can add this edge
    edge5 = Part.LineSegment(P9, P10).toShape()
    edges.append(edge5)

    # Create wire from edges
    path_wire = Part.Wire(edges)
    return path_wire




def create_sweep_shape(path_wire, W_rect=10, H_rect=20):
    """
    Creates the sweep shape by moving a rectangular cross-section along the path.

    Parameters:
    path_wire (Part.Wire): The wire representing the path.
    W_rect (float): Width of the rectangular cross-section.
    H_rect (float): Height of the rectangular cross-section.

    Returns:
    Part.Shape: The swept shape.
    """
    # Get the start point and tangent of the path
    X0 = path_wire.Vertexes[0].Point
    tangent = path_wire.Vertexes[1].Point.sub(X0)

    # Create a coordinate system with the Z-axis as the profile's height direction
    # The profile plane normal is the tangent of the path at the start point
    # Create the rotation to align the profile plane with the path's normal plane
    profile_normal = tangent.normalize()
    profile_y = Vector(0, 0, 1)  # Desired up direction for the profile (height in Z)
    profile_x = profile_normal.cross(profile_y).normalize()

    # Compute the rectangle vertices directly in global coordinates
    dx = W_rect
    dy = H_rect

    vertices = [X0,
                X0 + profile_x * dx,
                X0 + profile_x * dx + profile_y * dy,
                X0 + profile_y * dy]
    vertices = [*vertices, vertices[0]]
    # Create the rectangle wire
    rect_wire = Part.makePolygon([ Vector(v) for v in vertices])

    # Sweep the rectangle along the path using makePipeShell
    makeSolid = True
    isFrenet = False
    sweep = path_wire.makePipeShell([rect_wire, rect_wire], makeSolid, isFrenet)

    # Convert to a solid if it's not already
    #if not sweep.isSolid():
    #    sweep = Part.Solid(sweep)

    return sweep

def test_makePipeShell():
    dx =10
    dy = 5
    X0 = np.array([2, 0, 2])
    profile_x = Vector(1, 0, 0)
    profile_y = Vector(0, 0, 1)

    vertices = [X0,
                X0 + profile_x * dx,
                X0 + profile_x * dx + profile_y * dy,
                X0 + profile_y * dy]
    vertices = [*vertices, vertices[0]]
    # Create the rectangle wire
    rect_wire = Part.makePolygon([ Vector(v) for v in vertices])

    # Create a circle profile at the start of the path
    center = Vector(0, 0, 0)
    axis = Vector(1, 0, 0)
    circle = Part.Circle(center, axis , 3)
    circle_edge = circle.toShape()
    P1 = Vector(0, 0, 1)
    P2 = Vector(0, 1, 0)
    P3 = Vector(0, 0, -1)
    P4 = Vector(0, -1, -1)
    arc_edge = Part.Arc(P1, P2, P3).toShape()
    line_edge = Part.LineSegment(P3, P4).toShape()
    circle_wire = Part.Wire([arc_edge, line_edge])


    # Sweep the circle along the path
    sweep = circle_wire.makePipeShell([rect_wire.Wires[0]], True, False)
    return sweep

def main():
    # Example usage:
    # Define points A and B
    A = Vector(0, 100, 0)
    B = Vector(700, 150, 0)

    # Parameters
    L = 0.2  # Parametric length for path division
    R = 20   # Radius for circular transitions
    H = 20   # Vertical length to move downwards

    # Create the path wire
    path_wire = create_path_wire(A, B, L, R, H)

    # Create the sweep shape
    sweep_shape = create_sweep_shape(path_wire)
    return sweep_shape

def create(fn):
    # Add the shape to FreeCAD document
    doc = FreeCAD.newDocument("MillOperation")
    part_obj = doc.addObject("Part::Feature", "MillOperation")
    part_obj.Shape = fn()
    doc.recompute()

    path = script_dir / "path_test.FCStd"
    doc.saveAs(str(path))


# Main script
if __name__ == "__main__":
    #create(test_makePipeShell)
    create(main)

