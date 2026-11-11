# SPDX-License-Identifier: GPL-3.0-or-later

# i3wm-inspired look.
#
# Dark blue focused titlebars with gray inactive, matching the
# default i3 window manager color scheme.

import ion.app
from ion.types import ColorRGB, DecorLook


class Base:
    # Focused titlebar background.
    BLUE = ColorRGB.from_rgb_hex(0x285577)
    # Focused border / lighter blue.
    BLUE_BORDER = ColorRGB.from_rgb_hex(0x4C7899)
    # Focused-inactive / unfocused-active gray.
    GRAY = ColorRGB.from_rgb_hex(0x5F676A)
    # Dark gray for inactive windows.
    DARK_GRAY = ColorRGB.from_rgb_hex(0x222222)
    # Unfocused border.
    DARK_BORDER = ColorRGB.from_rgb_hex(0x333333)

    WHITE = ColorRGB.from_rgb_hex(0xFFFFFF)
    BLACK = ColorRGB.from_rgb_hex(0x000000)


class Custom:
    # Urgent background.
    RED = ColorRGB.from_rgb_hex(0x900000)
    # Urgent border.
    RED_BORDER = ColorRGB.from_rgb_hex(0x2F343A)
    # Unfocused text.
    TEXT_DIM = ColorRGB.from_rgb_hex(0x888888)
    # Disabled text.
    TEXT_DISABLED = ColorRGB.from_rgb_hex(0x666666)


look = DecorLook()

# Tab backgrounds.
look.tab_focused_active = Base.BLUE
look.tab_focused_inactive = Base.DARK_GRAY
look.tab_unfocused_active = Base.GRAY
look.tab_unfocused_inactive = Base.DARK_GRAY
look.tab_urgent = Custom.RED
look.tab_urgent_bevel_highlight = Custom.RED.offset(0.15)
look.tab_urgent_bevel_shadow = Custom.RED.offset(-0.15)

# Active-tab bevels (derived from the blue).
look.tab_focused_active_bevel_highlight = Base.BLUE_BORDER
look.tab_focused_active_bevel_shadow = Base.BLUE_BORDER
look.tab_unfocused_active_bevel_highlight = Base.DARK_BORDER
look.tab_unfocused_active_bevel_shadow = Base.DARK_BORDER

# Default bevels (inactive tabs).
look.bevel_highlight = Base.DARK_BORDER
look.bevel_shadow = Base.DARK_BORDER

look.bevel_width = 1

# Text: white on focused, dim on unfocused.
look.text_focused_active = Base.WHITE
look.text_inactive = Custom.TEXT_DIM
look.text_urgent = Base.WHITE
look.text_disabled = Custom.TEXT_DISABLED

# Menu text.
look.menu_text = Base.BLACK
look.menu_text_inactive = Base.BLACK

# Borders.
look.border = Base.DARK_BORDER
look.floating_border = Base.DARK_BORDER

# Divider.
look.divider = Base.DARK_BORDER

ion.app.decor.look = look
