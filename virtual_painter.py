"""
╔══════════════════════════════════════════════════════════════════════╗
║        ADVANCED VIRTUAL PAINTER CON GESTOS DE MANO  v3.1           ║
║         Python + OpenCV + MediaPipe + Fill Tool + Mouse Control     ║
╠══════════════════════════════════════════════════════════════════════╣
║  MODOS DISPONIBLES:                                                  ║
║    [1] Modo Pintura Libre  — dibuja sobre la camara en vivo         ║
║    [2] Modo Colorear       — colorea imagenes de lineas             ║
║    [3] Modo Libre          — controla el mouse del sistema          ║
╠══════════════════════════════════════════════════════════════════════╣
║  GESTOS EN MODO LIBRE (control del mouse):                          ║
║    Solo indice extendido   → Mover cursor                           ║
║    Pinch (pulgar+indice)   → Clic izquierdo / Iniciar drag          ║
║    Pinch mantenido+mover   → Arrastrar (drag)                       ║
║    Indice + medio          → Clic derecho                           ║
║    Indice + medio + anular → Doble clic                             ║
║    Mano abierta            → Soltar / Pausar                        ║
╠══════════════════════════════════════════════════════════════════════╣
║  GESTOS EN MODOS PINTURA/COLOREAR:                                  ║
║    Solo indice        → Dibujar / Rellenar                          ║
║    Indice + medio     → Pausar / Seleccion de UI                    ║
║    Puno cerrado       → Borrador                                    ║
║    Mano abierta       → Mover sin dibujar                          ║
║    Pinch              → Ajustar grosor                              ║
║    Pulgar arriba      → Siguiente color                             ║
║    Pulgar abajo       → Color anterior                              ║
╠══════════════════════════════════════════════════════════════════════╣
║  TECLAS:                                                             ║
║    1 / 2 / 3  → Cambiar modo (pintura / colorear / libre)           ║
║    O          → Abrir imagen para colorear                          ║
║    B / K / E  → Modo pincel / Relleno / Borrador                    ║
║    Ctrl+Z/Y   → Undo / Redo                                         ║
║    S          → Guardar                                             ║
║    C          → Limpiar / Restaurar                                 ║
║    R          → Restaurar imagen original                           ║
║    [ / ]      → Tolerancia de relleno -/+                          ║
║    + / -      → Grosor del pincel                                   ║
║    H          → Mostrar/Ocultar HUD                                 ║
║    F          → Pantalla completa                                   ║
║    Q / ESC    → Salir                                               ║
╚══════════════════════════════════════════════════════════════════════╝
"""

import cv2
import mediapipe as mp
import numpy as np
import os
import sys
import time
import math
import glob
from collections import deque
from datetime import datetime

# Importar pyautogui para control del mouse (Windows)
try:
    import pyautogui
    pyautogui.FAILSAFE = False   # Desactivar failsafe para uso normal
    pyautogui.PAUSE    = 0.0    # Sin pausa entre acciones para maxima fluidez
    PYAUTOGUI_AVAILABLE = True
    print("[OK] pyautogui disponible — Modo Libre activado")
except ImportError:
    PYAUTOGUI_AVAILABLE = False
    print("[AVISO] pyautogui no encontrado. Instala con: pip install pyautogui")
    print("        El Modo Libre estara desactivado hasta instalarlo.")

# ══════════════════════════════════════════════════════
#  CONFIGURACION GLOBAL
# ══════════════════════════════════════════════════════
CONFIG = {
    # Camara
    "camera_index": 0,
    "width": 1280,
    "height": 720,
    "flip_horizontal": True,

    # Pincel
    "default_brush_size": 8,
    "min_brush_size": 2,
    "max_brush_size": 60,
    "eraser_multiplier": 2,
    "canvas_opacity": 0.78,

    # Flood Fill
    "fill_tolerance": 28,
    "fill_tolerance_min": 4,
    "fill_tolerance_max": 80,

    # Suavizado
    "smoothing_points": 5,
    "gesture_smoothing": 8,

    # UI
    "palette_height": 88,
    "ui_margin": 10,
    "show_hud": True,
    "hud_alpha": 0.82,

    # Undo/Redo
    "max_undo_steps": 50,

    # Guardar
    "save_dir": "paintings",
    "save_format": "png",

    # MediaPipe
    "detection_confidence": 0.75,
    "tracking_confidence": 0.75,

    # Imagenes para colorear
    "images_dir": "images_to_color",
    "image_extensions": ["*.png", "*.jpg", "*.jpeg", "*.bmp"],

    # Modo Libre — control del mouse
    "mouse_smoothing": 7,        # Suavizado del cursor (mayor = mas suave pero mas lento)
    "pinch_threshold": 45,       # Distancia en px para considerar pinch
    "pinch_release_threshold": 60,
    "drag_min_move": 8,          # Pixeles minimos para iniciar drag
    "click_cooldown_frames": 18, # Frames de cooldown entre clics
    "right_click_cooldown": 22,
    "double_click_cooldown": 25,
    # Zona activa de la camara para el mouse (evita bordes con deteccion mala)
    "mouse_zone_margin": 0.08,   # 8% de margen en cada borde
}

# ══════════════════════════════════════════════════════
#  PALETA DE COLORES (BGR)
# ══════════════════════════════════════════════════════
COLORS = [
    {"name": "Negro",       "bgr": (0,   0,   0  )},
    {"name": "Blanco",      "bgr": (255, 255, 255)},
    {"name": "Rojo",        "bgr": (0,   0,   220)},
    {"name": "Naranja",     "bgr": (0,   120, 255)},
    {"name": "Amarillo",    "bgr": (0,   220, 220)},
    {"name": "Verde",       "bgr": (0,   200, 60 )},
    {"name": "Verde Oliva", "bgr": (0,   160, 80 )},
    {"name": "Cian",        "bgr": (220, 200, 0  )},
    {"name": "Azul",        "bgr": (230, 80,  0  )},
    {"name": "Celeste",     "bgr": (240, 160, 80 )},
    {"name": "Magenta",     "bgr": (200, 0,   200)},
    {"name": "Morado",      "bgr": (160, 0,   120)},
    {"name": "Rosa",        "bgr": (160, 100, 240)},
    {"name": "Marron",      "bgr": (30,  80,  140)},
    {"name": "Gris",        "bgr": (130, 130, 130)},
]

# Modos de la aplicacion
APP_MODE_PAINT  = "PAINT"
APP_MODE_COLOR  = "COLOR"
APP_MODE_FREE   = "FREE"    # ← NUEVO: control del mouse

# Herramientas
TOOL_BRUSH  = "BRUSH"
TOOL_FILL   = "FILL"
TOOL_ERASER = "ERASER"

# Landmarks MediaPipe
TIP   = [4, 8, 12, 16, 20]
PIP   = [3, 6, 10, 14, 18]
WRIST = 0


# ══════════════════════════════════════════════════════
#  FLOOD FILL
# ══════════════════════════════════════════════════════
def flood_fill(image, seed_pt, fill_color, tolerance):
    x, y = seed_pt
    h, w = image.shape[:2]
    if not (0 <= x < w and 0 <= y < h):
        return image
    result = image.copy()
    mask   = np.zeros((h + 2, w + 2), dtype=np.uint8)
    lo     = (tolerance, tolerance, tolerance)
    hi     = (tolerance, tolerance, tolerance)
    flags  = 8 | cv2.FLOODFILL_FIXED_RANGE
    cv2.floodFill(result, mask, (x, y), fill_color, lo, hi, flags)
    return result


def flood_fill_smooth(image, seed_pt, fill_color, tolerance):
    filled     = flood_fill(image, seed_pt, fill_color, tolerance)
    diff       = cv2.absdiff(image, filled)
    diff_gray  = cv2.cvtColor(diff, cv2.COLOR_BGR2GRAY)
    _, changed = cv2.threshold(diff_gray, 1, 255, cv2.THRESH_BINARY)
    kernel     = np.ones((3, 3), np.uint8)
    border     = cv2.dilate(changed, kernel, iterations=2) - changed
    blurred    = cv2.GaussianBlur(filled, (3, 3), 0)
    border3    = cv2.cvtColor(border, cv2.COLOR_GRAY2BGR)
    result     = np.where(border3 > 0, blurred, filled)
    return result.astype(np.uint8)


