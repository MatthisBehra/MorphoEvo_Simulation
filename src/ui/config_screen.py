import pygame


# ─── Palette ─────────────────────────────────────────────────────────────────
C_BG      = (12, 14, 20)
C_PANEL   = (22, 26, 38)
C_ACCENT  = (80, 220, 140)
C_ACCENT2 = (60, 160, 255)
C_TEXT    = (220, 230, 240)
C_MUTED   = (100, 115, 135)
C_BORDER  = (45, 55, 75)


def draw_rounded_rect(surface, color, rect, radius=12, border=0, border_color=None):
    pygame.draw.rect(surface, color, rect, border_radius=radius)
    if border and border_color:
        pygame.draw.rect(surface, border_color, rect, border, border_radius=radius)


# ─── Widgets ──────────────────────────────────────────────────────────────────

class Slider:
    def __init__(self, x, y, w, min_val, max_val, default, label, color=C_ACCENT):
        self.rect      = pygame.Rect(x, y, w, 6)
        self.min       = min_val
        self.max       = max_val
        self.value     = default
        self.label     = label
        self.color     = color
        self.dragging  = False
        self.handle_r  = 11

    @property
    def handle_x(self):
        t = (self.value - self.min) / (self.max - self.min)
        return int(self.rect.x + t * self.rect.w)

    def handle_rect(self):
        hx = self.handle_x
        hy = self.rect.centery
        return pygame.Rect(hx - self.handle_r, hy - self.handle_r,
                           self.handle_r * 2, self.handle_r * 2)

    def handle_event(self, event):
        if event.type == pygame.MOUSEBUTTONDOWN:
            if self.handle_rect().collidepoint(event.pos):
                self.dragging = True
        elif event.type == pygame.MOUSEBUTTONUP:
            self.dragging = False
        elif event.type == pygame.MOUSEMOTION and self.dragging:
            rel = (event.pos[0] - self.rect.x) / self.rect.w
            self.value = round(self.min + max(0, min(1, rel)) * (self.max - self.min))

    def draw(self, surface, font_sm, font_val):
        track_bg = pygame.Rect(self.rect.x, self.rect.centery - 3, self.rect.w, 6)
        draw_rounded_rect(surface, C_BORDER, track_bg, 3)

        filled_w = self.handle_x - self.rect.x
        if filled_w > 0:
            track_fill = pygame.Rect(self.rect.x, self.rect.centery - 3, filled_w, 6)
            draw_rounded_rect(surface, self.color, track_fill, 3)

        hx, hy = self.handle_x, self.rect.centery
        pygame.draw.circle(surface, C_BG, (hx, hy), self.handle_r)
        pygame.draw.circle(surface, self.color, (hx, hy), self.handle_r - 2)

        lbl = font_sm.render(self.label, True, C_MUTED)
        surface.blit(lbl, (self.rect.x, self.rect.y - 28))

        val_txt = font_val.render(str(self.value), True, self.color)
        surface.blit(val_txt, (self.rect.right + 18, self.rect.centery - val_txt.get_height() // 2))


class Button:
    def __init__(self, x: int, y: int, w: int, h: int, text: str):
        self.rect     = pygame.Rect(x, y, w, h)
        self.text     = text
        self._hovered = False

    def handle_event(self, event: pygame.event.Event) -> bool:
        if event.type == pygame.MOUSEMOTION:
            self._hovered = self.rect.collidepoint(event.pos)
        if event.type == pygame.MOUSEBUTTONDOWN:
            if self.rect.collidepoint(event.pos):
                return True
        return False

    def draw(self, surface: pygame.Surface, font: pygame.font.Font) -> None:
        color = C_ACCENT if self._hovered else (40, 180, 110)
        draw_rounded_rect(surface, color, self.rect, radius=10)
        txt = font.render(self.text, True, C_BG)
        tw, th = txt.get_size()
        surface.blit(txt, (self.rect.centerx - tw // 2, self.rect.centery - th // 2))


class SpeedSelector:
    """Sélecteur horizontal de vitesse de simulation (boutons-radio)."""

    # Options : (label affiché, valeur numérique interne)
    OPTIONS: list[tuple[str, int]] = [("1x", 1), ("4x", 4), ("8x", 8), ("HEADLESS", -1)]

    def __init__(self, center_x: int, y: int, btn_w: int = 90, btn_h: int = 32, gap: int = 10):
        self.selected: str = "4x"  # Défaut : 4x
        self.btn_w = btn_w
        self.btn_h = btn_h
        self.gap = gap
        # Calcul de la largeur totale pour centrer le groupe
        total_w = len(self.OPTIONS) * btn_w + (len(self.OPTIONS) - 1) * gap
        start_x = center_x - total_w // 2
        # Pré-calcul des rectangles pour chaque option
        self._rects: list[tuple[str, pygame.Rect]] = []
        for i, (label, _val) in enumerate(self.OPTIONS):
            rx = start_x + i * (btn_w + gap)
            self._rects.append((label, pygame.Rect(rx, y, btn_w, btn_h)))

    def handle_event(self, event: pygame.event.Event) -> None:
        """Gère le clic sur un bouton du sélecteur."""
        if event.type == pygame.MOUSEBUTTONDOWN:
            for label, rect in self._rects:
                if rect.collidepoint(event.pos):
                    self.selected = label
                    break

    def draw(self, surface: pygame.Surface, font: pygame.font.Font) -> None:
        """Dessine le groupe de boutons-radio."""
        for label, rect in self._rects:
            is_active = (label == self.selected)
            bg = C_ACCENT if is_active else C_PANEL
            fg = C_BG if is_active else C_MUTED
            border_col = C_ACCENT if is_active else C_BORDER
            draw_rounded_rect(surface, bg, rect, radius=8,
                              border=1, border_color=border_col)
            txt = font.render(label, True, fg)
            tw, th = txt.get_size()
            surface.blit(txt, (rect.centerx - tw // 2, rect.centery - th // 2))

    @property
    def selected_mode(self) -> str:
        """Retourne la chaîne de mode normalisée pour la valeur de retour."""
        return self.selected.lower()


# ─── Main class ───────────────────────────────────────────────────────────────

class ConfigScreen:
    """
    Displays a configuration UI and blocks until the user clicks "Launch".

    Usage:
        config = ConfigScreen(screen, clock, screen_width, screen_height)
        n_segments, n_creatures = config.run()
    """

    def __init__(self, screen, clock, screen_width, screen_height):
        self.screen  = screen
        self.clock   = clock
        self.sw      = screen_width
        self.sh      = screen_height

        pygame.font.init()
        self.font_title = pygame.font.SysFont("Courier New", 38, bold=True)
        self.font_sub   = pygame.font.SysFont("Courier New", 15)
        self.font_sm    = pygame.font.SysFont("Courier New", 14)
        self.font_val   = pygame.font.SysFont("Courier New", 22, bold=True)
        self.font_btn   = pygame.font.SysFont("Courier New", 18, bold=True)

        cx = self.sw // 2
        panel_w, panel_h = 560, 540  # +80px pour le sélecteur de vitesse
        self.panel_rect = pygame.Rect(
            cx - panel_w // 2,
            self.sh // 2 - panel_h // 2,
            panel_w, panel_h
        )

        sx = self.panel_rect.x + 50
        sw = panel_w - 140

        self.slider_duration = Slider(sx, self.panel_rect.y + 110, sw,
                                      5, 60, 15, "GENERATION DURATION (s)", color=C_ACCENT)
        self.slider_pop = Slider(sx, self.panel_rect.y + 210, sw,
                                 1, 100, 30, "POPULATION SIZE", color=C_ACCENT2)
        self.slider_showcase = Slider(sx, self.panel_rect.y + 310, sw,
                                      0, 3, 3, "SHOWCASE DURATION (s)", color=C_ACCENT)
        # Sélecteur de vitesse (entre le slider showcase et le bouton Launch)
        self.speed_selector = SpeedSelector(cx, self.panel_rect.y + 390)
        self.btn = Button(cx - 100, self.panel_rect.bottom - 65, 200, 44, "LAUNCH SIMULATION")

    def run(self) -> tuple[int, int, int, str]:
        """Bloque jusqu'à validation, retourne (gen_duration, n_creatures, showcase_duration, speed_mode)."""
        tick: int = 0
        while True:
            self.clock.tick(60)
            tick += 1

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    pygame.quit()
                    raise SystemExit
                self.slider_duration.handle_event(event)
                self.slider_pop.handle_event(event)
                self.slider_showcase.handle_event(event)
                self.speed_selector.handle_event(event)
                if self.btn.handle_event(event):
                    return (
                        self.slider_duration.value,
                        self.slider_pop.value,
                        self.slider_showcase.value,
                        self.speed_selector.selected_mode,
                    )

            self._draw(tick)
            pygame.display.flip()

    # ─── Private drawing helpers ──────────────────────────────────────────────

    def _draw(self, tick):
        self.screen.fill(C_BG)
        self._draw_grid()
        self._draw_corner_accents()
        self._draw_panel(tick)

    def _draw_grid(self):
        for x in range(0, self.sw, 60):
            pygame.draw.line(self.screen, (20, 24, 36), (x, 0), (x, self.sh))
        for y in range(0, self.sh, 60):
            pygame.draw.line(self.screen, (20, 24, 36), (0, y), (self.sw, y))

    def _draw_corner_accents(self):
        corners = [
            ((0, 0),           1,  1),
            ((self.sw, 0),    -1,  1),
            ((0, self.sh),     1, -1),
            ((self.sw, self.sh), -1, -1),
        ]
        for (cx, cy), dx, dy in corners:
            pygame.draw.line(self.screen, C_ACCENT, (cx, cy), (cx + dx * 40, cy), 2)
            pygame.draw.line(self.screen, C_ACCENT, (cx, cy), (cx, cy + dy * 40), 2)

    def _draw_panel(self, tick):
        pr = self.panel_rect

        draw_rounded_rect(self.screen, C_PANEL, pr, radius=16,
                          border=1, border_color=C_BORDER)

        # Top accent bar
        bar = pygame.Rect(pr.x, pr.y, pr.w, 4)
        pygame.draw.rect(self.screen, C_ACCENT, bar, border_radius=2)

        # Title
        title = self.font_title.render("EVOLUTION CONFIG", True, C_TEXT)
        self.screen.blit(title, (pr.centerx - title.get_width() // 2, pr.y + 22))

        # Animated subtitle
        dots = "." * ((tick // 20) % 4)
        sub = self.font_sub.render(f"configure your simulation{dots}", True, C_MUTED)
        self.screen.blit(sub, (pr.centerx - sub.get_width() // 2, pr.y + 68))

        # Sliders
        self.slider_duration.draw(self.screen, self.font_sm, self.font_val)
        self.slider_pop.draw(self.screen, self.font_sm, self.font_val)
        self.slider_showcase.draw(self.screen, self.font_sm, self.font_val)

        # Label du sélecteur de vitesse
        speed_lbl = self.font_sm.render("SPEED MODE", True, C_MUTED)
        self.screen.blit(speed_lbl, (pr.centerx - speed_lbl.get_width() // 2, pr.y + 358))

        # Sélecteur de vitesse
        self.speed_selector.draw(self.screen, self.font_sm)

        # Divider
        div_y = pr.bottom - 80
        pygame.draw.line(self.screen, C_BORDER, (pr.x + 30, div_y), (pr.right - 30, div_y), 1)

        # Button
        self.btn.draw(self.screen, self.font_btn)