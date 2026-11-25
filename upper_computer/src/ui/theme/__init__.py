# @file: src/ui/theme/__init__.py
# @brief: Theme package exporting apply_studio_theme and apply_fusion_dark_theme.
# @exports: apply_studio_theme, apply_fusion_dark_theme

from src.ui.theme.fusion_dark_theme import apply_fusion_dark_theme
from src.ui.theme.studio_dark_theme import apply_studio_theme

__all__ = ["apply_studio_theme", "apply_fusion_dark_theme"]
