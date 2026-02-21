# Automate fusion preprocessing and g-code

1. Mode parts (*.step) to process into the workspace folder.
2. Open tools/master.f3d
3. `Shift+S` or UTILITIES -> ADD-INs -> "Scripts and Add-Ins"
   -> run "masif_load_transform.py"
4. G-code file should be generated in `workspace/g-code` up to 12 files
   (4 positions x 3 tools)   

## Script functions
- Copy part 4 times to four positions.
- Apply 3 tools to each positions.
- holes 8mm, drill exactly according to the model
- holes 5mm, drill exactly according to model only holes of 5mm diameter
  drill down to 1mm other holes (just as marks)
- mill, mill 1mm deep pockets for drawer rails, should be done in two   
  passes; second finishing 0.5mm border
- should automaticaly assign each operation to exactly one position
- script produces:
  Within Fusion
  a) design (parts after transform to cannonical position)
  b) manufacture steps
  Files:
  c) produced and saved g-code files
  d) log for each input part file
