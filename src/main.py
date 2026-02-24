import pygame
import random

from physics.environment import Environment
from entities.creature import Creature
from ui.config_screen import ConfigScreen
from ui.camera import Camera


SCREEN_WIDTH  = 1080
SCREEN_HEIGHT = 720
FPS           = 60
TIME_STEP     = 1.0 / FPS

# ─── Physics world ────────────────────────────────────────────────────────────
env = Environment(gravity=(0, -900))
GROUND_Y_COORD_PYMUNK = 5
GROUND_COLOR          = (0, 100, 0)

sol_shape = env.add_static_segment(
    start=(0, GROUND_Y_COORD_PYMUNK),
    end=(SCREEN_WIDTH * 200, GROUND_Y_COORD_PYMUNK),
    thickness=5.0
)


# ─── HUD ──────────────────────────────────────────────────────────────────────
def draw_hud(screen, font, best_dist, best_idx, n_creatures):
    bg = pygame.Surface((220, 76), pygame.SRCALPHA)
    bg.fill((255, 255, 255, 160))
    screen.blit(bg, (8, 8))
    lines = [
        f"Best creature : #{best_idx + 1}",
        f"Distance      : {best_dist:.1f} px",
        f"Population    : {n_creatures}",
    ]
    for i, line in enumerate(lines):
        surf = font.render(line, True, (30, 30, 30))
        screen.blit(surf, (14, 14 + i * 22))


# ─── Entry point ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    pygame.init()
    screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
    pygame.display.set_caption("Evolution Simulation")
    clock = pygame.time.Clock()
    font  = pygame.font.SysFont("Courier New", 16, bold=True)

    n_segments, n_creatures = ConfigScreen(screen, clock, SCREEN_WIDTH, SCREEN_HEIGHT).run()

    creatures = []
    for i in range(n_creatures):
        start_pos = (100 + i * 20, GROUND_Y_COORD_PYMUNK + 120 + random.uniform(-5, 5))  # Above ground, spaced out
        creatures.append(Creature(env.space, start_pos, n_segments))

    camera = Camera(SCREEN_WIDTH, SCREEN_HEIGHT)

    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

        env.step(TIME_STEP)
        current_time = pygame.time.get_ticks() / 1000.0

        # ── Find leader ───────────────────────────────────────────────────────
        best_idx  = 0
        best_dist = 0
        for i, c in enumerate(creatures):
            dist = c.get_fitness(start_x=100)
            if dist > best_dist:
                best_dist = dist
                best_idx  = i

        camera.follow(creatures[best_idx].get_position())

        # ── Render ────────────────────────────────────────────────────────────
        screen.fill((220, 235, 255))
        camera.draw_ground(screen, sol_shape, GROUND_COLOR)

        for i, c in enumerate(creatures):
            c.act(current_time)
            camera.draw_creature(screen, c, is_best=(i == best_idx))

        # "BEST" label above the leader
        lx, ly = camera.world_to_screen(
            creatures[best_idx].get_position(),
            creatures[best_idx].bodies[0].position.y + 35,
        )
        label = font.render("★ BEST", True, (200, 50, 50))
        screen.blit(label, (lx - label.get_width() // 2, ly))

        draw_hud(screen, font, best_dist, best_idx, n_creatures)

        pygame.display.flip()
        clock.tick(FPS)

    pygame.quit()