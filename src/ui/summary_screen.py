import pygame


def draw_summary_overlay(screen, font_lg, font_sm, gen_num,
                         best_fit_a, best_fit_b, remaining_s):
    """
    Semi-transparent banner centred on the screen divider during SHOWCASE state.
    Called every frame while state == STATE_SHOWCASE.
    """
    sw = screen.get_width()
    banner_h = 90
    banner_y = screen.get_height() // 2 - banner_h // 2

    bg = pygame.Surface((sw, banner_h), pygame.SRCALPHA)
    bg.fill((10, 10, 30, 210))
    screen.blit(bg, (0, banner_y))

    pygame.draw.line(screen, (80, 220, 140), (0, banner_y), (sw, banner_y), 2)
    pygame.draw.line(screen, (80, 220, 140),
                     (0, banner_y + banner_h), (sw, banner_y + banner_h), 2)

    line1 = font_lg.render(
        f"GENERATION {gen_num}  —  BEST CREATURES", True, (220, 230, 240))
    line2 = font_sm.render(
        f"Env A : {best_fit_a:.1f} px    |    "
        f"Env B : {best_fit_b:.1f}    |    "
        f"Next gen in {max(0.0, remaining_s):.1f}s",
        True, (150, 200, 240),
    )

    gap = 6
    total_h = line1.get_height() + gap + line2.get_height()
    y1 = banner_y + (banner_h - total_h) // 2

    screen.blit(line1, (sw // 2 - line1.get_width() // 2, y1))
    screen.blit(line2, (sw // 2 - line2.get_width() // 2,
                        y1 + line1.get_height() + gap))
