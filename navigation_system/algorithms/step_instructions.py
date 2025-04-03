from typing import List, Tuple
from navigation_system.models.node import NavigationGraph

def get_navigation_instructions(graph: NavigationGraph, path: List[str]) -> List[str]:
    """
    Converts a path of node IDs into human-readable navigation instructions.
    Each instruction has the format: "[direction]: [distance in feet]"
    
    Args:
        graph: The navigation graph containing the nodes
        path: A list of node IDs representing the path
        
    Returns:
        A list of string instructions
    """
    if not path or len(path) < 2:
        return []
    
    instructions = []
    current_direction = "forward"  # Default initial direction
    current_distance = 0
    
    # Need at least three nodes to determine a turn
    for i in range(len(path) - 1):
        # Get current and next nodes
        current_node = graph.nodes[path[i]]
        next_node = graph.nodes[path[i + 1]]
        
        # Calculate segment vector
        dx = float(next_node.x) - float(current_node.x)
        dy = float(next_node.y) - float(current_node.y)
        
        # Calculate distance for this segment
        distance = graph._calculate_distance(current_node, next_node)
        distance_feet = round(distance)
        
        # For the first segment, we just move forward
        if i == 0:
            current_distance = distance_feet
            continue
        
        # For subsequent segments, we need to determine if we're turning
        prev_node = graph.nodes[path[i-1]]
        
        # Calculate previous segment vector
        prev_dx = float(current_node.x) - float(prev_node.x)
        prev_dy = float(current_node.y) - float(prev_node.y)
        
        # Determine turn direction
        turn_direction = get_relative_direction(prev_dx, prev_dy, dx, dy)
        
        # If direction changed, add the previous instruction and start a new one
        if turn_direction != "straight":
            instructions.append(f"{current_direction}: {current_distance} feet")
            current_direction = turn_direction
            current_distance = distance_feet
        else:
            # Continue straight, add to the distance
            current_distance += distance_feet
    
    # Add the last instruction
    instructions.append(f"{current_direction}: {current_distance} feet")
    
    return instructions

def get_relative_direction(prev_dx: float, prev_dy: float, dx: float, dy: float) -> str:
    """
    Determines the relative direction (left, right, straight) based on previous and current vectors.
    
    Args:
        prev_dx, prev_dy: Previous direction vector
        dx, dy: Current direction vector
        
    Returns:
        A string indicating the relative direction
    """
    # Normalize vectors
    prev_mag = (prev_dx**2 + prev_dy**2)**0.5
    curr_mag = (dx**2 + dy**2)**0.5
    
    if prev_mag == 0 or curr_mag == 0:
        return "straight"
    
    prev_dx, prev_dy = prev_dx/prev_mag, prev_dy/prev_mag
    dx, dy = dx/curr_mag, dy/curr_mag
    
    # Calculate the dot product for the angle
    dot_product = prev_dx * dx + prev_dy * dy
    
    # If vectors are nearly parallel, continue straight
    if abs(dot_product) > 0.95:  # cos(18°) ≈ 0.95, so this is a turn less than 18 degrees
        return "straight"
    
    # To determine left/right, we need to find which side of the previous vector
    # the new vector falls on. This is essentially finding which side of the line
    # the new point is on.
    
    # Compute the signed angle between vectors
    # Using the formula: angle = atan2(cross_product, dot_product)
    cross_product = prev_dx * dy - prev_dy * dx
    
    # If cross product is positive, the turn is counter-clockwise (left)
    # If cross product is negative, the turn is clockwise (right)
    if cross_product > 0:
        return "left"
    else:
        return "right"
    