# ══════════════════════════════════════════════════════
#  CONTROLADOR DE MOUSE (Modo Libre)
# ══════════════════════════════════════════════════════
class MouseController:
    """
    Traduce posicion de la mano en movimientos y clics del mouse de Windows.
    Usa suavizado exponencial para un movimiento fluido.
    """

    def __init__(self, cfg, cam_w, cam_h):
        self.cfg    = cfg
        self.cam_w  = cam_w
        self.cam_h  = cam_h

        # Resolucion de pantalla
        if PYAUTOGUI_AVAILABLE:
            self.scr_w, self.scr_h = pyautogui.size()
        else:
            self.scr_w, self.scr_h = 1920, 1080

        # Suavizado exponencial del cursor
        self._sx = None   # posicion suavizada x
        self._sy = None   # posicion suavizada y
        self._alpha = 1.0 / max(cfg["mouse_smoothing"], 1)

        # Estado del mouse
        self.is_dragging    = False
        self.drag_start_pos = None
        self.mouse_down     = False

        # Cooldowns (en frames)
        self._click_cd       = 0
        self._rclick_cd      = 0
        self._dclick_cd      = 0

        # Estado del pinch previo
        self._was_pinching   = False
        self._pinch_frames   = 0   # frames consecutivos en pinch
        self._pinch_drag_thr = 6   # frames de pinch para activar drag

        # Historial de posiciones para detectar movimiento en drag
        self._pos_history    = deque(maxlen=5)

        # Para doble clic: detectar dos pinch rapidos
        self._last_pinch_time = 0.0
        self._double_click_window = 0.4  # segundos entre dos pinch para doble clic

    def tick(self):
        """Decrementar cooldowns cada frame."""
        if self._click_cd  > 0: self._click_cd  -= 1
        if self._rclick_cd > 0: self._rclick_cd -= 1
        if self._dclick_cd > 0: self._dclick_cd -= 1

    def cam_to_screen(self, cx, cy):
        """Convierte coordenadas de camara a coordenadas de pantalla con zona activa."""
        mg = self.cfg["mouse_zone_margin"]
        # Normalizar dentro de la zona activa (recortar margenes)
        nx = np.clip((cx / self.cam_w - mg) / (1.0 - 2*mg), 0.0, 1.0)
        ny = np.clip((cy / self.cam_h - mg) / (1.0 - 2*mg), 0.0, 1.0)
        sx = int(nx * self.scr_w)
        sy = int(ny * self.scr_h)
        return sx, sy

    def smooth_move(self, cx, cy):
        """Suaviza y mueve el cursor del sistema."""
        if not PYAUTOGUI_AVAILABLE:
            return
        sx, sy = self.cam_to_screen(cx, cy)

        if self._sx is None:
            self._sx, self._sy = float(sx), float(sy)
        else:
            a = self._alpha
            self._sx = a * sx + (1 - a) * self._sx
            self._sy = a * sy + (1 - a) * self._sy

        self._pos_history.append((int(self._sx), int(self._sy)))

        if self.is_dragging:
            pyautogui.dragTo(int(self._sx), int(self._sy), button='left', _pause=False)
        else:
            pyautogui.moveTo(int(self._sx), int(self._sy), _pause=False)

    def handle_pinch(self, is_pinching, cx, cy):
        """
        Gestiona clic izquierdo, drag y doble clic basado en pinch.
        Retorna string de accion para mostrar en HUD.
        """
        if not PYAUTOGUI_AVAILABLE:
            return ""

        action = ""
        now = time.time()

        if is_pinching:
            self._pinch_frames += 1

            if not self._was_pinching:
                # Inicio de pinch — verificar doble clic
                if (self._click_cd == 0 and self._dclick_cd == 0 and
                        now - self._last_pinch_time < self._double_click_window):
                    pyautogui.doubleClick(_pause=False)
                    self._dclick_cd = self.cfg["double_click_cooldown"]
                    self._click_cd  = self.cfg["click_cooldown_frames"]
                    self.is_dragging = False
                    action = "DOBLE CLIC"
                elif self._click_cd == 0:
                    # Primer pinch: hacer clic y preparar posible drag
                    pyautogui.mouseDown(button='left', _pause=False)
                    self.mouse_down     = True
                    self.drag_start_pos = (int(self._sx or cx), int(self._sy or cy))
                    action = "CLIC IZQUIERDO"
                self._last_pinch_time = now

            else:
                # Pinch continuo — verificar si hay suficiente movimiento para drag
                if (self.mouse_down and not self.is_dragging and
                        self._pinch_frames >= self._pinch_drag_thr and
                        self.drag_start_pos is not None):
                    if self._sx is not None:
                        dx = abs(self._sx - self.drag_start_pos[0])
                        dy = abs(self._sy - self.drag_start_pos[1])
                        if dx + dy > self.cfg["drag_min_move"]:
                            self.is_dragging = True
                            action = "ARRASTRANDO..."

                if self.is_dragging:
                    action = "ARRASTRANDO..."

        else:
            # Fin de pinch
            if self._was_pinching:
                if self.is_dragging:
                    pyautogui.mouseUp(button='left', _pause=False)
                    self.is_dragging = False
                    self.mouse_down  = False
                    action = "SOLTADO"
                elif self.mouse_down:
                    pyautogui.mouseUp(button='left', _pause=False)
                    self.mouse_down = False
                    self._click_cd  = self.cfg["click_cooldown_frames"]
            self._pinch_frames = 0

        self._was_pinching = is_pinching
        return action

    def right_click(self):
        if not PYAUTOGUI_AVAILABLE or self._rclick_cd > 0:
            return ""
        # Soltar cualquier drag activo antes
        if self.is_dragging or self.mouse_down:
            pyautogui.mouseUp(button='left', _pause=False)
            self.is_dragging = False
            self.mouse_down  = False
        pyautogui.click(button='right', _pause=False)
        self._rclick_cd = self.cfg["right_click_cooldown"]
        return "CLIC DERECHO"

    def release_all(self):
        """Libera cualquier boton presionado (seguridad al salir del modo)."""
        if not PYAUTOGUI_AVAILABLE:
            return
        if self.mouse_down or self.is_dragging:
            try:
                pyautogui.mouseUp(button='left', _pause=False)
            except Exception:
                pass
        self.is_dragging    = False
        self.mouse_down     = False
        self._was_pinching  = False
        self._pinch_frames  = 0
        self._sx = None
        self._sy = None

    @property
    def screen_pos(self):
        if self._sx is not None:
            return (int(self._sx), int(self._sy))
        return None


