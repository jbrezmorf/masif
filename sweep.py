import sys
sys.path.append('/usr/lib/freecad-python3/lib/') # this path is different for windows or mac users
import FreeCAD
from FreeCAD import Part, Base
import json
import math
import argparse
import MeshPart
import os
from pprint import pprint

def swept_shape_with_straight_or_spline_edges(sets_of_points, connection_type, smoothness=8):
    
    sets_of_edges=[]
    sets_of_faces=[]
    sets_of_wires=[]
    print('connection_type',connection_type)
    print('smoothness',smoothness)
    for points in sets_of_points:
        print(points)
        edges = []

        if connection_type == 'straight':
            #many straight lines (snake skin)
            for c,i in enumerate(points): 
                point1 = Base.Vector(points[c])
                if c == len(points)-1: 
                    point2= Base.Vector(points[0])
                else:
                    point2= Base.Vector(points[c+1])
                if point1 != point2:
                    edge = Part.makeLine(point1,point2)
                    edges.append(edge)
            filled_face = Part.makeFilledFace(edges) 

        if connection_type == 'spline':
            absolutePoints=[]
            for point in points:
                absolutePoints.append(FreeCAD.Vector(point))
            if absolutePoints[0] != absolutePoints[-1]:
                absolutePoints.append(absolutePoints[0])
            curve=Part.BSplineCurve(absolutePoints,None,None,True,smoothness,None,False)
            edges = curve.toShape()
            filled_face = Part.makeFilledFace([edges]) 

        wire = Part.Wire(edges)
        sets_of_faces.append(filled_face)
        sets_of_wires.append(wire)
        Part.show(filled_face)
        sets_of_edges.append(edges)

    outer_surface = Part.makeSweep(sets_of_wires, False, True, False)
    
    reduced_sets_of_faces= outer_surface.Faces +[sets_of_faces[0]] +[sets_of_faces[-1]]
    # reduced_sets_of_faces= outer_surface.Faces
    shell = Part.Shell(reduced_sets_of_faces)
    shell.sewShape()
    solid = Part.Solid(shell)
    Part.show(solid)
    return solid  