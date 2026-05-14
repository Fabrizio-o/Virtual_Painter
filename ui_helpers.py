"""
ui_helpers.py - Funciones de dibujo para la interfaz de Magic Paint
Contiene: sidebar cacheada, botones glassmorphism, nubes, título animado,
          primitivas geométricas y glow sin frame.copy().
"""
import cv2
import numpy as np
import math
import time

from config import UI, MAGIC_LETTERS, PAINT_LETTERS

# ─────────────────────────────────────────────
#  CACHE GLOBAL DE SIDEBAR
# ─────────────────────────────────────────────
_SIDEBAR_CACHE = {}

def _build_sidebar_strip(width, height):
    """Construye la tira de sidebar UNA sola vez y la cachea."""
    key = (width, height)
    if key in _SIDEBAR_CACHE:
        return _SIDEBAR_CACHE[key]
    strip = np.zeros((height, width, 3), dtype=np.uint8)
    y_idx = np.arange(height, dtype=np.float32) / height
    b_ch  = (180*(1-y_idx) + 140*y_idx).astype(np.uint8)
    g_ch  = (220*(1-y_idx) + 215*y_idx).astype(np.uint8)
    r_ch  = (255*(1-y_idx) + 235*y_idx).astype(np.uint8)
    strip[:, :, 0] = b_ch[:, np.newaxis]
    strip[:, :, 1] = g_ch[:, np.newaxis]
    strip[:, :, 2] = r_ch[:, np.newaxis]
    dot_spacing = 14
    for dy in range(0, height, dot_spacing):
        for dx in range(4, width, dot_spacing):
            if dy < height and dx < width:
                cv2.circle(strip, (dx, dy), 1, (160, 220, 240), -1)
    strip[0, :] = (140, 210, 255)
    strip[2, :] = (100, 220, 255)
    _SIDEBAR_CACHE[key] = strip
    return strip


def draw_glass_sidebar_fast(frame, x_start, width, height):
    """Copia la sidebar pre-renderizada sobre el frame — O(1), sin loops."""
    strip = _build_sidebar_strip(width, height)
    frame[:height, x_start:x_start+width] = strip


# ─────────────────────────────────────────────
#  NUBES ANIMADAS
# ─────────────────────────────────────────────
def draw_clouds_fast(frame, t):
    """Nubes animadas sin frame.copy(): blend directo sobre ROI superior."""
    H, W = frame.shape[:2]
    clouds = [
        (120,  55, 0.30, 1.00),
        (400,  35, 0.18, 1.30),
        (700,  75, 0.24, 0.85),
        (950,  45, 0.35, 0.75),
        (1100, 65, 0.20, 0.90),
    ]
    cloud_h = 110
    roi = frame[:cloud_h, :].copy()
    for base_x, cy_base, speed, s in clouds:
        offset = int((t * speed * 60) % (W + 300)) - 150
        cx     = (base_x + offset) % (W + 200) - 100
        cy     = cy_base
        col    = (255, 255, 255)
        cv2.ellipse(roi, (int(cx),       int(cy+30*s)), (int(80*s), int(30*s)), 0, 0, 360, col, -1)
        cv2.ellipse(roi, (int(cx-45*s),  int(cy+18*s)), (int(42*s), int(32*s)), 0, 0, 360, col, -1)
        cv2.ellipse(roi, (int(cx+45*s),  int(cy+14*s)), (int(46*s), int(36*s)), 0, 0, 360, col, -1)
        cv2.ellipse(roi, (int(cx+5*s),   int(cy)),      (int(38*s), int(32*s)), 0, 0, 360, col, -1)
        cv2.circle(roi, (int(cx-12*s), int(cy+10*s)), max(1, int(4*s)), (135, 180, 210), -1)
        cv2.circle(roi, (int(cx+14*s), int(cy+10*s)), max(1, int(4*s)), (135, 180, 210), -1)
        cv2.ellipse(roi, (int(cx+1*s), int(cy+18*s)),
                    (int(10*s), int(6*s)), 0, 0, 180, (135, 180, 210), max(1, int(2*s)))
    cv2.addWeighted(roi, 0.60, frame[:cloud_h, :], 0.40, 0, frame[:cloud_h, :])


# ─────────────────────────────────────────────
#  TÍTULO ANIMADO
# ─────────────────────────────────────────────
def draw_animated_title(frame, cx, start_y, t):
    font = cv2.FONT_HERSHEY_SIMPLEX
    scale = 0.82; thick = 2; lw = 23; gap = 3
    for letters, y in [(MAGIC_LETTERS, start_y), (PAINT_LETTERS, start_y+38)]:
        total_w = len(letters) * (lw + gap)
        x = cx - total_w // 2
        for i, (ch, col) in enumerate(letters):
            phase   = math.sin(t*2.8 + i*0.75)
            dy      = int(phase * 5)
            scale_f = scale + 0.07 * abs(phase)
            cv2.putText(frame, ch, (x+2, y+dy+2), font, scale_f, (200, 175, 140), thick+1, cv2.LINE_AA)
            cv2.putText(frame, ch, (x,   y+dy),   font, scale_f, col,             thick,   cv2.LINE_AA)
            x += lw + gap