# ══════════════════════════════════════════════════════
#  SELECTOR DE IMAGENES
# ══════════════════════════════════════════════════════
class ImageSelector:
    THUMB_W   = 200
    THUMB_H   = 160
    COLS      = 5
    BG_COLOR  = (28, 28, 35)
    SEL_COLOR = (80, 200, 120)

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
                th = np.full((self.THUMB_H, self.THUMB_W, 3), 80, dtype=np.uint8)
                cv2.putText(th, "?", (80, 90), cv2.FONT_HERSHEY_SIMPLEX, 2, (200,200,200), 3)
            self.thumbnails.append(th)

    def _build_grid(self, W, H):
        canvas = np.full((H, W, 3), self.BG_COLOR, dtype=np.uint8)
        mg, pad = 18, 10
        tw, th  = self.THUMB_W, self.THUMB_H
        cv2.putText(canvas, "SELECCIONA UNA IMAGEN PARA COLOREAR",
                    (mg, 42), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (200,220,255), 2, cv2.LINE_AA)
        cv2.putText(canvas, "Flechas/WASD para navegar  |  ENTER para seleccionar  |  ESC para cancelar",
                    (mg, 70), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (140,140,160), 1, cv2.LINE_AA)
        start_y = 90
        for i, (thumb, path) in enumerate(zip(self.thumbnails, self.image_paths)):
            row = i // self.COLS
            col = i % self.COLS
            x   = mg + col * (tw + pad)
            y   = start_y + row * (th + pad + 22)
            if y + th + 22 > H:
                break
            if i == self.selected:
                cv2.rectangle(canvas, (x-4, y-4), (x+tw+4, y+th+4), self.SEL_COLOR, 3)
                ov = canvas.copy()
                cv2.rectangle(ov, (x, y), (x+tw, y+th), (80,200,120), -1)
                canvas = cv2.addWeighted(ov, 0.15, canvas, 0.85, 0)
            else:
                cv2.rectangle(canvas, (x-2, y-2), (x+tw+2, y+th+2), (60,60,70), 1)
            canvas[y:y+th, x:x+tw] = thumb
            fname = os.path.basename(path)[:22]
            cv2.putText(canvas, fname, (x, y+th+16),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.38, (180,180,200), 1, cv2.LINE_AA)
        cv2.putText(canvas,
                    f"[R] Recargar  |  {len(self.image_paths)} imagen(es) en '{self.images_dir}'",
                    (mg, H-14), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (100,100,120), 1, cv2.LINE_AA)
        return canvas

    def show(self, W=1280, H=720):
        win = "Seleccionar Imagen"
        cv2.namedWindow(win, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(win, W, H)
        while True:
            cv2.imshow(win, self._build_grid(W, H))
            key = cv2.waitKey(50) & 0xFF
            n   = len(self.image_paths)
            if n == 0:
                if key in (ord('r'), ord('R')): self._load()
                elif key == 27:
                    cv2.destroyWindow(win); return None
                continue
            if key == 27:
                cv2.destroyWindow(win); return None
            elif key in (13, 32):
                cv2.destroyWindow(win); return self.image_paths[self.selected]
            elif key in (81, ord('a')): self.selected = (self.selected - 1) % n
            elif key in (83, ord('d')): self.selected = (self.selected + 1) % n
            elif key in (82, ord('w')): self.selected = max(0, self.selected - self.COLS)
            elif key in (84, ord('s')): self.selected = min(n-1, self.selected + self.COLS)
            elif key in (ord('r'), ord('R')): self._load()


# ══════════════════════════════════════════════════════
#  SELECTOR DE COLORES
# ══════════════════════════════════════════════════════
class ColorPicker:
    COLS = 8
    SWATCH_W = 70
    SWATCH_H = 50
    BG_COLOR = (28, 28, 35)
    SEL_COLOR = (80, 200, 120)

    EXTENDED_COLORS = [
        {"name": "Negro",           "bgr": (1, 1, 1)},
        {"name": "Gris Oscuro",     "bgr": (50, 50, 50)},
        {"name": "Gris",            "bgr": (128, 128, 128)},
        {"name": "Gris Claro",      "bgr": (180, 180, 180)},
        {"name": "Blanco",          "bgr": (255, 255, 255)},
        {"name": "Rojo Oscuro",     "bgr": (0, 0, 100)},
        {"name": "Rojo",            "bgr": (0, 0, 220)},
        {"name": "Rojo Brillante",  "bgr": (0, 0, 255)},
        {"name": "Naranja Oscuro",  "bgr": (0, 60, 160)},
        {"name": "Naranja",         "bgr": (0, 120, 255)},
        {"name": "Amarillo Oscuro", "bgr": (0, 180, 200)},
        {"name": "Amarillo",        "bgr": (0, 220, 220)},
        {"name": "Amarillo Brill",  "bgr": (0, 255, 255)},
        {"name": "Lima",            "bgr": (80, 255, 80)},
        {"name": "Verde Lima",      "bgr": (120, 255, 0)},
        {"name": "Verde",           "bgr": (0, 200, 60)},
        {"name": "Verde Oscuro",    "bgr": (0, 100, 40)},
        {"name": "Verde Bosque",    "bgr": (0, 130, 60)},
        {"name": "Verde Oliva",     "bgr": (0, 160, 80)},
        {"name": "Cian Oscuro",     "bgr": (150, 180, 0)},
        {"name": "Cian",            "bgr": (220, 200, 0)},
        {"name": "Cian Brillante",  "bgr": (255, 255, 0)},
        {"name": "Azul Cielo",      "bgr": (230, 150, 0)},
        {"name": "Azul",            "bgr": (230, 80, 0)},
        {"name": "Azul Real",       "bgr": (200, 50, 0)},
        {"name": "Azul Marino",     "bgr": (130, 30, 30)},
        {"name": "Azul Oscuro",     "bgr": (100, 20, 20)},
        {"name": "Violeta",         "bgr": (100, 0, 100)},
        {"name": "Morado",          "bgr": (160, 0, 120)},
        {"name": "Purpura",         "bgr": (180, 50, 150)},
        {"name": "Magenta",         "bgr": (200, 0, 200)},
        {"name": "Rosa",            "bgr": (160, 100, 240)},
        {"name": "Rosa Oscuro",     "bgr": (100, 50, 120)},
        {"name": "Rosa Brillante",  "bgr": (180, 150, 220)},
        {"name": "Salmon",          "bgr": (100, 130, 180)},
        {"name": "Coral",           "bgr": (80, 127, 180)},
        {"name": "Marron Oscuro",   "bgr": (20, 50, 90)},
        {"name": "Marron",          "bgr": (30, 80, 140)},
        {"name": "Marron Claro",    "bgr": (60, 120, 160)},
        {"name": "Beige",           "bgr": (130, 180, 200)},
        {"name": "Piel Muy Clara",  "bgr": (180, 200, 220)},
        {"name": "Piel Clara",      "bgr": (140, 180, 210)},
        {"name": "Piel Clara Med.", "bgr": (130, 160, 190)},
        {"name": "Piel Media",      "bgr": (110, 140, 170)},
        {"name": "Piel Morena",     "bgr": (80, 110, 140)},
        {"name": "Piel Oscura",     "bgr": (50, 70, 100)},
        {"name": "Piel Muy Osc.",   "bgr": (30, 50, 70)},
        {"name": "Cafe",            "bgr": (25, 40, 65)},
    ]

    def __init__(self):
        self.colors   = self.EXTENDED_COLORS
        self.selected = 0

    def _build_grid(self, W, H):
        canvas = np.full((H, W, 3), self.BG_COLOR, dtype=np.uint8)
        mg = 20
        n  = len(self.colors)
        cv2.putText(canvas, "SELECCIONA UN COLOR",
                    (mg, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (200,220,255), 2, cv2.LINE_AA)
        cv2.putText(canvas, "Flechas/WASD para navegar  |  ENTER para seleccionar  |  ESC para cancelar",
                    (mg, 70), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (140,140,160), 1, cv2.LINE_AA)
        start_y = 100
        for i, c in enumerate(self.colors):
            row = i // self.COLS
            col = i % self.COLS
            x   = mg + col * (self.SWATCH_W + 8)
            y   = start_y + row * (self.SWATCH_H + 25)
            if y + self.SWATCH_H > H - 50: break
            if i == self.selected:
                cv2.rectangle(canvas, (x-4, y-4), (x+self.SWATCH_W+4, y+self.SWATCH_H+4), self.SEL_COLOR, 3)
            cv2.rectangle(canvas, (x, y), (x+self.SWATCH_W, y+self.SWATCH_H), c["bgr"], -1)
            cv2.rectangle(canvas, (x, y), (x+self.SWATCH_W, y+self.SWATCH_H), (80,80,90), 1)
            cv2.putText(canvas, c["name"], (x, y+self.SWATCH_H+18),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.35, (180,180,200), 1, cv2.LINE_AA)
        cv2.putText(canvas, f"{n} colores disponibles",
                    (mg, H-20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (100,100,120), 1, cv2.LINE_AA)
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


# ══════════════════════════════════════════════════════
#  CLASE PRINCIPAL: VirtualPainter v3.1
# ══════════════════════════════════════════════════════
class VirtualPainter:

    def __init__(self):
        self.cfg = CONFIG
        self.W   = self.cfg["width"]
        self.H   = self.cfg["height"]

        self.app_mode    = APP_MODE_PAINT
        self.active_tool = TOOL_BRUSH

        self.canvas = np.zeros((self.H, self.W, 3), dtype=np.uint8)

        self.color_image_path = None
        self.color_image_orig = None
        self.color_layer      = None
        self.fill_tolerance   = self.cfg["fill_tolerance"]

        self.drawing       = False
        self.prev_point    = None
        self.brush_size    = self.cfg["default_brush_size"]
        self.eraser_mode   = False
        self.color_index   = 0
        self.current_color = COLORS[0]["bgr"]
        self.show_hud      = self.cfg["show_hud"]
        self.fullscreen    = False

        self.smooth_points = deque(maxlen=self.cfg["smoothing_points"])
        self.smooth_brush  = deque(maxlen=10)

        self.undo_stack = deque(maxlen=self.cfg["max_undo_steps"])
        self.redo_stack = deque(maxlen=self.cfg["max_undo_steps"])
        self._push_undo()

        self._gesture_buffer      = deque(maxlen=self.cfg["gesture_smoothing"])
        self._last_stable_gesture = "NONE"
        self._fill_done           = False

        self._hover_color_idx = -1
        self._hover_frames    = 0
        self._hover_threshold = 18

        self._hover_btn        = None
        self._hover_btn_frames = 0
        self._hover_btn_thr    = 20

        self._notif       = ""
        self._notif_timer = 0

        self._fps_buf = deque(maxlen=30)
        self._last_t  = time.time()

        # Controlador de mouse para Modo Libre
        self.mouse_ctrl   = MouseController(self.cfg, self.W, self.H)
        self._mouse_action = ""          # accion actual para mostrar en HUD
        self._mouse_action_timer = 0

        # MediaPipe
        self.mp_hands       = mp.solutions.hands
        self.hands          = self.mp_hands.Hands(
            static_image_mode=False,
            max_num_hands=1,
            min_detection_confidence=self.cfg["detection_confidence"],
            min_tracking_confidence=self.cfg["tracking_confidence"],
        )
        self.mp_draw        = mp.solutions.drawing_utils
        self.mp_draw_styles = mp.solutions.drawing_styles

        os.makedirs(self.cfg["images_dir"], exist_ok=True)
        os.makedirs(self.cfg["save_dir"],   exist_ok=True)

        self.img_selector = ImageSelector(
            self.cfg["images_dir"], self.cfg["image_extensions"])

        self._build_ui()

    # ──────────────────────────────────────────────
    def _notify(self, msg, dur=80):
        self._notif       = msg
        self._notif_timer = dur

    def _set_mouse_action(self, action, dur=30):
        if action:
            self._mouse_action       = action
            self._mouse_action_timer = dur

    def _get_layer(self):
        if self.app_mode == APP_MODE_COLOR and self.color_layer is not None:
            return self.color_layer
        return self.canvas

    def _set_layer(self, data):
        if self.app_mode == APP_MODE_COLOR and self.color_layer is not None:
            self.color_layer = data
        else:
            self.canvas = data

    def _push_undo(self):
        self.undo_stack.append(self._get_layer().copy())
        self.redo_stack.clear()

    def undo(self):
        if len(self.undo_stack) > 1:
            self.redo_stack.append(self.undo_stack.pop())
            self._set_layer(self.undo_stack[-1].copy())
            self._notify("Undo")

    def redo(self):
        if self.redo_stack:
            s = self.redo_stack.pop()
            self.undo_stack.append(s)
            self._set_layer(s.copy())
            self._notify("Redo")

    def load_color_image(self, path):
        img = cv2.imread(path)
        if img is None:
            self._notify(f"Error: no se pudo abrir {os.path.basename(path)}")
            return False
        img = cv2.resize(img, (self.W, self.H), interpolation=cv2.INTER_AREA)
        self.color_image_orig = img.copy()
        self.color_layer      = img.copy()
        self.color_image_path = path
        self.app_mode         = APP_MODE_COLOR
        self.undo_stack.clear()
        self.redo_stack.clear()
        self._push_undo()
        self._notify(f"Imagen: {os.path.basename(path)}")
        return True

    def reset_color_image(self):
        if self.color_image_orig is not None:
            self._push_undo()
            self.color_layer = self.color_image_orig.copy()
            self._notify("Imagen restaurada al original")

    def save_drawing(self, frame_bg=None):
        ts  = datetime.now().strftime("%Y%m%d_%H%M%S")
        ext = self.cfg["save_format"]
        if self.app_mode == APP_MODE_COLOR and self.color_layer is not None:
            path = os.path.join(self.cfg["save_dir"], f"colored_{ts}.{ext}")
            cv2.imwrite(path, self.color_layer)
        elif frame_bg is not None:
            path = os.path.join(self.cfg["save_dir"], f"painting_{ts}.{ext}")
            cv2.imwrite(path, self._merge_canvas(frame_bg))
        else:
            path = os.path.join(self.cfg["save_dir"], f"canvas_{ts}.{ext}")
            cv2.imwrite(path, self.canvas)
        self._notify(f"Guardado: {os.path.basename(path)}")
        return path

    # ──────────────────────────────────────────────
    #  CONSTRUCCION DE UI
    # ──────────────────────────────────────────────
    def _build_ui(self):
        W, H  = self.W, self.H
        ph    = self.cfg["palette_height"]
        mg    = self.cfg["ui_margin"]
        n     = len(COLORS)

        self.palette_corner = False
        swatch_w = 36
        pal_x = W - (n * swatch_w) - mg - 10
        pal_y = H - ph - mg - 10

        self.color_rects = []
        for i in range(n):
            x1 = pal_x + i * swatch_w
            x2 = x1 + swatch_w - 2
            y1 = pal_y
            y2 = y1 + 32
            self.color_rects.append((x1, y1, x2, y2))

        bw, bh = 100, 32
        bx1    = mg + 10
        bx2    = mg + 10 + bw + 8

        self.buttons = {
            "UNDO":         (bx1, mg,       bx1+bw, mg+bh),
            "REDO":         (bx1, mg+36,    bx1+bw, mg+36+bh),
            "CLEAR":        (bx1, mg+72,    bx1+bw, mg+72+bh),
            "SAVE":         (bx1, mg+108,   bx1+bw, mg+108+bh),
            "BRUSH":        (bx2, mg,       bx2+bw, mg+bh),
            "FILL":         (bx2, mg+36,    bx2+bw, mg+36+bh),
            "ERASER":       (bx2, mg+72,    bx2+bw, mg+72+bh),
            "OPEN_IMG":     (bx2, mg+108,   bx2+bw, mg+108+bh),
            "COLOR_PICKER": (bx1, mg+144,   bx1+bw*2+8, mg+144+bh),
            # ← NUEVO botón Modo Libre
            "FREE_MODE":    (bx1, mg+182,   bx1+bw*2+8, mg+182+bh),
        }

    # ──────────────────────────────────────────────
    #  DETECCION DE DEDOS
    # ──────────────────────────────────────────────
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
        pt    = lambda i: (int(lm[i].x*w), int(lm[i].y*h))
        thumb = pt(4); index = pt(8); wrist = pt(0)
        pinch = math.dist(thumb, index)

        if n_up == 0:                                        return "ERASER"
        if n_up >= 4:                                        return "OPEN"
        if up[1] and not up[2] and not up[3] and not up[4]:
            if pinch < 55:                                   return "PINCH"
            return "DRAW"
        if up[1] and up[2] and not up[3] and not up[4]:     return "SELECT"
        if up[1] and up[2] and up[3] and not up[4]:         return "THREE_FINGERS"
        if up[0] and not up[1] and not up[2] and not up[3]:
            if thumb[1] < wrist[1] - 50:                    return "THUMB_UP"
            if thumb[1] > wrist[1] + 50:                    return "THUMB_DOWN"
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

    def _apply_fill(self, pt):
        self._push_undo()
        result = flood_fill_smooth(
            self._get_layer(), pt, self.current_color, self.fill_tolerance)
        self._set_layer(result)
        self._notify(f"Relleno aplicado (tol={self.fill_tolerance})")

    def _check_color_hover(self, pt):
        x, y = pt
        if hasattr(self, 'palette_corner') and self.palette_corner:
            for i, (x1, y1, x2, y2) in enumerate(self.color_rects):
                if x1 <= x <= x2 and y1 <= y <= y2:
                    if self._hover_color_idx == i:
                        self._hover_frames += 1
                        if self._hover_frames >= self._hover_threshold:
                            self.color_index   = i
                            self.current_color = COLORS[i]["bgr"]
                            self.eraser_mode   = False
                            self.active_tool   = TOOL_BRUSH
                            self._hover_frames = 0
                            self._notify(f"Color: {COLORS[i]['name']}")
                    else:
                        self._hover_color_idx = i
                        self._hover_frames    = 0
                    return True
        self._hover_color_idx = -1
        self._hover_frames    = 0
        return False

    def _check_btn_hover(self, pt, frame_bg=None):
        x, y = pt
        for name, (x1, y1, x2, y2) in self.buttons.items():
            if x1 <= x <= x2 and y1 <= y <= y2:
                if self._hover_btn == name:
                    self._hover_btn_frames += 1
                    if self._hover_btn_frames >= self._hover_btn_thr:
                        self._trigger_btn(name, frame_bg)
                        self._hover_btn_frames = 0
                else:
                    self._hover_btn        = name
                    self._hover_btn_frames = 0
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
                self._notify("Imagen restaurada")
            else:
                self.canvas[:] = 0
                self._notify("Canvas limpiado")
        elif name == "BRUSH":
            self.active_tool = TOOL_BRUSH;  self.eraser_mode = False
            self._notify("Herramienta: Pincel")
        elif name == "FILL":
            self.active_tool = TOOL_FILL;   self.eraser_mode = False
            self._notify("Herramienta: Relleno")
        elif name == "ERASER":
            self.active_tool = TOOL_ERASER; self.eraser_mode = True
            self._notify("Herramienta: Borrador")
        elif name == "OPEN_IMG":
            self._open_selector()
        elif name == "COLOR_PICKER":
            self._open_color_picker()
        elif name == "FREE_MODE":
            self._toggle_free_mode()

    def _open_selector(self):
        self.img_selector._load()
        path = self.img_selector.show(self.W, self.H)
        if path:
            self.load_color_image(path)

    def _open_color_picker(self):
        picker = ColorPicker()
        result = picker.show(self.W, self.H)
        if result:
            self.current_color = result["bgr"]
            found = False
            for i, c in enumerate(COLORS):
                if c["bgr"] == result["bgr"]:
                    self.color_index = i; found = True; break
            if not found:
                self.color_index = -1
            self.eraser_mode = False
            self.active_tool = TOOL_BRUSH
            self._notify(f"Color: {result['name']}")

    def _toggle_free_mode(self):
        if self.app_mode == APP_MODE_FREE:
            # Salir del modo libre
            self.mouse_ctrl.release_all()
            self.app_mode = APP_MODE_PAINT
            self._notify("Modo: Pintura Libre")
        else:
            if not PYAUTOGUI_AVAILABLE:
                self._notify("Instala pyautogui: pip install pyautogui")
                return
            # Limpiar suavizado al entrar
            self.mouse_ctrl.release_all()
            self.app_mode = APP_MODE_FREE
            self._notify("MODO LIBRE activado — controla el mouse con tu mano")

    # ──────────────────────────────────────────────
    #  PROCESAMIENTO MODO LIBRE
    # ──────────────────────────────────────────────
    def _process_free_mode(self, lm, gesture):
        """
        Interpreta los landmarks en modo libre para controlar el mouse.
        """
        h, w   = self.H, self.W
        pt     = lambda i: (int(lm[i].x*w), int(lm[i].y*h))
        index  = pt(8)    # punta del indice
        thumb  = pt(4)    # punta del pulgar
        middle = pt(12)   # punta del medio

        pinch_dist = math.dist(thumb, index)
        is_pinching = pinch_dist < self.cfg["pinch_threshold"]

        up = self._fingers_up(lm)

        # Mover cursor con el indice
        self.mouse_ctrl.smooth_move(index[0], index[1])

        # Clic derecho: indice + medio extendidos (SELECT)
        if gesture == "SELECT" and not is_pinching:
            action = self.mouse_ctrl.right_click()
            if action:
                self._set_mouse_action(action)

        # Doble clic / clic izquierdo / drag: pinch
        elif gesture in ("DRAW", "PINCH") or is_pinching:
            action = self.mouse_ctrl.handle_pinch(True, index[0], index[1])
            if action:
                self._set_mouse_action(action)

        else:
            # Soltar pinch
            action = self.mouse_ctrl.handle_pinch(False, index[0], index[1])
            if action:
                self._set_mouse_action(action)

        self.mouse_ctrl.tick()

        # Retornar info para el cursor visual
        return {
            "index": index,
            "thumb": thumb,
            "pinch_dist": pinch_dist,
            "is_pinching": is_pinching,
            "is_dragging": self.mouse_ctrl.is_dragging,
        }

    # ──────────────────────────────────────────────
    #  COMPOSICION DEL FRAME
    # ──────────────────────────────────────────────
    def _merge_canvas(self, frame):
        op    = self.cfg["canvas_opacity"]
        mask  = (self.canvas.sum(axis=2) > 0).astype(np.uint8)
        mask3 = np.stack([mask]*3, axis=-1)
        blend = np.where(mask3,
                         cv2.addWeighted(frame, 1-op, self.canvas, op, 0),
                         frame)
        return blend.astype(np.uint8)

    # ──────────────────────────────────────────────
    #  CURSOR VIRTUAL EN MODO LIBRE
    # ──────────────────────────────────────────────
    def _draw_free_cursor(self, output, info):
        idx   = info["index"]
        thumb = info["thumb"]
        dist  = info["pinch_dist"]
        is_p  = info["is_pinching"]
        is_d  = info["is_dragging"]

        # Linea entre pulgar e indice
        cv2.line(output, thumb, idx, (200, 200, 200), 1, cv2.LINE_AA)

        # Circulo en el indice
        if is_d:
            color  = (0, 80, 255)   # Naranja: arrastrando
            radius = 18
            cv2.circle(output, idx, radius, color, 3, cv2.LINE_AA)
            cv2.putText(output, "DRAG", (idx[0]+20, idx[1]-10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 2, cv2.LINE_AA)
        elif is_p:
            color  = (0, 255, 100)  # Verde: clic
            radius = 14
            cv2.circle(output, idx, radius, color, -1, cv2.LINE_AA)
            cv2.circle(output, idx, radius+4, color, 2, cv2.LINE_AA)
        else:
            color  = (255, 220, 0)  # Cyan/amarillo: moviendo
            radius = 14
            cv2.circle(output, idx, radius, color, 2, cv2.LINE_AA)
            cv2.circle(output, idx, 4,      color, -1, cv2.LINE_AA)

        # Indicador de distancia de pinch (barra pequeña)
        bar_x, bar_y = 20, self.H - 80
        bar_w        = 200
        thr          = self.cfg["pinch_threshold"]
        rel          = np.clip(dist / (thr * 2), 0, 1)
        filled       = int(bar_w * (1 - rel))
        cv2.rectangle(output, (bar_x, bar_y),     (bar_x+bar_w, bar_y+12), (40,40,40), -1)
        cv2.rectangle(output, (bar_x, bar_y),     (bar_x+filled, bar_y+12),
                      (0,200,80) if is_p else (80,180,220), -1)
        cv2.rectangle(output, (bar_x, bar_y),     (bar_x+bar_w, bar_y+12), (80,80,80), 1)
        cv2.putText(output, "PINCH", (bar_x, bar_y-6),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.42, (160,160,160), 1, cv2.LINE_AA)

    # ──────────────────────────────────────────────
    #  CURSOR VIRTUAL (modos pintura/colorear)
    # ──────────────────────────────────────────────
    def _draw_cursor(self, frame, pt, gesture):
        col = self.current_color if not self.eraser_mode else (200,200,200)

        if self.active_tool == TOOL_FILL and gesture == "DRAW":
            cv2.rectangle(frame, (pt[0]-16, pt[1]-10), (pt[0]+16, pt[1]+18), col, -1)
            cv2.rectangle(frame, (pt[0]-16, pt[1]-10), (pt[0]+16, pt[1]+18), (220,220,220), 2)
            cv2.putText(frame, "F", (pt[0]-5, pt[1]+10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (20,20,20), 2)
        elif self.active_tool == TOOL_ERASER or self.eraser_mode:
            er = self.brush_size * self.cfg["eraser_multiplier"] + 4
            cv2.circle(frame, pt, er, (200,200,200), 2, cv2.LINE_AA)
            cv2.line(frame, (pt[0]-er, pt[1]), (pt[0]+er, pt[1]), (200,200,200), 1)
            cv2.line(frame, (pt[0], pt[1]-er), (pt[0], pt[1]+er), (200,200,200), 1)
        elif gesture == "DRAW":
            cv2.circle(frame, pt, self.brush_size+4, col, 2, cv2.LINE_AA)
            cv2.circle(frame, pt, 3, (255,255,255), -1)
        elif gesture == "SELECT":
            cv2.drawMarker(frame, pt, (200,200,60), cv2.MARKER_CROSS, 22, 2, cv2.LINE_AA)
        else:
            cv2.circle(frame, pt, 10, (140,140,140), 1, cv2.LINE_AA)

    # ──────────────────────────────────────────────
    #  RENDERIZADO DEL HUD
    # ──────────────────────────────────────────────
    def _draw_ui(self, frame, gesture, fps):
        if not self.show_hud:
            return frame

        W, H  = self.W, self.H
        ph    = self.cfg["palette_height"]
        mg    = self.cfg["ui_margin"]

        # ── Swatches de color
        if self.palette_corner:
            for i, (c, (x1, y1, x2, y2)) in enumerate(zip(COLORS, self.color_rects)):
                bgr = c["bgr"]
                sel = (i == self.color_index) and not self.eraser_mode
                hov = (i == self._hover_color_idx)
                cv2.rectangle(frame, (x1+2, y1+2), (x2+2, y2+2), (0,0,0), -1)
                cv2.rectangle(frame, (x1, y1), (x2, y2), bgr, -1)
                bc = (255,255,255) if sel else (60,60,70)
                bt = 3 if sel else 1
                if hov: bc = (80,220,180); bt = 2
                cv2.rectangle(frame, (x1, y1), (x2, y2), bc, bt)
                if sel:
                    dc = (0,0,0) if sum(bgr) > 380 else (255,255,255)
                    cv2.circle(frame, ((x1+x2)//2, (y1+y2)//2+8), 4, dc, -1)

        # ── Botones
        BTN_TEXT = {
            "UNDO":         "DESHACER",
            "REDO":         "REHACER",
            "CLEAR":        "LIMPIAR",
            "SAVE":         "GUARDAR",
            "BRUSH":        "PINCEL",
            "FILL":         "RELLENO",
            "ERASER":       "BORRADOR",
            "OPEN_IMG":     "ABRIR IMG",
            "COLOR_PICKER": "SELEC. COLORES",
            "FREE_MODE":    "MODO LIBRE",     # ← nuevo
        }
        TOOL_MAP = {"BRUSH": TOOL_BRUSH, "FILL": TOOL_FILL, "ERASER": TOOL_ERASER}
        is_free  = (self.app_mode == APP_MODE_FREE)

        for name, (x1, y1, x2, y2) in self.buttons.items():
            is_hov    = (self._hover_btn == name)
            is_active = TOOL_MAP.get(name) == self.active_tool
            # Boton Modo Libre se resalta cuando esta activo
            if name == "FREE_MODE":
                is_active = is_free

            if is_hov:
                bg = (70, 110, 70)
            elif is_active and name == "FREE_MODE":
                bg = (0, 60, 120)   # Azul cuando Modo Libre activo
            elif is_active:
                bg = (40, 90, 40)
            else:
                bg = (30, 30, 40)

            cv2.rectangle(frame, (x1, y1), (x2, y2), bg, -1)
            if name == "FREE_MODE" and is_active:
                border = (0, 200, 255)  # Cyan para Modo Libre activo
            elif is_active:
                border = (0, 220, 100)
            elif is_hov:
                border = (160, 220, 160)
            else:
                border = (70, 70, 85)
            cv2.rectangle(frame, (x1, y1), (x2, y2), border, 2 if is_active else 1)

            # Icono especial para Modo Libre
            txt_col = (0, 220, 255) if (name == "FREE_MODE" and is_active) else (230, 230, 230)
            cv2.putText(frame, BTN_TEXT[name], (x1+7, y1+22),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, txt_col, 1, cv2.LINE_AA)

            if is_hov and self._hover_btn_frames > 0:
                prog = int((x2-x1)*self._hover_btn_frames/self._hover_btn_thr)
                cv2.rectangle(frame, (x1, y2-4), (x1+prog, y2), (80,220,80), -1)

        # ── Panel info (inferior izquierdo)
        ix, iy  = 12, H - 230
        panel_w = 340
        ov2 = frame.copy()
        cv2.rectangle(ov2, (ix-8, iy-8), (ix+panel_w, H-12), (12,12,18), -1)
        frame = cv2.addWeighted(ov2, 0.78, frame, 0.22, 0)

        def T(s, yo, col=(200,200,200), sc=0.50, th=1):
            cv2.putText(frame, s, (ix, iy+yo),
                        cv2.FONT_HERSHEY_SIMPLEX, sc, col, th, cv2.LINE_AA)

        if is_free:
            T("Modo:    MODO LIBRE", 20, (0,220,255), sc=0.55, th=2)
            T("Indice extendido  → Mover cursor",   44, (180,180,180), sc=0.42)
            T("Pinch             → Clic izquierdo", 62, (180,180,180), sc=0.42)
            T("Pinch + mover     → Arrastrar",      80, (180,180,180), sc=0.42)
            T("Indice + medio    → Clic derecho",   98, (180,180,180), sc=0.42)
            T("Indice+med+anu    → Doble clic",    116, (180,180,180), sc=0.42)
            T(f"Gesto:   {gesture}", 138, (200,200,100))
            T(f"FPS:     {fps:.1f}", 160, (80,220,80))

            # Accion del mouse
            if self._mouse_action_timer > 0:
                self._mouse_action_timer -= 1
                a_col = (0, 255, 150) if "CLIC" in self._mouse_action else \
                        (0, 180, 255) if "DRAG" in self._mouse_action or "ARRASTR" in self._mouse_action else \
                        (180, 180, 60)
                T(f">>> {self._mouse_action}", 185, a_col, sc=0.55, th=2)

            # Posicion del cursor en pantalla
            sp = self.mouse_ctrl.screen_pos
            if sp:
                T(f"Cursor: {sp[0]}, {sp[1]} px", 208, (120,120,120), sc=0.40)
        else:
            mode_lbl = "PINTURA LIBRE" if self.app_mode == APP_MODE_PAINT else "COLOREAR IMAGEN"
            tool_lbl = {"BRUSH":"Pincel","FILL":"Relleno","ERASER":"Borrador"}[self.active_tool]
            T(f"Modo:    {mode_lbl}",   20, (80, 200, 255), sc=0.50, th=2)
            T(f"Herram:  {tool_lbl}",   42, (150, 230, 150))
            T(f"Gesto:   {gesture}",    64, (200, 200, 100))
            if self.active_tool == TOOL_FILL:
                T(f"Toleran: {self.fill_tolerance}  ([ ] ajustar)", 86,  (200,180,80))
                T(f"Grosor:  {self.brush_size}px",  108)
            else:
                T(f"Grosor:  {self.brush_size}px",  86)
            T(f"Undo: {len(self.undo_stack)-1}   Redo: {len(self.redo_stack)}", 130)
            T(f"FPS:  {fps:.1f}", 152, (80,220,80))

        # ── Indicador de modo (centro superior)
        if is_free:
            mode_col = (0, 220, 255)
            mode_str = "MODO: LIBRE (CONTROL DEL MOUSE)"
        elif self.app_mode == APP_MODE_COLOR:
            mode_col = (80, 200, 255)
            mode_str = "MODO: COLOREAR IMAGEN"
        else:
            mode_col = (80, 255, 140)
            mode_str = "MODO: PINTURA LIBRE"
        cv2.putText(frame, mode_str, (W//2 - 180, ph + mg*2 - 4),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.62, mode_col, 2, cv2.LINE_AA)

        # ── Barra tolerancia fill
        if self.active_tool == TOOL_FILL and not is_free:
            tx, ty = W//2+150, ph//2+mg
            bw, bh = 170, 14
            tmin   = self.cfg["fill_tolerance_min"]
            tmax   = self.cfg["fill_tolerance_max"]
            prog   = int(bw*(self.fill_tolerance-tmin)/(tmax-tmin))
            cv2.rectangle(frame, (tx,ty), (tx+bw,ty+bh), (35,35,35), -1)
            cv2.rectangle(frame, (tx,ty), (tx+prog,ty+bh), (200,150,50), -1)
            cv2.rectangle(frame, (tx,ty), (tx+bw,ty+bh), (90,90,90), 1)
            cv2.putText(frame, f"Tolerancia: {self.fill_tolerance}",
                        (tx, ty-6), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (200,180,80), 1, cv2.LINE_AA)

        # ── Notificacion flotante
        if self._notif_timer > 0:
            self._notif_timer -= 1
            a  = min(1.0, self._notif_timer/20)
            nx = W//2 - 240
            ny = H//2 - 30
            ov_n = frame.copy()
            cv2.rectangle(ov_n, (nx-16,ny-32), (nx+486,ny+14), (20,20,30), -1)
            frame = cv2.addWeighted(ov_n, 1-a*0.7, frame, a*0.7, 0)
            cv2.putText(frame, self._notif, (nx, ny),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.72, (80,240,180), 2, cv2.LINE_AA)

        return frame

    # ──────────────────────────────────────────────
    #  BUCLE PRINCIPAL
    # ──────────────────────────────────────────────
    def run(self):
        cap = cv2.VideoCapture(self.cfg["camera_index"])
        cap.set(cv2.CAP_PROP_FRAME_WIDTH,  self.W)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.H)
        cap.set(cv2.CAP_PROP_FPS, 60)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

        if not cap.isOpened():
            print("Error: no se pudo abrir la camara.")
            return

        win = "Advanced Virtual Painter v3.1"
        cv2.namedWindow(win, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(win, self.W, self.H)
        _print_banner()

        last_bg          = None
        gesture          = "NONE"
        _hand_lm_to_draw = None
        _smooth_to_draw  = None
        _free_info       = None   # info del modo libre para el cursor

        while True:
            ret, frame = cap.read()
            if not ret:
                print("Error leyendo frame.")
                break

            if self.cfg["flip_horizontal"]:
                frame = cv2.flip(frame, 1)
            fh, fw = frame.shape[:2]
            if fw != self.W or fh != self.H:
                frame = cv2.resize(frame, (self.W, self.H))

            last_bg = frame.copy()

            now = time.time()
            self._fps_buf.append(1.0/max(now - self._last_t, 1e-6))
            self._last_t = now
            fps = float(np.mean(self._fps_buf))

            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            rgb.flags.writeable = False
            res = self.hands.process(rgb)
            rgb.flags.writeable = True

            _hand_lm_to_draw = None
            _smooth_to_draw  = None
            _free_info       = None

            if res.multi_hand_landmarks:
                for hand_lm in res.multi_hand_landmarks:
                    lm = hand_lm.landmark

                    ix = int(lm[8].x * self.W)
                    iy = int(lm[8].y * self.H)
                    tx = int(lm[4].x * self.W)
                    ty = int(lm[4].y * self.H)
                    pinch_dist = math.dist((tx,ty),(ix,iy))

                    mn, mx = self.cfg["min_brush_size"], self.cfg["max_brush_size"]
                    self.brush_size = self._smooth_bs(
                        int(mn + float(np.clip((pinch_dist-20)/200,0,1))*(mx-mn)))

                    raw_g   = self._detect_gesture(lm)
                    gesture = self._stable_gesture(raw_g)
                    smooth  = self._smooth_pt((ix, iy))

                    _hand_lm_to_draw = hand_lm
                    _smooth_to_draw  = smooth

                    # ══════════════════════════════
                    #  MODO LIBRE — control del mouse
                    # ══════════════════════════════
                    if self.app_mode == APP_MODE_FREE:
                        _free_info = self._process_free_mode(lm, gesture)

                    # ══════════════════════════════
                    #  MODOS PINTURA / COLOREAR
                    # ══════════════════════════════
                    else:
                        if gesture == "THUMB_UP":
                            self.color_index   = (self.color_index + 1) % len(COLORS)
                            self.current_color = COLORS[self.color_index]["bgr"]
                            self.eraser_mode   = False
                            self._notify(f">> {COLORS[self.color_index]['name']}")

                        elif gesture == "THUMB_DOWN":
                            self.color_index   = (self.color_index - 1) % len(COLORS)
                            self.current_color = COLORS[self.color_index]["bgr"]
                            self.eraser_mode   = False
                            self._notify(f"<< {COLORS[self.color_index]['name']}")

                        elif gesture == "ERASER":
                            if self.active_tool != TOOL_ERASER:
                                self.active_tool = TOOL_ERASER
                                self.eraser_mode = True
                                self._notify("Borrador activado")

                        elif gesture == "OPEN":
                            self.drawing    = False
                            self.prev_point = None

                        if gesture in ("SELECT", "OPEN", "PINCH"):
                            self._check_color_hover(smooth)
                            self._check_btn_hover(smooth, last_bg)
                            self.drawing    = False
                            self.prev_point = None
                            self._fill_done = False

                        elif gesture == "DRAW":
                            self._check_color_hover(smooth)
                            self._hover_btn        = None
                            self._hover_btn_frames = 0

                            in_btn = any(
                                x1<=smooth[0]<=x2 and y1<=smooth[1]<=y2
                                for x1,y1,x2,y2 in self.buttons.values())
                            in_pal = any(
                                x1<=smooth[0]<=x2 and y1<=smooth[1]<=y2
                                for x1,y1,x2,y2 in self.color_rects)

                            if not in_btn and not in_pal:
                                if self.active_tool == TOOL_FILL:
                                    if not self._fill_done:
                                        self._apply_fill(smooth)
                                        self._fill_done = True
                                    self.drawing    = False
                                    self.prev_point = None
                                elif self.active_tool == TOOL_ERASER or self.eraser_mode:
                                    if not self.drawing:
                                        self._push_undo()
                                        self.drawing = True
                                    esize = self.brush_size * self.cfg["eraser_multiplier"]
                                    if self.app_mode == APP_MODE_COLOR and self.color_image_orig is not None:
                                        mask_e = np.zeros((self.H,self.W), dtype=np.uint8)
                                        cv2.circle(mask_e, smooth, esize, 255, -1)
                                        mask3 = np.stack([mask_e]*3, axis=-1)
                                        self.color_layer = np.where(
                                            mask3>0, self.color_image_orig, self.color_layer
                                        ).astype(np.uint8)
                                    else:
                                        self._stroke(smooth,(0,0,0),esize)
                                    self.prev_point = smooth
                                else:
                                    if not self.drawing:
                                        self._push_undo()
                                        self.drawing = True
                                    self._stroke(smooth, self.current_color, self.brush_size)
                                    self.prev_point = smooth
                            else:
                                self.drawing    = False
                                self.prev_point = None
                                self._fill_done = False
                        else:
                            self.drawing    = False
                            self.prev_point = None
                            self._fill_done = False

            else:
                # Sin mano detectada
                if self.app_mode == APP_MODE_FREE:
                    self.mouse_ctrl.handle_pinch(False, 0, 0)
                    self.mouse_ctrl.tick()
                self.drawing    = False
                self.prev_point = None
                self._fill_done = False
                self.smooth_points.clear()
                self._gesture_buffer.clear()
                gesture = "NONE"

            # ── Composicion del frame final
            if self.app_mode == APP_MODE_FREE:
                # En modo libre: solo la camara con overlay semitransparente
                overlay = frame.copy()
                cv2.rectangle(overlay, (0,0), (self.W, self.H), (0,0,40), -1)
                output = cv2.addWeighted(overlay, 0.10, frame, 0.90, 0)
            elif self.app_mode == APP_MODE_COLOR and self.color_layer is not None:
                output = cv2.addWeighted(self.color_layer, 0.88, frame, 0.12, 0)
            else:
                output = self._merge_canvas(frame)

            # ── Landmarks y cursor SOBRE el output compuesto
            if _hand_lm_to_draw is not None and _smooth_to_draw is not None:
                hand_style = self.mp_draw_styles.DrawingSpec(
                    color=(0, 255, 127), thickness=3, circle_radius=6)
                conn_style = self.mp_draw_styles.DrawingSpec(
                    color=(0, 200, 255), thickness=2)
                self.mp_draw.draw_landmarks(
                    output, _hand_lm_to_draw,
                    self.mp_hands.HAND_CONNECTIONS,
                    hand_style, conn_style)

                idx_x = int(_hand_lm_to_draw.landmark[8].x * self.W)
                idx_y = int(_hand_lm_to_draw.landmark[8].y * self.H)
                cv2.circle(output, (idx_x, idx_y), 12, (255,255,0), 2, cv2.LINE_AA)
                cv2.circle(output, (idx_x, idx_y), 5,  (0,255,255), -1, cv2.LINE_AA)

                if self.app_mode == APP_MODE_FREE and _free_info is not None:
                    self._draw_free_cursor(output, _free_info)
                else:
                    self._draw_cursor(output, _smooth_to_draw, gesture)

            output = self._draw_ui(output, gesture, fps)
            cv2.imshow(win, output)

            # ── Teclado
            key = cv2.waitKey(1) & 0xFF

            if key in (ord('q'), 27):
                self.mouse_ctrl.release_all()
                break
            elif key == ord('1'):
                self.mouse_ctrl.release_all()
                self.app_mode = APP_MODE_PAINT
                self._notify("Modo: Pintura Libre")
            elif key == ord('2'):
                if self.color_layer is not None:
                    self.mouse_ctrl.release_all()
                    self.app_mode = APP_MODE_COLOR
                    self._notify("Modo: Colorear Imagen")
                else:
                    self._notify("Carga primero una imagen (tecla O)")
            elif key == ord('3'):
                self._toggle_free_mode()
            elif key in (ord('o'), ord('O')):
                self._open_selector()
            elif key in (ord('b'), ord('B')):
                self.active_tool = TOOL_BRUSH;  self.eraser_mode = False
                self._notify("Pincel")
            elif key in (ord('k'), ord('K')):
                self.active_tool = TOOL_FILL;   self.eraser_mode = False
                self._notify("Relleno (Flood Fill)")
            elif key in (ord('e'), ord('E')):
                self.active_tool = TOOL_ERASER; self.eraser_mode = True
                self._notify("Borrador")
            elif key in (ord('c'), ord('C')):
                self._push_undo()
                if self.app_mode == APP_MODE_COLOR and self.color_image_orig is not None:
                    self.color_layer = self.color_image_orig.copy()
                    self._notify("Imagen restaurada")
                else:
                    self.canvas[:] = 0
                    self._notify("Canvas limpiado")
            elif key in (ord('r'), ord('R')):
                self.reset_color_image()
            elif key in (ord('h'), ord('H')):
                self.show_hud = not self.show_hud
            elif key in (ord('f'), ord('F')):
                self.fullscreen = not self.fullscreen
                cv2.setWindowProperty(win, cv2.WND_PROP_FULLSCREEN,
                    cv2.WINDOW_FULLSCREEN if self.fullscreen else cv2.WINDOW_NORMAL)
            elif key in (ord('s'), ord('S')):
                self.save_drawing(last_bg)
            elif key == 26: self.undo()
            elif key == 25: self.redo()
            elif key in (ord('+'), ord('=')):
                self.brush_size = min(self.brush_size+2, self.cfg["max_brush_size"])
            elif key == ord('-'):
                self.brush_size = max(self.brush_size-2, self.cfg["min_brush_size"])
            elif key == ord(']'):
                self.fill_tolerance = min(self.fill_tolerance+4, self.cfg["fill_tolerance_max"])
                self._notify(f"Tolerancia fill: {self.fill_tolerance}")
            elif key == ord('['):
                self.fill_tolerance = max(self.fill_tolerance-4, self.cfg["fill_tolerance_min"])
                self._notify(f"Tolerancia fill: {self.fill_tolerance}")

        cap.release()
        self.hands.close()
        cv2.destroyAllWindows()
        print(f"\n[OK] Archivos guardados en: ./{self.cfg['save_dir']}/")


# ══════════════════════════════════════════════════════
#  GENERADOR DE IMAGENES DE EJEMPLO
# ══════════════════════════════════════════════════════
def create_sample_images(out_dir):
    os.makedirs(out_dir, exist_ok=True)
    W, H = 800, 600

    img = np.full((H, W, 3), 255, dtype=np.uint8)
    cx, cy = W//2, H//2
    for r in range(40, 260, 42):
        cv2.circle(img, (cx, cy), r, (0,0,0), 2)
    for a in range(0, 360, 30):
        rd = math.radians(a)
        cv2.line(img,
                 (int(cx+42*math.cos(rd)), int(cy+42*math.sin(rd))),
                 (int(cx+250*math.cos(rd)), int(cy+250*math.sin(rd))), (0,0,0), 2)
    for a in range(0, 360, 45):
        rd = math.radians(a)
        px, py = int(cx+145*math.cos(rd)), int(cy+145*math.sin(rd))
        cv2.ellipse(img, (px,py), (36,20), a, 0, 360, (0,0,0), 2)
    cv2.imwrite(os.path.join(out_dir, "mandala.png"), img)

    img = np.full((H, W, 3), 255, dtype=np.uint8)
    cv2.line(img, (0,H//2), (W,H//2), (0,0,0), 2)
    cv2.circle(img, (130,110), 72, (0,0,0), 2)
    mountains = np.array([[0,H//2],[160,185],[320,H//2],[510,170],[720,H//2],[W,H//2]])
    cv2.polylines(img, [mountains], False, (0,0,0), 3)
    cv2.imwrite(os.path.join(out_dir, "paisaje.png"), img)

    img = np.full((H, W, 3), 255, dtype=np.uint8)
    cv2.circle(img, (400,300), 185, (0,0,0), 3)
    for ex in [340, 460]:
        cv2.circle(img, (ex,268), 38, (0,0,0), 3)
        cv2.circle(img, (ex,268), 14, (0,0,0), -1)
    cv2.imwrite(os.path.join(out_dir, "gato.png"), img)

    print(f"[OK] Imagenes de ejemplo generadas en '{out_dir}/'")


# ══════════════════════════════════════════════════════
#  BANNER
# ══════════════════════════════════════════════════════
def _print_banner():
    print("=" * 68)
    print("  ADVANCED VIRTUAL PAINTER v3.1  —  con MODO LIBRE")
    print("=" * 68)
    print("  Modos:   [1] Pintura libre   [2] Colorear imagen   [3] Modo Libre")
    print("  Herram:  [B] Pincel   [K] Fill   [E] Borrador")
    print("  Imagen:  [O] Abrir   [R] Restaurar   [S] Guardar")
    print("  Ctrl+Z Undo  |  Ctrl+Y Redo  |  Q Salir")
    print("-" * 68)
    print("  MODO LIBRE — Gestos del mouse:")
    print("    Indice solo       → Mover cursor")
    print("    Pinch             → Clic izquierdo")
    print("    Pinch + mover     → Arrastrar (drag)")
    print("    Indice + medio    → Clic derecho")
    print("    2 pinch rapidos   → Doble clic")
    print("=" * 68)
    if not PYAUTOGUI_AVAILABLE:
        print("  [!] AVISO: Instala pyautogui para usar el Modo Libre:")
        print("      pip install pyautogui")
        print("=" * 68)


# ══════════════════════════════════════════════════════
#  PUNTO DE ENTRADA
# ══════════════════════════════════════════════════════
def main():
    if len(sys.argv) > 1 and sys.argv[1].lstrip('-').isdigit():
        CONFIG["camera_index"] = int(sys.argv[1])

    if "--gen-samples" in sys.argv:
        create_sample_images(CONFIG["images_dir"])
        return

    total = sum(
        len(glob.glob(os.path.join(CONFIG["images_dir"], ext)))
        for ext in CONFIG["image_extensions"])
    if total == 0:
        print(f"[INFO] Generando imagenes de ejemplo en '{CONFIG['images_dir']}'...")
        create_sample_images(CONFIG["images_dir"])

    painter = VirtualPainter()
    painter.run()


if __name__ == "__main__":
    main()