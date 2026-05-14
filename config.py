"""
config.py - Constantes, configuración y paleta de colores de Magic Paint
"""
import os

# ─────────────────────────────────────────────
#  MODOS Y HERRAMIENTAS
# ─────────────────────────────────────────────
APP_MODE_PAINT = "PAINT"
APP_MODE_COLOR = "COLOR"
APP_MODE_FREE  = "FREE"

TOOL_BRUSH  = "BRUSH"
TOOL_FILL   = "FILL"
TOOL_ERASER = "ERASER"

# Índices de landmarks de MediaPipe
TIP = [4, 8, 12, 16, 20]
PIP = [3, 6, 10, 14, 18]

# ─────────────────────────────────────────────
#  PALETA DE COLORES DE LA UI
# ─────────────────────────────────────────────
UI = {
    "bg_dark":       (235, 248, 255),
    "bg_panel":      (255, 249, 230),
    "bg_panel2":     (255, 240, 210),
    "vivo_rojo":     (80,  107, 255),
    "vivo_verde":    (80,  222, 100),
    "vivo_azul":     (255, 160,  80),
    "vivo_amarillo": (80,  202, 254),
    "vivo_naranja":  (60,  159, 255),
    "vivo_morado":   (245, 110, 197),
    "vivo_rosa":     (157, 107, 255),
    "vivo_cyan":     (251, 219,  72),
    "text_blanco":   (50,   40,  30),
    "text_claro":    (100,  80,  60),
    "text_oscuro":   (240, 230, 220),
    "tool_brush":    (50,  205,  50),
    "tool_fill":     (255, 140,   0),
    "tool_eraser":   (220,  20,  60),
    "tool_color":    (148,   0, 211),
    "tool_undo":     (30,  144, 255),
    "tool_redo":     (30,  144, 255),
    "tool_clear":    (255,  69,   0),
    "tool_save":     (0,   200, 100),
    "tool_open":     (255,  20, 147),
    "tool_free":     (0,   206, 209),
    "tool_print":    (139,  90,  43),
    "mode_paint":    (80,  222, 100),
    "mode_color":    (60,  159, 255),
    "mode_free":     (251, 219,  72),
    "border_claro":  (200, 180, 150),
    "border_brillo": (150, 130, 100),
}

# ─────────────────────────────────────────────
#  CONFIGURACIÓN GENERAL
# ─────────────────────────────────────────────
CONFIG = {
    "camera_index": 0,
    "width":  1280,
    "height":  720,
    "flip_horizontal": True,
    "default_brush_size": 8,
    "min_brush_size": 2,
    "max_brush_size": 60,
    "eraser_multiplier": 3,
    "canvas_opacity": 0.80,
    "fill_tolerance": 28,
    "fill_tolerance_min": 4,
    "fill_tolerance_max": 80,
    "smoothing_points": 5,
    "gesture_smoothing": 8,
    "show_hud": True,
    "max_undo_steps": 50,
    "save_dir": "paintings",
    "save_format": "png",
    "detection_confidence": 0.65,
    "tracking_confidence":  0.65,
    "images_dir": "images_to_color",
    "image_extensions": ["*.png", "*.jpg", "*.jpeg", "*.bmp"],
    "mouse_smoothing": 7,
    "pinch_threshold": 45,
    "pinch_release_threshold": 60,
    "drag_min_move": 8,
    "click_cooldown_frames": 18,
    "right_click_cooldown": 22,
    "double_click_cooldown": 25,
    "mouse_zone_margin": 0.08,
    "skip_frames_detection": 1,
    "skip_frames_free_mode": 3,
    "particle_count": 12,
    "max_paint_splashes": 8,
    "ui_update_every": 1,
    "upec_logo_path": os.path.join(os.path.dirname(os.path.abspath(__file__)), "upec_logo.png"),
    "cloud_redraw_interval": 4,
}

# ─────────────────────────────────────────────
#  COLORES DE PINTURA (paleta básica)
# ─────────────────────────────────────────────
COLORS = [
    {"name": "Negro",      "bgr": (  0,   0,   0)},
    {"name": "Blanco",     "bgr": (255, 255, 255)},
    {"name": "Rojo",       "bgr": (  0,   0, 220)},
    {"name": "Naranja",    "bgr": (  0, 120, 255)},
    {"name": "Amarillo",   "bgr": (  0, 220, 220)},
    {"name": "Verde",      "bgr": (  0, 200,  60)},
    {"name": "Verde Oliva","bgr": (  0, 160,  80)},
    {"name": "Cian",       "bgr": (220, 200,   0)},
    {"name": "Azul",       "bgr": (230,  80,   0)},
    {"name": "Celeste",    "bgr": (240, 160,  80)},
    {"name": "Magenta",    "bgr": (200,   0, 200)},
    {"name": "Morado",     "bgr": (160,   0, 120)},
    {"name": "Rosa",       "bgr": (160, 100, 240)},
    {"name": "Marron",     "bgr": ( 30,  80, 140)},
    {"name": "Gris",       "bgr": (130, 130, 130)},
]

# ─────────────────────────────────────────────
#  LETRAS ANIMADAS DEL TÍTULO
# ─────────────────────────────────────────────
MAGIC_LETTERS = [
    ("M", (80, 107, 255)), ("A", (60, 159, 255)), ("G", (80, 202, 254)),
    ("I", (80, 222, 100)), ("C", (251, 219,  72)),
]
PAINT_LETTERS = [
    ("P", (245, 110, 197)), ("A", (157, 107, 255)), ("I", (60, 159, 255)),
    ("N", (80, 202, 254)),  ("T", (80, 107, 255)),
]
