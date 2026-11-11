# SPDX-License-Identifier: GPL-3.0-or-later

# Amiga Workbench-inspired look.
#
# Blue and orange/white palette reminiscent of AmigaOS Workbench 3.1
# with its distinctive two-tone active/inactive title-bars.

import ion.app
from ion.types import ColorRGB, DecorLook


class Base:
    # Workbench 2.x screen blue.
    BLUE = ColorRGB.from_rgb_hex(0x6688CC)
    # Darker blue for unfocused active.
    BLUE_DARK = ColorRGB.from_rgb_hex(0x5571AA)
    # Workbench orange for alerts.
    ORANGE = ColorRGB.from_rgb_hex(0xDD8833)

    WHITE = ColorRGB.from_rgb_hex(0xFFFFFF)
    BLACK = ColorRGB.from_rgb_hex(0x000000)


class Custom:
    # Inactive window gray.
    GRAY = ColorRGB.from_rgb_hex(0x999999)
    GRAY_DARK = ColorRGB.from_rgb_hex(0x555555)
    GRAY_LIGHT = ColorRGB.from_rgb_hex(0xDDDDDD)
    GRAY_MID = ColorRGB.from_rgb_hex(0x808080)


look = DecorLook()

# Tab backgrounds.
look.tab_focused_active = Base.BLUE
look.tab_focused_inactive = Custom.GRAY
look.tab_unfocused_active = Base.BLUE_DARK
look.tab_unfocused_inactive = Custom.GRAY
look.tab_urgent = Base.ORANGE
look.tab_urgent_bevel_highlight = Base.ORANGE.offset(0.25)
look.tab_urgent_bevel_shadow = Base.ORANGE.offset(-0.25)

# Active-tab bevels (derived from the blue).
look.tab_focused_active_bevel_highlight = ColorRGB.from_rgb_hex(0xAABBEE)
look.tab_focused_active_bevel_shadow = ColorRGB.from_rgb_hex(0x334477)
look.tab_unfocused_active_bevel_highlight = ColorRGB.from_rgb_hex(0x8899CC)
look.tab_unfocused_active_bevel_shadow = ColorRGB.from_rgb_hex(0x2C3A66)

# Default bevels (inactive tabs).
look.bevel_highlight = Custom.GRAY_LIGHT
look.bevel_shadow = Custom.GRAY_DARK

look.bevel_width = 1

# Text: black on orange for urgent (high contrast on warm background).
look.text_focused_active = Base.BLACK
look.text_inactive = Base.BLACK
look.text_urgent = Base.BLACK
look.text_disabled = Custom.GRAY_MID

# Borders.
look.border = Base.BLACK
look.floating_border = Base.BLACK

# Divider.
look.divider = Custom.GRAY

ion.app.decor.look = look
