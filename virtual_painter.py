"""
╔══════════════════════════════════════════════════════════════════════╗
║      MAGIC PAINT  — Pintura Virtual con Gestos de Mano  v5.0        ║
║           Python + OpenCV + MediaPipe  |  Edicion Feria             ║
║                    [VERSION NIÑOS - TEMA ALEGRE]                    ║
╠══════════════════════════════════════════════════════════════════════╣
║  CAMBIOS v5.0:                                                       ║
║   • Botones con colores más saturados y visibles                    ║
║   • Optimización de lag en modo libre (skip frames, menos blends)   ║
║   • Botón IMPRIMIR con encabezado UPEC + logo institucional         ║
╚══════════════════════════════════════════════════════════════════════╝
"""

import cv2
import mediapipe as mp
import numpy as np
import os, sys, time, math, glob
from collections import deque
from datetime import datetime

try:
    import pyautogui
    pyautogui.FAILSAFE = False
    pyautogui.PAUSE    = 0.0
    PYAUTOGUI_OK = True
except ImportError:
    PYAUTOGUI_OK = False

# =============================================================
#  TEMA VISUAL — COLORES CÁLIDOS Y ALEGRES PARA NIÑOS
# =============================================================
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
    # ── Botones IZQUIERDOS — colores saturados y contrastantes ──────
    "tool_brush":    (0,   180,  0),     # Verde puro intenso
    "tool_fill":     (0,   120, 255),    # Azul vivo
    "tool_eraser":   (0,    50, 220),    # Rojo intenso
    "tool_color":    (180,   0, 180),    # Morado saturado
    # ── Botones DERECHOS ────────────────────────────────────────────
    "tool_undo":     (200, 130,   0),    # Naranja oscuro
    "tool_redo":     (200, 130,   0),    # Naranja oscuro
    "tool_clear":    (0,     0, 200),    # Rojo fuerte
    "tool_save":     (0,   160,   0),    # Verde oscuro
    "tool_open":     (180,   0, 140),    # Magenta oscuro
    "tool_free":     (0,   160, 160),    # Cyan oscuro
    "tool_print":    (100,  60,   0),    # Café/marrón oscuro — NUEVO
    "mode_paint":    (80,  222, 100),
    "mode_color":    (60,  159, 255),
    "mode_free":     (251, 219,  72),
    "border_claro":  (200, 180, 150),
    "border_brillo": (150, 130, 100),
}

# =============================================================
#  CONFIGURACION
# =============================================================
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
    # ── OPTIMIZACIÓN: skip más agresivo en modo libre ─────────────
    "skip_frames_detection": 1,
    "skip_frames_free_mode": 2,      # NUEVO: salta más frames en modo libre
    "particle_count": 20,
    "max_paint_splashes": 15,
    "ui_update_every": 2,
    # Ruta del logo institucional (relativa al script)
    "upec_logo_path": os.path.join(os.path.dirname(os.path.abspath(__file__)), "upec_logo.png"),
}

# =============================================================
#  PALETA DE COLORES (BGR)
# =============================================================
COLORS = [
    {"name": "Negro",    "bgr": (  0,   0,   0)},
    {"name": "Blanco",   "bgr": (255, 255, 255)},
    {"name": "Rojo",     "bgr": (  0,   0, 220)},
    {"name": "Naranja",  "bgr": (  0, 120, 255)},
    {"name": "Amarillo", "bgr": (  0, 220, 220)},
    {"name": "Verde",    "bgr": (  0, 200,  60)},
    {"name": "Verde Oliva","bgr": (  0, 160,  80)},
    {"name": "Cian",     "bgr": (220, 200,   0)},
    {"name": "Azul",     "bgr": (230,  80,   0)},
    {"name": "Celeste",  "bgr": (240, 160,  80)},
    {"name": "Magenta",  "bgr": (200,   0, 200)},
    {"name": "Morado",   "bgr": (160,   0, 120)},
    {"name": "Rosa",     "bgr": (160, 100, 240)},
    {"name": "Marron",   "bgr": ( 30,  80, 140)},
    {"name": "Gris",     "bgr": (130, 130, 130)},
]

APP_MODE_PAINT  = "PAINT"
APP_MODE_COLOR  = "COLOR"
APP_MODE_FREE   = "FREE"
TOOL_BRUSH  = "BRUSH"
TOOL_FILL   = "FILL"
TOOL_ERASER = "ERASER"

TIP = [4, 8, 12, 16, 20]
PIP = [3, 6, 10, 14, 18]

MAGIC_LETTERS = [
    ("M", (80,  107, 255)),
    ("A", (60,  159, 255)),
    ("G", (80,  202, 254)),
    ("I", (80,  222, 100)),
    ("C", (251, 219,  72)),
]
PAINT_LETTERS = [
    ("P", (245, 110, 197)),
    ("A", (157, 107, 255)),
    ("I", (60,  159, 255)),
    ("N", (80,  202, 254)),
    ("T", (80,  107, 255)),
]

# =============================================================
#  NUBES ANIMADAS
# =============================================================
def draw_clouds(frame, t):
    H, W = frame.shape[:2]
    clouds = [
        {"base_x": 120,  "y": 55,  "speed": 0.30, "scale": 1.00, "alpha": 0.55},
        {"base_x": 400,  "y": 35,  "speed": 0.18, "scale": 1.30, "alpha": 0.45},
        {"base_x": 700,  "y": 75,  "speed": 0.24, "scale": 0.85, "alpha": 0.50},
        {"base_x": 950,  "y": 45,  "speed": 0.35, "scale": 0.75, "alpha": 0.40},
        {"base_x": 1100, "y": 65,  "speed": 0.20, "scale": 0.90, "alpha": 0.38},
    ]
    overlay = frame.copy()
    for c in clouds:
        offset = int((t * c["speed"] * 60) % (W + 300)) - 150
        cx = (c["base_x"] + offset) % (W + 200) - 100
        cy = int(c["y"])
        s  = c["scale"]
        col = (255, 255, 255)
        cv2.ellipse(overlay, (int(cx),       int(cy+30*s)), (int(80*s), int(30*s)), 0, 0, 360, col, -1)
        cv2.ellipse(overlay, (int(cx-45*s),  int(cy+18*s)), (int(42*s), int(32*s)), 0, 0, 360, col, -1)
        cv2.ellipse(overlay, (int(cx+45*s),  int(cy+14*s)), (int(46*s), int(36*s)), 0, 0, 360, col, -1)
        cv2.ellipse(overlay, (int(cx+5*s),   int(cy)),      (int(38*s), int(32*s)), 0, 0, 360, col, -1)
        cv2.circle(overlay, (int(cx-12*s), int(cy+10*s)), max(1, int(4*s)), (135, 180, 210), -1)
        cv2.circle(overlay, (int(cx+14*s), int(cy+10*s)), max(1, int(4*s)), (135, 180, 210), -1)
        cv2.circle(overlay, (int(cx-10*s), int(cy+8*s)),  max(1, int(2*s)), (255, 255, 255), -1)
        cv2.circle(overlay, (int(cx+16*s), int(cy+8*s)),  max(1, int(2*s)), (255, 255, 255), -1)
        cv2.ellipse(overlay, (int(cx+1*s), int(cy+18*s)),
                    (int(10*s), int(6*s)), 0, 0, 180, (135, 180, 210), max(1, int(2*s)))
    cv2.addWeighted(overlay, 0.60, frame, 0.40, 0, frame)


# =============================================================
#  TÍTULO ANIMADO LETRA A LETRA
# =============================================================
def draw_animated_title(frame, cx, start_y, t):
    font  = cv2.FONT_HERSHEY_SIMPLEX
    scale = 0.82
    thick = 2
    lw    = 23
    gap   = 3
    for letters, y in [(MAGIC_LETTERS, start_y), (PAINT_LETTERS, start_y + 38)]:
        total_w = len(letters) * (lw + gap)
        x = cx - total_w // 2
        for i, (ch, col) in enumerate(letters):
            phase   = math.sin(t * 2.8 + i * 0.75)
            dy      = int(phase * 5)
            scale_f = scale + 0.07 * abs(phase)
            cv2.putText(frame, ch, (x+2, y+dy+2), font,
                        scale_f, (200, 175, 140), thick+1, cv2.LINE_AA)
            cv2.putText(frame, ch, (x, y+dy), font,
                        scale_f, col, thick, cv2.LINE_AA)
            x += lw + gap


# =============================================================
#  HELPERS DE DIBUJO UI
# =============================================================
def draw_rounded_rect(img, x1, y1, x2, y2, r, color, thickness=-1):
    if thickness == -1:
        cv2.rectangle(img, (x1+r, y1), (x2-r, y2), color, -1)
        cv2.rectangle(img, (x1, y1+r), (x2, y2-r), color, -1)
        for cx, cy in [(x1+r, y1+r), (x2-r, y1+r),
                       (x1+r, y2-r), (x2-r, y2-r)]:
            cv2.circle(img, (cx, cy), r, color, -1)
    else:
        cv2.rectangle(img, (x1+r, y1), (x2-r, y2), color, thickness)
        cv2.rectangle(img, (x1, y1+r), (x2, y2-r), color, thickness)
        cv2.rectangle(img, (x1, y1), (x2, y2), color, thickness)
        for cx, cy, a1, a2 in [(x1+r, y1+r, 180, 270), (x2-r, y1+r, 270, 360),
                                (x2-r, y2-r, 0, 90),   (x1+r, y2-r, 90, 180)]:
            cv2.ellipse(img, (cx, cy), (r, r), 0, a1, a2, color, thickness)


def draw_glow_circle(img, cx, cy, r, color, intensity=0.6):
    for i in range(4, 0, -1):
        alpha = intensity * (i / 4) * 0.3
        glow_r = r + i * 3
        overlay = img.copy()
        cv2.circle(overlay, (cx, cy), glow_r, color, -1)
        cv2.addWeighted(overlay, alpha, img, 1 - alpha, 0, img)
    cv2.circle(img, (cx, cy), r, color, -1)


def draw_neon_border(img, x1, y1, x2, y2, color, thickness=2, glow=True):
    if glow:
        for i in range(3, 0, -1):
            alpha = 0.12 * i
            ov = img.copy()
            cv2.rectangle(ov, (x1-i, y1-i), (x2+i, y2+i), color, thickness)
            cv2.addWeighted(ov, alpha, img, 1-alpha, 0, img)
    cv2.rectangle(img, (x1, y1), (x2, y2), color, thickness)


