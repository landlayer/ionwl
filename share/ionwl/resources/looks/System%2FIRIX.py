# SPDX-License-Identifier: GPL-3.0-or-later

# SGI IRIX-inspired look.
#
# Warm olive-tan palette with prominent bevels, recalling the
# classic SGI 4Dwm / Motif window manager appearance.

import ion.app
from ion.types import ColorRGB, DecorLook


class Base:
    # 4Dwm active titlebar olive-tan.
    OLIVE = ColorRGB.from_rgb_hex(0xA59F80)
    # Inactive titlebar gray.
    GRAY = ColorRGB.from_rgb_hex(0x808080)
    # Inactive bevel highlight.
    GRAY_HI = ColorRGB.from_rgb_hex(0xC6C6C6)
    # Inactive bevel shadow.
    GRAY_SHADOW = ColorRGB.from_rgb_hex(0x424242)

    # Popup background.
    POPUP = ColorRGB.from_rgb_hex(0xC1C1C1)
    # Popup bevel highlight.
    POPUP_HI = ColorRGB.from_rgb_hex(0xE8E8E8)
    # Popup bevel shadow.
    POPUP_SHADOW = ColorRGB.from_rgb_hex(0x707070)

    WHITE = ColorRGB.from_rgb_hex(0xFFFFFF)
    BLACK = ColorRGB.from_rgb_hex(0x000000)


class Custom:
    RED = ColorRGB.from_rgb_hex(0xB85353)


look = DecorLook()

# Tab backgrounds.
look.tab_focused_active = Base.OLIVE
look.tab_focused_inactive = Base.GRAY
look.tab_unfocused_active = Base.GRAY
look.tab_unfocused_inactive = Base.GRAY
look.tab_urgent = Custom.RED
look.tab_urgent_bevel_highlight = Custom.RED.offset(0.25)
look.tab_urgent_bevel_shadow = Custom.RED.offset(-0.25)

# Active-tab bevels (derived from olive).
look.tab_focused_active_bevel_highlight = ColorRGB.from_rgb_hex(0xDAD7CA)
look.tab_focused_active_bevel_shadow = ColorRGB.from_rgb_hex(0x5B5746)
look.tab_unfocused_active_bevel_highlight = Base.GRAY_HI
look.tab_unfocused_active_bevel_shadow = Base.GRAY_SHADOW

# Default bevels (inactive tabs, frame borders).
look.bevel_highlight = Base.GRAY_HI
look.bevel_shadow = Base.GRAY_SHADOW

# Wider bevels for the chunky Motif/4Dwm look.
look.bevel_width = 2

# Text colors.
look.text_focused_active = Base.BLACK
look.text_inactive = Base.BLACK
look.text_urgent = Base.WHITE
look.text_disabled = Base.GRAY

# Borders.
look.border = Base.BLACK
look.floating_border = Base.BLACK

# Divider.
look.divider = Base.GRAY

# Menu.
look.menu_bg = Base.POPUP
look.menu_bevel_highlight = Base.POPUP_HI
look.menu_bevel_shadow = Base.POPUP_SHADOW

ion.app.decor.look = look
