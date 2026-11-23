# @file: src/ui/design_system/tokens.py
# @brief: Authoritative UniUni v3 design tokens (ugc-v3.css) for dark surfaces, brand accents, typography, and layout sizing.
# @exports: C_CANVAS, C_BASE, C_PANEL, C_CARD, C_CONTROL, C_CONTROL_HOVER, C_FLOAT, C_ACCENT, C_OK, C_WARN, C_DANGER, ROBOT_COLORS, C_TEXT_1, C_TEXT_2, C_TEXT_3, LINE, LINE_STRONG, H_HEADER, H_STATUS, W_RIGHT_LIB, W_OPBAR, W_TRACK_HEAD

from __future__ import annotations

# Surface Palette (Dark-mode layered neutrals)
C_CANVAS = "#060708"
C_BASE = "#0b0c0f"
C_PANEL = "#101114"
C_CARD = "#15161a"
C_CONTROL = "#191a20"
C_CONTROL_HOVER = "#20222a"

# Floating Overlays & Modals
C_FLOAT = "#0e0f12"
C_FLOAT_2 = "#121317"
C_FLOAT_3 = "#16171c"
C_FLOAT_EDGE = "rgba(236, 239, 243, 0.22)"

# Brand Accent & Semantic Status
C_ACCENT = "#2e7bf7"
C_ACCENT_DIM = "rgba(46, 123, 247, 0.16)"
C_ACCENT_BORDER = "rgba(46, 123, 247, 0.45)"
C_ACCENT_BRIGHT = "#6fa3ff"
C_ON_ACCENT = "#ffffff"

C_OK = "#2bb673"
C_OK_DIM = "rgba(43, 182, 115, 0.18)"
C_WARN = "#f0a228"
C_WARN_DIM = "rgba(240, 162, 40, 0.18)"
C_DANGER = "#ee4d5a"
C_DANGER_DIM = "rgba(238, 77, 90, 0.18)"

# Robot Track Color Coding (--robot-1..5)
ROBOT_COLORS = (
    "#2e7bf7",
    "#8b7cff",
    "#e06fc4",
    "#f0a228",
    "#2bb673",
)

# Typography & Hairlines
C_TEXT_1 = "#e4e6ea"
C_TEXT_2 = "#9ba0aa"
C_TEXT_3 = "#6a6f78"

LINE = "rgba(236, 239, 243, 0.10)"
LINE_STRONG = "rgba(236, 239, 243, 0.18)"

# Font Stacks
FONT_UI = '"Microsoft YaHei UI", "PingFang SC", "Segoe UI", sans-serif'
FONT_MONO = '"JetBrains Mono", "Consolas", "Cascadia Mono", monospace'

# Radii & Control Dimensions
R_CARD = 8
R_BTN = 6
R_CTRL = 4

H_BTN = 32
H_BTN_SM = 28
H_BTN_XS = 24

# Fixed UniUni Shell Geometry
H_HEADER = 32
H_STATUS = 28
H_TL_HEADER = 38
H_TL_RULER = 28
H_TL_TRACK = 54

W_RIGHT_LIB = 330
W_OPBAR = 40
W_TRACK_HEAD = 168
