# SPDX-License-Identifier: GPL-3.0-or-later

"""RenderWake Blender extension entrypoint."""

from .addon import renderwake as _impl


def register():
    _impl.register()


def unregister():
    _impl.unregister()