# ─────────────────────────────────────────────
#  PRIMITIVAS GEOMÉTRICAS
# ─────────────────────────────────────────────
def _lerp_color(c1, c2, t):
    return tuple(int(c1[i]*(1-t) + c2[i]*t) for i in range(3))


def _fill_rounded(img, x1, y1, x2, y2, r, color):
    cv2.rectangle(img, (x1+r, y1), (x2-r, y2), color, -1)
    cv2.rectangle(img, (x1, y1+r), (x2, y2-r), color, -1)
    for cx, cy in [(x1+r, y1+r), (x2-r, y1+r), (x1+r, y2-r), (x2-r, y2-r)]:
        cv2.circle(img, (cx, cy), r, color, -1)


def _stroke_rounded(img, x1, y1, x2, y2, r, color, thickness):
    r = max(r, 1)
    cv2.line(img, (x1+r, y1), (x2-r, y1), color, thickness)
    cv2.line(img, (x1+r, y2), (x2-r, y2), color, thickness)
    cv2.line(img, (x1, y1+r), (x1, y2-r), color, thickness)
    cv2.line(img, (x2, y1+r), (x2, y2-r), color, thickness)
    cv2.ellipse(img, (x1+r, y1+r), (r, r), 180, 0, 90, color, thickness)
    cv2.ellipse(img, (x2-r, y1+r), (r, r), 270, 0, 90, color, thickness)
    cv2.ellipse(img, (x2-r, y2-r), (r, r),   0, 0, 90, color, thickness)
    cv2.ellipse(img, (x1+r, y2-r), (r, r),  90, 0, 90, color, thickness)


def draw_rounded_rect(img, x1, y1, x2, y2, r, color, thickness=-1):
    if thickness == -1:
        _fill_rounded(img, x1, y1, x2, y2, r, color)
    else:
        _stroke_rounded(img, x1, y1, x2, y2, r, color, thickness)


def draw_neon_border(img, x1, y1, x2, y2, color, thickness=2, glow=True):
    if glow:
        dim = tuple(max(0, int(c*0.4)) for c in color)
        cv2.rectangle(img, (x1-2, y1-2), (x2+2, y2+2), dim, thickness)
    cv2.rectangle(img, (x1, y1), (x2, y2), color, thickness)


