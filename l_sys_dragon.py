import matplotlib.pyplot as plt
from dataclasses import dataclass

@dataclass
class Segment:
    x: int
    y1: int
    y2: int

def get_dragon_vertical_segments(depth, axiom:str = '+FX'): # axiom for depth=11
    """
    Generates vertical line segments from the dragon curve L-system.

    Parameters:
    depth (int): The recursion depth of the L-system.

    Returns:
    List[Segment]: A list of Segment objects representing vertical line segments.
    """
    # Replace compute_delta function with a dictionary
    delta_dict = {
        0: (1, 0),
        90: (0, 1),
        180: (-1, 0),
        270: (0, -1)
    }

    def process_instruction(s, depth, position, heading):
        nonlocal vertical_segments
        # Refactor while loop to 'for c in s:'
        for c in s:
            if c == 'F':
                delta = delta_dict[heading % 360]
                new_position = (position[0] + delta[0], position[1] + delta[1])
                if delta[0] == 0:
                    # Vertical move
                    x = position[0]
                    y1 = position[1]
                    y2 = new_position[1]
                    if y1 <= y2:
                        segment = Segment(x, y1, y2)
                    else:
                        segment = Segment(x, y2, y1)
                    vertical_segments.append(segment)
                position = new_position
            elif c == '+':
                heading = (heading + 90) % 360
            elif c == '-':
                heading = (heading - 90) % 360
            elif c in 'XY':
                if depth > 0:
                    if c == 'X':
                        new_s = 'X+YF+'
                    elif c == 'Y':
                        new_s = '-FX-Y'
                    position, heading = process_instruction(new_s, depth - 1, position, heading)
                else:
                    pass  # At depth 0, 'X' and 'Y' are ignored
            else:
                pass  # Ignore other characters
        return position, heading

    vertical_segments = []
    initial_position = (0, 0)
    initial_heading = 0  # Facing along positive X-axis
    process_instruction(axiom, depth, initial_position, initial_heading)

    # Collect segments by X coordinate
    vertical_segments.sort(key = lambda seg : (seg.x, seg.y1))

    # Merge connected segments at the same X
    merged = [vertical_segments[0]]
    for seg in vertical_segments[1:]:
        assert seg.y1 != seg.y2
        prev_seg = merged[-1]
        # Fix comparison of y-coordinates
        if (prev_seg.x == seg.x) and (seg.y1 - prev_seg.y2) < 1e-2 :
            # Overlapping or adjacent intervals, merge them
            merged[-1] = Segment(seg.x, prev_seg.y1, max(prev_seg.y2, seg.y2))
        else:
            merged.append(seg)
    X = [seg.x for seg in merged]
    Y1 = [seg.y1 for seg in merged]
    Y2 = [seg.y2 for seg in merged]

    return merged, (float(min(X)), float(max(X))), (float(min(Y1)), float(max(Y2)))

def plot_segments(segments):
    """
    Plots vertical segments using matplotlib.

    Parameters:
    segments (List[Segment]): The list of segments to plot.
    """
    fig, ax = plt.subplots()
    for segment in segments:
        x = segment.x
        y1 = segment.y1
        y2 = segment.y2
        ax.plot([x, x], [y1, y2], color='blue')
    ax.set_aspect('equal')
    plt.title('Dragon Curve Vertical Segments')
    plt.xlabel('X')
    plt.ylabel('Y')
    plt.grid(True)
    plt.show()

# Main script
if __name__ == "__main__":
    # Example usage:
    depth = 11 # Adjust the recursion depth as needed
    segments, xr, yr = get_dragon_vertical_segments(depth)
    print("N segments: ", len(segments))
    print("X range:", xr, "Y range", yr)

    # Optionally, sort segments by x and merge connected segments at the same x
    # (But per your request, we will omit this step)

    # Plot the segments using matplotlib
    plot_segments(segments)

