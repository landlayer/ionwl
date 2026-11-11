# SPDX-License-Identifier: GPL-3.0-or-later

# Grey-violet default look.
#
# This is the compositor's built-in default color scheme: muted violet
# accents on a neutral grey background. All values here match the
# compiled-in defaults so this file serves as a reference and as a
# starting point for customization.
#
# Base colors are from the original Notion look_greyviolet.lua.
# Custom colors are additions that do not appear in the Lua source.

import ion.app
from ion.types import ColorRGB, DecorLook


class Base:
    # Muted violet for focused active elements.
    VIOLET = ColorRGB.from_rgb_hex(0x666699)
    # Lighter violet-grey for unfocused active elements.
    VIOLET_LIGHT = ColorRGB.from_rgb_hex(0x9999AA)
    # Focused active bevel pair.
    VIOLET_HIGHLIGHT = ColorRGB.from_rgb_hex(0xAAAACC)
    VIOLET_SHADOW = ColorRGB.from_rgb_hex(0x333366)
    # Unfocused active bevel pair.
    LAVENDER_HIGHLIGHT = ColorRGB.from_rgb_hex(0xEEEEFF)
    LAVENDER_SHADOW = ColorRGB.from_rgb_hex(0x777788)
    # Neutral grey for inactive elements.
    GRAY = ColorRGB.from_rgb_hex(0xAAAAAA)
    GRAY_MID = ColorRGB.from_rgb_hex(0x808080)

    # Dark red for urgent indicators (from Notion, not greyviolet).
    RED = ColorRGB.from_rgb_hex(0x901010)
    RED_HIGHLIGHT = ColorRGB.from_rgb_hex(0xC04040)
    RED_SHADOW = ColorRGB.from_rgb_hex(0x600808)

    WHITE = ColorRGB.from_rgb_hex(0xEEEEEE)
    BLACK = ColorRGB.from_rgb_hex(0x000000)


class Custom:
    # Default bevel shadow.
    GRAY_SHADOW = ColorRGB.from_rgb_hex(0x777777)


look = DecorLook()

# Tab backgrounds.
look.tab_focused_active = Base.VIOLET
look.tab_focused_inactive = Base.GRAY
look.tab_unfocused_active = Base.VIOLET_LIGHT
look.tab_unfocused_inactive = Base.GRAY
look.tab_urgent = Base.RED
look.tab_urgent_bevel_highlight = Base.RED_HIGHLIGHT
look.tab_urgent_bevel_shadow = Base.RED_SHADOW

# Active-tab bevels.
look.tab_focused_active_bevel_highlight = Base.VIOLET_HIGHLIGHT
look.tab_focused_active_bevel_shadow = Base.VIOLET_SHADOW
look.tab_unfocused_active_bevel_highlight = Base.LAVENDER_HIGHLIGHT
look.tab_unfocused_active_bevel_shadow = Base.LAVENDER_SHADOW

# Default bevels (inactive tabs, frame borders, menus).
look.bevel_highlight = Base.WHITE
look.bevel_shadow = Custom.GRAY_SHADOW

look.bevel_width = 1

# Text.
look.text_focused_active = Base.WHITE
look.text_inactive = Base.BLACK
look.text_urgent = Base.WHITE
look.text_disabled = Base.GRAY_MID

# Borders.
look.border = Base.BLACK
look.floating_border = Base.BLACK

# Divider.
look.divider = Base.VIOLET_LIGHT

# Menu.
look.menu_text = Base.WHITE
look.menu_text_inactive = Base.BLACK
look.menu_bg = Base.VIOLET_LIGHT
look.menu_bevel_highlight = Base.WHITE
look.menu_bevel_shadow = Custom.GRAY_SHADOW

ion.app.decor.look = look
