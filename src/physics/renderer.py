import pygame

def draw_segment(screen, shape, screen_height, color=(0, 0, 0)):
    """
    Renders a Pymunk static segment (like the ground) onto the Pygame window.
    :param screen: The Pygame surface to draw on.
    :param shape: The Pymunk Segment shape object.
    :param screen_height: Used to flip the Y-axis for correct visual orientation.
    :param color: RGB tuple for the line color.
    """
    # 'a' and 'b' are the local endpoints of the Pymunk segment
    p1 = shape.a 
    p2 = shape.b

    # Coordinate Transformation: 
    # Pygame's origin (0,0) is TOP-left. Pymunk's origin is usually BOTTOM-left.
    # We subtract the y-coordinate from screen_height to "flip" the world upright.
    v1 = (p1.x, screen_height - p1.y)  
    v2 = (p2.x, screen_height - p2.y) 
    
    # Draw the line using the segment's physical radius for thickness
    pygame.draw.line(
        screen,
        color,
        v1,
        v2,
        int(shape.radius * 2) # Diameter = radius * 2
    )