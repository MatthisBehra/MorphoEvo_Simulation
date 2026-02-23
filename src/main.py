import pygame
import random

from physics.environment import Environment
from physics.renderer import draw_segment
from entities.creature import Creature
from physics.configscreen import ConfigScreen


SCREEN_WIDTH = 1080
SCREEN_HEIGHT = 720
FPS = 60
TIME_STEP = 1.0 / FPS

# Initialize the physics environment with downward gravity
env = Environment(gravity=(0, -900))
GROUND_Y_COORD_PYMUNK = 5
GROUND_COLOR = (0, 100, 0)

# Create a static collision shape representing the ground
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

    # Show config UI and retrieve parameters
    n_segments, n_creatures = ConfigScreen(screen, clock, SCREEN_WIDTH, SCREEN_HEIGHT).run()

    # Instantiate the population of creatures at a starting position
    creatures = []
    for i in range(n_creatures):
        start_pos = (100, 100 + random.uniform(-5, 5))
        creatures.append(Creature(env.space, start_pos, n_segments))

    # --- Main Simulation Loop ---
    running = True
    while running:
        # Handle window events (like closing the window)
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

        # Step the physics engine forward
        env.step(TIME_STEP)
        current_time = pygame.time.get_ticks() / 1000.0

        # Rendering: Clear screen and draw the static ground
        screen.fill((255, 255, 255))
        draw_segment(screen, sol_shape, SCREEN_HEIGHT, GROUND_COLOR)

        best_dist = 0
        # Update and render each creature
        for creature in creatures:
            creature.act(current_time)
            creature.draw(screen, SCREEN_HEIGHT)

            # Calculate horizontal distance traveled from start (X=100)
            dist = creature.get_position() - 100
            if dist > best_dist:
                best_dist = dist

        # Periodically log the position to the console (roughly every second)
        if pygame.time.get_ticks() % 1000 < 20:
            print(f"Position X: {creature.get_position():.2f}")

        pygame.display.flip()
        clock.tick(FPS)

    pygame.quit()