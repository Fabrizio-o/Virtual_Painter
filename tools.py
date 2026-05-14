"""
tools.py - Herramientas de dibujo y selectores de Magic Paint
Contiene: flood_fill, ColorPicker, ImageSelector
"""
import cv2
import numpy as np
import glob
import os
import time

from config import UI
from ui_helpers import (
    put_text_centered, draw_rounded_rect, draw_neon_border,
    draw_gradient_bar, draw_clouds_fast,
)


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
    COLS      = 6
    SWATCH_W  = 90
    SWATCH_H  = 60
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
        self.colors   = self.EXTENDED_COLORS
        self.selected = 0

    def _build_grid(self, W, H):
        canvas = np.full((H, W, 3), self.BG_COLOR, dtype=np.uint8)
        mg = 20; n = len(self.colors)
        cv2.rectangle(canvas, (0, 0), (W, 70), (255, 240, 210), -1)
        cv2.putText(canvas, "SELECCIONA UN COLOR",
                    (mg, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (60, 120, 255), 2, cv2.LINE_AA)
        cv2.putText(canvas, "Flechas/WASD  |  ENTER seleccionar  |  ESC cancelar",
                    (mg, 65), cv2.FONT_HERSHEY_SIMPLEX, 0.48, (120, 90, 60), 1, cv2.LINE_AA)
        for i, c in enumerate(self.colors):
            row = i // self.COLS; col = i % self.COLS
            x = mg + col*(self.SWATCH_W+12)
            y = 90 + row*(self.SWATCH_H+30)
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
            name = c["name"][:12]
            (tw, _), _ = cv2.getTextSize(name, cv2.FONT_HERSHEY_SIMPLEX, 0.4, 1)
            cv2.putText(canvas, name,
                        (x+(self.SWATCH_W-tw)//2, y+self.SWATCH_H+18),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.4, (80, 60, 40), 1, cv2.LINE_AA)
        cv2.rectangle(canvas, (0, H-35), (W, H), (255, 240, 210), -1)
        cv2.putText(canvas, f"{n} colores disponibles",
                    (mg, H-12), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (120, 90, 60), 1, cv2.LINE_AA)
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


# ─────────────────────────────────────────────
#  SELECTOR DE IMÁGENES
# ─────────────────────────────────────────────
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
        self.image_paths.sort()
        self.thumbnails = []
        for p in self.image_paths:
            img = cv2.imread(p)
            if img is not None:
                th = cv2.resize(img, (self.THUMB_W, self.THUMB_H),
                                interpolation=cv2.INTER_AREA)
            else:
                th = np.full((self.THUMB_H, self.THUMB_W, 3), 230, dtype=np.uint8)
                put_text_centered(th, "?", self.THUMB_W//2, self.THUMB_H//2,
                                  1.5, (150, 100, 60), 3)
            self.thumbnails.append(th)

    def _build_grid(self, W, H):
        bg = np.zeros((H, W, 3), dtype=np.uint8)
        y_idx = np.arange(H, dtype=np.float32) / H
        bg[:, :, 0] = (255*(1-y_idx) + 230*y_idx).astype(np.uint8)[:, np.newaxis]
        bg[:, :, 1] = (210*(1-y_idx) + 245*y_idx).astype(np.uint8)[:, np.newaxis]
        bg[:, :, 2] = (135*(1-y_idx) + 255*y_idx).astype(np.uint8)[:, np.newaxis]
        draw_clouds_fast(bg, time.time())
        cv2.rectangle(bg, (0, 0), (W, 85), (255, 249, 230), -1)
        draw_gradient_bar(bg, 0, 82, W, 85, UI["vivo_cyan"], UI["vivo_rosa"])
        put_text_centered(bg, "SELECCIONA UNA IMAGEN PARA COLOREAR",
                          W//2, 32, 0.9, (60, 120, 255), 2)
        put_text_centered(bg, "Flechas/WASD  |  ENTER seleccionar  |  ESC cancelar",
                          W//2, 62, 0.48, (100, 80, 60), 1)
        mg = 20; pad = 14
        for i, (thumb, path) in enumerate(zip(self.thumbnails, self.image_paths)):
            row = i // self.COLS; col = i % self.COLS
            x = mg + col*(self.THUMB_W + pad)
            y = 98 + row*(self.THUMB_H + pad + 26)
            if y + self.THUMB_H + 26 > H - 40:
                break
            tw, th = self.THUMB_W, self.THUMB_H
            if i == self.selected:
                draw_rounded_rect(bg, x-6, y-6, x+tw+6, y+th+6, 6, UI["vivo_verde"], -1)
                draw_rounded_rect(bg, x-6, y-6, x+tw+6, y+th+6, 6, (235, 248, 255), -1)
                draw_neon_border(bg, x-4, y-4, x+tw+4, y+th+4, UI["vivo_verde"], 3)
            else:
                cv2.rectangle(bg, (x-2, y-2), (x+tw+2, y+th+2), UI["border_claro"], 1)
            bg[y:y+th, x:x+tw] = thumb
            fname  = os.path.basename(path)[:24]
            col_t  = UI["vivo_verde"] if i == self.selected else UI["text_claro"]
            cv2.putText(bg, fname, (x, y+th+20),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.40, col_t, 1, cv2.LINE_AA)
        cv2.rectangle(bg, (0, H-38), (W, H), (255, 249, 230), -1)
        put_text_centered(bg, f"[R] Recargar  |  {len(self.image_paths)} imagen(es)",
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
                if key in (ord('r'), ord('R')):
                    self._load()
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
