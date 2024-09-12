import FreeCAD
import Part
from FreeCAD import Base

# Create document and objects
doc = FreeCAD.newDocument()
base_box = Part.makeBox(10, 10, 10)
base_box.Placement = FreeCAD.Placement(Base.Vector(-5, -5, 0), FreeCAD.Rotation())
tool_cylinder = Part.makeCylinder(5, 10)
#tool_cylinder.Placement = FreeCAD.Placement(Base.Vector(5, 5, 0), FreeCAD.Rotation())

# Perform cut operation
result_shape = base_box.cut(tool_cylinder)
# Apply a reversed transformation
#transformation = FreeCAD.Matrix()
#transformation.move(Base.Vector(5, 5, 0))
#xy = result_shape.transformGeometry(transformation)

# Now base_box has this transformation as its natural position
# Continue to use base_box without needing to adjust its Placement further

# Create feature for the result
result_feature = doc.addObject("Part::Feature", "CutResult")
result_feature.Shape = result_shape.transformGeometry(base_box.Placement.toMatrix().inverse())
#print(xy.Placement)
#print(result_feature.Placement)
# Reset placement to default
#result_feature.Placement = FreeCAD.Placement()

doc.recompute()