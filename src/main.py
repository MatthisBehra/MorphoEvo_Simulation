import pygame
import pymunk

from physics.environment import Environment
from physics.renderer import draw_segment

SCREEN_WIDTH = 1080
SCREEN_HEIGHT = 720 
FPS = 60
TIME_STEP = 1.0 / FPS

env = Environment(gravity=(0, -900))
GROUND_Y_COORD_PYMUNK = 5
GROUND_COLOR = (0, 0, 0)

sol_shape = env.add_static_segment(
    start=(0, GROUND_Y_COORD_PYMUNK),
    end=(SCREEN_WIDTH, GROUND_Y_COORD_PYMUNK),
    thickness=5.0
)


if __name__ == "__main__":
    pygame.init()
    screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
    pygame.display.set_caption("Evolution Simulation")
    clock = pygame.time.Clock()
    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
        env.step(TIME_STEP)
        screen.fill((255, 255, 255)) 
        draw_segment(screen, sol_shape, SCREEN_HEIGHT, GROUND_COLOR) 
        
        pygame.display.flip()
        clock.tick(FPS)  
    pygame.quit()