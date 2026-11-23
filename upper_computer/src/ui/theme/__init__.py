# @file: src/ui/theme/__init__.py
# @brief: Transitional theme package exporting apply_uniuni_theme and apply_fusion_dark_theme for main.py compatibility.
# @exports: apply_uniuni_theme, apply_fusion_dark_theme

from src.ui.theme.fusion_dark_theme import apply_fusion_dark_theme
from src.ui.theme.uniuni_inspired_theme import apply_uniuni_theme

__all__ = ["apply_uniuni_theme", "apply_fusion_dark_theme"]
