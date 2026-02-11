# Automate CNC code generation for manufacturing similar parts

I have 8 models of wooden planes of the same dimansions, each with slightly different
set of holes and pockets, but using only 3 tools.
Each model must be CNC processed in 4 steps 2x faces 2x top and bottom part  in orer to fit into
CNC table.
Whole script should do following:
1. load the model
2. copy into 4 transformations (top/bottom part, left / right face), all aligned with top, left, upper corner at origin so the part extends to X+, Y+ and Z-
3. loop over the copies for each call copy_process function will call 3 subfunctions:
- holes_8mm
- mill
- holes_5mm

holes_8mm:
Create separate file for holes_8mm function.
The function will take the part that has top manufacturing face at
level z=0 and top left manufacturing corner at origin.
It should detect all holes with diameter 8mm and apply a drill
operation. I wuppose to template that operation through GUI,
but i need guidence how to create such template, name it and
refer it in the code.

mill:
The mill function takes again aligned part as the holes_8mm function.
It should detect all horizontal faces at level -0.1 cm and apply
two step milling operation: coarse and fine.

holes_5mm
The function 0.5mm will detect all holes with diameter 0.5cm and smaller.
The holes with 0.5mm diameter exactly will be drilled with the
full depth according to model. The smaller diameter holes should
only be marked with the 5mm tool, so the depth should be just 1mm.

Each subfunction ends with calling a common G-code generation function + saving to a file with name:
<basename of input model>_<L/R><top/bot>_<op name>

## Guidelines
- Do not ask me for anything; proceed with reasonable assumptions.
- Do any edits within this directory as needed.
- do not run any code as it must be run within Fusion 360
- We are running Python 3.14.
- Use minimalistic code style, let code raise, we are coding scripts
- But use robust paradigms. 
- Use functional approach
- Introduce suitable datacalsses to reduce number of passed parameters.
- dataclasses can provide "readonly" methods producing derived data and objects
- use the logging function from tools, thats our only debugging tool; prefer more logging rather than less
