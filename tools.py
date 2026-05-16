"""
tools.py - Herramientas de dibujo y selectores de Magic Paint
Contiene: flood_fill, ColorPicker, ImageSelector
"""
import cv2
import numpy as np
import glob
import os

from config import UI
from ui_helpers import (
    put_text_centered, draw_rounded_rect, draw_neon_border,
    draw_gradient_bar,
)


# ─────────────────────────────────────────────
#  TECLAS DE NAVEGACIÓN (multiplataforma)
# ─────────────────────────────────────────────
def _nav_key(raw):
    """
    Detecta teclas de navegación a partir del valor RAW de cv2.waitKeyEx().
    No aplicar & 0xFF antes de llamar esta función.

    Valores de flechas por plataforma:
      Linux  (sin máscara): Izq=65361  Der=65363  Arr=65362  Abj=65364
      Windows(sin máscara): Izq=2424832 Der=2555904 Arr=2490368 Abj=2621440
      macOS  (sin máscara): Izq=63234  Der=63235  Arr=63232  Abj=63233
      Con &0xFF (Linux):    Izq=81     Der=83     Arr=82     Abj=84
    """
    if raw < 0:
        return None

    # Flechas: verificar valor COMPLETO primero (sin máscara)
    if raw in (65361, 2424832, 63234): return "LEFT"
    if raw in (65363, 2555904, 63235): return "RIGHT"
    if raw in (65362, 2490368, 63232): return "UP"
    if raw in (65364, 2621440, 63233): return "DOWN"

    k = raw & 0xFF

    # Flechas ya enmascaradas (algunos entornos Linux)
    if k == 81: return "LEFT"
    if k == 83: return "RIGHT"
    if k == 82: return "UP"
    if k == 84: return "DOWN"

    # WASD (compatibilidad)
    if k in (ord('a'), ord('A')): return "LEFT"
    if k in (ord('d'), ord('D')): return "RIGHT"
    if k in (ord('w'), ord('W')): return "UP"
    if k in (ord('s'), ord('S')): return "DOWN"

    if k in (13, 32): return "CONFIRM"
    if k == 27:       return "CANCEL"
    if k in (ord('r'), ord('R')): return "RELOAD"
    return None


# ─────────────────────────────────────────────
#  BARRA DE DESPLAZAMIENTO
# ─────────────────────────────────────────────
def _draw_scrollbar(canvas, x, y_top, track_h, scroll_y, max_scroll, total_h):
    """Dibuja una barra de desplazamiento vertical."""
    if max_scroll <= 0:
        return
    # Pista
    cv2.rectangle(canvas, (x, y_top), (x+10, y_top+track_h), (210, 200, 185), -1)
    cv2.rectangle(canvas, (x, y_top), (x+10, y_top+track_h), (170, 155, 135), 1)
    # Thumb
    viewport_h = total_h - max_scroll
    thumb_h    = max(24, int(track_h * viewport_h / total_h))
    thumb_y    = y_top + int((track_h - thumb_h) * scroll_y / max_scroll)
    cv2.rectangle(canvas, (x+1, thumb_y),   (x+9, thumb_y+thumb_h), (100, 80, 55), -1)
    cv2.rectangle(canvas, (x+1, thumb_y),   (x+9, thumb_y+thumb_h), (70, 50, 30),  1)


# ─────────────────────────────────────────────
#  FLOOD FILL
# ─────────────────────────────────────────────
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
    filled = flood_fill(image, seed_pt, fill_color, tolerance)
    diff   = cv2.absdiff(image, filled)
    _, changed = cv2.threshold(
        cv2.cvtColor(diff, cv2.COLOR_BGR2GRAY), 1, 255, cv2.THRESH_BINARY)
    kernel = np.ones((3, 3), np.uint8)
    border  = cv2.dilate(changed, kernel, iterations=2) - changed
    blurred = cv2.GaussianBlur(filled, (3, 3), 0)
    mask_border = cv2.cvtColor(border, cv2.COLOR_GRAY2BGR) > 0
    return np.where(mask_border, blurred, filled).astype(np.uint8)


