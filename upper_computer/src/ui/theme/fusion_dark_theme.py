# @file: src/ui/theme/fusion_dark_theme.py
# @brief: Compatibility theme entry forwarding to the studio dark theme engine.
# @exports: apply_fusion_dark_theme

from __future__ import annotations

from typing import Any

from src.ui.theme.studio_dark_theme import apply_studio_theme


def apply_fusion_dark_theme(app: Any) -> None:
    """Forward Fusion dark theme request to studio palette initializer."""
    apply_studio_theme(app)
