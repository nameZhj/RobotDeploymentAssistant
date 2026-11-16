# @file: src/ui/theme/fusion_dark_theme.py
# @brief: Compatibility theme entry forwarding to the UniUni v3 theme engine.
# @exports: apply_fusion_dark_theme

from __future__ import annotations

from typing import Any

from src.ui.theme.uniuni_inspired_theme import apply_uniuni_theme


def apply_fusion_dark_theme(app: Any) -> None:
    """Forward Fusion dark theme request to UniUni v3 palette initializer."""
    apply_uniuni_theme(app)
