"""
**Output Hotplug**

Use the ``output_add_pre`` hook to configure monitors as they are
connected. The callback receives the :class:`ion.types.Output` object before it
is used, so properties like position and transform take effect
immediately.
"""

import ion


@ion.app.hooks.output_add_pre.append
def configure_output(output: ion.types.Output) -> None:
    if output.name == "DP-2":
        output.configure(position=(0, 0), transform=90)
    elif output.name == "HDMI-A-1":
        output.configure(position=(2560, 0))
