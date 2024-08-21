"""
TODO:
1. figure out where to place part signature, make common function to add the signature
2. common mechanism to add parts and shift them automatically, add only parts we are working on
3. 
"""
from pathlib import Path
import pandas as pd

import FreeCAD
from FreeCAD import Base
import Part


# Get the directory of the current script
script_dir = Path(__file__).parent

# Load the ODS file
# Replace 'your_file.ods' with the path to your ODS file
df = pd.read_excel(script_dir / 'Objednávka MAPH.ods', engine='odf', header=None)

# Convert column letter 'I' to a 0-based index
col_identifier = ord('I') - ord('A')

# Filter rows where the 'I' column is not empty
identifiers = df[df.iloc[:, col_identifier].notna()]
print(identifiers)



doc = FreeCAD.newDocument("Wood_CNC_Project")
panel1_group = doc.addObject("App::DocumentObjectGroup", "Panel1")
panel2_group = doc.addObject("App::DocumentObjectGroup", "Panel2")



thickness = 18  # mm
width_panel1 = 600  # mm
length_panel1 = 800  # mm

# Define common hole positions, sizes, etc.
hole_diameter = 5  # mm

# Panel 1 creation
panel1 = Part.makeBox(width_panel1, length_panel1, thickness)
panel1_obj = doc.addObject("Part::Feature", "Panel1_Shape")
panel1_obj.Shape = panel1
panel1_group.addObject(panel1_obj)

# Drilling holes on Panel 1
hole1 = Part.makeCylinder(hole_diameter/2, thickness)
hole1.translate(Base.Vector(100, 100, 0))  # Position hole on the panel
panel1 = panel1.cut(hole1)

panel1_obj.Shape = panel1  # Update the shape with the hole

# Panel 2 creation (similar to Panel 1)
width_panel2 = 500  # mm
length_panel2 = 700  # mm

panel2 = Part.makeBox(width_panel2, length_panel2, thickness)
panel2_obj = doc.addObject("Part::Feature", "Panel2_Shape")
panel2_obj.Shape = panel2
panel2_group.addObject(panel2_obj)

# Drilling holes on Panel 2
hole2 = Part.makeCylinder(hole_diameter/2, thickness)
hole2.translate(Base.Vector(150, 150, 0))  # Position hole on the panel
panel2 = panel2.cut(hole2)

panel2_obj.Shape = panel2  # Update the shape with the hole


import FreeCAD as App
import Draft

doc = App.activeDocument()

# Function to add a label to a part
def add_label_to_part(part, label_text, offset=(10, 10, 10)):
    # Get the center of the part's bounding box for label positioning
    center = part.Shape.BoundBox.Center
    label_position = center.add(App.Vector(*offset))
    
    # Create the label
    label = Draft.makeLabel([label_position], label_text)
    label.ViewObject.FontSize = 20  # Adjust the font size as needed
    label.ViewObject.TextColor = (1.0, 0.0, 0.0)  # Set color to red (RGB)
    
    return label





def add_drilling_pattern(panel, positions, hole_diameter, thickness):
    for pos in positions:
        hole = Part.makeCylinder(hole_diameter/2, thickness)
        hole.translate(Base.Vector(pos[0], pos[1], 0))
        panel = panel.cut(hole)
    return panel

# Apply a shared drilling pattern to both panels
shared_positions = [(200, 200), (300, 300)]
panel1 = add_drilling_pattern(panel1, shared_positions, hole_diameter, thickness)
panel2 = add_drilling_pattern(panel2, shared_positions, hole_diameter, thickness)

# Update the shapes in the document
panel1_obj.Shape = panel1
panel2_obj.Shape = panel2


# Example: Add labels to parts in your document
for obj in doc.Objects:
    if obj.TypeId == "Part::Feature":  # Check if the object is a Part
        add_label_to_part(obj, obj.Label)


doc.recompute()
doc.saveAs("/path/to/save/Wood_CNC_Project.FCStd")