def put_text_centered(img, text, cx, cy, font_scale, color, thickness=1):
    (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX,
                                   font_scale, thickness)
    cv2.putText(img, text, (cx - tw//2, cy + th//2),
                cv2.FONT_HERSHEY_SIMPLEX, font_scale, color, thickness, cv2.LINE_AA)


_gradient_cache = {}
def draw_gradient_bar(img, x1, y1, x2, y2, color_left, color_right):
    w = x2 - x1
    key = (w, color_left, color_right)
    if key not in _gradient_cache:
        gradient = np.zeros((1, w, 3), dtype=np.uint8)
        for i in range(w):
            t = i / max(w-1, 1)
            gradient[0, i] = tuple(int(color_left[j] * (1-t) + color_right[j] * t) for j in range(3))
        _gradient_cache[key] = gradient
    img[y1:y2, x1:x2] = _gradient_cache[key]


# =============================================================
#  FLOOD FILL
# =============================================================
def flood_fill(image, seed_pt, fill_color, tolerance):
    x, y = seed_pt
    h, w = image.shape[:2]
    if not (0 <= x < w and 0 <= y < h):
        return image
    result = image.copy()
    mask   = np.zeros((h+2, w+2), dtype=np.uint8)
    lo = hi = (tolerance, tolerance, tolerance)
    cv2.floodFill(result, mask, (x, y), fill_color, lo, hi,
                  8 | cv2.FLOODFILL_FIXED_RANGE)
    return result

def flood_fill_smooth(image, seed_pt, fill_color, tolerance):
    filled    = flood_fill(image, seed_pt, fill_color, tolerance)
    diff      = cv2.absdiff(image, filled)
    _, changed= cv2.threshold(cv2.cvtColor(diff, cv2.COLOR_BGR2GRAY),
                               1, 255, cv2.THRESH_BINARY)
    kernel    = np.ones((3,3), np.uint8)
    border    = cv2.dilate(changed, kernel, iterations=2) - changed
    blurred   = cv2.GaussianBlur(filled, (3,3), 0)
    mask_border = cv2.cvtColor(border, cv2.COLOR_GRAY2BGR) > 0
    return np.where(mask_border, blurred, filled).astype(np.uint8)


# =============================================================
#  CONTROLADOR DE MOUSE
# =============================================================
class MouseController:
    __slots__ = ('cfg', 'cam_w', 'cam_h', 'scr_w', 'scr_h', '_sx', '_sy',
                 '_alpha', 'is_dragging', 'mouse_down', '_was_pinching',
                 'drag_start_pos', '_pinch_frames', '_click_cd', '_rclick_cd',
                 '_dclick_cd', '_pos_history', '_last_pinch_t', '_dclick_window')

    def __init__(self, cfg, cam_w, cam_h):
        self.cfg   = cfg
        self.cam_w = cam_w
        self.cam_h = cam_h
        self.scr_w, self.scr_h = (pyautogui.size() if PYAUTOGUI_OK else (1920,1080))
        self._sx = self._sy = None
        self._alpha = 1.0 / max(cfg["mouse_smoothing"], 1)
        self.is_dragging = self.mouse_down = self._was_pinching = False
        self.drag_start_pos = None
        self._pinch_frames  = 0
        self._click_cd = self._rclick_cd = self._dclick_cd = 0
        self._pos_history   = deque(maxlen=5)
        self._last_pinch_t  = 0.0
        self._dclick_window = 0.4

    def tick(self):
        for attr in ('_click_cd', '_rclick_cd', '_dclick_cd'):
            v = getattr(self, attr)
            if v > 0: setattr(self, attr, v-1)

    def cam_to_screen(self, cx, cy):
        mg = self.cfg["mouse_zone_margin"]
        nx = float(np.clip((cx/self.cam_w - mg)/(1-2*mg), 0, 1))
        ny = float(np.clip((cy/self.cam_h - mg)/(1-2*mg), 0, 1))
        return int(nx*self.scr_w), int(ny*self.scr_h)

    def smooth_move(self, cx, cy):
        if not PYAUTOGUI_OK: return
        sx, sy = self.cam_to_screen(cx, cy)
        if self._sx is None:
            self._sx, self._sy = float(sx), float(sy)
        else:
            a = self._alpha
            self._sx = a*sx + (1-a)*self._sx
            self._sy = a*sy + (1-a)*self._sy
        self._pos_history.append((int(self._sx), int(self._sy)))
        if self.is_dragging:
            pyautogui.dragTo(int(self._sx), int(self._sy), button='left', _pause=False)
        else:
            pyautogui.moveTo(int(self._sx), int(self._sy), _pause=False)

    def handle_pinch(self, is_pinching, cx, cy):
        if not PYAUTOGUI_OK: return ""
        action = ""
        now    = time.time()
        if is_pinching:
            self._pinch_frames += 1
            if not self._was_pinching:
                if (self._click_cd == 0 and self._dclick_cd == 0 and
                        now - self._last_pinch_t < self._dclick_window):
                    pyautogui.doubleClick(_pause=False)
                    self._dclick_cd = self.cfg["double_click_cooldown"]
                    self._click_cd  = self.cfg["click_cooldown_frames"]
                    self.is_dragging = False
                    action = "DOBLE CLIC"
                elif self._click_cd == 0:
                    pyautogui.mouseDown(button='left', _pause=False)
                    self.mouse_down = True
                    self.drag_start_pos = (int(self._sx or cx), int(self._sy or cy))
                    action = "CLIC IZQUIERDO"
                self._last_pinch_t = now
            else:
                if (self.mouse_down and not self.is_dragging and
                        self._pinch_frames >= 6 and self.drag_start_pos):
                    if self._sx and (abs(self._sx-self.drag_start_pos[0]) +
                                      abs(self._sy-self.drag_start_pos[1])) > self.cfg["drag_min_move"]:
                        self.is_dragging = True
                        action = "ARRASTRANDO"
                if self.is_dragging: action = "ARRASTRANDO"
        else:
            if self._was_pinching:
                if self.is_dragging or self.mouse_down:
                    pyautogui.mouseUp(button='left', _pause=False)
                    self.is_dragging = self.mouse_down = False
                    action = "SOLTADO"
                self._click_cd = self.cfg["click_cooldown_frames"]
            self._pinch_frames = 0
        self._was_pinching = is_pinching
        return action

    def right_click(self):
        if not PYAUTOGUI_OK or self._rclick_cd > 0: return ""
        if self.is_dragging or self.mouse_down:
            pyautogui.mouseUp(button='left', _pause=False)
            self.is_dragging = self.mouse_down = False
        pyautogui.click(button='right', _pause=False)
        self._rclick_cd = self.cfg["right_click_cooldown"]
        return "CLIC DERECHO"

    def release_all(self):
        if not PYAUTOGUI_OK: return
        if self.mouse_down or self.is_dragging:
            try: pyautogui.mouseUp(button='left', _pause=False)
            except: pass
        self.is_dragging = self.mouse_down = self._was_pinching = False
        self._pinch_frames = 0
        self._sx = self._sy = None

    @property
    def screen_pos(self):
        return (int(self._sx), int(self._sy)) if self._sx is not None else None


# =============================================================
#  SELECTOR DE COLORES (48 colores)
# =============================================================
class ColorPicker:
    COLS = 6
    SWATCH_W = 90
    SWATCH_H = 60
    BG_COLOR = (255, 249, 230)
    SEL_COLOR = (80, 222, 100)

    EXTENDED_COLORS = [
        {"name": "Negro",          "bgr": (1,   1,   1)},
        {"name": "Gris Oscuro",    "bgr": (50,  50,  50)},
        {"name": "Gris",           "bgr": (128, 128, 128)},
        {"name": "Gris Claro",     "bgr": (180, 180, 180)},
        {"name": "Blanco",         "bgr": (255, 255, 255)},
        {"name": "Rojo Oscuro",    "bgr": (0,   0,   100)},
        {"name": "Rojo",           "bgr": (0,   0,   220)},
        {"name": "Rojo Brillante", "bgr": (0,   0,   255)},
        {"name": "Naranja Oscuro", "bgr": (0,   60,  160)},
        {"name": "Naranja",        "bgr": (0,   120, 255)},
        {"name": "Amarillo Oscuro","bgr": (0,   180, 200)},
        {"name": "Amarillo",       "bgr": (0,   220, 220)},
        {"name": "Amarillo Brill", "bgr": (0,   255, 255)},
        {"name": "Lima",           "bgr": (80,  255, 80)},
        {"name": "Verde Lima",     "bgr": (120, 255, 0)},
        {"name": "Verde",          "bgr": (0,   200, 60)},
        {"name": "Verde Oscuro",   "bgr": (0,   100, 40)},
        {"name": "Verde Bosque",   "bgr": (0,   130, 60)},
        {"name": "Verde Oliva",    "bgr": (0,   160, 80)},
        {"name": "Cian Oscuro",    "bgr": (150, 180, 0)},
        {"name": "Cian",           "bgr": (220, 200, 0)},
        {"name": "Cian Brillante", "bgr": (255, 255, 0)},
        {"name": "Azul Cielo",     "bgr": (230, 150, 0)},
        {"name": "Azul",           "bgr": (230, 80,  0)},
        {"name": "Azul Real",      "bgr": (200, 50,  0)},
        {"name": "Azul Marino",    "bgr": (130, 30,  30)},
        {"name": "Azul Oscuro",    "bgr": (100, 20,  20)},
        {"name": "Violeta",        "bgr": (100, 0,   100)},
        {"name": "Morado",         "bgr": (160, 0,   120)},
        {"name": "Purpura",        "bgr": (180, 50,  150)},
        {"name": "Magenta",        "bgr": (200, 0,   200)},
        {"name": "Rosa",           "bgr": (160, 100, 240)},
        {"name": "Rosa Oscuro",    "bgr": (100, 50,  120)},
        {"name": "Rosa Brillante", "bgr": (180, 150, 220)},
        {"name": "Salmon",         "bgr": (100, 130, 180)},
        {"name": "Coral",          "bgr": (80,  127, 180)},
        {"name": "Marron Oscuro",  "bgr": (20,  50,  90)},
        {"name": "Marron",         "bgr": (30,  80,  140)},
        {"name": "Marron Claro",   "bgr": (60,  120, 160)},
        {"name": "Beige",          "bgr": (130, 180, 200)},
        {"name": "Piel Muy Clara", "bgr": (180, 200, 220)},
        {"name": "Piel Clara",     "bgr": (140, 180, 210)},
        {"name": "Piel Clara Med.","bgr": (130, 160, 190)},
        {"name": "Piel Media",     "bgr": (110, 140, 170)},
        {"name": "Piel Morena",    "bgr": (80,  110, 140)},
        {"name": "Piel Oscura",    "bgr": (50,  70,  100)},
        {"name": "Piel Muy Osc.", "bgr": (30,  50,  70)},
        {"name": "Cafe",           "bgr": (25,  40,  65)},
    ]

    def __init__(self):
        self.colors   = self.EXTENDED_COLORS
        self.selected = 0

    def _build_grid(self, W, H):
        canvas = np.full((H, W, 3), self.BG_COLOR, dtype=np.uint8)
        mg = 20
        n  = len(self.colors)
        cv2.rectangle(canvas, (0, 0), (W, 70), (255, 240, 210), -1)
        cv2.putText(canvas, "SELECCIONA UN COLOR", (mg, 40),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.9, (60, 120, 255), 2, cv2.LINE_AA)
        cv2.putText(canvas,
                    "Flechas/WASD para navegar  |  ENTER para seleccionar  |  ESC para cancelar",
                    (mg, 65), cv2.FONT_HERSHEY_SIMPLEX, 0.48, (120, 90, 60), 1, cv2.LINE_AA)
        start_y = 90
        for i, c in enumerate(self.colors):
            row = i // self.COLS
            col = i % self.COLS
            x   = mg + col * (self.SWATCH_W + 12)
            y   = start_y + row * (self.SWATCH_H + 30)
            if i == self.selected:
                for ex in [4, 3, 2]:
                    alpha = 0.1 * (4 - ex)
                    ov = canvas.copy()
                    cv2.rectangle(ov, (x-6-ex, y-6-ex),
                                  (x+self.SWATCH_W+6+ex, y+self.SWATCH_H+6+ex),
                                  self.SEL_COLOR, 2)
                    cv2.addWeighted(ov, alpha, canvas, 1-alpha, 0, canvas)
                cv2.rectangle(canvas, (x-6, y-6),
                              (x+self.SWATCH_W+6, y+self.SWATCH_H+6),
                              self.SEL_COLOR, 3)
            else:
                cv2.rectangle(canvas, (x-2, y-2),
                              (x+self.SWATCH_W+2, y+self.SWATCH_H+2),
                              (200, 180, 150), 1)
            cv2.rectangle(canvas, (x, y), (x+self.SWATCH_W, y+self.SWATCH_H), c["bgr"], -1)
            cv2.rectangle(canvas, (x, y), (x+self.SWATCH_W, y+self.SWATCH_H), (180, 160, 130), 1)
            name = c["name"][:12]
            (tw, th), _ = cv2.getTextSize(name, cv2.FONT_HERSHEY_SIMPLEX, 0.4, 1)
            cv2.putText(canvas, name, (x + (self.SWATCH_W - tw)//2, y+self.SWATCH_H+18),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.4, (80, 60, 40), 1, cv2.LINE_AA)
        cv2.rectangle(canvas, (0, H-35), (W, H), (255, 240, 210), -1)
        cv2.putText(canvas, f"{n} colores disponibles", (mg, H-12),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (120, 90, 60), 1, cv2.LINE_AA)
        return canvas

    def show(self, W=1280, H=720):
        win = "Selector de Color"
        cv2.namedWindow(win, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(win, W, H)
        while True:
            cv2.imshow(win, self._build_grid(W, H))
            key = cv2.waitKey(50) & 0xFF
            n   = len(self.colors)
            if key == 27:
                cv2.destroyWindow(win); return None
            elif key in (13, 32):
                cv2.destroyWindow(win); return self.colors[self.selected]
            elif key in (81, ord('a')): self.selected = (self.selected - 1) % n
            elif key in (83, ord('d')): self.selected = (self.selected + 1) % n
            elif key in (82, ord('w')): self.selected = max(0, self.selected - self.COLS)
            elif key in (84, ord('s')): self.selected = min(n-1, self.selected + self.COLS)


# =============================================================
#  SELECTOR DE IMAGENES
# =============================================================
class ImageSelector:
    THUMB_W = 210
    THUMB_H = 158
    COLS    = 5

    def __init__(self, images_dir, extensions):
        self.images_dir  = images_dir
        self.extensions  = extensions
        self.image_paths = []
        self.thumbnails  = []
        self.selected    = 0
        self._load()

    def _load(self):
        self.image_paths = []
        for ext in self.extensions:
            self.image_paths += glob.glob(os.path.join(self.images_dir, ext))
        self.image_paths = sorted(self.image_paths)
        self.thumbnails  = []
        for p in self.image_paths:
            img = cv2.imread(p)
            if img is not None:
                th = cv2.resize(img, (self.THUMB_W, self.THUMB_H), interpolation=cv2.INTER_AREA)
            else:
                th = np.full((self.THUMB_H, self.THUMB_W, 3), 230, dtype=np.uint8)
                put_text_centered(th, "?", self.THUMB_W//2, self.THUMB_H//2,
                                  1.5, (150, 100, 60), 3)
            self.thumbnails.append(th)

    def _build_grid(self, W, H):
        bg = np.zeros((H, W, 3), dtype=np.uint8)
        for y in range(H):
            t = y / H
            b = int(255*(1-t) + 230*t)
            g = int(210*(1-t) + 245*t)
            r = int(135*(1-t) + 255*t)
            bg[y, :] = (b, g, r)
        draw_clouds(bg, time.time())
        cv2.rectangle(bg, (0, 0), (W, 85), (255, 249, 230), -1)
        draw_gradient_bar(bg, 0, 82, W, 85, UI["vivo_cyan"], UI["vivo_rosa"])
        put_text_centered(bg, "SELECCIONA UNA IMAGEN PARA COLOREAR",
                          W//2, 32, 0.9, (60, 120, 255), 2)
        put_text_centered(bg,
            "Flechas/WASD para navegar  |  ENTER para seleccionar  |  ESC para cancelar",
            W//2, 62, 0.48, (100, 80, 60), 1)
        mg, pad = 20, 14
        for i, (thumb, path) in enumerate(zip(self.thumbnails, self.image_paths)):
            row = i // self.COLS
            col = i % self.COLS
            x   = mg + col * (self.THUMB_W + pad)
            y   = 98  + row * (self.THUMB_H + pad + 26)
            if y + self.THUMB_H + 26 > H - 40: break
            tw, th = self.THUMB_W, self.THUMB_H
            if i == self.selected:
                draw_rounded_rect(bg, x-6, y-6, x+tw+6, y+th+6, 6, UI["vivo_verde"], -1)
                draw_rounded_rect(bg, x-6, y-6, x+tw+6, y+th+6, 6, (235, 248, 255), -1)
                draw_neon_border(bg, x-4, y-4, x+tw+4, y+th+4, UI["vivo_verde"], 3)
            else:
                cv2.rectangle(bg, (x-2, y-2), (x+tw+2, y+th+2), UI["border_claro"], 1)
            bg[y:y+th, x:x+tw] = thumb
            fname = os.path.basename(path)
            fname = fname[:24] if len(fname) > 24 else fname
            col_t = UI["vivo_verde"] if i == self.selected else UI["text_claro"]
            cv2.putText(bg, fname, (x, y+th+20),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.40, col_t, 1, cv2.LINE_AA)
        cv2.rectangle(bg, (0, H-38), (W, H), (255, 249, 230), -1)
        put_text_centered(
            bg, f"[R] Recargar  |  {len(self.image_paths)} imagen(es) disponibles",
            W//2, H-19, 0.44, UI["text_claro"], 1)
        return bg

    def show(self, W=1280, H=720):
        win = "Magic Paint - Seleccionar Imagen"
        cv2.namedWindow(win, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(win, W, H)
        while True:
            cv2.imshow(win, self._build_grid(W, H))
            key = cv2.waitKey(50) & 0xFF
            n   = len(self.image_paths)
            if n == 0:
                if key in (ord('r'), ord('R')): self._load()
                elif key == 27: cv2.destroyWindow(win); return None
                continue
            if key == 27:        cv2.destroyWindow(win); return None
            elif key in (13,32): cv2.destroyWindow(win); return self.image_paths[self.selected]
            elif key in (81, ord('a')): self.selected = (self.selected-1) % n
            elif key in (83, ord('d')): self.selected = (self.selected+1) % n
            elif key in (82, ord('w')): self.selected = max(0, self.selected-self.COLS)
            elif key in (84, ord('s')): self.selected = min(n-1, self.selected+self.COLS)
            elif key in (ord('r'), ord('R')): self._load()


# =============================================================
#  CLASE PRINCIPAL
# =============================================================
class VirtualPainter:

    class Particle:
        __slots__ = ('x', 'y', 'vx', 'vy', 'r', 'col', 'life', 'age', 'W', 'H')
        def __init__(self, W, H):
            self.reset(W, H)
        def reset(self, W, H):
            self.x   = float(np.random.randint(0, W))
            self.y   = float(np.random.randint(0, H))
            self.vx  = float(np.random.uniform(-1.2, 1.2))
            self.vy  = float(np.random.uniform(-2.0, -0.4))
            self.r   = int(np.random.randint(2, 6))
            colors   = [UI["vivo_cyan"], UI["vivo_verde"], UI["vivo_rosa"],
                        UI["vivo_naranja"], UI["vivo_amarillo"], UI["vivo_morado"]]
            self.col = colors[np.random.randint(0, len(colors))]
            self.life= int(np.random.randint(60, 180))
            self.age = 0
            self.W   = W
            self.H   = H
        def update(self):
            self.x  += self.vx
            self.y  += self.vy
            self.vy += 0.04
            self.age += 1
            if self.age > self.life or self.y > self.H+10 or self.x < 0 or self.x > self.W:
                self.reset(self.W, self.H)
        def draw(self, frame):
            if self.age >= self.life: return
            alpha = 1.0 - self.age/self.life
            r = max(1, int(self.r * alpha))
            cv2.circle(frame, (int(self.x), int(self.y)), r, self.col, -1, cv2.LINE_AA)

    def __init__(self):
        self.cfg = CONFIG
        self.W   = self.cfg["width"]
        self.H   = self.cfg["height"]

        self.app_mode    = APP_MODE_PAINT
        self.active_tool = TOOL_BRUSH

        self.canvas           = np.zeros((self.H, self.W, 3), dtype=np.uint8)
        self.color_image_orig = None
        self.color_layer      = None
        self.color_image_path = None
        self.fill_tolerance   = self.cfg["fill_tolerance"]

        self.drawing       = False
        self.prev_point    = None
        self.brush_size    = self.cfg["default_brush_size"]
        self.eraser_mode   = False
        self.color_index   = 2
        self.current_color = COLORS[2]["bgr"]
        self.show_hud      = self.cfg["show_hud"]
        self.fullscreen    = False

        self.smooth_points = deque(maxlen=self.cfg["smoothing_points"])
        self.smooth_brush  = deque(maxlen=10)
        self.undo_stack    = deque(maxlen=self.cfg["max_undo_steps"])
        self.redo_stack    = deque(maxlen=self.cfg["max_undo_steps"])
        self._push_undo()

        self._gesture_buffer      = deque(maxlen=self.cfg["gesture_smoothing"])
        self._last_stable_gesture = "NONE"
        self._fill_done           = False

        self._hover_btn         = None
        self._hover_btn_frames  = 0
        self._hover_btn_thr     = 20
        self._btn_hover_progress = 0

        self._notif       = ""
        self._notif_timer = 0
        self._notif_color = UI["vivo_verde"]

        self._trail      = deque(maxlen=20)
        self._paint_splashes = []

        self._particles = [self.Particle(self.W, self.H) for _ in range(self.cfg["particle_count"])]

        self._fps_buf = deque(maxlen=30)
        self._last_t  = time.time()

        self._frame_counter = 0
        self._last_landmarks = None
        self._last_gesture = "NONE"
        self._hand_present = False

        # ── OPTIMIZACIÓN: cachés para modo libre ─────────────────────
        self._free_bg_cache     = None   # fondo pre-renderizado en modo libre
        self._free_bg_frame_cnt = -1     # frame en que se actualizó el caché
        self._free_bg_interval  = 3      # re-render del fondo cada N frames

        self.mouse_ctrl        = MouseController(self.cfg, self.W, self.H)
        self._mouse_action     = ""
        self._mouse_action_t   = 0

        # Cargar logo UPEC una sola vez
        self._upec_logo = None
        logo_path = self.cfg.get("upec_logo_path", "")
        if os.path.isfile(logo_path):
            logo_raw = cv2.imread(logo_path, cv2.IMREAD_UNCHANGED)
            if logo_raw is not None:
                self._upec_logo = logo_raw

        self.mp_hands       = mp.solutions.hands
        self.hands          = self.mp_hands.Hands(
            static_image_mode=False, max_num_hands=1,
            min_detection_confidence=self.cfg["detection_confidence"],
            min_tracking_confidence=self.cfg["tracking_confidence"],
        )
        self.mp_draw        = mp.solutions.drawing_utils
        self.mp_draw_styles = mp.solutions.drawing_styles

        os.makedirs(self.cfg["images_dir"], exist_ok=True)
        os.makedirs(self.cfg["save_dir"],   exist_ok=True)
        self.img_selector = ImageSelector(self.cfg["images_dir"],
                                          self.cfg["image_extensions"])
        self._build_ui()

        self._static_ui_cache = {}
        self._ui_update_counter = 0

    def _notify(self, msg, color=None, dur=90):
        self._notif       = msg
        self._notif_timer = dur
        self._notif_color = color or UI["vivo_verde"]

    def _set_mouse_action(self, a, dur=35):
        if a: self._mouse_action = a; self._mouse_action_t = dur

    def _get_layer(self):
        if self.app_mode == APP_MODE_COLOR and self.color_layer is not None:
            return self.color_layer
        return self.canvas

    def _set_layer(self, d):
        if self.app_mode == APP_MODE_COLOR and self.color_layer is not None:
            self.color_layer = d
        else:
            self.canvas = d

    def _push_undo(self):
        current = self._get_layer()
        if len(self.undo_stack) == 0 or not np.array_equal(self.undo_stack[-1], current):
            self.undo_stack.append(current.copy())
            self.redo_stack.clear()

    def undo(self):
        if len(self.undo_stack) > 1:
            self.redo_stack.append(self.undo_stack.pop())
            self._set_layer(self.undo_stack[-1].copy())
            self._notify("Deshacer", UI["vivo_amarillo"])

    def redo(self):
        if self.redo_stack:
            s = self.redo_stack.pop()
            self.undo_stack.append(s)
            self._set_layer(s.copy())
            self._notify("Rehacer", UI["vivo_amarillo"])

    def load_color_image(self, path):
        img = cv2.imread(path)
        if img is None:
            self._notify(f"Error abriendo imagen", UI["vivo_rojo"])
            return False
        draw_start_x = self.SIDEBAR_W
        draw_end_x   = self.W - self.SIDEBAR_W
        draw_width   = draw_end_x - draw_start_x
        draw_height  = self.H
        img_resized = cv2.resize(img, (draw_width, draw_height), interpolation=cv2.INTER_AREA)
        full_canvas = np.zeros((self.H, self.W, 3), dtype=np.uint8)
        full_canvas[:, draw_start_x:draw_end_x] = img_resized
        self.color_image_orig = full_canvas.copy()
        self.color_layer      = full_canvas.copy()
        self.color_image_path = path
        self.app_mode         = APP_MODE_COLOR
        self.undo_stack.clear(); self.redo_stack.clear()
        self._push_undo()
        self._notify(f"Imagen: {os.path.basename(path)}", UI["vivo_cyan"])
        return True

    def reset_color_image(self):
        if self.color_image_orig is not None:
            self._push_undo()
            self.color_layer = self.color_image_orig.copy()
            self._notify("Imagen restaurada", UI["vivo_naranja"])

    def save_drawing(self, frame_bg=None):
        ts  = datetime.now().strftime("%Y%m%d_%H%M%S")
        ext = self.cfg["save_format"]
        if self.app_mode == APP_MODE_COLOR and self.color_layer is not None:
            draw_start_x = self.SIDEBAR_W
            draw_end_x   = self.W - self.SIDEBAR_W
            save_img     = self.color_layer[:, draw_start_x:draw_end_x]
            gray = cv2.cvtColor(save_img, cv2.COLOR_BGR2GRAY)
            _, thresh = cv2.threshold(gray, 1, 255, cv2.THRESH_BINARY)
            coords = cv2.findNonZero(thresh)
            if coords is not None:
                x, y, w, h = cv2.boundingRect(coords)
                save_img = save_img[y:y+h, x:x+w]
            path = os.path.join(self.cfg["save_dir"], f"colored_{ts}.{ext}")
            cv2.imwrite(path, save_img)
        elif frame_bg is not None:
            path = os.path.join(self.cfg["save_dir"], f"painting_{ts}.{ext}")
            cv2.imwrite(path, self._merge_canvas(frame_bg))
        else:
            path = os.path.join(self.cfg["save_dir"], f"canvas_{ts}.{ext}")
            cv2.imwrite(path, self.canvas)
        self._notify(f"Guardado!", UI["vivo_verde"])
        print(f"[OK] {path}")
        return path

    # ── NUEVO: IMPRIMIR con encabezado UPEC ──────────────────────────
    def print_drawing(self, frame_bg=None):
        """
        Genera una imagen de impresión con:
          - Encabezado blanco con logo UPEC + título institucional
          - El dibujo/canvas debajo
        Guarda el archivo y lo muestra en pantalla para imprimir con Ctrl+P del SO.
        """
        # 1. Obtener la imagen base que se imprimirá
        if self.app_mode == APP_MODE_COLOR and self.color_layer is not None:
            draw_start_x = self.SIDEBAR_W
            draw_end_x   = self.W - self.SIDEBAR_W
            art = self.color_layer[:, draw_start_x:draw_end_x].copy()
        elif frame_bg is not None:
            merged = self._merge_canvas(frame_bg)
            art = merged[:, self.SIDEBAR_W:self.W - self.SIDEBAR_W].copy()
        else:
            art = self.canvas.copy()

        # 2. Dimensiones de impresión (A4 aprox a 150 dpi: 1240 x 1754)
        PRINT_W = 1240
        ART_H   = 900

        # Escalar arte al ancho de impresión
        art_h_orig, art_w_orig = art.shape[:2]
        scale_factor = PRINT_W / art_w_orig
        new_art_h = int(art_h_orig * scale_factor)
        art_resized = cv2.resize(art, (PRINT_W, new_art_h), interpolation=cv2.INTER_LANCZOS4)
        # Recortar o rellenar a ART_H
        if new_art_h > ART_H:
            art_resized = art_resized[:ART_H, :]
        elif new_art_h < ART_H:
            pad = np.full((ART_H - new_art_h, PRINT_W, 3), 255, dtype=np.uint8)
            art_resized = np.vstack([art_resized, pad])

        # 3. Construir encabezado blanco
        HEADER_H = 160
        header = np.full((HEADER_H, PRINT_W, 3), 255, dtype=np.uint8)

        # Línea superior verde UPEC
        cv2.rectangle(header, (0, 0), (PRINT_W, 8), (0, 120, 50), -1)
        # Línea inferior del encabezado
        cv2.line(header, (0, HEADER_H - 4), (PRINT_W, HEADER_H - 4), (0, 120, 50), 3)

        # Logo UPEC a la izquierda
        logo_x = 20
        if self._upec_logo is not None:
            logo_h_target = HEADER_H - 30
            logo_src = self._upec_logo
            lh, lw = logo_src.shape[:2]
            logo_scale = logo_h_target / lh
            lw_new = int(lw * logo_scale)
            lh_new = logo_h_target
            logo_resized = cv2.resize(logo_src, (lw_new, lh_new), interpolation=cv2.INTER_AREA)
            # Soporte RGBA
            ly1, ly2 = 15, 15 + lh_new
            lx1, lx2 = logo_x, logo_x + lw_new
            if logo_resized.shape[2] == 4:
                alpha_ch = logo_resized[:, :, 3:4] / 255.0
                rgb      = logo_resized[:, :, :3]
                bg_roi   = header[ly1:ly2, lx1:lx2]
                header[ly1:ly2, lx1:lx2] = (rgb * alpha_ch + bg_roi * (1 - alpha_ch)).astype(np.uint8)
            else:
                header[ly1:ly2, lx1:lx2] = logo_resized
            text_x = lx2 + 30
        else:
            text_x = logo_x

        # Texto institucional centrado en la parte restante del encabezado
        font = cv2.FONT_HERSHEY_SIMPLEX
        title1 = "Universidad Politecnica del Carchi"
        title2 = "Carrera de Computacion"
        title3 = "Magic Paint - Pintura con Gestos de Mano"

        available_w = PRINT_W - text_x - 20
        center_x = text_x + available_w // 2

        # Línea 1 — nombre institución
        (tw1, _), _ = cv2.getTextSize(title1, font, 0.95, 2)
        cv2.putText(header, title1, (center_x - tw1//2, 55),
                    font, 0.95, (0, 100, 40), 2, cv2.LINE_AA)
        # Línea 2 — carrera
        (tw2, _), _ = cv2.getTextSize(title2, font, 0.75, 2)
        cv2.putText(header, title2, (center_x - tw2//2, 92),
                    font, 0.75, (30, 80, 30), 2, cv2.LINE_AA)
        # Línea 3 — título de la actividad
        (tw3, _), _ = cv2.getTextSize(title3, font, 0.55, 1)
        cv2.putText(header, title3, (center_x - tw3//2, 122),
                    font, 0.55, (80, 80, 80), 1, cv2.LINE_AA)
        # Fecha
        date_str = datetime.now().strftime("%d/%m/%Y  %H:%M")
        (twd, _), _ = cv2.getTextSize(date_str, font, 0.44, 1)
        cv2.putText(header, date_str, (PRINT_W - twd - 20, 148),
                    font, 0.44, (120, 120, 120), 1, cv2.LINE_AA)

        # 4. Pie de página
        FOOTER_H = 40
        footer = np.full((FOOTER_H, PRINT_W, 3), 255, dtype=np.uint8)
        cv2.rectangle(footer, (0, 0), (PRINT_W, 4), (0, 120, 50), -1)
        put_text_centered(footer, "Universidad Politecnica del Carchi  -  UPEC  |  www.upec.edu.ec",
                          PRINT_W//2, 26, 0.42, (80, 80, 80), 1)

        # 5. Ensamblar página completa
        page = np.vstack([header, art_resized, footer])

        # 6. Guardar
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_path = os.path.join(self.cfg["save_dir"], f"impresion_upec_{ts}.png")
        cv2.imwrite(out_path, page)

        # 7. Mostrar ventana de previsualización con instrucción de impresión
        win_print = "Vista Previa de Impresion - Cierra con ESC"
        preview_scale = min(1.0, 900 / page.shape[0])
        preview_w = int(page.shape[1] * preview_scale)
        preview_h = int(page.shape[0] * preview_scale)
        preview = cv2.resize(page, (preview_w, preview_h), interpolation=cv2.INTER_AREA)

        # Banner de instrucción
        banner_h = 36
        banner = np.full((banner_h, preview_w, 3), (30, 30, 30), dtype=np.uint8)
        cv2.putText(banner,
                    f"Archivo: {out_path}   |   Abre el archivo y usa Ctrl+P para imprimir   |   ESC para cerrar",
                    (10, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.44, (200, 230, 200), 1, cv2.LINE_AA)
        final_preview = np.vstack([banner, preview])

        cv2.namedWindow(win_print, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(win_print, preview_w, preview_h + banner_h)
        cv2.imshow(win_print, final_preview)

        self._notify(f"Impresion guardada!", UI["tool_print"])
        print(f"[OK] Impresion UPEC guardada en: {out_path}")

        # Espera hasta ESC o click en X — no bloquea el loop principal
        # (el usuario cierra la ventana cuando quiera)
        return out_path

    def _build_ui(self):
        W, H = self.W, self.H
        self.SIDEBAR_W = 160
        self.SIDEBAR_H = H

        BTN_W = 140
        BTN_H = 48
        BTN_X = 10
        BTN_GAP = 6
        start_y = 140

        def btn_y(i): return start_y + i * (BTN_H + BTN_GAP)

        self.left_buttons = {
            "BRUSH":        (BTN_X, btn_y(0), BTN_X+BTN_W, btn_y(0)+BTN_H),
            "FILL":         (BTN_X, btn_y(1), BTN_X+BTN_W, btn_y(1)+BTN_H),
            "ERASER":       (BTN_X, btn_y(2), BTN_X+BTN_W, btn_y(2)+BTN_H),
            "COLOR_PICKER": (BTN_X, btn_y(3), BTN_X+BTN_W, btn_y(3)+BTN_H),
        }

        right_x = self.W - BTN_W - 10
        self.right_buttons = {
            "UNDO":      (right_x, btn_y(0), right_x+BTN_W, btn_y(0)+BTN_H),
            "REDO":      (right_x, btn_y(1), right_x+BTN_W, btn_y(1)+BTN_H),
            "CLEAR":     (right_x, btn_y(2), right_x+BTN_W, btn_y(2)+BTN_H),
            "SAVE":      (right_x, btn_y(3), right_x+BTN_W, btn_y(3)+BTN_H),
            "OPEN_IMG":  (right_x, btn_y(4), right_x+BTN_W, btn_y(4)+BTN_H),
            "FREE_MODE": (right_x, btn_y(5), right_x+BTN_W, btn_y(5)+BTN_H),
            "PRINT":     (right_x, btn_y(6), right_x+BTN_W, btn_y(6)+BTN_H),  # NUEVO
        }

        self.buttons = {**self.left_buttons, **self.right_buttons}

        self.DRAW_X1 = self.SIDEBAR_W
        self.DRAW_Y1 = 0
        self.DRAW_X2 = W - self.SIDEBAR_W
        self.DRAW_Y2 = H

    def _fingers_up(self, lm):
        h, w = self.H, self.W
        pts = [(int(lm[i].x*w), int(lm[i].y*h)) for i in range(21)]
        up = [pts[TIP[0]][0] > pts[PIP[0]][0]]
        for i in range(1, 5):
            up.append(pts[TIP[i]][1] < pts[PIP[i]][1])
        return up

    def _detect_gesture(self, lm):
        up    = self._fingers_up(lm)
        n_up  = sum(up)
        h, w  = self.H, self.W
        def pt(i): return (int(lm[i].x*w), int(lm[i].y*h))
        thumb = pt(4); index = pt(8); wrist = pt(0)
        pinch = math.dist(thumb, index)
        if n_up == 0: return "ERASER"
        if n_up >= 4: return "OPEN"
        if up[1] and not up[2] and not up[3] and not up[4]:
            return "PINCH" if pinch < 55 else "DRAW"
        if up[1] and up[2] and not up[3]: return "SELECT"
        if up[1] and up[2] and up[3] and not up[4]: return "THREE"
        if up[0] and not up[1] and not up[2] and not up[3]:
            if thumb[1] < wrist[1] - 50: return "THUMB_UP"
            if thumb[1] > wrist[1] + 50: return "THUMB_DOWN"
            return "OPEN"
        return "SELECT"

    def _stable_gesture(self, g):
        self._gesture_buffer.append(g)
        if len(self._gesture_buffer) == self._gesture_buffer.maxlen:
            from collections import Counter
            self._last_stable_gesture = Counter(
                self._gesture_buffer).most_common(1)[0][0]
        return self._last_stable_gesture

    def _smooth_pt(self, pt):
        self.smooth_points.append(pt)
        return (int(np.mean([p[0] for p in self.smooth_points])),
                int(np.mean([p[1] for p in self.smooth_points])))

    def _smooth_bs(self, s):
        self.smooth_brush.append(s)
        return int(np.mean(self.smooth_brush))

    def _stroke(self, pt, color, size):
        layer = self._get_layer()
        if self.prev_point:
            cv2.line(layer, self.prev_point, pt, color, size, cv2.LINE_AA)
        cv2.circle(layer, pt, size//2, color, -1, cv2.LINE_AA)
        self._set_layer(layer)
        if not self.prev_point and color != (0,0,0):
            if len(self._paint_splashes) < self.cfg["max_paint_splashes"]:
                self._paint_splashes.append([pt[0], pt[1], size+4, color, 0, 18])

    def _apply_fill(self, pt):
        self._push_undo()
        result = flood_fill_smooth(self._get_layer(), pt,
                                   self.current_color, self.fill_tolerance)
        self._set_layer(result)
        if len(self._paint_splashes) < self.cfg["max_paint_splashes"]:
            self._paint_splashes.append([pt[0], pt[1], 30, self.current_color, 0, 25])
        self._notify(f"Relleno (tol: {self.fill_tolerance})", UI["vivo_naranja"])

    def _check_btn_hover(self, pt, frame_bg=None):
        x, y = pt
        for name, (x1, y1, x2, y2) in self.buttons.items():
            if x1 <= x <= x2 and y1 <= y <= y2:
                if self._hover_btn == name:
                    self._hover_btn_frames += 1
                    self._btn_hover_progress = min(1.0, self._hover_btn_frames / self._hover_btn_thr)
                    if self._hover_btn_frames >= self._hover_btn_thr:
                        self._trigger_btn(name, frame_bg)
                        self._hover_btn_frames = 0
                else:
                    self._hover_btn        = name
                    self._hover_btn_frames = 0
                    self._btn_hover_progress = 0
                return True
        self._hover_btn        = None
        self._hover_btn_frames = 0
        self._btn_hover_progress = 0
        return False

    def _trigger_btn(self, name, frame_bg=None):
        if   name == "UNDO":     self.undo()
        elif name == "REDO":     self.redo()
        elif name == "SAVE":     self.save_drawing(frame_bg)
        elif name == "PRINT":    self.print_drawing(frame_bg)   # NUEVO
        elif name == "CLEAR":
            self._push_undo()
            if self.app_mode == APP_MODE_COLOR and self.color_image_orig is not None:
                self.color_layer = self.color_image_orig.copy()
                self._notify("Imagen restaurada", UI["vivo_naranja"])
            else:
                self.canvas[:] = 0
                self._notify("Canvas limpiado", UI["vivo_rojo"])
        elif name == "BRUSH":
            self.active_tool = TOOL_BRUSH;  self.eraser_mode = False
            self._notify("Herramienta: Pincel", UI["tool_brush"])
        elif name == "FILL":
            self.active_tool = TOOL_FILL;   self.eraser_mode = False
            self._notify("Herramienta: Relleno", UI["tool_fill"])
        elif name == "ERASER":
            self.active_tool = TOOL_ERASER; self.eraser_mode = True
            self._notify("Herramienta: Borrador", UI["tool_eraser"])
        elif name == "OPEN_IMG":
            self.img_selector._load()
            path = self.img_selector.show(self.W, self.H)
            if path: self.load_color_image(path)
        elif name == "FREE_MODE":
            self._toggle_free_mode()
        elif name == "COLOR_PICKER":
            self._open_color_picker()

    def _open_color_picker(self):
        picker = ColorPicker()
        result = picker.show(self.W, self.H)
        if result:
            self.current_color = result["bgr"]
            found = False
            for i, c in enumerate(COLORS):
                if c["bgr"] == result["bgr"]:
                    self.color_index = i
                    found = True
                    break
            if not found:
                self.color_index = -1
            self.eraser_mode = False
            self.active_tool = TOOL_BRUSH
            self._notify(f"Color: {result['name']}", result["bgr"])

    def _toggle_free_mode(self):
        if self.app_mode == APP_MODE_FREE:
            self.mouse_ctrl.release_all()
            self.app_mode = APP_MODE_PAINT
            self._free_bg_cache = None  # invalidar caché
            self._notify("Modo: Pintura Libre", UI["mode_paint"])
        else:
            if not PYAUTOGUI_OK:
                self._notify("Instala: pip install pyautogui", UI["vivo_rojo"])
                return
            self.mouse_ctrl.release_all()
            self.app_mode = APP_MODE_FREE
            self._free_bg_cache = None  # invalidar caché
            self._notify("MODO LIBRE - Controla el mouse!", UI["mode_free"])

    def _process_free_mode(self, lm, gesture):
        h, w   = self.H, self.W
        def pt(i): return (int(lm[i].x*w), int(lm[i].y*h))
        index  = pt(8); thumb = pt(4)
        pinch_dist  = math.dist(thumb, index)
        is_pinching = pinch_dist < self.cfg["pinch_threshold"]
        self.mouse_ctrl.smooth_move(index[0], index[1])
        if gesture == "SELECT" and not is_pinching:
            a = self.mouse_ctrl.right_click()
            if a: self._set_mouse_action(a)
        elif gesture in ("DRAW","PINCH") or is_pinching:
            a = self.mouse_ctrl.handle_pinch(True, index[0], index[1])
            if a: self._set_mouse_action(a)
        else:
            a = self.mouse_ctrl.handle_pinch(False, index[0], index[1])
            if a: self._set_mouse_action(a)
        self.mouse_ctrl.tick()
        return {"index": index, "thumb": thumb,
                "pinch_dist": pinch_dist, "is_pinching": is_pinching,
                "is_dragging": self.mouse_ctrl.is_dragging}

    def _merge_canvas(self, frame):
        H, W = frame.shape[:2]
        sky = np.zeros((H, W, 3), dtype=np.uint8)
        for y in range(H):
            t = y / H
            b = int(255*(1-t) + 230*t)
            g = int(210*(1-t) + 245*t)
            r = int(135*(1-t) + 255*t)
            sky[y, :] = (b, g, r)
        draw_clouds(sky, time.time())
        op = self.cfg["canvas_opacity"]
        if np.any(self.canvas):
            mask = (self.canvas.sum(axis=2) > 0)
            if np.any(mask):
                sky[mask] = cv2.addWeighted(
                    sky[mask], 1-op, self.canvas[mask], op, 0)
        return sky

    # ── OPTIMIZACIÓN: fondo modo libre con caché ──────────────────────
    def _build_free_bg(self, frame):
        """
        Construye el fondo del modo libre. Se cachea cada N frames para
        evitar recalcular el degradado y las nubes en cada frame.
        """
        output = np.zeros((self.H, self.W, 3), dtype=np.uint8)
        # Degradado — vectorizado con numpy (mucho más rápido que loop)
        y_idx = np.arange(self.H, dtype=np.float32) / self.H
        b_chan = (255 * (1 - y_idx) + 230 * y_idx).astype(np.uint8)
        g_chan = (210 * (1 - y_idx) + 245 * y_idx).astype(np.uint8)
        r_chan = (135 * (1 - y_idx) + 255 * y_idx).astype(np.uint8)
        output[:, :, 0] = b_chan[:, np.newaxis]
        output[:, :, 1] = g_chan[:, np.newaxis]
        output[:, :, 2] = r_chan[:, np.newaxis]
        draw_clouds(output, time.time())
        # Blend con cámara: sólo 25% cámara, más ligero
        cv2.addWeighted(frame, 0.25, output, 0.75, 0, output)
        return output

    def _update_effects(self, frame):
        for p in self._particles:
            p.update()
            p.draw(frame)
        alive = []
        for s in self._paint_splashes:
            x, y, r, col, age, max_age = s
            if age < max_age:
                a  = 1.0 - age/max_age
                cr = int(r * (1 + age*0.4))
                ov = frame.copy()
                cv2.circle(ov, (x, y), cr, col, -1, cv2.LINE_AA)
                cv2.addWeighted(ov, a * 0.5, frame, 1 - a * 0.5, 0, frame)
                s[4] += 1
                alive.append(s)
        self._paint_splashes = alive
        for i, (tx, ty, tc) in enumerate(self._trail):
            if i == 0: continue
            a  = (i+1) / len(self._trail)
            r  = max(1, int(a * 6))
            ov = frame.copy()
            cv2.circle(ov, (tx, ty), r, tc, -1, cv2.LINE_AA)
            cv2.addWeighted(ov, a*0.4, frame, 1-a*0.4, 0, frame)

    def _draw_paint_blobs(self, frame, t):
        paint_colors = [
            (80,107,255),(80,202,254),(80,222,100),
            (251,219,72),(60,159,255),(245,110,197),
            (157,107,255),(251,160,80)
        ]
        blob_w = self.SIDEBAR_W // len(paint_colors)
        for side_x in [0, self.W - self.SIDEBAR_W]:
            for i, pc in enumerate(paint_colors):
                bx = side_x + i * blob_w
                by = self.H - 20
                wave = int(6 * math.sin(t * 2.0 + i * 0.8))
                peak = int(4 * math.sin(t * 2.5 + i * 1.1))
                pts = np.array([
                    [bx,             self.H],
                    [bx,             by + wave],
                    [bx+blob_w//2,   by - 10 + peak],
                    [bx+blob_w,      by + wave],
                    [bx+blob_w,      self.H],
                ], dtype=np.int32)
                cv2.fillPoly(frame, [pts], pc)

    def _draw_ui(self, frame, gesture, fps):
        if not self.show_hud:
            return frame

        W, H = self.W, self.H
        is_free = (self.app_mode == APP_MODE_FREE)
        t = time.time()

        # ── Sidebars con degradado cálido ──────────────────────────────
        for x_start in [0, W - self.SIDEBAR_W]:
            for y in range(H):
                yf = y / H
                b  = int(255*(1-yf) + 230*yf)
                g  = int(249*(1-yf) + 235*yf)
                r  = int(230*(1-yf) + 210*yf)
                frame[y, x_start:x_start+self.SIDEBAR_W] = (b, g, r)

        # Bordes de sidebar
        col_v = UI["vivo_cyan"] if not is_free else UI["mode_free"]
        draw_neon_border(frame, self.SIDEBAR_W-3, 0, self.SIDEBAR_W+3, H, col_v, 1, True)
        draw_neon_border(frame, W-self.SIDEBAR_W-3, 0, W-self.SIDEBAR_W+3, H,
                         UI["vivo_amarillo"], 1, True)

        # Manchas de pintura animadas
        self._draw_paint_blobs(frame, t)

        # ── Header ─────────────────────────────────────────────────────
        header_h = 48
        cv2.rectangle(frame, (self.SIDEBAR_W, 0), (W-self.SIDEBAR_W, header_h),
                      (255, 249, 230), -1)
        draw_gradient_bar(frame, self.SIDEBAR_W, header_h-2, W-self.SIDEBAR_W, header_h,
                          UI["vivo_cyan"], UI["vivo_rosa"])

        # ── Panel título ───────────────────────────────────────────────
        cv2.rectangle(frame, (4, 4), (self.SIDEBAR_W-4, 130), (255, 245, 220), -1)
        cv2.rectangle(frame, (4, 4), (self.SIDEBAR_W-4, 130), UI["vivo_naranja"], 2)
        draw_animated_title(frame, self.SIDEBAR_W//2, 38, t)
        draw_gradient_bar(frame, 8, 80, self.SIDEBAR_W-8, 82,
                          UI["vivo_cyan"], UI["vivo_rosa"])
        put_text_centered(frame, "v5.0", self.SIDEBAR_W//2, 96,
                          0.38, UI["text_claro"], 1)
        put_text_centered(frame, "GESTOS", self.SIDEBAR_W//2, 114,
                          0.38, UI["text_claro"], 1)

        # ══════════════════════════════════════════════════════════════
        #  BOTONES IZQUIERDOS — colores saturados y texto blanco
        # ══════════════════════════════════════════════════════════════
        LEFT_BTN_INFO = {
            "BRUSH":        ("PINCEL",   UI["tool_brush"],  "B"),
            "FILL":         ("RELLENO",  UI["tool_fill"],   "F"),
            "ERASER":       ("BORRADOR", UI["tool_eraser"], "X"),
            "COLOR_PICKER": ("COLORES",  UI["tool_color"],  "C"),
        }

        for name, (x1, y1, x2, y2) in self.left_buttons.items():
            if name not in LEFT_BTN_INFO: continue
            label, accent, icon = LEFT_BTN_INFO[name]
            is_hov    = (self._hover_btn == name)
            is_active = (name == "BRUSH"  and self.active_tool == TOOL_BRUSH) or \
                        (name == "FILL"   and self.active_tool == TOOL_FILL)  or \
                        (name == "ERASER" and self.active_tool == TOOL_ERASER)

            # Fondo: color sólido del botón (activo=más oscuro, hover=acento, normal=acento claro)
            if is_active:
                # Activo: relleno sólido con el color del botón, más oscuro
                bg = tuple(max(0, int(c * 0.65)) for c in accent)
            elif is_hov:
                bg = accent
            else:
                # Normal: versión semisaturada del color (más visible que antes)
                bg = tuple(min(255, int(c * 0.55) + 60) for c in accent)

            # Resplandor activo
            if is_active:
                for expand in [5, 3, 1]:
                    ov = frame.copy()
                    draw_rounded_rect(ov, x1-expand, y1-expand,
                                      x2+expand, y2+expand, 8, accent, 2)
                    cv2.addWeighted(ov, 0.18, frame, 0.82, 0, frame)

            draw_rounded_rect(frame, x1, y1, x2, y2, 6, bg, -1)

            # Borde: blanco si activo/hover para máximo contraste
            border_c = (255, 255, 255) if (is_active or is_hov) else accent
            bth      = 3 if is_active else (2 if is_hov else 1)
            draw_rounded_rect(frame, x1, y1, x2, y2, 6, border_c, bth)

            # Icono (fondo circular oscuro para legibilidad)
            icon_cx = x1 + 22
            icon_cy = (y1 + y2) // 2
            cv2.circle(frame, (icon_cx, icon_cy), 13, (0, 0, 0), -1)
            cv2.circle(frame, (icon_cx, icon_cy), 13, (255, 255, 255), 1)
            (iw, ih), _ = cv2.getTextSize(icon, cv2.FONT_HERSHEY_SIMPLEX, 0.52, 2)
            cv2.putText(frame, icon, (icon_cx - iw//2, icon_cy + ih//2),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.52, (255, 255, 255), 2, cv2.LINE_AA)

            # Texto label — siempre blanco para contraste
            cv2.putText(frame, label, (x1+44, (y1+y2)//2+6),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.46,
                        (255, 255, 255), 2, cv2.LINE_AA)

            # Barra de progreso hover
            if is_hov and self._btn_hover_progress > 0:
                prog = int((x2-x1) * self._btn_hover_progress)
                draw_rounded_rect(frame, x1, y2-5, x1+prog, y2, 2, (255,255,255), -1)

        # ══════════════════════════════════════════════════════════════
        #  BOTONES DERECHOS — mismo esquema de colores saturados
        # ══════════════════════════════════════════════════════════════
        RIGHT_BTN_INFO = {
            "UNDO":     ("DESHACER", UI["tool_undo"],  "<"),
            "REDO":     ("REHACER",  UI["tool_undo"],  ">"),
            "CLEAR":    ("LIMPIAR",  UI["tool_clear"], "C"),
            "SAVE":     ("GUARDAR",  UI["tool_save"],  "S"),
            "OPEN_IMG": ("ABRIR",    UI["tool_open"],  "O"),
            "FREE_MODE":("LIBRE",    UI["tool_free"],  "L"),
            "PRINT":    ("IMPRIMIR", UI["tool_print"], "P"),   # NUEVO
        }

        for name, (x1, y1, x2, y2) in self.right_buttons.items():
            if name not in RIGHT_BTN_INFO: continue
            label, accent, icon = RIGHT_BTN_INFO[name]
            is_hov    = (self._hover_btn == name)
            is_active = (name == "FREE_MODE" and is_free)

            if is_active:
                bg = tuple(max(0, int(c * 0.65)) for c in accent)
            elif is_hov:
                bg = accent
            else:
                bg = tuple(min(255, int(c * 0.55) + 60) for c in accent)

            if is_active:
                for expand in [5, 3, 1]:
                    ov = frame.copy()
                    draw_rounded_rect(ov, x1-expand, y1-expand,
                                      x2+expand, y2+expand, 8, accent, 2)
                    cv2.addWeighted(ov, 0.18, frame, 0.82, 0, frame)

            draw_rounded_rect(frame, x1, y1, x2, y2, 6, bg, -1)

            border_c = (255, 255, 255) if (is_active or is_hov) else accent
            bth      = 3 if is_active else (2 if is_hov else 1)
            draw_rounded_rect(frame, x1, y1, x2, y2, 6, border_c, bth)

            icon_cx = x1 + 22
            icon_cy = (y1 + y2) // 2
            cv2.circle(frame, (icon_cx, icon_cy), 13, (0, 0, 0), -1)
            cv2.circle(frame, (icon_cx, icon_cy), 13, (255, 255, 255), 1)
            (iw, ih), _ = cv2.getTextSize(icon, cv2.FONT_HERSHEY_SIMPLEX, 0.52, 2)
            cv2.putText(frame, icon, (icon_cx - iw//2, icon_cy + ih//2),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.52, (255, 255, 255), 2, cv2.LINE_AA)

            cv2.putText(frame, label, (x1+44, (y1+y2)//2+6),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.46,
                        (255, 255, 255), 2, cv2.LINE_AA)

            if is_hov and self._btn_hover_progress > 0:
                prog = int((x2-x1) * self._btn_hover_progress)
                draw_rounded_rect(frame, x1, y2-5, x1+prog, y2, 2, (255,255,255), -1)

        # ── Badge de modo actual ───────────────────────────────────────
        mode_labels = {
            APP_MODE_PAINT: ("PINTURA LIBRE", UI["mode_paint"]),
            APP_MODE_COLOR: ("COLOREAR",      UI["mode_color"]),
            APP_MODE_FREE:  ("MODO LIBRE",    UI["mode_free"]),
        }
        mode_txt, mode_col = mode_labels[self.app_mode]
        badge_x = self.SIDEBAR_W + 16
        (btw, bth), _ = cv2.getTextSize(mode_txt, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 2)
        draw_rounded_rect(frame, badge_x-8, 6, badge_x+btw+8, header_h-6,
                          6, tuple(int(c*0.15) for c in mode_col), -1)
        draw_rounded_rect(frame, badge_x-8, 6, badge_x+btw+8, header_h-6,
                          6, mode_col, 2)
        cv2.putText(frame, mode_txt, (badge_x, header_h//2+8),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, mode_col, 2, cv2.LINE_AA)

        # ── Gesto detectado ────────────────────────────────────────────
        GESTURE_ICONS = {
            "DRAW":      "DIBUJANDO",
            "SELECT":    "SELECCIONAR",
            "ERASER":    "BORRADOR",
            "OPEN":      "PAUSADO",
            "PINCH":     "GROSOR",
            "THUMB_UP":  "SIGUIENTE COLOR",
            "THUMB_DOWN":"COLOR ANTERIOR",
            "NONE":      "Sin mano",
            "THREE":     "3 DEDOS",
        }
        g_label = GESTURE_ICONS.get(gesture, gesture)
        g_col   = UI["vivo_verde"]   if gesture == "DRAW" \
             else UI["vivo_amarillo"] if gesture in ("SELECT","PINCH") \
             else UI["vivo_rosa"]     if gesture == "ERASER" \
             else UI["text_claro"]
        (gtw,_), _ = cv2.getTextSize(g_label, cv2.FONT_HERSHEY_SIMPLEX, 0.44, 1)
        gx = W - self.SIDEBAR_W - gtw - 20
        cv2.putText(frame, "Gesto:", (gx-55, header_h//2+6),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.38, UI["text_claro"], 1, cv2.LINE_AA)
        cv2.putText(frame, g_label, (gx, header_h//2+6),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.44, g_col, 1, cv2.LINE_AA)

        # ── FPS ────────────────────────────────────────────────────────
        fps_col = UI["vivo_verde"] if fps > 25 else UI["vivo_amarillo"]
        cv2.putText(frame, f"FPS:{int(fps)}",
                    (W-self.SIDEBAR_W+10, header_h-12),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.42, fps_col, 1, cv2.LINE_AA)

        # ── Notificación ───────────────────────────────────────────────
        if self._notif_timer > 0:
            self._notif_timer -= 1
            alpha = min(1.0, self._notif_timer / 20.0)
            nx = self.SIDEBAR_W + 20
            ny = H - 60
            (nw, nh), _ = cv2.getTextSize(self._notif, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
            ov = frame.copy()
            cv2.rectangle(ov, (nx-10, ny-nh-8), (nx+nw+10, ny+8),
                          (255, 249, 230), -1)
            cv2.rectangle(ov, (nx-10, ny-nh-8), (nx+nw+10, ny+8),
                          self._notif_color, 2)
            cv2.addWeighted(ov, alpha*0.88, frame, 1-alpha*0.88, 0, frame)
            cv2.putText(frame, self._notif, (nx, ny),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                        self._notif_color, 2, cv2.LINE_AA)

        self._ui_update_counter += 1
        return frame

    def _draw_cursor(self, frame, pt, gesture):
        col = self.current_color if not self.eraser_mode else (180, 160, 130)
        r   = self.brush_size + 4
        self._trail.append((pt[0], pt[1], col))
        if self.active_tool == TOOL_FILL and gesture == "DRAW":
            cv2.rectangle(frame, (pt[0]-14, pt[1]-8),
                          (pt[0]+14, pt[1]+18), col, -1)
            cv2.rectangle(frame, (pt[0]-14, pt[1]-8),
                          (pt[0]+14, pt[1]+18), UI["vivo_amarillo"], 2)
            cv2.putText(frame, "F", (pt[0]-5, pt[1]+12),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, (20,20,20), 2, cv2.LINE_AA)
        elif self.active_tool == TOOL_ERASER or self.eraser_mode:
            er = self.brush_size * self.cfg["eraser_multiplier"] + 4
            ov = frame.copy()
            cv2.circle(ov, pt, er, (200, 180, 150), -1)
            cv2.addWeighted(ov, 0.15, frame, 0.85, 0, frame)
            cv2.circle(frame, pt, er, (180, 160, 130), 2, cv2.LINE_AA)
            cv2.line(frame, (pt[0]-er, pt[1]), (pt[0]+er, pt[1]), (180,160,130), 1)
            cv2.line(frame, (pt[0], pt[1]-er), (pt[0], pt[1]+er), (180,160,130), 1)
        elif gesture == "DRAW":
            draw_glow_circle(frame, pt[0], pt[1], r, col, 0.4)
            cv2.circle(frame, pt, 4, (255, 255, 255), -1)
        elif gesture == "SELECT":
            cv2.drawMarker(frame, pt, UI["vivo_amarillo"],
                           cv2.MARKER_CROSS, 26, 2, cv2.LINE_AA)
            cv2.circle(frame, pt, 14, UI["vivo_amarillo"], 1, cv2.LINE_AA)
        else:
            cv2.circle(frame, pt, 12, UI["text_claro"], 1, cv2.LINE_AA)
            cv2.circle(frame, pt, 3,  UI["text_claro"], -1)

    def _draw_free_cursor(self, output, info):
        idx  = info["index"]
        thumb= info["thumb"]
        dist = info["pinch_dist"]
        is_p = info["is_pinching"]
        is_d = info["is_dragging"]
        cv2.line(output, thumb, idx, UI["text_claro"], 1, cv2.LINE_AA)
        if is_d:
            draw_glow_circle(output, idx[0], idx[1], 16, UI["vivo_naranja"], 0.5)
            cv2.putText(output, "DRAG", (idx[0]+22, idx[1]-8),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, UI["vivo_naranja"], 2)
        elif is_p:
            draw_glow_circle(output, idx[0], idx[1], 14, UI["vivo_verde"], 0.6)
        else:
            cv2.circle(output, idx, 14, UI["mode_free"], 2, cv2.LINE_AA)
            cv2.circle(output, idx, 4,  UI["mode_free"], -1)
        bx, by = self.SIDEBAR_W + 20, self.H - 60
        bw     = 180
        thr    = self.cfg["pinch_threshold"]
        rel    = float(np.clip(dist/(thr*2), 0, 1))
        filled = int(bw*(1-rel))
        cv2.putText(output, "PINCH", (bx, by-4),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.40, UI["text_claro"], 1, cv2.LINE_AA)
        cv2.rectangle(output, (bx,by), (bx+bw,by+10), (255, 240, 210), -1)
        col_bar = UI["vivo_verde"] if is_p else UI["mode_free"]
        cv2.rectangle(output, (bx,by), (bx+filled,by+10), col_bar, -1)
        cv2.rectangle(output, (bx,by), (bx+bw,by+10), UI["border_claro"], 1)

    def run(self):
        cap = cv2.VideoCapture(self.cfg["camera_index"])
        cap.set(cv2.CAP_PROP_FRAME_WIDTH,  self.W)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.H)
        cap.set(cv2.CAP_PROP_FPS, 60)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

        if not cap.isOpened():
            print("[ERROR] No se pudo abrir la camara.")
            return

        win = "Magic Paint - Gestos de Mano v5.0"
        cv2.namedWindow(win, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(win, self.W, self.H)
        _print_banner()

        last_bg    = None
        gesture    = "NONE"
        _lm_draw   = None
        _smooth_d  = None
        _free_info = None

        while True:
            ret, frame = cap.read()
            if not ret:
                print("[ERROR] Frame fallido.")
                break

            if self.cfg["flip_horizontal"]:
                frame = cv2.flip(frame, 1)
            fh, fw = frame.shape[:2]
            if fw != self.W or fh != self.H:
                frame = cv2.resize(frame, (self.W, self.H))

            last_bg = frame.copy()

            now = time.time()
            self._fps_buf.append(1.0 / max(now-self._last_t, 1e-6))
            self._last_t = now
            fps = float(np.mean(self._fps_buf))

            self._frame_counter += 1

            # ── OPTIMIZACIÓN: skip más agresivo en modo libre ─────────
            if self.app_mode == APP_MODE_FREE:
                skip = self.cfg["skip_frames_free_mode"]
            else:
                skip = self.cfg["skip_frames_detection"]
            process_hands = (self._frame_counter % (skip + 1) == 0)

            if process_hands:
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                rgb.flags.writeable = False
                res = self.hands.process(rgb)
                rgb.flags.writeable = True

                if res.multi_hand_landmarks:
                    self._hand_present   = True
                    self._last_landmarks = res.multi_hand_landmarks[0]
                    hand_lm = self._last_landmarks
                    lm = hand_lm.landmark
                    ix = int(lm[8].x*self.W);  iy = int(lm[8].y*self.H)
                    tx = int(lm[4].x*self.W);  ty = int(lm[4].y*self.H)
                    pinch_d = math.dist((tx,ty),(ix,iy))
                    mn, mx = self.cfg["min_brush_size"], self.cfg["max_brush_size"]
                    self.brush_size = self._smooth_bs(
                        int(mn + float(np.clip((pinch_d-20)/200,0,1))*(mx-mn)))
                    raw_g = self._detect_gesture(lm)
                    self._last_gesture = self._stable_gesture(raw_g)
                else:
                    self._hand_present   = False
                    self._last_landmarks = None
                    self._last_gesture   = "NONE"
                    self._gesture_buffer.clear()
                    self.smooth_points.clear()
            else:
                if not self._hand_present:
                    self._last_gesture = "NONE"

            if not self._hand_present:
                gesture   = "NONE"
                _lm_draw  = None
                _smooth_d = None
                _free_info = None
                self.drawing     = False
                self.prev_point  = None
                self._fill_done  = False
                if self.app_mode == APP_MODE_FREE:
                    self.mouse_ctrl.handle_pinch(False, 0, 0)
                    self.mouse_ctrl.tick()
            else:
                gesture  = self._last_gesture
                _lm_draw = self._last_landmarks
                if _lm_draw is not None:
                    lm = _lm_draw.landmark
                    _smooth_d = self._smooth_pt((int(lm[8].x*self.W), int(lm[8].y*self.H)))

                    if self.app_mode == APP_MODE_FREE:
                        _free_info = self._process_free_mode(lm, gesture)
                    else:
                        if gesture == "THUMB_UP":
                            self.color_index   = (self.color_index+1) % len(COLORS)
                            self.current_color = COLORS[self.color_index]["bgr"]
                            self.eraser_mode   = False
                            self._notify(f"Color: {COLORS[self.color_index]['name']}",
                                         COLORS[self.color_index]["bgr"])
                        elif gesture == "THUMB_DOWN":
                            self.color_index   = (self.color_index-1) % len(COLORS)
                            self.current_color = COLORS[self.color_index]["bgr"]
                            self.eraser_mode   = False
                            self._notify(f"Color: {COLORS[self.color_index]['name']}",
                                         COLORS[self.color_index]["bgr"])
                        elif gesture == "ERASER":
                            if self.active_tool != TOOL_ERASER:
                                self.active_tool = TOOL_ERASER
                                self.eraser_mode = True
                                self._notify("Borrador activado", UI["tool_eraser"])
                        elif gesture == "OPEN":
                            self.drawing = False; self.prev_point = None

                        if gesture in ("SELECT","OPEN","PINCH"):
                            if _smooth_d:
                                self._check_btn_hover(_smooth_d, last_bg)
                            self.drawing = False; self.prev_point = None
                            self._fill_done = False
                        elif gesture == "DRAW" and _smooth_d:
                            self._hover_btn        = None
                            self._hover_btn_frames = 0
                            self._btn_hover_progress = 0

                            in_left_sidebar  = _smooth_d[0] < self.SIDEBAR_W
                            in_right_sidebar = _smooth_d[0] > self.W - self.SIDEBAR_W
                            in_btn_left  = any(x1<=_smooth_d[0]<=x2 and y1<=_smooth_d[1]<=y2
                                               for x1,y1,x2,y2 in self.left_buttons.values())
                            in_btn_right = any(x1<=_smooth_d[0]<=x2 and y1<=_smooth_d[1]<=y2
                                               for x1,y1,x2,y2 in self.right_buttons.values())
                            in_header = _smooth_d[1] < 48

                            blocked = in_left_sidebar or in_right_sidebar or \
                                      in_btn_left or in_btn_right or in_header

                            if not blocked:
                                if self.active_tool == TOOL_FILL:
                                    if not self._fill_done:
                                        self._apply_fill(_smooth_d)
                                        self._fill_done = True
                                    self.drawing = False; self.prev_point = None
                                elif self.active_tool == TOOL_ERASER or self.eraser_mode:
                                    if not self.drawing:
                                        self._push_undo(); self.drawing = True
                                    esize = self.brush_size * self.cfg["eraser_multiplier"]
                                    if self.app_mode == APP_MODE_COLOR and self.color_image_orig is not None:
                                        mask_e = np.zeros((self.H,self.W), dtype=np.uint8)
                                        cv2.circle(mask_e, _smooth_d, esize, 255, -1)
                                        self.color_layer = np.where(
                                            np.stack([mask_e]*3,axis=-1)>0,
                                            self.color_image_orig, self.color_layer
                                        ).astype(np.uint8)
                                    else:
                                        self._stroke(_smooth_d,(0,0,0),esize)
                                    self.prev_point = _smooth_d
                                else:
                                    if not self.drawing:
                                        self._push_undo(); self.drawing = True
                                    self._stroke(_smooth_d, self.current_color, self.brush_size)
                                    self.prev_point = _smooth_d
                            else:
                                self.drawing = False; self.prev_point = None
                                self._fill_done = False
                        else:
                            self.drawing    = False; self.prev_point = None
                            self._fill_done = False

            # ── Renderizado ─────────────────────────────────────────────
            if self.app_mode == APP_MODE_FREE:
                # OPTIMIZACIÓN: fondo con caché + degradado vectorizado
                if (self._free_bg_cache is None or
                        self._frame_counter - self._free_bg_frame_cnt >= self._free_bg_interval):
                    self._free_bg_cache     = self._build_free_bg(frame)
                    self._free_bg_frame_cnt = self._frame_counter
                output = self._free_bg_cache.copy()
            elif self.app_mode == APP_MODE_COLOR and self.color_layer is not None:
                output = cv2.addWeighted(self.color_layer, 0.88, frame, 0.12, 0)
            else:
                output = self._merge_canvas(frame)

            if self.app_mode != APP_MODE_COLOR:
                self._update_effects(output)

            if _lm_draw is not None and _smooth_d is not None and self._hand_present:
                self.mp_draw.draw_landmarks(
                    output, _lm_draw, self.mp_hands.HAND_CONNECTIONS,
                    self.mp_draw_styles.DrawingSpec(
                        color=UI["vivo_verde"], thickness=2, circle_radius=4),
                    self.mp_draw_styles.DrawingSpec(
                        color=UI["vivo_cyan"], thickness=2))

                if self.app_mode == APP_MODE_FREE and _free_info is not None:
                    self._draw_free_cursor(output, _free_info)
                else:
                    self._draw_cursor(output, _smooth_d, gesture)

            output = self._draw_ui(output, gesture, fps)
            cv2.imshow(win, output)

            key = cv2.waitKey(1) & 0xFF
            if key in (ord('q'), 27):
                self.mouse_ctrl.release_all()
                break
            elif key == ord('1'):
                self.mouse_ctrl.release_all()
                self.app_mode = APP_MODE_PAINT
                self._free_bg_cache = None
                self._notify("Modo: Pintura Libre", UI["mode_paint"])
            elif key == ord('2'):
                if self.color_layer is not None:
                    self.mouse_ctrl.release_all()
                    self.app_mode = APP_MODE_COLOR
                    self._free_bg_cache = None
                    self._notify("Modo: Colorear Imagen", UI["mode_color"])
                else:
                    self._notify("Carga una imagen primero (tecla O)", UI["vivo_rojo"])
            elif key == ord('3'):
                self._toggle_free_mode()
            elif key in (ord('o'),ord('O')):
                self.img_selector._load()
                path = self.img_selector.show(self.W, self.H)
                if path:
                    self.load_color_image(path)
            elif key in (ord('b'),ord('B')):
                self.active_tool = TOOL_BRUSH;  self.eraser_mode = False
                self._notify("Herramienta: Pincel", UI["tool_brush"])
            elif key in (ord('k'),ord('K')):
                self.active_tool = TOOL_FILL;   self.eraser_mode = False
                self._notify("Herramienta: Relleno", UI["tool_fill"])
            elif key in (ord('e'),ord('E')):
                self.active_tool = TOOL_ERASER; self.eraser_mode = True
                self._notify("Herramienta: Borrador", UI["tool_eraser"])
            elif key in (ord('c'),ord('C')):
                self._push_undo()
                if self.app_mode == APP_MODE_COLOR and self.color_image_orig is not None:
                    self.color_layer = self.color_image_orig.copy()
                    self._notify("Imagen restaurada", UI["vivo_naranja"])
                else:
                    self.canvas[:] = 0
                    self._notify("Canvas limpiado", UI["vivo_rojo"])
            elif key in (ord('r'),ord('R')):
                self.reset_color_image()
            elif key in (ord('h'),ord('H')):
                self.show_hud = not self.show_hud
            elif key in (ord('f'),ord('F')):
                self.fullscreen = not self.fullscreen
                cv2.setWindowProperty(win, cv2.WND_PROP_FULLSCREEN,
                    cv2.WINDOW_FULLSCREEN if self.fullscreen else cv2.WINDOW_NORMAL)
            elif key in (ord('s'),ord('S')):
                self.save_drawing(last_bg)
            elif key in (ord('p'),ord('P')):         # NUEVO: tecla P para imprimir
                self.print_drawing(last_bg)
            elif key == 26:
                self.undo()
            elif key == 25:
                self.redo()
            elif key in (ord('+'),ord('=')):
                self.brush_size = min(self.brush_size+2, self.cfg["max_brush_size"])
            elif key == ord('-'):
                self.brush_size = max(self.brush_size-2, self.cfg["min_brush_size"])
            elif key == ord(']'):
                self.fill_tolerance = min(self.fill_tolerance+4, self.cfg["fill_tolerance_max"])
                self._notify(f"Tolerancia: {self.fill_tolerance}", UI["vivo_naranja"])
            elif key == ord('['):
                self.fill_tolerance = max(self.fill_tolerance-4, self.cfg["fill_tolerance_min"])
                self._notify(f"Tolerancia: {self.fill_tolerance}", UI["vivo_naranja"])

        cap.release()
        self.hands.close()
        cv2.destroyAllWindows()
        print(f"\n[OK] Obras guardadas en ./{self.cfg['save_dir']}/")


# =============================================================
#  CREAR IMÁGENES DE EJEMPLO
# =============================================================
def create_sample_images(out_dir):
    os.makedirs(out_dir, exist_ok=True)
    W, H = 800, 600

    img = np.full((H,W,3), 255, dtype=np.uint8)
    cx, cy = W//2, H//2
    for r in range(40,260,42):
        cv2.circle(img,(cx,cy),r,(0,0,0),2)
    for a in range(0,360,30):
        rd = math.radians(a)
        cv2.line(img,(int(cx+42*math.cos(rd)),int(cy+42*math.sin(rd))),
                     (int(cx+250*math.cos(rd)),int(cy+250*math.sin(rd))),(0,0,0),2)
    for a in range(0,360,45):
        rd = math.radians(a)
        px,py = int(cx+145*math.cos(rd)),int(cy+145*math.sin(rd))
        cv2.ellipse(img,(px,py),(36,20),a,0,360,(0,0,0),2)
    cv2.imwrite(os.path.join(out_dir,"mandala.png"),img)

    img = np.full((H,W,3),255,dtype=np.uint8)
    cv2.line(img,(0,H//2),(W,H//2),(0,0,0),2)
    cv2.circle(img,(130,110),72,(0,0,0),2)
    mts = np.array([[0,H//2],[160,185],[320,H//2],[510,170],[720,H//2],[W,H//2]])
    cv2.polylines(img,[mts],False,(0,0,0),3)
    cv2.imwrite(os.path.join(out_dir,"paisaje.png"),img)

    img = np.full((H,W,3),255,dtype=np.uint8)
    cv2.circle(img,(400,300),185,(0,0,0),3)
    for ex in [340,460]:
        cv2.circle(img,(ex,268),38,(0,0,0),3)
        cv2.circle(img,(ex,268),14,(0,0,0),-1)
    cv2.imwrite(os.path.join(out_dir,"gato.png"),img)

    print(f"[OK] Imagenes de ejemplo en '{out_dir}/'")


def _print_banner():
    print("=" * 68)
    print("   M A G I C   P A I N T  v5.0  -  Feria de Tecnologia")
    print("   Universidad Politecnica del Carchi - Carrera de Computacion")
    print("=" * 68)
    print("  Modos:   [1] Pintura libre   [2] Colorear   [3] Modo Libre")
    print("  Herram:  [B] Pincel  [K] Fill  [E] Borrador")
    print("  Imagen:  [O] Abrir  [R] Restaurar  [S] Guardar  [P] Imprimir")
    print("  Colores: [C] Selector de colores (48 colores)")
    print("  Ctrl+Z Undo  |  Ctrl+Y Redo  |  H HUD  |  F Full  |  Q Salir")
    print("=" * 68)
    if not PYAUTOGUI_OK:
        print("  [!] Instala pyautogui para Modo Libre: pip install pyautogui")
        print("=" * 68)


def main():
    if len(sys.argv) > 1 and sys.argv[1].lstrip('-').isdigit():
        CONFIG["camera_index"] = int(sys.argv[1])
    if "--gen-samples" in sys.argv:
        create_sample_images(CONFIG["images_dir"])
        return

    total = sum(len(glob.glob(os.path.join(CONFIG["images_dir"], ext)))
                for ext in CONFIG["image_extensions"])
    if total == 0:
        print(f"[INFO] Generando imagenes de ejemplo en '{CONFIG['images_dir']}'...")
        create_sample_images(CONFIG["images_dir"])

    VirtualPainter().run()


if __name__ == "__main__":
    main()