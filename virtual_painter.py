"""
╔══════════════════════════════════════════════════════════════════════╗
║      MAGIC PAINT  — Pintura Virtual con Gestos de Mano  v4.0        ║
║           Python + OpenCV + MediaPipe  |  Edicion Feria             ║
╠══════════════════════════════════════════════════════════════════════╣
║  MODOS:                                                              ║
║   [1] PINTURA LIBRE  — dibuja sobre la camara en tiempo real        ║
║   [2] COLOREAR       — colorea imagenes con el bote de pintura      ║
║   [3] MODO LIBRE     — controla el mouse del sistema                ║
╠══════════════════════════════════════════════════════════════════════╣
║  GESTOS PRINCIPALES:                                                 ║
║   Solo indice     → Dibujar / Rellenar                              ║
║   2 dedos         → Seleccionar en menu                             ║
║   Puno cerrado    → Borrador                                        ║
║   Mano abierta    → Pausar                                          ║
║   Pinch           → Cambiar grosor                                  ║
║   Pulgar arriba   → Siguiente color                                 ║
╠══════════════════════════════════════════════════════════════════════╣
║  TECLAS:  1/2/3 Modo | B Pincel | K Fill | E Borrador              ║
║           O Abrir img | S Guardar | Ctrl+Z Undo | H HUD | Q Salir  ║
╚══════════════════════════════════════════════════════════════════════╝
"""

import cv2
import mediapipe as mp
import numpy as np
import os, sys, time, math, glob
from collections import deque
from datetime import datetime

# pyautogui opcional para Modo Libre
try:
    import pyautogui
    pyautogui.FAILSAFE = False
    pyautogui.PAUSE    = 0.0
    PYAUTOGUI_OK = True
except ImportError:
    PYAUTOGUI_OK = False

# ══════════════════════════════════════════════════════════════════════
#  TEMA VISUAL — PALETA NEON PARA FERIA
# ══════════════════════════════════════════════════════════════════════
UI = {
    "bg_dark":      (15,  12,  28),
    "bg_panel":     (22,  18,  42),
    "bg_panel2":    (30,  26,  55),
    "neon_cyan":    (255, 230,  0),
    "neon_green":   ( 50, 255, 120),
    "neon_pink":    (180,  60, 255),
    "neon_orange":  (  0, 160, 255),
    "neon_purple":  (220,  80, 180),
    "neon_yellow":  (  0, 240, 255),
    "text_white":   (240, 240, 255),
    "text_dim":     (140, 130, 170),
    "text_bright":  (255, 255, 255),
    "active_brush":  ( 50, 255, 120),
    "active_fill":   (  0, 200, 255),
    "active_eraser": (180,  60, 255),
    "active_free":   (  0, 220, 255),
    "mode_paint":  ( 50, 255, 120),
    "mode_color":  (  0, 200, 255),
    "mode_free":   (255, 180,  0),
    "border_dim":   ( 60,  50,  90),
    "border_bright":(120, 100, 180),
}

# ══════════════════════════════════════════════════════════════════════
#  CONFIGURACION
# ══════════════════════════════════════════════════════════════════════
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
    "detection_confidence": 0.75,
    "tracking_confidence":  0.75,
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
}

# ══════════════════════════════════════════════════════════════════════
#  PALETA DE COLORES SIMPLIFICADA (BGR)
# ══════════════════════════════════════════════════════════════════════
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


# ══════════════════════════════════════════════════════════════════════
#  HELPERS DE DIBUJO UI
# ══════════════════════════════════════════════════════════════════════
def draw_rounded_rect(img, x1, y1, x2, y2, r, color, thickness=-1):
    if thickness == -1:
        cv2.rectangle(img, (x1+r, y1), (x2-r, y2), color, -1)
        cv2.rectangle(img, (x1, y1+r), (x2, y2-r), color, -1)
        for cx, cy in [(x1+r, y1+r), (x2-r, y1+r),
                       (x1+r, y2-r), (x2-r, y2-r)]:
            cv2.circle(img, (cx, cy), r, color, -1)
    else:
        cv2.rectangle(img, (x1+r, y1), (x2-r, y1), color, thickness)
        cv2.rectangle(img, (x1+r, y2), (x2-r, y2), color, thickness)
        cv2.rectangle(img, (x1, y1+r), (x1, y2-r), color, thickness)
        cv2.rectangle(img, (x2, y1+r), (x2, y2-r), color, thickness)
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
            alpha = 0.15 * i
            ov = img.copy()
            cv2.rectangle(ov, (x1-i, y1-i), (x2+i, y2+i), color, thickness)
            cv2.addWeighted(ov, alpha, img, 1-alpha, 0, img)
    cv2.rectangle(img, (x1, y1), (x2, y2), color, thickness)