def put_text_centered(img, text, cx, cy, font_scale, color, thickness=1):
    (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, font_scale, thickness)
    cv2.putText(img, text, (cx-tw//2, cy+th//2),
                cv2.FONT_HERSHEY_SIMPLEX, font_scale, color, thickness, cv2.LINE_AA)


# ─────────────────────────────────────────────
#  BARRA DE DEGRADADO (con caché)
# ─────────────────────────────────────────────
_gradient_cache = {}

def draw_gradient_bar(img, x1, y1, x2, y2, color_left, color_right):
    w   = x2 - x1
    key = (w, color_left, color_right)
    if key not in _gradient_cache:
        grad = np.zeros((1, w, 3), dtype=np.uint8)
        for i in range(w):
            t2 = i / max(w-1, 1)
            grad[0, i] = tuple(int(color_left[j]*(1-t2) + color_right[j]*t2) for j in range(3))
        _gradient_cache[key] = grad
    img[y1:y2, x1:x2] = _gradient_cache[key]


# ─────────────────────────────────────────────
#  GLOW Y BORDE NEON (sin frame.copy())
# ─────────────────────────────────────────────
def draw_glow_circle_fast(img, cx, cy, r, color, intensity=0.5):
    dim1 = tuple(max(0, int(c*0.25)) for c in color)
    dim2 = tuple(max(0, int(c*0.45)) for c in color)
    cv2.circle(img, (cx, cy), r+8, dim1, -1, cv2.LINE_AA)
    cv2.circle(img, (cx, cy), r+4, dim2, -1, cv2.LINE_AA)
    cv2.circle(img, (cx, cy), r,   color, -1, cv2.LINE_AA)


def draw_glass_border_fast(frame, x, y1, y2, color):
    dim = tuple(max(0, int(c*0.3)) for c in color)
    cv2.line(frame, (x-1, y1), (x-1, y2), dim, 3)
    cv2.line(frame, (x,   y1), (x,   y2), color, 1)


# ─────────────────────────────────────────────
#  BOTÓN GLASSMORPHISM OPTIMIZADO
# ─────────────────────────────────────────────
def draw_glass_button_fast(frame, x1, y1, x2, y2,
                           label, icon_char, accent_color,
                           is_active=False, is_hover=False,
                           hover_progress=0.0, t=0.0):
    W = x2-x1; H = y2-y1; r = 10

    # 1. Fondo
    bg_base = (18, 14, 22)
    if is_active:   bg = _lerp_color(bg_base, accent_color, 0.22)
    elif is_hover:  bg = _lerp_color(bg_base, accent_color, 0.14)
    else:           bg = _lerp_color(bg_base, accent_color, 0.06)
    _fill_rounded(frame, x1, y1, x2, y2, r, bg)

    # 2. Degradado interno (mitad superior, sin copy)
    mid    = y1 + H//2
    bright = tuple(min(255, int(bg[c]+20)) for c in range(3))
    _fill_rounded(frame, x1, y1, x2, mid, r, bright)
    _fill_rounded(frame, x1, y1+r, x2, mid, 0, bg)
    cv2.line(frame, (x1+r+2, y1+2), (x2-r-2, y1+2), (200, 200, 210), 1)

    # 3. Borde neon
    if is_active:
        pulse = 0.75 + 0.25*math.sin(t*4.0)
        bcol  = tuple(min(255, int(accent_color[c]*pulse)) for c in range(3))
        dim   = tuple(max(0,   int(accent_color[c]*0.3))   for c in range(3))
        _stroke_rounded(frame, x1-2, y1-2, x2+2, y2+2, r+2, dim, 2)
        _stroke_rounded(frame, x1,   y1,   x2,   y2,   r,   bcol, 2)
    elif is_hover:
        dim  = tuple(max(0, int(accent_color[c]*0.35)) for c in range(3))
        _stroke_rounded(frame, x1-1, y1-1, x2+1, y2+1, r+1, dim, 2)
        _stroke_rounded(frame, x1,   y1,   x2,   y2,   r, accent_color, 2)
    else:
        bcol = tuple(max(0, int(c*0.55)) for c in accent_color)
        _stroke_rounded(frame, x1, y1, x2, y2, r, bcol, 1)

    # 4. Icono circular
    icon_cx = x1+26; icon_cy = (y1+y2)//2
    if is_active:
        dim_icon = tuple(max(0, int(c*0.3)) for c in accent_color)
        cv2.circle(frame, (icon_cx, icon_cy), 16, dim_icon,     -1, cv2.LINE_AA)
        cv2.circle(frame, (icon_cx, icon_cy), 13, accent_color, -1, cv2.LINE_AA)
        cv2.circle(frame, (icon_cx, icon_cy), 13, (255,255,255), 1, cv2.LINE_AA)
        icon_text_col = (10, 10, 10)
    elif is_hover:
        icon_bg = _lerp_color(accent_color, (255,255,255), 0.2)
        cv2.circle(frame, (icon_cx, icon_cy), 13, icon_bg,       -1, cv2.LINE_AA)
        cv2.circle(frame, (icon_cx, icon_cy), 13, (255,255,255),  1, cv2.LINE_AA)
        icon_text_col = (10, 10, 10)
    else:
        icon_bg = tuple(max(0, int(c*0.45)) for c in accent_color)
        cv2.circle(frame, (icon_cx, icon_cy), 13, icon_bg,      -1, cv2.LINE_AA)
        cv2.circle(frame, (icon_cx, icon_cy), 13, accent_color,  1, cv2.LINE_AA)
        icon_text_col = (255, 255, 255)

    (iw, ih), _ = cv2.getTextSize(icon_char, cv2.FONT_HERSHEY_SIMPLEX, 0.50, 2)
    cv2.putText(frame, icon_char, (icon_cx-iw//2, icon_cy+ih//2),
                cv2.FONT_HERSHEY_SIMPLEX, 0.50, icon_text_col, 2, cv2.LINE_AA)

    # 5. Texto con sombra
    txt_x = x1+48; txt_y = (y1+y2)//2+6
    cv2.putText(frame, label, (txt_x+1, txt_y+1),
                cv2.FONT_HERSHEY_SIMPLEX, 0.48, (0,0,0), 2, cv2.LINE_AA)
    if is_active or is_hover:
        tcol = tuple(min(255, int(accent_color[c]*1.4)) for c in range(3))
    else:
        tcol = (255, 255, 255)
    cv2.putText(frame, label, (txt_x, txt_y),
                cv2.FONT_HERSHEY_SIMPLEX, 0.48, tcol, 1, cv2.LINE_AA)

    # 6. Barra de progreso hover
    if is_hover and hover_progress > 0:
        bar_y = y2-4; bar_w = int(W*hover_progress)
        cv2.rectangle(frame, (x1+r, bar_y), (x2-r, y2), (40, 40, 50), -1)
        if bar_w > 2:
            cv2.rectangle(frame, (x1+r, bar_y), (x1+r+bar_w, y2), accent_color, -1)

    # 7. Punto de estado activo
    if is_active:
        dot_x, dot_y = x2-8, y1+8
        pulse2 = 0.5 + 0.5*math.sin(t*5.0)
        dot_r  = int(4 + pulse2*2)
        dim_dot = tuple(max(0, int(c*0.4)) for c in accent_color)
        cv2.circle(frame, (dot_x, dot_y), dot_r+2, dim_dot,      -1, cv2.LINE_AA)
        cv2.circle(frame, (dot_x, dot_y), dot_r,   (255,255,255), -1, cv2.LINE_AA)
        cv2.circle(frame, (dot_x, dot_y), dot_r,   accent_color,   1, cv2.LINE_AA)
