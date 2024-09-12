import FreeCAD
import Part
import numpy as np

# Create a new document
doc = FreeCAD.newDocument()

# Create a box
width, height, depth = 10, 10, 10
base_box = Part.makeBox(width, height, depth)

# Add the box to the document with translation
box_feature = doc.addObject("Part::Feature", "TranslatedBox")
box_feature.Shape = base_box
translation_vector = FreeCAD.Vector(30, 40, 50)
box_feature.Placement = FreeCAD.Placement(translation_vector, FreeCAD.Rotation())

# Define expected corners of the AABB
expected = np.array([30, 40, 50, 40, 50, 60])  # [XMin, YMin, ZMin, XMax, YMax, ZMax]

corners = lambda bbox : np.array([bbox.XMin, bbox.YMin, bbox.ZMin, bbox.XMax, bbox.YMax, bbox.ZMax])

# Access the AABB
bbox1 = box_feature.Shape.BoundBox
assert np.allclose(expected, corners(bbox1)), "The bounding box1 does not match the expected values."
print(corners(bbox1))
# Recompute the document to apply changes
doc.recompute()

# Access the AABB
bbox2 = box_feature.Shape.BoundBox
# Assert to check if the actual bounding box matches the expected bounding box
assert np.allclose(expected, corners(bbox2)), "The bounding box2 does not match the expected values."
print(corners(bbox2))

print("Bounding box correctly matches expected values.")