def put_text_centered(img, text, cx, cy, font_scale, color, thickness=1):
    (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX,
                                   font_scale, thickness)
    cv2.putText(img, text, (cx - tw//2, cy + th//2),
                cv2.FONT_HERSHEY_SIMPLEX, font_scale, color, thickness, cv2.LINE_AA)


def draw_gradient_bar(img, x1, y1, x2, y2, color_left, color_right):
    w = x2 - x1
    for i in range(w):
        t = i / max(w-1, 1)
        c = tuple(int(color_left[j] * (1-t) + color_right[j] * t) for j in range(3))
        cv2.line(img, (x1+i, y1), (x1+i, y2), c, 1)


# ══════════════════════════════════════════════════════════════════════
#  FLOOD FILL
# ══════════════════════════════════════════════════════════════════════
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
    return np.where(cv2.cvtColor(border, cv2.COLOR_GRAY2BGR) > 0,
                    blurred, filled).astype(np.uint8)


# ══════════════════════════════════════════════════════════════════════
#  CONTROLADOR DE MOUSE
# ══════════════════════════════════════════════════════════════════════
class MouseController:
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


# ══════════════════════════════════════════════════════════════════════
#  SELECTOR DE COLORES (48 colores)
# ══════════════════════════════════════════════════════════════════════
class ColorPicker:
    COLS = 6
    SWATCH_W = 90
    SWATCH_H = 60
    BG_COLOR = (28, 28, 35)
    SEL_COLOR = (80, 200, 120)

    EXTENDED_COLORS = [
        {"name": "Negro", "bgr": (1, 1, 1)},
        {"name": "Gris Oscuro", "bgr": (50, 50, 50)},
        {"name": "Gris", "bgr": (128, 128, 128)},
        {"name": "Gris Claro", "bgr": (180, 180, 180)},
        {"name": "Blanco", "bgr": (255, 255, 255)},
        {"name": "Rojo Oscuro", "bgr": (0, 0, 100)},
        {"name": "Rojo", "bgr": (0, 0, 220)},
        {"name": "Rojo Brillante", "bgr": (0, 0, 255)},
        {"name": "Naranja Oscuro", "bgr": (0, 60, 160)},
        {"name": "Naranja", "bgr": (0, 120, 255)},
        {"name": "Amarillo Oscuro", "bgr": (0, 180, 200)},
        {"name": "Amarillo", "bgr": (0, 220, 220)},
        {"name": "Amarillo Brill", "bgr": (0, 255, 255)},
        {"name": "Lima", "bgr": (80, 255, 80)},
        {"name": "Verde Lima", "bgr": (120, 255, 0)},
        {"name": "Verde", "bgr": (0, 200, 60)},
        {"name": "Verde Oscuro", "bgr": (0, 100, 40)},
        {"name": "Verde Bosque", "bgr": (0, 130, 60)},
        {"name": "Verde Oliva", "bgr": (0, 160, 80)},
        {"name": "Cian Oscuro", "bgr": (150, 180, 0)},
        {"name": "Cian", "bgr": (220, 200, 0)},
        {"name": "Cian Brillante", "bgr": (255, 255, 0)},
        {"name": "Azul Cielo", "bgr": (230, 150, 0)},
        {"name": "Azul", "bgr": (230, 80, 0)},
        {"name": "Azul Real", "bgr": (200, 50, 0)},
        {"name": "Azul Marino", "bgr": (130, 30, 30)},
        {"name": "Azul Oscuro", "bgr": (100, 20, 20)},
        {"name": "Violeta", "bgr": (100, 0, 100)},
        {"name": "Morado", "bgr": (160, 0, 120)},
        {"name": "Purpura", "bgr": (180, 50, 150)},
        {"name": "Magenta", "bgr": (200, 0, 200)},
        {"name": "Rosa", "bgr": (160, 100, 240)},
        {"name": "Rosa Oscuro", "bgr": (100, 50, 120)},
        {"name": "Rosa Brillante", "bgr": (180, 150, 220)},
        {"name": "Salmon", "bgr": (100, 130, 180)},
        {"name": "Coral", "bgr": (80, 127, 180)},
        {"name": "Marron Oscuro", "bgr": (20, 50, 90)},
        {"name": "Marron", "bgr": (30, 80, 140)},
        {"name": "Marron Claro", "bgr": (60, 120, 160)},
        {"name": "Beige", "bgr": (130, 180, 200)},
        {"name": "Piel Muy Clara", "bgr": (180, 200, 220)},
        {"name": "Piel Clara", "bgr": (140, 180, 210)},
        {"name": "Piel Clara Med.", "bgr": (130, 160, 190)},
        {"name": "Piel Media", "bgr": (110, 140, 170)},
        {"name": "Piel Morena", "bgr": (80, 110, 140)},
        {"name": "Piel Oscura", "bgr": (50, 70, 100)},
        {"name": "Piel Muy Osc.", "bgr": (30, 50, 70)},
        {"name": "Cafe", "bgr": (25, 40, 65)},
    ]

    def __init__(self):
        self.colors   = self.EXTENDED_COLORS
        self.selected = 0

    def _build_grid(self, W, H):
        canvas = np.full((H, W, 3), self.BG_COLOR, dtype=np.uint8)
        mg = 20
        n  = len(self.colors)
        
        # Header
        cv2.rectangle(canvas, (0, 0), (W, 70), (22, 18, 42), -1)
        cv2.putText(canvas, "SELECCIONA UN COLOR", (mg, 40), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.9, (200,220,255), 2, cv2.LINE_AA)
        cv2.putText(canvas, "Flechas/WASD para navegar  |  ENTER para seleccionar  |  ESC para cancelar",
                    (mg, 65), cv2.FONT_HERSHEY_SIMPLEX, 0.48, (140,140,160), 1, cv2.LINE_AA)
        
        start_y = 90
        rows = (n + self.COLS - 1) // self.COLS
        grid_h = rows * (self.SWATCH_H + 30) + 20
        
        for i, c in enumerate(self.colors):
            row = i // self.COLS
            col = i % self.COLS
            x   = mg + col * (self.SWATCH_W + 12)
            y   = start_y + row * (self.SWATCH_H + 30)
            
            if i == self.selected:
                # Borde de seleccion con glow
                for ex in [4, 3, 2]:
                    alpha = 0.1 * (4 - ex)
                    ov = canvas.copy()
                    cv2.rectangle(ov, (x-6-ex, y-6-ex), (x+self.SWATCH_W+6+ex, y+self.SWATCH_H+6+ex), self.SEL_COLOR, 2)
                    cv2.addWeighted(ov, alpha, canvas, 1-alpha, 0, canvas)
                cv2.rectangle(canvas, (x-6, y-6), (x+self.SWATCH_W+6, y+self.SWATCH_H+6), self.SEL_COLOR, 3)
            else:
                cv2.rectangle(canvas, (x-2, y-2), (x+self.SWATCH_W+2, y+self.SWATCH_H+2), (60,60,80), 1)
            
            # Swatch de color
            cv2.rectangle(canvas, (x, y), (x+self.SWATCH_W, y+self.SWATCH_H), c["bgr"], -1)
            cv2.rectangle(canvas, (x, y), (x+self.SWATCH_W, y+self.SWATCH_H), (120,120,140), 1)
            
            # Nombre del color
            name = c["name"][:12]
            (tw, th), _ = cv2.getTextSize(name, cv2.FONT_HERSHEY_SIMPLEX, 0.4, 1)
            cv2.putText(canvas, name, (x + (self.SWATCH_W - tw)//2, y+self.SWATCH_H+18),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.4, (180,180,200), 1, cv2.LINE_AA)
        
        # Footer
        cv2.rectangle(canvas, (0, H-35), (W, H), (22, 18, 42), -1)
        cv2.putText(canvas, f"{n} colores disponibles", (mg, H-12),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (100,100,120), 1, cv2.LINE_AA)
        
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


# ══════════════════════════════════════════════════════════════════════
#  SELECTOR DE IMAGENES
# ══════════════════════════════════════════════════════════════════════
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
                th = cv2.resize(img, (self.THUMB_W, self.THUMB_H))
            else:
                th = np.full((self.THUMB_H, self.THUMB_W, 3), 40, dtype=np.uint8)
                put_text_centered(th, "?", self.THUMB_W//2, self.THUMB_H//2,
                                  1.5, (150,150,150), 3)
            self.thumbnails.append(th)

    def _build_grid(self, W, H):
        bg = np.full((H, W, 3), UI["bg_dark"], dtype=np.uint8)

        cv2.rectangle(bg, (0, 0), (W, 85), UI["bg_panel"], -1)
        draw_gradient_bar(bg, 0, 82, W, 85, UI["neon_cyan"], UI["neon_pink"])

        put_text_centered(bg, "SELECCIONA UNA IMAGEN PARA COLOREAR",
                          W//2, 32, 0.9, UI["neon_cyan"], 2)
        put_text_centered(bg,
            "Flechas/WASD para navegar  |  ENTER para seleccionar  |  ESC para cancelar",
            W//2, 62, 0.48, UI["text_dim"], 1)

        mg, pad = 20, 14
        for i, (thumb, path) in enumerate(zip(self.thumbnails, self.image_paths)):
            row = i // self.COLS
            col = i % self.COLS
            x   = mg + col * (self.THUMB_W + pad)
            y   = 98  + row * (self.THUMB_H + pad + 26)
            if y + self.THUMB_H + 26 > H - 40: break

            tw, th = self.THUMB_W, self.THUMB_H

            if i == self.selected:
                draw_rounded_rect(bg, x-6, y-6, x+tw+6, y+th+6, 6,
                                  UI["neon_green"], -1)
                draw_rounded_rect(bg, x-6, y-6, x+tw+6, y+th+6, 6,
                                  UI["bg_dark"], -1)
                draw_neon_border(bg, x-4, y-4, x+tw+4, y+th+4,
                                 UI["neon_green"], 3)
            else:
                cv2.rectangle(bg, (x-2, y-2), (x+tw+2, y+th+2),
                              UI["border_dim"], 1)

            bg[y:y+th, x:x+tw] = thumb

            fname = os.path.basename(path)
            fname = fname[:24] if len(fname) > 24 else fname
            col_t = UI["neon_green"] if i == self.selected else UI["text_dim"]
            cv2.putText(bg, fname, (x, y+th+20),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.40, col_t, 1, cv2.LINE_AA)

        cv2.rectangle(bg, (0, H-38), (W, H), UI["bg_panel"], -1)
        put_text_centered(
            bg, f"[R] Recargar  |  {len(self.image_paths)} imagen(es) disponibles",
            W//2, H-19, 0.44, UI["text_dim"], 1)
        return bg

    def show(self, W=1280, H=720):
        win = "Magic Paint — Seleccionar Imagen"
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


# ══════════════════════════════════════════════════════════════════════
#  CLASE PRINCIPAL
# ══════════════════════════════════════════════════════════════════════
class VirtualPainter:

    class Particle:
        def __init__(self, W, H):
            self.reset(W, H)
        def reset(self, W, H):
            self.x   = float(np.random.randint(0, W))
            self.y   = float(np.random.randint(0, H))
            self.vx  = float(np.random.uniform(-1.2, 1.2))
            self.vy  = float(np.random.uniform(-2.0, -0.4))
            self.r   = int(np.random.randint(2, 6))
            colors   = [UI["neon_cyan"], UI["neon_green"], UI["neon_pink"],
                        UI["neon_orange"], UI["neon_yellow"], UI["neon_purple"]]
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

        self._notif       = ""
        self._notif_timer = 0
        self._notif_color = UI["neon_green"]

        self._trail      = deque(maxlen=20)
        self._paint_splashes = []

        self._particles = [self.Particle(self.W, self.H) for _ in range(35)]

        self._title_pulse = 0.0

        self._fps_buf = deque(maxlen=30)
        self._last_t  = time.time()

        self.mouse_ctrl        = MouseController(self.cfg, self.W, self.H)
        self._mouse_action     = ""
        self._mouse_action_t   = 0

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

    def _notify(self, msg, color=None, dur=90):
        self._notif       = msg
        self._notif_timer = dur
        self._notif_color = color or UI["neon_green"]

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
        self.undo_stack.append(self._get_layer().copy())
        self.redo_stack.clear()

    def undo(self):
        if len(self.undo_stack) > 1:
            self.redo_stack.append(self.undo_stack.pop())
            self._set_layer(self.undo_stack[-1].copy())
            self._notify("↩  Deshacer", UI["neon_yellow"])

    def redo(self):
        if self.redo_stack:
            s = self.redo_stack.pop()
            self.undo_stack.append(s)
            self._set_layer(s.copy())
            self._notify("↪  Rehacer", UI["neon_yellow"])

    def load_color_image(self, path):
        img = cv2.imread(path)
        if img is None:
            self._notify(f"Error abriendo imagen", UI["neon_pink"])
            return False
        
        # Crear un canvas con offset para evitar los botones
        img = cv2.resize(img, (self.W - self.SIDEBAR_W, self.H), interpolation=cv2.INTER_AREA)
        
        # Crear un canvas completo con fondo negro y la imagen desplazada
        full_canvas = np.zeros((self.H, self.W, 3), dtype=np.uint8)
        full_canvas[:, self.SIDEBAR_W:self.W] = img
        
        self.color_image_orig = full_canvas.copy()
        self.color_layer = full_canvas.copy()
        self.color_image_path = path
        self.app_mode = APP_MODE_COLOR
        self.undo_stack.clear(); self.redo_stack.clear()
        self._push_undo()
        self._notify(f"Imagen cargada: {os.path.basename(path)}", UI["neon_cyan"])
        return True

    def reset_color_image(self):
        if self.color_image_orig is not None:
            self._push_undo()
            self.color_layer = self.color_image_orig.copy()
            self._notify("Imagen restaurada al original", UI["neon_orange"])

    def save_drawing(self, frame_bg=None):
        ts  = datetime.now().strftime("%Y%m%d_%H%M%S")
        ext = self.cfg["save_format"]
        if self.app_mode == APP_MODE_COLOR and self.color_layer is not None:
            # Guardar solo la parte visible de la imagen (sin la barra lateral)
            save_img = self.color_layer[:, self.SIDEBAR_W:self.W]
            path = os.path.join(self.cfg["save_dir"], f"colored_{ts}.{ext}")
            cv2.imwrite(path, save_img)
        elif frame_bg is not None:
            path = os.path.join(self.cfg["save_dir"], f"painting_{ts}.{ext}")
            cv2.imwrite(path, self._merge_canvas(frame_bg))
        else:
            path = os.path.join(self.cfg["save_dir"], f"canvas_{ts}.{ext}")
            cv2.imwrite(path, self.canvas)
        self._notify(f"💾  Guardado!", UI["neon_green"])
        print(f"[OK] {path}")
        return path

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

        self.buttons = {
            "BRUSH":     (BTN_X, btn_y(0), BTN_X+BTN_W, btn_y(0)+BTN_H),
            "FILL":      (BTN_X, btn_y(1), BTN_X+BTN_W, btn_y(1)+BTN_H),
            "ERASER":    (BTN_X, btn_y(2), BTN_X+BTN_W, btn_y(2)+BTN_H),
            "COLOR_PICKER": (BTN_X, btn_y(3), BTN_X+BTN_W, btn_y(3)+BTN_H),
            "UNDO":      (BTN_X, btn_y(5), BTN_X+BTN_W, btn_y(5)+BTN_H),
            "REDO":      (BTN_X, btn_y(6), BTN_X+BTN_W, btn_y(6)+BTN_H),
            "CLEAR":     (BTN_X, btn_y(7), BTN_X+BTN_W, btn_y(7)+BTN_H),
            "SAVE":      (BTN_X, btn_y(8), BTN_X+BTN_W, btn_y(8)+BTN_H),
            "OPEN_IMG":  (BTN_X, btn_y(9), BTN_X+BTN_W, btn_y(9)+BTN_H),
            "FREE_MODE": (BTN_X, btn_y(10), BTN_X+BTN_W, btn_y(10)+BTN_H),
        }

        # Area de dibujo
        self.DRAW_X1 = self.SIDEBAR_W
        self.DRAW_Y1 = 0
        self.DRAW_X2 = W
        self.DRAW_Y2 = H

    def _fingers_up(self, lm):
        h, w = self.H, self.W
        pts  = [(int(lm[i].x*w), int(lm[i].y*h)) for i in range(21)]
        up   = [pts[TIP[0]][0] > pts[PIP[0]][0]]
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
            self._paint_splashes.append([pt[0], pt[1], size+4, color, 0, 18])

    def _apply_fill(self, pt):
        self._push_undo()
        result = flood_fill_smooth(self._get_layer(), pt,
                                   self.current_color, self.fill_tolerance)
        self._set_layer(result)
        self._paint_splashes.append([pt[0], pt[1], 30, self.current_color, 0, 25])
        self._notify(f"Relleno  (tol: {self.fill_tolerance})", UI["neon_orange"])

    def _check_btn_hover(self, pt, frame_bg=None):
        x, y = pt
        if x > self.SIDEBAR_W: return False
        for name, (x1, y1, x2, y2) in self.buttons.items():
            if x1 <= x <= x2 and y1 <= y <= y2:
                if self._hover_btn == name:
                    self._hover_btn_frames += 1
                    if self._hover_btn_frames >= self._hover_btn_thr:
                        self._trigger_btn(name, frame_bg)
                        self._hover_btn_frames = 0
                else:
                    self._hover_btn       = name
                    self._hover_btn_frames= 0
                return True
        self._hover_btn        = None
        self._hover_btn_frames = 0
        return False

    def _trigger_btn(self, name, frame_bg=None):
        if   name == "UNDO":     self.undo()
        elif name == "REDO":     self.redo()
        elif name == "SAVE":     self.save_drawing(frame_bg)
        elif name == "CLEAR":
            self._push_undo()
            if self.app_mode == APP_MODE_COLOR and self.color_image_orig is not None:
                self.color_layer = self.color_image_orig.copy()
                self._notify("Imagen restaurada", UI["neon_orange"])
            else:
                self.canvas[:] = 0
                self._notify("Canvas limpiado", UI["neon_pink"])
        elif name == "BRUSH":
            self.active_tool = TOOL_BRUSH;  self.eraser_mode = False
            self._notify("Herramienta: Pincel", UI["active_brush"])
        elif name == "FILL":
            self.active_tool = TOOL_FILL;   self.eraser_mode = False
            self._notify("Herramienta: Bote de Pintura", UI["active_fill"])
        elif name == "ERASER":
            self.active_tool = TOOL_ERASER; self.eraser_mode = True
            self._notify("Herramienta: Borrador", UI["active_eraser"])
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
            self._notify("Modo: Pintura Libre", UI["mode_paint"])
        else:
            if not PYAUTOGUI_OK:
                self._notify("Instala: pip install pyautogui", UI["neon_pink"])
                return
            self.mouse_ctrl.release_all()
            self.app_mode = APP_MODE_FREE
            self._notify("MODO LIBRE — Controla el mouse!", UI["mode_free"])

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
        op    = self.cfg["canvas_opacity"]
        mask  = (self.canvas.sum(axis=2) > 0).astype(np.uint8)
        mask3 = np.stack([mask]*3, axis=-1)
        return np.where(mask3,
                        cv2.addWeighted(frame, 1-op, self.canvas, op, 0),
                        frame).astype(np.uint8)

    def _update_effects(self, frame):
        for p in self._particles:
            p.update()
            p.draw(frame)

        alive = []
        for s in self._paint_splashes:
            x, y, r, col, age, max_age = s
            if age < max_age:
                a = 1.0 - age/max_age
                cr = int(r * (1 + age*0.4))
                ov = frame.copy()
                cv2.circle(ov, (x, y), cr, col, -1, cv2.LINE_AA)
                cv2.addWeighted(ov, a * 0.5, frame, 1 - a * 0.5, 0, frame)
                s[4] += 1
                alive.append(s)
        self._paint_splashes = alive

        for i, (tx, ty, tc) in enumerate(self._trail):
            a   = (i+1) / len(self._trail)
            r   = max(1, int(a * 6))
            ov  = frame.copy()
            cv2.circle(ov, (tx, ty), r, tc, -1, cv2.LINE_AA)
            cv2.addWeighted(ov, a*0.4, frame, 1-a*0.4, 0, frame)

    def _draw_ui(self, frame, gesture, fps):
        if not self.show_hud:
            return frame

        W, H = self.W, self.H
        is_free = (self.app_mode == APP_MODE_FREE)

        # Sidebar izquierda
        sidebar = frame[:, :self.SIDEBAR_W].copy()
        for y in range(H):
            t   = y / H
            r   = int(UI["bg_dark"][0] * (1-t) + UI["bg_panel"][0] * t)
            g   = int(UI["bg_dark"][1] * (1-t) + UI["bg_panel"][1] * t)
            b   = int(UI["bg_dark"][2] * (1-t) + UI["bg_panel"][2] * t)
            sidebar[y, :] = (r, g, b)
        frame[:, :self.SIDEBAR_W] = sidebar

        for dx, alpha in [(3, 0.15), (2, 0.25), (1, 0.45), (0, 1.0)]:
            col_v = UI["neon_cyan"] if not is_free else UI["mode_free"]
            if alpha < 1.0:
                ov = frame.copy()
                cv2.line(ov, (self.SIDEBAR_W-dx, 0),
                         (self.SIDEBAR_W-dx, H), col_v, 1)
                cv2.addWeighted(ov, alpha, frame, 1-alpha, 0, frame)
            else:
                cv2.line(frame, (self.SIDEBAR_W-1, 0),
                         (self.SIDEBAR_W-1, H), col_v, 2)

        self._title_pulse = (self._title_pulse + 0.05) % (2*math.pi)
        pulse_val = 0.5 + 0.5 * math.sin(self._title_pulse)
        title_col = tuple(
            int(UI["neon_cyan"][i] * pulse_val + UI["neon_pink"][i] * (1-pulse_val))
            for i in range(3)
        )

        cv2.rectangle(frame, (4, 4), (self.SIDEBAR_W-4, 130), UI["bg_panel2"], -1)
        draw_neon_border(frame, 4, 4, self.SIDEBAR_W-4, 130, title_col, 2)

        put_text_centered(frame, "MAGIC", self.SIDEBAR_W//2, 35,
                          0.85, title_col, 2)
        put_text_centered(frame, "PAINT", self.SIDEBAR_W//2, 65,
                          0.85, UI["neon_pink"], 2)

        draw_gradient_bar(frame, 8, 80, self.SIDEBAR_W-8, 82,
                          UI["neon_cyan"], UI["neon_pink"])

        put_text_centered(frame, "v4.0", self.SIDEBAR_W//2, 98,
                          0.38, UI["text_dim"], 1)
        put_text_centered(frame, "GESTOS", self.SIDEBAR_W//2, 116,
                          0.38, UI["text_dim"], 1)

        # Botones
        TOOL_MAP = {"BRUSH": TOOL_BRUSH, "FILL": TOOL_FILL, "ERASER": TOOL_ERASER}
        BTN_META = {
            "BRUSH":    ("PINCEL",    "B",  UI["active_brush"],  "✏"),
            "FILL":     ("RELLENO",   "K",  UI["active_fill"],   "🪣"),
            "ERASER":   ("BORRADOR",  "E",  UI["active_eraser"], "⚪"),
            "COLOR_PICKER": ("COLORES","C",  UI["neon_cyan"],     "🎨"),
            "UNDO":     ("DESHACER",  "Z",  UI["neon_yellow"],   "↩"),
            "REDO":     ("REHACER",   "Y",  UI["neon_yellow"],   "↪"),
            "CLEAR":    ("LIMPIAR",   "C",  UI["neon_pink"],     "🗑"),
            "SAVE":     ("GUARDAR",   "S",  UI["neon_green"],    "💾"),
            "OPEN_IMG": ("ABRIR IMG", "O",  UI["neon_purple"],   "🖼"),
            "FREE_MODE":("MODO LIBRE","3",  UI["mode_free"],     "🖱"),
        }
        ASCII_ICONS = {
            "BRUSH":"[ ]","FILL":"[F]","ERASER":"[X]","COLOR_PICKER":"[C]",
            "UNDO":"<--","REDO":"-->","CLEAR":"CLR","SAVE":"SAV",
            "OPEN_IMG":"IMG","FREE_MODE":"FREE",
        }

        # Linea separadora
        sep_y = self.buttons["ERASER"][3] + 8
        cv2.line(frame, (8, sep_y), (self.SIDEBAR_W-8, sep_y), UI["border_dim"], 1)

        for name, (x1, y1, x2, y2) in self.buttons.items():
            if name not in BTN_META: continue
            label, key, accent, icon = BTN_META[name]
            is_hov    = (self._hover_btn == name)
            is_active = TOOL_MAP.get(name) == self.active_tool
            if name == "FREE_MODE": is_active = is_free

            if is_active:
                bg = tuple(int(c*0.25) for c in accent)
            elif is_hov:
                bg = UI["bg_panel2"]
            else:
                bg = UI["bg_panel"]

            draw_rounded_rect(frame, x1, y1, x2, y2, 6, bg, -1)

            border_c = accent if is_active else (UI["border_bright"] if is_hov else UI["border_dim"])
            bth      = 2 if (is_active or is_hov) else 1
            draw_rounded_rect(frame, x1, y1, x2, y2, 6, border_c, bth)

            if is_active:
                for expand in [4, 3, 2]:
                    ov = frame.copy()
                    draw_rounded_rect(ov, x1-expand, y1-expand,
                                      x2+expand, y2+expand, 8,
                                      accent, 1)
                    cv2.addWeighted(ov, 0.12, frame, 0.88, 0, frame)

            icon_text = ASCII_ICONS[name]
            put_text_centered(frame, icon_text, x1+22, (y1+y2)//2,
                              0.48, accent if (is_active or is_hov) else UI["text_dim"], 1)

            txt_col = accent if (is_active or is_hov) else UI["text_white"]
            cv2.putText(frame, label, (x1+44, (y1+y2)//2+6),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.42, txt_col, 1, cv2.LINE_AA)

            if is_hov and self._hover_btn_frames > 0:
                prog = int((x2-x1) * self._hover_btn_frames / self._hover_btn_thr)
                draw_rounded_rect(frame, x1, y2-5, x1+prog, y2, 2, accent, -1)

        # Info inferior
        info_y = self.buttons["FREE_MODE"][3] + 18
        items = []
        if not is_free:
            items = [
                (f"Grosor: {self.brush_size}px", UI["text_dim"]),
                (f"Undo: {len(self.undo_stack)-1}", UI["text_dim"]),
            ]
            if self.active_tool == TOOL_FILL:
                items.append((f"Tol: {self.fill_tolerance}", UI["neon_orange"]))
        items.append((f"FPS: {fps:.0f}", UI["neon_green"] if fps > 20 else UI["neon_pink"]))

        for i, (txt, col) in enumerate(items):
            cv2.putText(frame, txt, (8, info_y + i*18),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.38, col, 1, cv2.LINE_AA)

        # Header superior
        header_h = 48
        ov_hdr = frame.copy()
        cv2.rectangle(ov_hdr, (self.SIDEBAR_W, 0), (W, header_h), UI["bg_panel"], -1)
        cv2.addWeighted(ov_hdr, 0.90, frame, 0.10, 0, frame)

        draw_gradient_bar(frame, self.SIDEBAR_W, header_h-2, W, header_h,
                          UI["neon_cyan"], UI["neon_pink"])

        mode_labels = {
            APP_MODE_PAINT: ("PINTURA LIBRE",  UI["mode_paint"]),
            APP_MODE_COLOR: ("COLOREAR",        UI["mode_color"]),
            APP_MODE_FREE:  ("MODO LIBRE",      UI["mode_free"]),
        }
        mode_txt, mode_col = mode_labels[self.app_mode]
        badge_x = self.SIDEBAR_W + 16
        (btw, bth), _ = cv2.getTextSize(mode_txt, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 2)
        draw_rounded_rect(frame, badge_x-8, 6, badge_x+btw+8, header_h-6,
                          6, tuple(int(c*0.2) for c in mode_col), -1)
        draw_rounded_rect(frame, badge_x-8, 6, badge_x+btw+8, header_h-6,
                          6, mode_col, 2)
        cv2.putText(frame, mode_txt, (badge_x, header_h//2+8),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, mode_col, 2, cv2.LINE_AA)

        if not is_free:
            tool_txt  = {"BRUSH":"Pincel","FILL":"Relleno","ERASER":"Borrador"}[self.active_tool]
            tool_col  = {"BRUSH": UI["active_brush"],
                         "FILL":  UI["active_fill"],
                         "ERASER":UI["active_eraser"]}[self.active_tool]
            tbx = badge_x + btw + 28
            (ttw,_), _ = cv2.getTextSize(tool_txt, cv2.FONT_HERSHEY_SIMPLEX, 0.45, 1)
            draw_rounded_rect(frame, tbx-6, 8, tbx+ttw+6, header_h-8,
                              5, tuple(int(c*0.15) for c in tool_col), -1)
            draw_rounded_rect(frame, tbx-6, 8, tbx+ttw+6, header_h-8,
                              5, tool_col, 1)
            cv2.putText(frame, tool_txt, (tbx, header_h//2+7),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, tool_col, 1, cv2.LINE_AA)

        # Color actual
        if not is_free:
            cx_col = W - 180
            cv2.circle(frame, (cx_col, header_h//2),
                       18, self.current_color, -1)
            cv2.circle(frame, (cx_col, header_h//2),
                       18, UI["border_bright"], 2)
            cname = COLORS[self.color_index]["name"] \
                    if 0 <= self.color_index < len(COLORS) else "Custom"
            cv2.putText(frame, cname, (cx_col+24, header_h//2+6),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.42, UI["text_white"], 1, cv2.LINE_AA)

        # Gesto
        GESTURE_ICONS = {
            "DRAW":     "DIBUJANDO",
            "SELECT":   "SELECCIONAR",
            "ERASER":   "BORRADOR",
            "OPEN":     "PAUSADO",
            "PINCH":    "GROSOR",
            "THUMB_UP": "SIGUIENTE COLOR",
            "THUMB_DOWN":"COLOR ANTERIOR",
            "NONE":     "Sin mano",
            "THREE":    "3 DEDOS",
        }
        g_label = GESTURE_ICONS.get(gesture, gesture)
        g_col   = UI["neon_green"] if gesture == "DRAW" \
                  else UI["neon_yellow"] if gesture in ("SELECT","PINCH") \
                  else UI["neon_pink"] if gesture == "ERASER" \
                  else UI["text_dim"]
        (gtw,_), _ = cv2.getTextSize(g_label, cv2.FONT_HERSHEY_SIMPLEX, 0.44, 1)
        gx = W - gtw - 20
        cv2.putText(frame, "Gesto:", (gx-55, header_h//2+6),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.38, UI["text_dim"], 1, cv2.LINE_AA)
        cv2.putText(frame, g_label, (gx, header_h//2+6),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.44, g_col, 1, cv2.LINE_AA)

        # Panel modo libre
        if is_free:
            px, py = self.SIDEBAR_W + 16, header_h + 12
            pw, ph = 300, 200
            ov_f = frame.copy()
            draw_rounded_rect(ov_f, px, py, px+pw, py+ph, 10, UI["bg_panel"], -1)
            cv2.addWeighted(ov_f, 0.80, frame, 0.20, 0, frame)
            draw_rounded_rect(frame, px, py, px+pw, py+ph, 10, UI["mode_free"], 2)

            put_text_centered(frame, "MODO LIBRE", px+pw//2, py+22,
                              0.60, UI["mode_free"], 2)

            guide = [
                ("1 dedo",        "Mover cursor"),
                ("Pinch",         "Clic izquierdo"),
                ("Pinch + mover", "Arrastrar"),
                ("2 dedos",       "Clic derecho"),
                ("2 pinch rapido","Doble clic"),
            ]
            for j, (g, d) in enumerate(guide):
                yy = py + 48 + j * 26
                cv2.putText(frame, g, (px+10, yy),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.40, UI["neon_yellow"], 1, cv2.LINE_AA)
                cv2.putText(frame, "->", (px+138, yy),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.38, UI["text_dim"], 1, cv2.LINE_AA)
                cv2.putText(frame, d, (px+158, yy),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.40, (100,220,100), 1, cv2.LINE_AA)

            if self._mouse_action_t > 0:
                self._mouse_action_t -= 1
                ac = UI["neon_green"] if "CLIC" in self._mouse_action \
                     else UI["neon_orange"] if "DRAG" in self._mouse_action or "ARRASTR" in self._mouse_action \
                     else UI["text_dim"]
                put_text_centered(frame, self._mouse_action, px+pw//2, py+ph-14,
                                  0.55, ac, 2)
            sp = self.mouse_ctrl.screen_pos
            if sp:
                cv2.putText(frame, f"Pos: {sp[0]}, {sp[1]}",
                            (px+8, py+ph-14),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.36, UI["text_dim"], 1, cv2.LINE_AA)

        # Panel de gestos
        if not is_free:
            gx2 = W - 250
            gy2 = H - 200
            gw2 = 240
            gh2 = 190

            ov_g = frame.copy()
            draw_rounded_rect(ov_g, gx2, gy2, gx2+gw2, gy2+gh2, 10,
                               UI["bg_panel"], -1)
            cv2.addWeighted(ov_g, 0.82, frame, 0.18, 0, frame)
            draw_rounded_rect(frame, gx2, gy2, gx2+gw2, gy2+gh2, 10,
                               UI["neon_purple"], 1)

            put_text_centered(frame, "GESTOS", gx2+gw2//2, gy2+18,
                              0.50, UI["neon_purple"], 2)
            cv2.line(frame, (gx2+10, gy2+28), (gx2+gw2-10, gy2+28),
                     UI["border_dim"], 1)

            gesture_guide = [
                ("1 dedo",       "Dibujar"),
                ("2 dedos",      "Menu/Seleccionar"),
                ("Puno",         "Borrador"),
                ("Mano abierta", "Pausar"),
                ("Pinch",        "Grosor"),
                ("Pulgar arriba","Siguiente color"),
            ]
            for j, (gico, gdesc) in enumerate(gesture_guide):
                yy = gy2 + 46 + j*22
                cv2.putText(frame, gico, (gx2+8, yy),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.38,
                            UI["neon_cyan"], 1, cv2.LINE_AA)
                cv2.putText(frame, gdesc, (gx2+140, yy),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.38,
                            (100,220,100), 1, cv2.LINE_AA)

            keys_y = gy2 + gh2 - 18
            cv2.putText(frame, "H=HUD  F=Full  Q=Salir",
                        (gx2+8, keys_y),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.32, UI["text_dim"], 1, cv2.LINE_AA)

        # Notificacion
        if self._notif_timer > 0:
            self._notif_timer -= 1
            a  = min(1.0, self._notif_timer / 20)
            (nw, nh), _ = cv2.getTextSize(self._notif,
                                           cv2.FONT_HERSHEY_SIMPLEX, 0.7, 2)
            nx = W//2 - nw//2 - 20
            ny = H//2 - 26
            nxe= W//2 + nw//2 + 20
            nye= H//2 + 10

            ov_n = frame.copy()
            draw_rounded_rect(ov_n, nx, ny, nxe, nye, 10, UI["bg_dark"], -1)
            cv2.addWeighted(ov_n, 0.88*a, frame, 1-0.88*a, 0, frame)

            c = self._notif_color
            draw_rounded_rect(frame, nx, ny, nxe, nye, 10, c, 2)
            for ex in [6, 4, 2]:
                ov2 = frame.copy()
                draw_rounded_rect(ov2, nx-ex, ny-ex, nxe+ex, nye+ex, 12, c, 1)
                cv2.addWeighted(ov2, 0.08*a, frame, 1-0.08*a, 0, frame)

            cv2.putText(frame, self._notif,
                        (W//2 - nw//2, H//2 + 5),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, c, 2, cv2.LINE_AA)

        # Barra de tolerancia
        if self.active_tool == TOOL_FILL and not is_free:
            tx   = self.SIDEBAR_W + 20
            ty   = header_h + 8
            bw_t = 220
            bh_t = 20
            tmin = self.cfg["fill_tolerance_min"]
            tmax = self.cfg["fill_tolerance_max"]
            prog = int(bw_t*(self.fill_tolerance-tmin)/(tmax-tmin))

            cv2.putText(frame, f"Tolerancia relleno: {self.fill_tolerance}",
                        (tx, ty+13), cv2.FONT_HERSHEY_SIMPLEX, 0.42,
                        UI["neon_orange"], 1, cv2.LINE_AA)
            cv2.rectangle(frame, (tx, ty+18), (tx+bw_t, ty+18+bh_t),
                          UI["bg_panel2"], -1)
            draw_gradient_bar(frame, tx, ty+18, tx+prog, ty+18+bh_t,
                              UI["neon_orange"], UI["neon_yellow"])
            cv2.rectangle(frame, (tx, ty+18), (tx+bw_t, ty+18+bh_t),
                          UI["border_dim"], 1)
            cv2.putText(frame, "[ menos  ] mas",
                        (tx+bw_t+8, ty+30), cv2.FONT_HERSHEY_SIMPLEX,
                        0.34, UI["text_dim"], 1, cv2.LINE_AA)

        return frame

    def _draw_cursor(self, frame, pt, gesture):
        col = self.current_color if not self.eraser_mode else (200, 200, 200)
        r   = self.brush_size + 4

        self._trail.append((pt[0], pt[1], col))

        if self.active_tool == TOOL_FILL and gesture == "DRAW":
            cv2.rectangle(frame, (pt[0]-14, pt[1]-8),
                          (pt[0]+14, pt[1]+18), col, -1)
            cv2.rectangle(frame, (pt[0]-14, pt[1]-8),
                          (pt[0]+14, pt[1]+18), UI["neon_yellow"], 2)
            cv2.putText(frame, "F", (pt[0]-5, pt[1]+12),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55,
                        (20,20,20), 2, cv2.LINE_AA)
        elif self.active_tool == TOOL_ERASER or self.eraser_mode:
            er = self.brush_size * self.cfg["eraser_multiplier"] + 4
            ov = frame.copy()
            cv2.circle(ov, pt, er, (200,200,200), -1)
            cv2.addWeighted(ov, 0.15, frame, 0.85, 0, frame)
            cv2.circle(frame, pt, er, (200,200,200), 2, cv2.LINE_AA)
            cv2.line(frame, (pt[0]-er, pt[1]), (pt[0]+er, pt[1]),
                     (200,200,200), 1)
            cv2.line(frame, (pt[0], pt[1]-er), (pt[0], pt[1]+er),
                     (200,200,200), 1)
        elif gesture == "DRAW":
            draw_glow_circle(frame, pt[0], pt[1], r, col, 0.4)
            cv2.circle(frame, pt, 4, (255,255,255), -1)
        elif gesture == "SELECT":
            cv2.drawMarker(frame, pt, UI["neon_yellow"],
                           cv2.MARKER_CROSS, 26, 2, cv2.LINE_AA)
            cv2.circle(frame, pt, 14, UI["neon_yellow"], 1, cv2.LINE_AA)
        else:
            cv2.circle(frame, pt, 12, UI["text_dim"], 1, cv2.LINE_AA)
            cv2.circle(frame, pt, 3,  UI["text_dim"], -1)

    def _draw_free_cursor(self, output, info):
        idx  = info["index"]
        thumb= info["thumb"]
        dist = info["pinch_dist"]
        is_p = info["is_pinching"]
        is_d = info["is_dragging"]

        cv2.line(output, thumb, idx, UI["text_dim"], 1, cv2.LINE_AA)

        if is_d:
            draw_glow_circle(output, idx[0], idx[1], 16, UI["neon_orange"], 0.5)
            cv2.putText(output, "DRAG", (idx[0]+22, idx[1]-8),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, UI["neon_orange"], 2)
        elif is_p:
            draw_glow_circle(output, idx[0], idx[1], 14, UI["neon_green"], 0.6)
        else:
            cv2.circle(output, idx, 14, UI["mode_free"], 2, cv2.LINE_AA)
            cv2.circle(output, idx, 4,  UI["mode_free"], -1)

        # Barra de pinch - CORREGIDO: usar self.H en lugar de H
        bx, by = self.SIDEBAR_W + 20, self.H - 60
        bw     = 180
        thr    = self.cfg["pinch_threshold"]
        rel    = float(np.clip(dist/(thr*2), 0, 1))
        filled = int(bw*(1-rel))
        cv2.putText(output, "PINCH", (bx, by-4),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.40, UI["text_dim"], 1, cv2.LINE_AA)
        cv2.rectangle(output, (bx,by), (bx+bw,by+10), UI["bg_panel2"], -1)
        col_bar = UI["neon_green"] if is_p else UI["mode_free"]
        cv2.rectangle(output, (bx,by), (bx+filled,by+10), col_bar, -1)
        cv2.rectangle(output, (bx,by), (bx+bw,by+10), UI["border_dim"], 1)

    def run(self):
        cap = cv2.VideoCapture(self.cfg["camera_index"])
        cap.set(cv2.CAP_PROP_FRAME_WIDTH,  self.W)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.H)
        cap.set(cv2.CAP_PROP_FPS, 60)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

        if not cap.isOpened():
            print("[ERROR] No se pudo abrir la camara.")
            return

        win = "Magic Paint — Gestos de Mano v4.0"
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
            if not ret: print("[ERROR] Frame fallido."); break

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

            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            rgb.flags.writeable = False
            res = self.hands.process(rgb)
            rgb.flags.writeable = True

            _lm_draw = _smooth_d = _free_info = None

            if res.multi_hand_landmarks:
                for hand_lm in res.multi_hand_landmarks:
                    lm = hand_lm.landmark
                    ix = int(lm[8].x*self.W);  iy = int(lm[8].y*self.H)
                    tx = int(lm[4].x*self.W);  ty = int(lm[4].y*self.H)
                    pinch_d = math.dist((tx,ty),(ix,iy))

                    mn, mx = self.cfg["min_brush_size"], self.cfg["max_brush_size"]
                    self.brush_size = self._smooth_bs(
                        int(mn + float(np.clip((pinch_d-20)/200,0,1))*(mx-mn)))

                    raw_g   = self._detect_gesture(lm)
                    gesture = self._stable_gesture(raw_g)
                    smooth  = self._smooth_pt((ix, iy))

                    _lm_draw  = hand_lm
                    _smooth_d = smooth

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
                                self._notify("Borrador activado", UI["active_eraser"])
                        elif gesture == "OPEN":
                            self.drawing = False; self.prev_point = None

                        if gesture in ("SELECT","OPEN","PINCH"):
                            self._check_btn_hover(smooth, last_bg)
                            self.drawing = False; self.prev_point = None
                            self._fill_done = False

                        elif gesture == "DRAW":
                            self._hover_btn       = None
                            self._hover_btn_frames= 0

                            in_sidebar = smooth[0] < self.SIDEBAR_W
                            in_btn = any(x1<=smooth[0]<=x2 and y1<=smooth[1]<=y2
                                         for x1,y1,x2,y2 in self.buttons.values())
                            in_header  = smooth[1] < 48

                            blocked = in_sidebar or in_btn or in_header

                            if not blocked:
                                if self.active_tool == TOOL_FILL:
                                    if not self._fill_done:
                                        self._apply_fill(smooth)
                                        self._fill_done = True
                                    self.drawing = False; self.prev_point = None
                                elif self.active_tool == TOOL_ERASER or self.eraser_mode:
                                    if not self.drawing:
                                        self._push_undo(); self.drawing = True
                                    esize = self.brush_size * self.cfg["eraser_multiplier"]
                                    if self.app_mode == APP_MODE_COLOR and self.color_image_orig is not None:
                                        mask_e = np.zeros((self.H,self.W), dtype=np.uint8)
                                        cv2.circle(mask_e, smooth, esize, 255, -1)
                                        self.color_layer = np.where(
                                            np.stack([mask_e]*3,axis=-1)>0,
                                            self.color_image_orig, self.color_layer
                                        ).astype(np.uint8)
                                    else:
                                        self._stroke(smooth,(0,0,0),esize)
                                    self.prev_point = smooth
                                else:
                                    if not self.drawing:
                                        self._push_undo(); self.drawing = True
                                    self._stroke(smooth, self.current_color, self.brush_size)
                                    self.prev_point = smooth
                            else:
                                self.drawing = False; self.prev_point = None
                                self._fill_done = False
                        else:
                            self.drawing = False; self.prev_point = None
                            self._fill_done = False
            else:
                if self.app_mode == APP_MODE_FREE:
                    self.mouse_ctrl.handle_pinch(False, 0, 0)
                    self.mouse_ctrl.tick()
                self.drawing = False; self.prev_point = None
                self._fill_done = False
                self.smooth_points.clear(); self._gesture_buffer.clear()
                gesture = "NONE"

            if self.app_mode == APP_MODE_FREE:
                ov = frame.copy()
                cv2.rectangle(ov,(0,0),(self.W,self.H),(0,0,30),-1)
                output = cv2.addWeighted(ov, 0.10, frame, 0.90, 0)
            elif self.app_mode == APP_MODE_COLOR and self.color_layer is not None:
                output = cv2.addWeighted(self.color_layer, 0.88, frame, 0.12, 0)
            else:
                output = self._merge_canvas(frame)

            if self.app_mode != APP_MODE_COLOR:
                self._update_effects(output)

            if _lm_draw is not None and _smooth_d is not None:
                self.mp_draw.draw_landmarks(
                    output, _lm_draw, self.mp_hands.HAND_CONNECTIONS,
                    self.mp_draw_styles.DrawingSpec(
                        color=UI["neon_green"], thickness=2, circle_radius=4),
                    self.mp_draw_styles.DrawingSpec(
                        color=UI["neon_cyan"], thickness=2))

                if self.app_mode == APP_MODE_FREE and _free_info is not None:
                    self._draw_free_cursor(output, _free_info)
                else:
                    self._draw_cursor(output, _smooth_d, gesture)

            output = self._draw_ui(output, gesture, fps)
            cv2.imshow(win, output)

            key = cv2.waitKey(1) & 0xFF
            if key in (ord('q'), 27):
                self.mouse_ctrl.release_all(); break
            elif key == ord('1'):
                self.mouse_ctrl.release_all()
                self.app_mode = APP_MODE_PAINT
                self._notify("Modo: Pintura Libre", UI["mode_paint"])
            elif key == ord('2'):
                if self.color_layer is not None:
                    self.mouse_ctrl.release_all()
                    self.app_mode = APP_MODE_COLOR
                    self._notify("Modo: Colorear Imagen", UI["mode_color"])
                else:
                    self._notify("Carga una imagen primero (tecla O)", UI["neon_pink"])
            elif key == ord('3'):
                self._toggle_free_mode()
            elif key in (ord('o'),ord('O')):
                self.img_selector._load()
                path = self.img_selector.show(self.W, self.H)
                if path: self.load_color_image(path)
            elif key in (ord('b'),ord('B')):
                self.active_tool = TOOL_BRUSH;  self.eraser_mode = False
                self._notify("Herramienta: Pincel", UI["active_brush"])
            elif key in (ord('k'),ord('K')):
                self.active_tool = TOOL_FILL;   self.eraser_mode = False
                self._notify("Herramienta: Relleno", UI["active_fill"])
            elif key in (ord('e'),ord('E')):
                self.active_tool = TOOL_ERASER; self.eraser_mode = True
                self._notify("Herramienta: Borrador", UI["active_eraser"])
            elif key in (ord('c'),ord('C')):
                self._push_undo()
                if self.app_mode == APP_MODE_COLOR and self.color_image_orig is not None:
                    self.color_layer = self.color_image_orig.copy()
                    self._notify("Imagen restaurada", UI["neon_orange"])
                else:
                    self.canvas[:] = 0
                    self._notify("Canvas limpiado", UI["neon_pink"])
            elif key in (ord('r'),ord('R')): self.reset_color_image()
            elif key in (ord('h'),ord('H')): self.show_hud = not self.show_hud
            elif key in (ord('f'),ord('F')):
                self.fullscreen = not self.fullscreen
                cv2.setWindowProperty(win, cv2.WND_PROP_FULLSCREEN,
                    cv2.WINDOW_FULLSCREEN if self.fullscreen else cv2.WINDOW_NORMAL)
            elif key in (ord('s'),ord('S')): self.save_drawing(last_bg)
            elif key == 26: self.undo()
            elif key == 25: self.redo()
            elif key in (ord('+'),ord('=')): self.brush_size = min(self.brush_size+2, self.cfg["max_brush_size"])
            elif key == ord('-'): self.brush_size = max(self.brush_size-2, self.cfg["min_brush_size"])
            elif key == ord(']'):
                self.fill_tolerance = min(self.fill_tolerance+4, self.cfg["fill_tolerance_max"])
                self._notify(f"Tolerancia: {self.fill_tolerance}", UI["neon_orange"])
            elif key == ord('['):
                self.fill_tolerance = max(self.fill_tolerance-4, self.cfg["fill_tolerance_min"])
                self._notify(f"Tolerancia: {self.fill_tolerance}", UI["neon_orange"])

        cap.release()
        self.hands.close()
        cv2.destroyAllWindows()
        print(f"\n[OK] Obras guardadas en ./{self.cfg['save_dir']}/")


def create_sample_images(out_dir):
    os.makedirs(out_dir, exist_ok=True)
    W, H = 800, 600

    img = np.full((H,W,3), 255, dtype=np.uint8)
    cx, cy = W//2, H//2
    for r in range(40,260,42): cv2.circle(img,(cx,cy),r,(0,0,0),2)
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
    print("   M A G I C   P A I N T  v4.0  —  Feria de Tecnologia")
    print("=" * 68)
    print("  Modos:   [1] Pintura libre   [2] Colorear   [3] Modo Libre")
    print("  Herram:  [B] Pincel  [K] Fill  [E] Borrador")
    print("  Imagen:  [O] Abrir  [R] Restaurar  [S] Guardar")
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
        create_sample_images(CONFIG["images_dir"]); return

    total = sum(len(glob.glob(os.path.join(CONFIG["images_dir"], ext)))
                for ext in CONFIG["image_extensions"])
    if total == 0:
        print(f"[INFO] Generando imagenes de ejemplo en '{CONFIG['images_dir']}'...")
        create_sample_images(CONFIG["images_dir"])

    VirtualPainter().run()

if __name__ == "__main__":
    main()