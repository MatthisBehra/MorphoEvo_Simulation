import pygame

def draw_segment(screen, shape, screen_height, color=(0, 0, 0)):
    p1 = shape.a 
    p2 = shape.b
    v1 = (p1.x, screen_height - p1.y)  
    v2 = (p2.x, screen_height - p2.y) 
    
    pygame.draw.line(
        screen,
        color,
        v1,
        v2,
        int(shape.radius * 2)
    )