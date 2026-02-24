import pygame


class Camera:
    """
    Horizontal-only scrolling camera. The Y axis is fixed:
    the ground is always rendered at the bottom of the screen.

    Usage:
        camera = Camera(screen_width, screen_height)
        camera.follow(world_x)
        sx, sy = camera.world_to_screen(world_x, world_y)
        camera.draw_ground(screen, shape, color)
        camera.draw_creature(screen, creature, is_best=False)
    """

    def __init__(self, screen_w, screen_h, ground_y_world=5,
                 ground_margin=30, smooth=0.08):
        """
        :param ground_y_world:  Y coordinate of the ground in Pymunk world space.
        :param ground_margin:   Pixels from the bottom of the screen to the ground line.
        """
        self.screen_w       = screen_w
        self.screen_h       = screen_h
        self.x_offset       = 0.0
        self._smooth        = smooth

        # Fixed Y transform: world_y=ground_y_world maps to screen_y=(screen_h - ground_margin)
        # sy = screen_h - ground_margin - (world_y - ground_y_world)
        #    = (screen_h - ground_margin + ground_y_world) - world_y
        self._y_base = screen_h - ground_margin + ground_y_world

    # ── Transform ─────────────────────────────────────────────────────────────

    def follow(self, world_x):
        """Smoothly slide camera so world_x sits at horizontal centre."""
        target = world_x - self.screen_w // 2
        self.x_offset += (target - self.x_offset) * self._smooth

    def world_to_screen(self, world_x, world_y):
        """Convert Pymunk world coordinates to Pygame screen coordinates."""
        sx = world_x - self.x_offset
        sy = self._y_base - world_y        # Fixed Y: ground always at bottom
        return sx, sy

    # ── Drawing ───────────────────────────────────────────────────────────────

    def draw_ground(self, screen, shape, color):
        x1, y1 = self.world_to_screen(shape.a.x, shape.a.y)
        x2, y2 = self.world_to_screen(shape.b.x, shape.b.y)
        pygame.draw.line(screen, color, (x1, y1), (x2, y2),
                         max(1, int(shape.radius * 2)))

    def draw_creature(self, screen, creature, is_best=False):
        for shape in creature.shapes:
            verts = []
            for v in shape.get_vertices():
                wv = v.rotated(shape.body.angle) + shape.body.position
                verts.append(self.world_to_screen(wv.x, wv.y))

            color = creature.colors.get(id(shape), (120, 120, 120))
            outline_w = 3 if is_best else 1
            outline_c = (200, 50, 50) if is_best else (0, 0, 0)

            pygame.draw.polygon(screen, color, verts)
            pygame.draw.polygon(screen, outline_c, verts, outline_w)