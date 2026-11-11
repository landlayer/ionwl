# SPDX-License-Identifier: GPL-3.0-or-later

# BeOS-inspired look.
#
# Yellow active titlebars with gray inactive, matching the classic
# BeOS/Haiku desktop appearance.

import ion.app
from ion.types import ColorRGB, DecorLook


class Base:
    # Title bar yellow.
    YELLOW = ColorRGB.from_rgb_hex(0xD4CA46)
    # Panel/inactive gray.
    GRAY = ColorRGB.from_rgb_hex(0xE8E8E8)
    # Grey just above the shadow from the resize button (inactive).
    GRAY_MUTED = ColorRGB.from_rgb_hex(0xD3D3D3)
    # Bevel/shadow gray.
    GRAY_DARK = ColorRGB.from_rgb_hex(0x808080)

    GRAY_INACTIVE_TEXT = ColorRGB.from_rgb_hex(0x505050)

    WHITE = ColorRGB.from_rgb_hex(0xFFFFFF)
    BLACK = ColorRGB.from_rgb_hex(0x000000)


class Custom:
    RED = ColorRGB.from_rgb_hex(0xCC3333)
    DISABLED = ColorRGB.from_rgb_hex(0x999999)


look = DecorLook()

# Tab backgrounds.
look.tab_focused_active = Base.YELLOW
look.tab_focused_inactive = Base.GRAY
look.tab_unfocused_active = Base.GRAY_MUTED
look.tab_unfocused_inactive = Base.GRAY
look.tab_urgent = Custom.RED
look.tab_urgent_bevel_highlight = Custom.RED.offset(0.25)
look.tab_urgent_bevel_shadow = Custom.RED.offset(-0.25)

# Active-tab bevels (derived from the yellow).
look.tab_focused_active_bevel_highlight = ColorRGB.from_rgb_hex(0xF2ED95)
look.tab_focused_active_bevel_shadow = ColorRGB.from_rgb_hex(0x8B8322)
look.tab_unfocused_active_bevel_highlight = ColorRGB.from_rgb_hex(0xD4CE76)
look.tab_unfocused_active_bevel_shadow = ColorRGB.from_rgb_hex(0x726C1D)

# Default bevels (inactive tabs).
look.bevel_highlight = Base.WHITE
look.bevel_shadow = Base.GRAY_DARK

look.bevel_width = 1

# Text: black on yellow title-bars for readability.
look.text_focused_active = Base.BLACK
look.text_inactive = Base.GRAY_INACTIVE_TEXT
look.text_urgent = Base.WHITE
look.text_disabled = Custom.DISABLED

# Borders.
look.border = Base.BLACK
look.floating_border = Base.BLACK

# Divider.
look.divider = Base.GRAY

ion.app.decor.look = look