# ─────────────────────────────────────────────
#  SELECTOR DE COLORES
# ─────────────────────────────────────────────
class ColorPicker:
    COLS     = 6
    SWATCH_W = 90
    SWATCH_H = 60
    ROW_H    = 95      # SWATCH_H + espacio para etiqueta + padding
    HEADER_H = 78
    FOOTER_H = 38
    BG_COLOR  = (255, 249, 230)
    SEL_COLOR = (80,  222, 100)

    EXTENDED_COLORS = [
        {"name": "Negro",          "bgr": (  1,   1,   1)},
        {"name": "Gris Oscuro",    "bgr": ( 50,  50,  50)},
        {"name": "Gris",           "bgr": (128, 128, 128)},
        {"name": "Gris Claro",     "bgr": (180, 180, 180)},
        {"name": "Blanco",         "bgr": (255, 255, 255)},
        {"name": "Rojo Oscuro",    "bgr": (  0,   0, 100)},
        {"name": "Rojo",           "bgr": (  0,   0, 220)},
        {"name": "Rojo Brillante", "bgr": (  0,   0, 255)},
        {"name": "Naranja Oscuro", "bgr": (  0,  60, 160)},
        {"name": "Naranja",        "bgr": (  0, 120, 255)},
        {"name": "Amarillo Oscuro","bgr": (  0, 180, 200)},
        {"name": "Amarillo",       "bgr": (  0, 220, 220)},
        {"name": "Amarillo Brill", "bgr": (  0, 255, 255)},
        {"name": "Lima",           "bgr": ( 80, 255,  80)},
        {"name": "Verde Lima",     "bgr": (120, 255,   0)},
        {"name": "Verde",          "bgr": (  0, 200,  60)},
        {"name": "Verde Oscuro",   "bgr": (  0, 100,  40)},
        {"name": "Verde Bosque",   "bgr": (  0, 130,  60)},
        {"name": "Verde Oliva",    "bgr": (  0, 160,  80)},
        {"name": "Cian Oscuro",    "bgr": (150, 180,   0)},
        {"name": "Cian",           "bgr": (220, 200,   0)},
        {"name": "Cian Brillante", "bgr": (255, 255,   0)},
        {"name": "Azul Cielo",     "bgr": (230, 150,   0)},
        {"name": "Azul",           "bgr": (230,  80,   0)},
        {"name": "Azul Real",      "bgr": (200,  50,   0)},
        {"name": "Azul Marino",    "bgr": (130,  30,  30)},
        {"name": "Azul Oscuro",    "bgr": (100,  20,  20)},
        {"name": "Violeta",        "bgr": (100,   0, 100)},
        {"name": "Morado",         "bgr": (160,   0, 120)},
        {"name": "Purpura",        "bgr": (180,  50, 150)},
        {"name": "Magenta",        "bgr": (200,   0, 200)},
        {"name": "Rosa",           "bgr": (160, 100, 240)},
        {"name": "Rosa Oscuro",    "bgr": (100,  50, 120)},
        {"name": "Rosa Brillante", "bgr": (180, 150, 220)},
        {"name": "Salmon",         "bgr": (100, 130, 180)},
        {"name": "Coral",          "bgr": ( 80, 127, 180)},
        {"name": "Marron Oscuro",  "bgr": ( 20,  50,  90)},
        {"name": "Marron",         "bgr": ( 30,  80, 140)},
        {"name": "Marron Claro",   "bgr": ( 60, 120, 160)},
        {"name": "Beige",          "bgr": (130, 180, 200)},
        {"name": "Piel Muy Clara", "bgr": (180, 200, 220)},
        {"name": "Piel Clara",     "bgr": (140, 180, 210)},
        {"name": "Piel Clara Med.","bgr": (130, 160, 190)},
        {"name": "Piel Media",     "bgr": (110, 140, 170)},
        {"name": "Piel Morena",    "bgr": ( 80, 110, 140)},
        {"name": "Piel Oscura",    "bgr": ( 50,  70, 100)},
        {"name": "Piel Muy Osc.",  "bgr": ( 30,  50,  70)},
        {"name": "Cafe",           "bgr": ( 25,  40,  65)},
    ]

    def __init__(self):
        self.colors    = self.EXTENDED_COLORS
        self.selected  = 0
        self._scroll_y = 0

    # ── Auto-scroll para mantener la selección visible ────────
    def _update_scroll(self, viewport_h):
        row        = self.selected // self.COLS
        top        = row * self.ROW_H
        bot        = top + self.ROW_H
        n_rows     = (len(self.colors) + self.COLS - 1) // self.COLS
        max_scroll = max(0, n_rows * self.ROW_H - viewport_h)

        if top < self._scroll_y:
            self._scroll_y = top
        elif bot > self._scroll_y + viewport_h:
            self._scroll_y = bot - viewport_h

        self._scroll_y = int(np.clip(self._scroll_y, 0, max_scroll))

    def _build_grid(self, W, H):
        viewport_h = H - self.HEADER_H - self.FOOTER_H
        self._update_scroll(viewport_h)

        n_rows     = (len(self.colors) + self.COLS - 1) // self.COLS
        total_h    = n_rows * self.ROW_H
        max_scroll = max(0, total_h - viewport_h)
        mg = 20

        canvas = np.full((H, W, 3), self.BG_COLOR, dtype=np.uint8)

        # ── Swatches ─────────────────────────────────────────────
        for i, c in enumerate(self.colors):
            row = i // self.COLS
            col = i % self.COLS
            x   = mg + col * (self.SWATCH_W + 12)
            y   = self.HEADER_H + row * self.ROW_H - self._scroll_y

            # Saltar si está totalmente fuera del viewport
            if y + self.ROW_H <= self.HEADER_H or y >= H - self.FOOTER_H:
                continue

            if i == self.selected:
                cv2.rectangle(canvas,
                              (x-6, y-6), (x+self.SWATCH_W+6, y+self.SWATCH_H+6),
                              self.SEL_COLOR, 3)
            else:
                cv2.rectangle(canvas,
                              (x-2, y-2), (x+self.SWATCH_W+2, y+self.SWATCH_H+2),
                              (200, 180, 150), 1)

            cv2.rectangle(canvas, (x, y), (x+self.SWATCH_W, y+self.SWATCH_H), c["bgr"], -1)
            cv2.rectangle(canvas, (x, y), (x+self.SWATCH_W, y+self.SWATCH_H), (180, 160, 130), 1)

            label_y = y + self.SWATCH_H + 18
            if self.HEADER_H < label_y < H - self.FOOTER_H:
                name = c["name"][:12]
                (tw, _), _ = cv2.getTextSize(name, cv2.FONT_HERSHEY_SIMPLEX, 0.4, 1)
                cv2.putText(canvas, name,
                            (x + (self.SWATCH_W - tw) // 2, label_y),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.4, (80, 60, 40), 1, cv2.LINE_AA)

        # ── Scrollbar ────────────────────────────────────────────
        _draw_scrollbar(canvas, W-18, self.HEADER_H, viewport_h,
                        self._scroll_y, max_scroll, total_h)

        # ── Header encima del contenido (tapa el desborde) ───────
        cv2.rectangle(canvas, (0, 0), (W, self.HEADER_H), (255, 240, 210), -1)
        cv2.rectangle(canvas, (0, self.HEADER_H-3), (W, self.HEADER_H), (200, 180, 150), -1)
        cv2.putText(canvas, "SELECCIONA UN COLOR",
                    (mg, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (60, 120, 255), 2, cv2.LINE_AA)
        cv2.putText(canvas, "Flechas para navegar  |  ENTER seleccionar  |  ESC cancelar",
                    (mg, 66), cv2.FONT_HERSHEY_SIMPLEX, 0.47, (120, 90, 60), 1, cv2.LINE_AA)

        # ── Footer encima del contenido (tapa el desborde) ───────
        cv2.rectangle(canvas, (0, H-self.FOOTER_H), (W, H), (255, 240, 210), -1)
        cv2.rectangle(canvas, (0, H-self.FOOTER_H), (W, H-self.FOOTER_H+3), (200, 180, 150), -1)
        sel_name = self.colors[self.selected]["name"]
        cv2.putText(canvas,
                    f"{len(self.colors)} colores  |  Seleccionado: {sel_name}",
                    (mg, H - 12),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (120, 90, 60), 1, cv2.LINE_AA)

        return canvas

    def show(self, W=1280, H=720):
        win = "Selector de Color"
        cv2.namedWindow(win, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(win, W, H)
        while True:
            cv2.imshow(win, self._build_grid(W, H))
            raw = cv2.waitKeyEx(50)
            nav = _nav_key(raw)
            n   = len(self.colors)
            if nav == "CANCEL":
                cv2.destroyWindow(win); return None
            elif nav == "CONFIRM":
                cv2.destroyWindow(win); return self.colors[self.selected]
            elif nav == "LEFT":  self.selected = (self.selected - 1) % n
            elif nav == "RIGHT": self.selected = (self.selected + 1) % n
            elif nav == "UP":    self.selected = max(0, self.selected - self.COLS)
            elif nav == "DOWN":  self.selected = min(n - 1, self.selected + self.COLS)


# ─────────────────────────────────────────────
#  SELECTOR DE IMÁGENES
# ─────────────────────────────────────────────
class ImageSelector:
    THUMB_W  = 210
    THUMB_H  = 158
    COLS     = 5
    PAD      = 14
    LABEL_H  = 26
    HEADER_H = 92
    FOOTER_H = 42

    def __init__(self, images_dir, extensions):
        self.images_dir  = images_dir
        self.extensions  = extensions
        self.image_paths = []
        self.thumbnails  = []
        self.selected    = 0
        self._scroll_y   = 0
        self._load()

    @property
    def _row_h(self):
        return self.THUMB_H + self.PAD + self.LABEL_H  # 198 px

    def _load(self):
        self.image_paths = []
        for ext in self.extensions:
            self.image_paths += glob.glob(os.path.join(self.images_dir, ext))
        self.image_paths.sort()
        self.thumbnails = []
        for p in self.image_paths:
            img = cv2.imread(p)
            if img is not None:
                th = cv2.resize(img, (self.THUMB_W, self.THUMB_H),
                                interpolation=cv2.INTER_AREA)
            else:
                th = np.full((self.THUMB_H, self.THUMB_W, 3), 230, dtype=np.uint8)
                put_text_centered(th, "?", self.THUMB_W // 2, self.THUMB_H // 2,
                                  1.5, (150, 100, 60), 3)
            self.thumbnails.append(th)

    # ── Auto-scroll para mantener la selección visible ────────
    def _update_scroll(self, viewport_h):
        row        = self.selected // self.COLS
        top        = row * self._row_h
        bot        = top + self._row_h
        n_rows     = (len(self.image_paths) + self.COLS - 1) // self.COLS
        max_scroll = max(0, n_rows * self._row_h - viewport_h)

        if top < self._scroll_y:
            self._scroll_y = top
        elif bot > self._scroll_y + viewport_h:
            self._scroll_y = bot - viewport_h

        self._scroll_y = int(np.clip(self._scroll_y, 0, max_scroll))

    def _build_grid(self, W, H):
        viewport_h = H - self.HEADER_H - self.FOOTER_H
        if self.image_paths:
            self._update_scroll(viewport_h)

        n_rows     = max(1, (len(self.image_paths) + self.COLS - 1) // self.COLS)
        total_h    = n_rows * self._row_h
        max_scroll = max(0, total_h - viewport_h)
        mg = 20

        # Fondo degradado
        bg = np.zeros((H, W, 3), dtype=np.uint8)
        y_idx = np.arange(H, dtype=np.float32) / H
        bg[:, :, 0] = (255*(1-y_idx) + 230*y_idx).astype(np.uint8)[:, np.newaxis]
        bg[:, :, 1] = (210*(1-y_idx) + 245*y_idx).astype(np.uint8)[:, np.newaxis]
        bg[:, :, 2] = (135*(1-y_idx) + 255*y_idx).astype(np.uint8)[:, np.newaxis]

        # ── Miniaturas ───────────────────────────────────────────
        for i, (thumb, path) in enumerate(zip(self.thumbnails, self.image_paths)):
            row = i // self.COLS
            col = i % self.COLS
            x   = mg + col * (self.THUMB_W + self.PAD)
            y   = self.HEADER_H + row * self._row_h - self._scroll_y
            tw, th = self.THUMB_W, self.THUMB_H

            # Saltar si está totalmente fuera del viewport
            if y + self._row_h <= self.HEADER_H or y >= H - self.FOOTER_H:
                continue

            if i == self.selected:
                draw_rounded_rect(bg, x-6, y-6, x+tw+6, y+th+6, 6, UI["vivo_verde"], -1)
                draw_rounded_rect(bg, x-6, y-6, x+tw+6, y+th+6, 6, (235, 248, 255), -1)
                draw_neon_border(bg, x-4, y-4, x+tw+4, y+th+4, UI["vivo_verde"], 3)
            else:
                cv2.rectangle(bg, (x-2, y-2), (x+tw+2, y+th+2), UI["border_claro"], 1)

            # Pegar miniatura recortando al viewport
            y_clip_top = max(y, self.HEADER_H)
            y_clip_bot = min(y + th, H - self.FOOTER_H)
            if y_clip_top < y_clip_bot:
                src_top = y_clip_top - y
                src_bot = y_clip_bot - y
                bg[y_clip_top:y_clip_bot, x:x+tw] = thumb[src_top:src_bot, :]

            label_y = y + th + 20
            if self.HEADER_H < label_y < H - self.FOOTER_H:
                fname = os.path.basename(path)[:24]
                col_t = UI["vivo_verde"] if i == self.selected else UI["text_claro"]
                cv2.putText(bg, fname, (x, label_y),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.40, col_t, 1, cv2.LINE_AA)

        # ── Scrollbar ────────────────────────────────────────────
        _draw_scrollbar(bg, W-18, self.HEADER_H, viewport_h,
                        self._scroll_y, max_scroll, total_h)

        # ── Header encima del contenido (tapa el desborde) ───────
        cv2.rectangle(bg, (0, 0), (W, self.HEADER_H), (255, 249, 230), -1)
        draw_gradient_bar(bg, 0, self.HEADER_H-4, W, self.HEADER_H, UI["vivo_cyan"], UI["vivo_rosa"])
        put_text_centered(bg, "SELECCIONA UNA IMAGEN PARA COLOREAR",
                          W // 2, 32, 0.9, (60, 120, 255), 2)
        put_text_centered(bg, "Flechas para navegar  |  ENTER seleccionar  |  ESC cancelar",
                          W // 2, 62, 0.47, (100, 80, 60), 1)

        # ── Footer encima del contenido (tapa el desborde) ───────
        cv2.rectangle(bg, (0, H-self.FOOTER_H), (W, H), (255, 249, 230), -1)
        cv2.rectangle(bg, (0, H-self.FOOTER_H), (W, H-self.FOOTER_H+3), (180, 165, 140), -1)
        sel_name = (os.path.basename(self.image_paths[self.selected])
                    if self.image_paths else "ninguna")
        put_text_centered(bg,
                          f"[R] Recargar  |  {len(self.image_paths)} imagen(es)  |  "
                          f"Seleccionada: {sel_name}",
                          W // 2, H - 16, 0.43, UI["text_claro"], 1)

        return bg

    def show(self, W=1280, H=720):
        win = "Magic Paint - Seleccionar Imagen"
        cv2.namedWindow(win, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(win, W, H)
        while True:
            cv2.imshow(win, self._build_grid(W, H))
            raw = cv2.waitKeyEx(50)
            nav = _nav_key(raw)
            n   = len(self.image_paths)
            if n == 0:
                if nav == "RELOAD":
                    self._load()
                elif nav == "CANCEL":
                    cv2.destroyWindow(win); return None
                continue
            if nav == "CANCEL":
                cv2.destroyWindow(win); return None
            elif nav == "CONFIRM":
                cv2.destroyWindow(win); return self.image_paths[self.selected]
            elif nav == "LEFT":   self.selected = (self.selected - 1) % n
            elif nav == "RIGHT":  self.selected = (self.selected + 1) % n
            elif nav == "UP":     self.selected = max(0, self.selected - self.COLS)
            elif nav == "DOWN":   self.selected = min(n - 1, self.selected + self.COLS)
            elif nav == "RELOAD": self._load()