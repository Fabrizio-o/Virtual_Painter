"""
+======================================================================+
|      MAGIC PAINT  - Pintura Virtual con Gestos de Mano  v5.2        |
|           Python + OpenCV + MediaPipe  |  Edicion Feria             |
|                   [OPTIMIZADO - MAX PERFORMANCE]                    |
+======================================================================+
OPTIMIZACIONES v5.2:
  - Sidebars pre-renderizadas (0 loops por frame)
  - Botones: eliminados todos los frame.copy() en glow/border
  - draw_glass_button: de ~8 copies a 0 copies por boton
  - draw_glow_circle: de 4 copies a 0
  - draw_glass_border: de 3 copies a linea directa
  - draw_clouds: cache de nubes por intervalo, no cada frame
  - _merge_canvas: vectorizado con numpy (sin loops Python)
  - _update_effects: particulas sin frame.copy(), trail eliminado
  - _draw_paint_blobs: cache de poligonos pre-calculados
  - Notificacion: sin frame.copy()
  - skip_frames aumentado en modo libre
  - UI cache agresivo: solo redibuja botones cuando cambia estado
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
    "skip_frames_free_mode": 3,   # mas agresivo en modo libre
    "particle_count": 12,         # reducido de 20 a 12
    "max_paint_splashes": 8,      # reducido de 15 a 8
    "ui_update_every": 1,
    "upec_logo_path": os.path.join(os.path.dirname(os.path.abspath(__file__)), "upec_logo.png"),
    # OPT: cada cuantos frames redibujar nubes en canvas
    "cloud_redraw_interval": 4,
}

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

APP_MODE_PAINT = "PAINT"
APP_MODE_COLOR = "COLOR"
APP_MODE_FREE  = "FREE"
TOOL_BRUSH  = "BRUSH"
TOOL_FILL   = "FILL"
TOOL_ERASER = "ERASER"
TIP = [4, 8, 12, 16, 20]
PIP = [3, 6, 10, 14, 18]

MAGIC_LETTERS = [
    ("M",(80,107,255)),("A",(60,159,255)),("G",(80,202,254)),
    ("I",(80,222,100)),("C",(251,219,72)),
]
PAINT_LETTERS = [
    ("P",(245,110,197)),("A",(157,107,255)),("I",(60,159,255)),
    ("N",(80,202,254)),("T",(80,107,255)),
]

# =============================================================
#  CACHE GLOBAL DE SIDEBAR (pre-renderizada una sola vez)
# =============================================================
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
    strip[:,:,0] = b_ch[:,np.newaxis]
    strip[:,:,1] = g_ch[:,np.newaxis]
    strip[:,:,2] = r_ch[:,np.newaxis]
    # Puntos perlados
    dot_spacing = 14
    for dy in range(0, height, dot_spacing):
        for dx in range(4, width, dot_spacing):
            if dy < height and dx < width:
                cv2.circle(strip, (dx, dy), 1, (160,220,240), -1)
    strip[0,:] = (140,210,255)
    strip[2,:] = (100,220,255)
    _SIDEBAR_CACHE[key] = strip
    return strip

def draw_glass_sidebar_fast(frame, x_start, width, height):
    """Copia la sidebar pre-renderizada - O(1), sin loops."""
    strip = _build_sidebar_strip(width, height)
    frame[:height, x_start:x_start+width] = strip


# =============================================================
#  NUBES ANIMADAS - VERSION LIGERA
# =============================================================
def draw_clouds_fast(frame, t):
    """Nubes sin frame.copy(): usa blend directo sobre ROI."""
    H, W = frame.shape[:2]
    clouds = [
        (120,  55, 0.30, 1.00),
        (400,  35, 0.18, 1.30),
        (700,  75, 0.24, 0.85),
        (950,  45, 0.35, 0.75),
        (1100, 65, 0.20, 0.90),
    ]
    # Crear overlay solo de la franja superior donde van las nubes
    cloud_h = 110  # las nubes estan en y < 110
    roi = frame[:cloud_h, :].copy()
    for base_x, cy_base, speed, s in clouds:
        offset = int((t * speed * 60) % (W + 300)) - 150
        cx = (base_x + offset) % (W + 200) - 100
        cy = cy_base
        col = (255,255,255)
        cv2.ellipse(roi, (int(cx),      int(cy+30*s)), (int(80*s),int(30*s)), 0,0,360,col,-1)
        cv2.ellipse(roi, (int(cx-45*s), int(cy+18*s)), (int(42*s),int(32*s)), 0,0,360,col,-1)
        cv2.ellipse(roi, (int(cx+45*s), int(cy+14*s)), (int(46*s),int(36*s)), 0,0,360,col,-1)
        cv2.ellipse(roi, (int(cx+5*s),  int(cy)),      (int(38*s),int(32*s)), 0,0,360,col,-1)
        cv2.circle(roi, (int(cx-12*s), int(cy+10*s)), max(1,int(4*s)), (135,180,210),-1)
        cv2.circle(roi, (int(cx+14*s), int(cy+10*s)), max(1,int(4*s)), (135,180,210),-1)
        cv2.ellipse(roi, (int(cx+1*s), int(cy+18*s)),
                    (int(10*s),int(6*s)), 0,0,180,(135,180,210),max(1,int(2*s)))
    # Un solo blend sobre el ROI, no sobre el frame completo
    cv2.addWeighted(roi, 0.60, frame[:cloud_h,:], 0.40, 0, frame[:cloud_h,:])


# =============================================================
#  TITULO ANIMADO
# =============================================================
def draw_animated_title(frame, cx, start_y, t):
    font = cv2.FONT_HERSHEY_SIMPLEX
    scale = 0.82; thick = 2; lw, gap = 23, 3
    for letters, y in [(MAGIC_LETTERS, start_y),(PAINT_LETTERS, start_y+38)]:
        total_w = len(letters)*(lw+gap)
        x = cx - total_w//2
        for i,(ch,col) in enumerate(letters):
            phase   = math.sin(t*2.8 + i*0.75)
            dy      = int(phase*5)
            scale_f = scale + 0.07*abs(phase)
            cv2.putText(frame,ch,(x+2,y+dy+2),font,scale_f,(200,175,140),thick+1,cv2.LINE_AA)
            cv2.putText(frame,ch,(x,y+dy),    font,scale_f,col,          thick,  cv2.LINE_AA)
            x += lw+gap


# =============================================================
#  HELPERS GEOMETRICOS (sin frame.copy())
# =============================================================
def _lerp_color(c1, c2, t):
    return tuple(int(c1[i]*(1-t)+c2[i]*t) for i in range(3))

def _fill_rounded(img, x1, y1, x2, y2, r, color):
    cv2.rectangle(img,(x1+r,y1),(x2-r,y2),color,-1)
    cv2.rectangle(img,(x1,y1+r),(x2,y2-r),color,-1)
    for cx,cy in [(x1+r,y1+r),(x2-r,y1+r),(x1+r,y2-r),(x2-r,y2-r)]:
        cv2.circle(img,(cx,cy),r,color,-1)

def _stroke_rounded(img, x1, y1, x2, y2, r, color, thickness):
    r = max(r,1)
    cv2.line(img,(x1+r,y1),(x2-r,y1),color,thickness)
    cv2.line(img,(x1+r,y2),(x2-r,y2),color,thickness)
    cv2.line(img,(x1,y1+r),(x1,y2-r),color,thickness)
    cv2.line(img,(x2,y1+r),(x2,y2-r),color,thickness)
    cv2.ellipse(img,(x1+r,y1+r),(r,r),180,0,90,color,thickness)
    cv2.ellipse(img,(x2-r,y1+r),(r,r),270,0,90,color,thickness)
    cv2.ellipse(img,(x2-r,y2-r),(r,r),0,  0,90,color,thickness)
    cv2.ellipse(img,(x1+r,y2-r),(r,r),90, 0,90,color,thickness)

def draw_rounded_rect(img,x1,y1,x2,y2,r,color,thickness=-1):
    if thickness==-1: _fill_rounded(img,x1,y1,x2,y2,r,color)
    else:             _stroke_rounded(img,x1,y1,x2,y2,r,color,thickness)

def draw_neon_border(img,x1,y1,x2,y2,color,thickness=2,glow=True):
    # Glow simplificado: solo 1 capa en lugar de 3, sin frame.copy()
    if glow:
        dim = tuple(max(0,int(c*0.4)) for c in color)
        cv2.rectangle(img,(x1-2,y1-2),(x2+2,y2+2),dim,thickness)
    cv2.rectangle(img,(x1,y1),(x2,y2),color,thickness)

def put_text_centered(img,text,cx,cy,font_scale,color,thickness=1):
    (tw,th),_=cv2.getTextSize(text,cv2.FONT_HERSHEY_SIMPLEX,font_scale,thickness)
    cv2.putText(img,text,(cx-tw//2,cy+th//2),cv2.FONT_HERSHEY_SIMPLEX,font_scale,color,thickness,cv2.LINE_AA)

_gradient_cache = {}
def draw_gradient_bar(img,x1,y1,x2,y2,color_left,color_right):
    w = x2-x1
    key = (w,color_left,color_right)
    if key not in _gradient_cache:
        grad = np.zeros((1,w,3),dtype=np.uint8)
        for i in range(w):
            t2 = i/max(w-1,1)
            grad[0,i] = tuple(int(color_left[j]*(1-t2)+color_right[j]*t2) for j in range(3))
        _gradient_cache[key] = grad
    img[y1:y2,x1:x2] = _gradient_cache[key]

def draw_glow_circle_fast(img, cx, cy, r, color, intensity=0.5):
    """Glow sin frame.copy(): dibuja circulos concentricos con alpha manual."""
    # Version ligera: 2 capas con color mas oscuro, sin copy
    dim1 = tuple(max(0,int(c*0.25)) for c in color)
    dim2 = tuple(max(0,int(c*0.45)) for c in color)
    cv2.circle(img,(cx,cy),r+8,dim1,-1,cv2.LINE_AA)
    cv2.circle(img,(cx,cy),r+4,dim2,-1,cv2.LINE_AA)
    cv2.circle(img,(cx,cy),r,color,-1,cv2.LINE_AA)

def draw_glass_border_fast(frame, x, y1, y2, color):
    """Borde neon sin frame.copy(): solo 2 lineas."""
    dim = tuple(max(0,int(c*0.3)) for c in color)
    cv2.line(frame,(x-1,y1),(x-1,y2),dim,3)
    cv2.line(frame,(x,y1),(x,y2),color,1)


# =============================================================
#  BOTON GLASSMORPHISM - VERSION OPTIMIZADA (0 frame.copy())
# =============================================================
def draw_glass_button_fast(frame, x1, y1, x2, y2,
                           label, icon_char, accent_color,
                           is_active=False, is_hover=False,
                           hover_progress=0.0, t=0.0):
    W = x2-x1; H = y2-y1; r = 10

    # 1. Fondo
    bg_base = (18,14,22)
    if is_active:   bg = _lerp_color(bg_base, accent_color, 0.22)
    elif is_hover:  bg = _lerp_color(bg_base, accent_color, 0.14)
    else:           bg = _lerp_color(bg_base, accent_color, 0.06)
    _fill_rounded(frame,x1,y1,x2,y2,r,bg)

    # 2. Degradado interno (solo mitad superior, sin copy)
    mid = y1 + H//2
    bright = tuple(min(255,int(bg[c]+20)) for c in range(3))
    _fill_rounded(frame,x1,y1,x2,mid,r,bright)
    _fill_rounded(frame,x1,y1+r,x2,mid,0,bg)  # corregir zona media
    # linea de brillo superior - directo
    cv2.line(frame,(x1+r+2,y1+2),(x2-r-2,y1+2),(200,200,210),1)

    # 3. Borde neon (sin glow pesado, solo borde + sombra directa)
    if is_active:
        pulse = 0.75 + 0.25*math.sin(t*4.0)
        bcol  = tuple(min(255,int(accent_color[c]*pulse)) for c in range(3))
        # glow ligero: 1 rect exterior oscuro
        dim = tuple(max(0,int(accent_color[c]*0.3)) for c in range(3))
        _stroke_rounded(frame,x1-2,y1-2,x2+2,y2+2,r+2,dim,2)
        _stroke_rounded(frame,x1,y1,x2,y2,r,bcol,2)
    elif is_hover:
        dim = tuple(max(0,int(accent_color[c]*0.35)) for c in range(3))
        _stroke_rounded(frame,x1-1,y1-1,x2+1,y2+1,r+1,dim,2)
        _stroke_rounded(frame,x1,y1,x2,y2,r,accent_color,2)
    else:
        bcol = tuple(max(0,int(c*0.55)) for c in accent_color)
        _stroke_rounded(frame,x1,y1,x2,y2,r,bcol,1)

    # 4. Icono circular
    icon_cx = x1+26; icon_cy = (y1+y2)//2
    if is_active:
        # glow del icono sin copy: circulo oscuro + circulo brillante
        dim_icon = tuple(max(0,int(c*0.3)) for c in accent_color)
        cv2.circle(frame,(icon_cx,icon_cy),16,dim_icon,-1,cv2.LINE_AA)
        cv2.circle(frame,(icon_cx,icon_cy),13,accent_color,-1,cv2.LINE_AA)
        cv2.circle(frame,(icon_cx,icon_cy),13,(255,255,255),1,cv2.LINE_AA)
        icon_text_col = (10,10,10)
    elif is_hover:
        icon_bg = _lerp_color(accent_color,(255,255,255),0.2)
        cv2.circle(frame,(icon_cx,icon_cy),13,icon_bg,-1,cv2.LINE_AA)
        cv2.circle(frame,(icon_cx,icon_cy),13,(255,255,255),1,cv2.LINE_AA)
        icon_text_col = (10,10,10)
    else:
        icon_bg = tuple(max(0,int(c*0.45)) for c in accent_color)
        cv2.circle(frame,(icon_cx,icon_cy),13,icon_bg,-1,cv2.LINE_AA)
        cv2.circle(frame,(icon_cx,icon_cy),13,accent_color,1,cv2.LINE_AA)
        icon_text_col = (255,255,255)

    (iw,ih),_ = cv2.getTextSize(icon_char,cv2.FONT_HERSHEY_SIMPLEX,0.50,2)
    cv2.putText(frame,icon_char,(icon_cx-iw//2,icon_cy+ih//2),
                cv2.FONT_HERSHEY_SIMPLEX,0.50,icon_text_col,2,cv2.LINE_AA)

    # 5. Texto con sombra directa (sin copy)
    txt_x = x1+48; txt_y = (y1+y2)//2+6
    cv2.putText(frame,label,(txt_x+1,txt_y+1),cv2.FONT_HERSHEY_SIMPLEX,0.48,(0,0,0),2,cv2.LINE_AA)
    if is_active or is_hover:
        tcol = tuple(min(255,int(accent_color[c]*1.4)) for c in range(3))
    else:
        tcol = (255,255,255)
    cv2.putText(frame,label,(txt_x,txt_y),cv2.FONT_HERSHEY_SIMPLEX,0.48,tcol,1,cv2.LINE_AA)

    # 6. Barra de progreso hover (simplificada)
    if is_hover and hover_progress > 0:
        bar_y = y2-4; bar_w = int(W*hover_progress)
        cv2.rectangle(frame,(x1+r,bar_y),(x2-r,y2),(40,40,50),-1)
        if bar_w > 2:
            cv2.rectangle(frame,(x1+r,bar_y),(x1+r+bar_w,y2),accent_color,-1)

    # 7. Punto de estado activo
    if is_active:
        dot_x,dot_y = x2-8,y1+8
        pulse2 = 0.5+0.5*math.sin(t*5.0)
        dot_r  = int(4+pulse2*2)
        dim_dot = tuple(max(0,int(c*0.4)) for c in accent_color)
        cv2.circle(frame,(dot_x,dot_y),dot_r+2,dim_dot,-1,cv2.LINE_AA)
        cv2.circle(frame,(dot_x,dot_y),dot_r,(255,255,255),-1,cv2.LINE_AA)
        cv2.circle(frame,(dot_x,dot_y),dot_r,accent_color,1,cv2.LINE_AA)


# =============================================================
#  FLOOD FILL
# =============================================================
def flood_fill(image,seed_pt,fill_color,tolerance):
    x,y=seed_pt; h,w=image.shape[:2]
    if not (0<=x<w and 0<=y<h): return image
    result=image.copy()
    mask=np.zeros((h+2,w+2),dtype=np.uint8)
    lo=hi=(tolerance,tolerance,tolerance)
    cv2.floodFill(result,mask,(x,y),fill_color,lo,hi,8|cv2.FLOODFILL_FIXED_RANGE)
    return result

def flood_fill_smooth(image,seed_pt,fill_color,tolerance):
    filled=flood_fill(image,seed_pt,fill_color,tolerance)
    diff=cv2.absdiff(image,filled)
    _,changed=cv2.threshold(cv2.cvtColor(diff,cv2.COLOR_BGR2GRAY),1,255,cv2.THRESH_BINARY)
    kernel=np.ones((3,3),np.uint8)
    border=cv2.dilate(changed,kernel,iterations=2)-changed
    blurred=cv2.GaussianBlur(filled,(3,3),0)
    mask_border=cv2.cvtColor(border,cv2.COLOR_GRAY2BGR)>0
    return np.where(mask_border,blurred,filled).astype(np.uint8)


# =============================================================
#  MOUSE CONTROLLER
# =============================================================
class MouseController:
    __slots__=('cfg','cam_w','cam_h','scr_w','scr_h','_sx','_sy',
               '_alpha','is_dragging','mouse_down','_was_pinching',
               'drag_start_pos','_pinch_frames','_click_cd','_rclick_cd',
               '_dclick_cd','_pos_history','_last_pinch_t','_dclick_window')
    def __init__(self,cfg,cam_w,cam_h):
        self.cfg=cfg; self.cam_w=cam_w; self.cam_h=cam_h
        self.scr_w,self.scr_h=(pyautogui.size() if PYAUTOGUI_OK else (1920,1080))
        self._sx=self._sy=None
        self._alpha=1.0/max(cfg["mouse_smoothing"],1)
        self.is_dragging=self.mouse_down=self._was_pinching=False
        self.drag_start_pos=None; self._pinch_frames=0
        self._click_cd=self._rclick_cd=self._dclick_cd=0
        self._pos_history=deque(maxlen=5); self._last_pinch_t=0.0; self._dclick_window=0.4
    def tick(self):
        for attr in('_click_cd','_rclick_cd','_dclick_cd'):
            v=getattr(self,attr)
            if v>0: setattr(self,attr,v-1)
    def cam_to_screen(self,cx,cy):
        mg=self.cfg["mouse_zone_margin"]
        nx=float(np.clip((cx/self.cam_w-mg)/(1-2*mg),0,1))
        ny=float(np.clip((cy/self.cam_h-mg)/(1-2*mg),0,1))
        return int(nx*self.scr_w),int(ny*self.scr_h)
    def smooth_move(self,cx,cy):
        if not PYAUTOGUI_OK: return
        sx,sy=self.cam_to_screen(cx,cy)
        if self._sx is None: self._sx,self._sy=float(sx),float(sy)
        else:
            a=self._alpha
            self._sx=a*sx+(1-a)*self._sx; self._sy=a*sy+(1-a)*self._sy
        self._pos_history.append((int(self._sx),int(self._sy)))
        if self.is_dragging: pyautogui.dragTo(int(self._sx),int(self._sy),button='left',_pause=False)
        else:                pyautogui.moveTo(int(self._sx),int(self._sy),_pause=False)
    def handle_pinch(self,is_pinching,cx,cy):
        if not PYAUTOGUI_OK: return ""
        action=""; now=time.time()
        if is_pinching:
            self._pinch_frames+=1
            if not self._was_pinching:
                if(self._click_cd==0 and self._dclick_cd==0 and
                        now-self._last_pinch_t<self._dclick_window):
                    pyautogui.doubleClick(_pause=False)
                    self._dclick_cd=self.cfg["double_click_cooldown"]
                    self._click_cd=self.cfg["click_cooldown_frames"]
                    self.is_dragging=False; action="DOBLE CLIC"
                elif self._click_cd==0:
                    pyautogui.mouseDown(button='left',_pause=False)
                    self.mouse_down=True
                    self.drag_start_pos=(int(self._sx or cx),int(self._sy or cy))
                    action="CLIC IZQ"
                self._last_pinch_t=now
            else:
                if(self.mouse_down and not self.is_dragging and
                        self._pinch_frames>=6 and self.drag_start_pos):
                    if self._sx and(abs(self._sx-self.drag_start_pos[0])+
                                     abs(self._sy-self.drag_start_pos[1]))>self.cfg["drag_min_move"]:
                        self.is_dragging=True; action="ARRASTRANDO"
                if self.is_dragging: action="ARRASTRANDO"
        else:
            if self._was_pinching:
                if self.is_dragging or self.mouse_down:
                    pyautogui.mouseUp(button='left',_pause=False)
                    self.is_dragging=self.mouse_down=False; action="SOLTADO"
                self._click_cd=self.cfg["click_cooldown_frames"]
            self._pinch_frames=0
        self._was_pinching=is_pinching
        return action
    def right_click(self):
        if not PYAUTOGUI_OK or self._rclick_cd>0: return ""
        if self.is_dragging or self.mouse_down:
            pyautogui.mouseUp(button='left',_pause=False)
            self.is_dragging=self.mouse_down=False
        pyautogui.click(button='right',_pause=False)
        self._rclick_cd=self.cfg["right_click_cooldown"]; return "CLIC DER"
    def release_all(self):
        if not PYAUTOGUI_OK: return
        if self.mouse_down or self.is_dragging:
            try: pyautogui.mouseUp(button='left',_pause=False)
            except: pass
        self.is_dragging=self.mouse_down=self._was_pinching=False
        self._pinch_frames=0; self._sx=self._sy=None
    @property
    def screen_pos(self):
        return (int(self._sx),int(self._sy)) if self._sx is not None else None


# =============================================================
#  SELECTOR DE COLORES
# =============================================================
class ColorPicker:
    COLS=6; SWATCH_W=90; SWATCH_H=60
    BG_COLOR=(255,249,230); SEL_COLOR=(80,222,100)
    EXTENDED_COLORS=[
        {"name":"Negro","bgr":(1,1,1)},{"name":"Gris Oscuro","bgr":(50,50,50)},
        {"name":"Gris","bgr":(128,128,128)},{"name":"Gris Claro","bgr":(180,180,180)},
        {"name":"Blanco","bgr":(255,255,255)},{"name":"Rojo Oscuro","bgr":(0,0,100)},
        {"name":"Rojo","bgr":(0,0,220)},{"name":"Rojo Brillante","bgr":(0,0,255)},
        {"name":"Naranja Oscuro","bgr":(0,60,160)},{"name":"Naranja","bgr":(0,120,255)},
        {"name":"Amarillo Oscuro","bgr":(0,180,200)},{"name":"Amarillo","bgr":(0,220,220)},
        {"name":"Amarillo Brill","bgr":(0,255,255)},{"name":"Lima","bgr":(80,255,80)},
        {"name":"Verde Lima","bgr":(120,255,0)},{"name":"Verde","bgr":(0,200,60)},
        {"name":"Verde Oscuro","bgr":(0,100,40)},{"name":"Verde Bosque","bgr":(0,130,60)},
        {"name":"Verde Oliva","bgr":(0,160,80)},{"name":"Cian Oscuro","bgr":(150,180,0)},
        {"name":"Cian","bgr":(220,200,0)},{"name":"Cian Brillante","bgr":(255,255,0)},
        {"name":"Azul Cielo","bgr":(230,150,0)},{"name":"Azul","bgr":(230,80,0)},
        {"name":"Azul Real","bgr":(200,50,0)},{"name":"Azul Marino","bgr":(130,30,30)},
        {"name":"Azul Oscuro","bgr":(100,20,20)},{"name":"Violeta","bgr":(100,0,100)},
        {"name":"Morado","bgr":(160,0,120)},{"name":"Purpura","bgr":(180,50,150)},
        {"name":"Magenta","bgr":(200,0,200)},{"name":"Rosa","bgr":(160,100,240)},
        {"name":"Rosa Oscuro","bgr":(100,50,120)},{"name":"Rosa Brillante","bgr":(180,150,220)},
        {"name":"Salmon","bgr":(100,130,180)},{"name":"Coral","bgr":(80,127,180)},
        {"name":"Marron Oscuro","bgr":(20,50,90)},{"name":"Marron","bgr":(30,80,140)},
        {"name":"Marron Claro","bgr":(60,120,160)},{"name":"Beige","bgr":(130,180,200)},
        {"name":"Piel Muy Clara","bgr":(180,200,220)},{"name":"Piel Clara","bgr":(140,180,210)},
        {"name":"Piel Clara Med.","bgr":(130,160,190)},{"name":"Piel Media","bgr":(110,140,170)},
        {"name":"Piel Morena","bgr":(80,110,140)},{"name":"Piel Oscura","bgr":(50,70,100)},
        {"name":"Piel Muy Osc.","bgr":(30,50,70)},{"name":"Cafe","bgr":(25,40,65)},
    ]
    def __init__(self): self.colors=self.EXTENDED_COLORS; self.selected=0
    def _build_grid(self,W,H):
        canvas=np.full((H,W,3),self.BG_COLOR,dtype=np.uint8); mg=20; n=len(self.colors)
        cv2.rectangle(canvas,(0,0),(W,70),(255,240,210),-1)
        cv2.putText(canvas,"SELECCIONA UN COLOR",(mg,40),cv2.FONT_HERSHEY_SIMPLEX,0.9,(60,120,255),2,cv2.LINE_AA)
        cv2.putText(canvas,"Flechas/WASD  |  ENTER seleccionar  |  ESC cancelar",(mg,65),cv2.FONT_HERSHEY_SIMPLEX,0.48,(120,90,60),1,cv2.LINE_AA)
        for i,c in enumerate(self.colors):
            row=i//self.COLS; col=i%self.COLS
            x=mg+col*(self.SWATCH_W+12); y=90+row*(self.SWATCH_H+30)
            if i==self.selected:
                cv2.rectangle(canvas,(x-6,y-6),(x+self.SWATCH_W+6,y+self.SWATCH_H+6),self.SEL_COLOR,3)
            else:
                cv2.rectangle(canvas,(x-2,y-2),(x+self.SWATCH_W+2,y+self.SWATCH_H+2),(200,180,150),1)
            cv2.rectangle(canvas,(x,y),(x+self.SWATCH_W,y+self.SWATCH_H),c["bgr"],-1)
            cv2.rectangle(canvas,(x,y),(x+self.SWATCH_W,y+self.SWATCH_H),(180,160,130),1)
            name=c["name"][:12]
            (tw,_),_=cv2.getTextSize(name,cv2.FONT_HERSHEY_SIMPLEX,0.4,1)
            cv2.putText(canvas,name,(x+(self.SWATCH_W-tw)//2,y+self.SWATCH_H+18),cv2.FONT_HERSHEY_SIMPLEX,0.4,(80,60,40),1,cv2.LINE_AA)
        cv2.rectangle(canvas,(0,H-35),(W,H),(255,240,210),-1)
        cv2.putText(canvas,f"{n} colores disponibles",(mg,H-12),cv2.FONT_HERSHEY_SIMPLEX,0.45,(120,90,60),1,cv2.LINE_AA)
        return canvas
    def show(self,W=1280,H=720):
        win="Selector de Color"
        cv2.namedWindow(win,cv2.WINDOW_NORMAL); cv2.resizeWindow(win,W,H)
        while True:
            cv2.imshow(win,self._build_grid(W,H))
            key=cv2.waitKey(50)&0xFF; n=len(self.colors)
            if key==27: cv2.destroyWindow(win); return None
            elif key in(13,32): cv2.destroyWindow(win); return self.colors[self.selected]
            elif key in(81,ord('a')): self.selected=(self.selected-1)%n
            elif key in(83,ord('d')): self.selected=(self.selected+1)%n
            elif key in(82,ord('w')): self.selected=max(0,self.selected-self.COLS)
            elif key in(84,ord('s')): self.selected=min(n-1,self.selected+self.COLS)


# =============================================================
#  SELECTOR DE IMAGENES
# =============================================================
class ImageSelector:
    THUMB_W=210; THUMB_H=158; COLS=5
    def __init__(self,images_dir,extensions):
        self.images_dir=images_dir; self.extensions=extensions
        self.image_paths=[]; self.thumbnails=[]; self.selected=0; self._load()
    def _load(self):
        self.image_paths=[]
        for ext in self.extensions:
            self.image_paths+=glob.glob(os.path.join(self.images_dir,ext))
        self.image_paths=sorted(self.image_paths); self.thumbnails=[]
        for p in self.image_paths:
            img=cv2.imread(p)
            if img is not None:
                th=cv2.resize(img,(self.THUMB_W,self.THUMB_H),interpolation=cv2.INTER_AREA)
            else:
                th=np.full((self.THUMB_H,self.THUMB_W,3),230,dtype=np.uint8)
                put_text_centered(th,"?",self.THUMB_W//2,self.THUMB_H//2,1.5,(150,100,60),3)
            self.thumbnails.append(th)
    def _build_grid(self,W,H):
        bg=np.zeros((H,W,3),dtype=np.uint8)
        y_idx=np.arange(H,dtype=np.float32)/H
        bg[:,:,0]=(255*(1-y_idx)+230*y_idx).astype(np.uint8)[:,np.newaxis]
        bg[:,:,1]=(210*(1-y_idx)+245*y_idx).astype(np.uint8)[:,np.newaxis]
        bg[:,:,2]=(135*(1-y_idx)+255*y_idx).astype(np.uint8)[:,np.newaxis]
        draw_clouds_fast(bg,time.time())
        cv2.rectangle(bg,(0,0),(W,85),(255,249,230),-1)
        draw_gradient_bar(bg,0,82,W,85,UI["vivo_cyan"],UI["vivo_rosa"])
        put_text_centered(bg,"SELECCIONA UNA IMAGEN PARA COLOREAR",W//2,32,0.9,(60,120,255),2)
        put_text_centered(bg,"Flechas/WASD  |  ENTER seleccionar  |  ESC cancelar",W//2,62,0.48,(100,80,60),1)
        mg,pad=20,14
        for i,(thumb,path) in enumerate(zip(self.thumbnails,self.image_paths)):
            row=i//self.COLS; col=i%self.COLS
            x=mg+col*(self.THUMB_W+pad); y=98+row*(self.THUMB_H+pad+26)
            if y+self.THUMB_H+26>H-40: break
            tw,th=self.THUMB_W,self.THUMB_H
            if i==self.selected:
                draw_rounded_rect(bg,x-6,y-6,x+tw+6,y+th+6,6,UI["vivo_verde"],-1)
                draw_rounded_rect(bg,x-6,y-6,x+tw+6,y+th+6,6,(235,248,255),-1)
                draw_neon_border(bg,x-4,y-4,x+tw+4,y+th+4,UI["vivo_verde"],3)
            else:
                cv2.rectangle(bg,(x-2,y-2),(x+tw+2,y+th+2),UI["border_claro"],1)
            bg[y:y+th,x:x+tw]=thumb
            fname=os.path.basename(path)[:24]
            col_t=UI["vivo_verde"] if i==self.selected else UI["text_claro"]
            cv2.putText(bg,fname,(x,y+th+20),cv2.FONT_HERSHEY_SIMPLEX,0.40,col_t,1,cv2.LINE_AA)
        cv2.rectangle(bg,(0,H-38),(W,H),(255,249,230),-1)
        put_text_centered(bg,f"[R] Recargar  |  {len(self.image_paths)} imagen(es)",W//2,H-19,0.44,UI["text_claro"],1)
        return bg
    def show(self,W=1280,H=720):
        win="Magic Paint - Seleccionar Imagen"
        cv2.namedWindow(win,cv2.WINDOW_NORMAL); cv2.resizeWindow(win,W,H)
        while True:
            cv2.imshow(win,self._build_grid(W,H))
            key=cv2.waitKey(50)&0xFF; n=len(self.image_paths)
            if n==0:
                if key in(ord('r'),ord('R')): self._load()
                elif key==27: cv2.destroyWindow(win); return None
                continue
            if key==27: cv2.destroyWindow(win); return None
            elif key in(13,32): cv2.destroyWindow(win); return self.image_paths[self.selected]
            elif key in(81,ord('a')): self.selected=(self.selected-1)%n
            elif key in(83,ord('d')): self.selected=(self.selected+1)%n
            elif key in(82,ord('w')): self.selected=max(0,self.selected-self.COLS)
            elif key in(84,ord('s')): self.selected=min(n-1,self.selected+self.COLS)
            elif key in(ord('r'),ord('R')): self._load()


# =============================================================
#  CLASE PRINCIPAL
# =============================================================
class VirtualPainter:

    class Particle:
        __slots__=('x','y','vx','vy','r','col','life','age','W','H')
        def __init__(self,W,H): self.reset(W,H)
        def reset(self,W,H):
            self.x=float(np.random.randint(0,W)); self.y=float(np.random.randint(0,H))
            self.vx=float(np.random.uniform(-1.2,1.2)); self.vy=float(np.random.uniform(-2.0,-0.4))
            self.r=int(np.random.randint(2,5))
            colors=[UI["vivo_cyan"],UI["vivo_verde"],UI["vivo_rosa"],
                    UI["vivo_naranja"],UI["vivo_amarillo"],UI["vivo_morado"]]
            self.col=colors[np.random.randint(0,len(colors))]
            self.life=int(np.random.randint(60,150)); self.age=0; self.W=W; self.H=H
        def update(self):
            self.x+=self.vx; self.y+=self.vy; self.vy+=0.04; self.age+=1
            if self.age>self.life or self.y>self.H+10 or self.x<0 or self.x>self.W:
                self.reset(self.W,self.H)
        def draw(self,frame):
            if self.age>=self.life: return
            r=max(1,int(self.r*(1.0-self.age/self.life)))
            cv2.circle(frame,(int(self.x),int(self.y)),r,self.col,-1,cv2.LINE_AA)

    def __init__(self):
        self.cfg=CONFIG; self.W=self.cfg["width"]; self.H=self.cfg["height"]
        self.app_mode=APP_MODE_PAINT; self.active_tool=TOOL_BRUSH
        self.canvas=np.zeros((self.H,self.W,3),dtype=np.uint8)
        self.color_image_orig=None; self.color_layer=None; self.color_image_path=None
        self.fill_tolerance=self.cfg["fill_tolerance"]
        self.drawing=False; self.prev_point=None
        self.brush_size=self.cfg["default_brush_size"]
        self.eraser_mode=False; self.color_index=2
        self.current_color=COLORS[2]["bgr"]
        self.show_hud=self.cfg["show_hud"]; self.fullscreen=False
        self.smooth_points=deque(maxlen=self.cfg["smoothing_points"])
        self.smooth_brush=deque(maxlen=10)
        self.undo_stack=deque(maxlen=self.cfg["max_undo_steps"])
        self.redo_stack=deque(maxlen=self.cfg["max_undo_steps"])
        self._push_undo()
        self._gesture_buffer=deque(maxlen=self.cfg["gesture_smoothing"])
        self._last_stable_gesture="NONE"; self._fill_done=False
        self._hover_btn=None; self._hover_btn_frames=0
        self._hover_btn_thr=20; self._btn_hover_progress=0
        self._notif=""; self._notif_timer=0; self._notif_color=UI["vivo_verde"]
        self._paint_splashes=[]
        self._particles=[self.Particle(self.W,self.H) for _ in range(self.cfg["particle_count"])]
        self._fps_buf=deque(maxlen=30); self._last_t=time.time()
        self._frame_counter=0; self._last_landmarks=None
        self._last_gesture="NONE"; self._hand_present=False
        self._free_bg_cache=None; self._free_bg_frame_cnt=-1; self._free_bg_interval=4
        # Cache del fondo cielo vectorizado
        self._sky_base=None
        self._cloud_frame_cnt=-1
        self._cloud_interval=self.cfg["cloud_redraw_interval"]
        self._sky_with_clouds=None
        # Cache de blobs de pintura (poligonos pre-calculados)
        self._blob_cache={}; self._blob_t_last=-99
        self.mouse_ctrl=MouseController(self.cfg,self.W,self.H)
        self._mouse_action=""; self._mouse_action_t=0
        self._upec_logo=None
        logo_path=self.cfg.get("upec_logo_path","")
        if os.path.isfile(logo_path):
            logo_raw=cv2.imread(logo_path,cv2.IMREAD_UNCHANGED)
            if logo_raw is not None: self._upec_logo=logo_raw
        self.mp_hands=mp.solutions.hands
        self.hands=self.mp_hands.Hands(
            static_image_mode=False,max_num_hands=1,
            min_detection_confidence=self.cfg["detection_confidence"],
            min_tracking_confidence=self.cfg["tracking_confidence"])
        self.mp_draw=mp.solutions.drawing_utils
        self.mp_draw_styles=mp.solutions.drawing_styles
        os.makedirs(self.cfg["images_dir"],exist_ok=True)
        os.makedirs(self.cfg["save_dir"],exist_ok=True)
        self.img_selector=ImageSelector(self.cfg["images_dir"],self.cfg["image_extensions"])
        self._build_ui()
        self._ui_update_counter=0
        # Pre-construir sidebar cache al inicio
        _build_sidebar_strip(self.SIDEBAR_W, self.H)

    def _notify(self,msg,color=None,dur=90):
        self._notif=msg; self._notif_timer=dur; self._notif_color=color or UI["vivo_verde"]

    def _get_layer(self):
        if self.app_mode==APP_MODE_COLOR and self.color_layer is not None: return self.color_layer
        return self.canvas

    def _set_layer(self,d):
        if self.app_mode==APP_MODE_COLOR and self.color_layer is not None: self.color_layer=d
        else: self.canvas=d

    def _push_undo(self):
        current=self._get_layer()
        if len(self.undo_stack)==0 or not np.array_equal(self.undo_stack[-1],current):
            self.undo_stack.append(current.copy()); self.redo_stack.clear()

    def undo(self):
        if len(self.undo_stack)>1:
            self.redo_stack.append(self.undo_stack.pop())
            self._set_layer(self.undo_stack[-1].copy()); self._notify("Deshacer",UI["vivo_amarillo"])

    def redo(self):
        if self.redo_stack:
            s=self.redo_stack.pop(); self.undo_stack.append(s)
            self._set_layer(s.copy()); self._notify("Rehacer",UI["vivo_amarillo"])

    def load_color_image(self,path):
        img=cv2.imread(path)
        if img is None: self._notify("Error abriendo imagen",UI["vivo_rojo"]); return False
        draw_start_x=self.SIDEBAR_W; draw_end_x=self.W-self.SIDEBAR_W
        img_resized=cv2.resize(img,(draw_end_x-draw_start_x,self.H),interpolation=cv2.INTER_AREA)
        full_canvas=np.zeros((self.H,self.W,3),dtype=np.uint8)
        full_canvas[:,draw_start_x:draw_end_x]=img_resized
        self.color_image_orig=full_canvas.copy(); self.color_layer=full_canvas.copy()
        self.color_image_path=path; self.app_mode=APP_MODE_COLOR
        self.undo_stack.clear(); self.redo_stack.clear(); self._push_undo()
        self._notify(f"Imagen: {os.path.basename(path)}",UI["vivo_cyan"]); return True

    def reset_color_image(self):
        if self.color_image_orig is not None:
            self._push_undo(); self.color_layer=self.color_image_orig.copy()
            self._notify("Imagen restaurada",UI["vivo_naranja"])

    def save_drawing(self,frame_bg=None):
        ts=datetime.now().strftime("%Y%m%d_%H%M%S"); ext=self.cfg["save_format"]
        if self.app_mode==APP_MODE_COLOR and self.color_layer is not None:
            save_img=self.color_layer[:,self.SIDEBAR_W:self.W-self.SIDEBAR_W]
            gray=cv2.cvtColor(save_img,cv2.COLOR_BGR2GRAY)
            _,thresh=cv2.threshold(gray,1,255,cv2.THRESH_BINARY)
            coords=cv2.findNonZero(thresh)
            if coords is not None:
                x,y,w,h=cv2.boundingRect(coords); save_img=save_img[y:y+h,x:x+w]
            path=os.path.join(self.cfg["save_dir"],f"colored_{ts}.{ext}")
            cv2.imwrite(path,save_img)
        elif frame_bg is not None:
            path=os.path.join(self.cfg["save_dir"],f"painting_{ts}.{ext}")
            cv2.imwrite(path,self._merge_canvas_fast(frame_bg))
        else:
            path=os.path.join(self.cfg["save_dir"],f"canvas_{ts}.{ext}")
            cv2.imwrite(path,self.canvas)
        self._notify("Guardado!",UI["vivo_verde"]); print(f"[OK] {path}"); return path

    def print_drawing(self,frame_bg=None):
        if self.app_mode==APP_MODE_COLOR and self.color_layer is not None:
            art=self.color_layer[:,self.SIDEBAR_W:self.W-self.SIDEBAR_W].copy()
        elif frame_bg is not None:
            merged=self._merge_canvas_fast(frame_bg)
            art=merged[:,self.SIDEBAR_W:self.W-self.SIDEBAR_W].copy()
        else: art=self.canvas.copy()
        PRINT_W=1240; ART_H=900
        art_h_orig,art_w_orig=art.shape[:2]
        art_resized=cv2.resize(art,(PRINT_W,int(art_h_orig*PRINT_W/art_w_orig)),interpolation=cv2.INTER_LANCZOS4)
        if art_resized.shape[0]>ART_H: art_resized=art_resized[:ART_H,:]
        elif art_resized.shape[0]<ART_H:
            pad=np.full((ART_H-art_resized.shape[0],PRINT_W,3),255,dtype=np.uint8)
            art_resized=np.vstack([art_resized,pad])
        HEADER_H=160; header=np.full((HEADER_H,PRINT_W,3),255,dtype=np.uint8)
        cv2.rectangle(header,(0,0),(PRINT_W,8),(0,120,50),-1)
        cv2.line(header,(0,HEADER_H-4),(PRINT_W,HEADER_H-4),(0,120,50),3)
        logo_x=20; text_x=logo_x
        if self._upec_logo is not None:
            lh,lw=self._upec_logo.shape[:2]; logo_h_target=HEADER_H-30
            lw_new=int(lw*logo_h_target/lh)
            logo_resized=cv2.resize(self._upec_logo,(lw_new,logo_h_target),interpolation=cv2.INTER_AREA)
            ly1,ly2=15,15+logo_h_target; lx1,lx2=logo_x,logo_x+lw_new
            if logo_resized.shape[2]==4:
                alpha_ch=logo_resized[:,:,3:4]/255.0; rgb=logo_resized[:,:,:3]
                bg_roi=header[ly1:ly2,lx1:lx2]
                header[ly1:ly2,lx1:lx2]=(rgb*alpha_ch+bg_roi*(1-alpha_ch)).astype(np.uint8)
            else: header[ly1:ly2,lx1:lx2]=logo_resized
            text_x=lx2+30
        font=cv2.FONT_HERSHEY_SIMPLEX
        available_w=PRINT_W-text_x-20; center_x=text_x+available_w//2
        for title,y,fs,th,col in [
            ("UNIVERSIDAD POLITECNICA ESTATAL DEL CARCHI",55,0.95,2,(0,100,40)),
            ("CARRERA DE COMPUTACION",92,0.75,2,(30,80,30)),
            ("Feria Agroalimentaria, Tecnologica y Turistica Sostenible UPEC - Pintura con Gestos de Mano",122,0.55,1,(80,80,80))]:
            (tw,_),_=cv2.getTextSize(title,font,fs,th)
            cv2.putText(header,title,(center_x-tw//2,y),font,fs,col,th,cv2.LINE_AA)
        date_str=datetime.now().strftime("%d/%m/%Y  %H:%M")
        (twd,_),_=cv2.getTextSize(date_str,font,0.44,1)
        cv2.putText(header,date_str,(PRINT_W-twd-20,148),font,0.44,(120,120,120),1,cv2.LINE_AA)
        FOOTER_H=40; footer=np.full((FOOTER_H,PRINT_W,3),255,dtype=np.uint8)
        cv2.rectangle(footer,(0,0),(PRINT_W,4),(0,120,50),-1)
        put_text_centered(footer,"UNIVERSIDAD POLITECNICA ESTATAL DEL CARCHI - UPEC  |  www.upec.edu.ec",
                          PRINT_W//2,26,0.42,(80,80,80),1)
        page=np.vstack([header,art_resized,footer])
        ts=datetime.now().strftime("%Y%m%d_%H%M%S")
        out_path=os.path.join(self.cfg["save_dir"],f"impresion_upec_{ts}.png")
        cv2.imwrite(out_path,page)
        preview_scale=min(1.0,900/page.shape[0])
        preview_w=int(page.shape[1]*preview_scale); preview_h=int(page.shape[0]*preview_scale)
        preview=cv2.resize(page,(preview_w,preview_h),interpolation=cv2.INTER_AREA)
        banner_h=36; banner=np.full((banner_h,preview_w,3),(30,30,30),dtype=np.uint8)
        cv2.putText(banner,f"Guardado: {out_path}   |   Ctrl+P para imprimir   |   ESC para cerrar",
                    (10,24),cv2.FONT_HERSHEY_SIMPLEX,0.44,(200,230,200),1,cv2.LINE_AA)
        win_print="Vista Previa de Impresion - ESC para cerrar"
        cv2.namedWindow(win_print,cv2.WINDOW_NORMAL)
        cv2.resizeWindow(win_print,preview_w,preview_h+banner_h)
        cv2.imshow(win_print,np.vstack([banner,preview]))
        self._notify("Impresion guardada!",UI["tool_print"]); print(f"[OK] {out_path}")
        return out_path

    def _build_ui(self):
        W,H=self.W,self.H
        self.SIDEBAR_W=165; self.SIDEBAR_H=H
        BTN_W=148; BTN_H=50; BTN_X=8; BTN_GAP=7; start_y=145
        def btn_y(i): return start_y+i*(BTN_H+BTN_GAP)
        self.left_buttons={
            "BRUSH":       (BTN_X,btn_y(0),BTN_X+BTN_W,btn_y(0)+BTN_H),
            "FILL":        (BTN_X,btn_y(1),BTN_X+BTN_W,btn_y(1)+BTN_H),
            "ERASER":      (BTN_X,btn_y(2),BTN_X+BTN_W,btn_y(2)+BTN_H),
            "COLOR_PICKER":(BTN_X,btn_y(3),BTN_X+BTN_W,btn_y(3)+BTN_H),
        }
        right_x=self.W-BTN_W-8
        self.right_buttons={
            "UNDO":     (right_x,btn_y(0),right_x+BTN_W,btn_y(0)+BTN_H),
            "REDO":     (right_x,btn_y(1),right_x+BTN_W,btn_y(1)+BTN_H),
            "CLEAR":    (right_x,btn_y(2),right_x+BTN_W,btn_y(2)+BTN_H),
            "SAVE":     (right_x,btn_y(3),right_x+BTN_W,btn_y(3)+BTN_H),
            "OPEN_IMG": (right_x,btn_y(4),right_x+BTN_W,btn_y(4)+BTN_H),
            "FREE_MODE":(right_x,btn_y(5),right_x+BTN_W,btn_y(5)+BTN_H),
            "PRINT":    (right_x,btn_y(6),right_x+BTN_W,btn_y(6)+BTN_H),
        }
        self.buttons={**self.left_buttons,**self.right_buttons}
        self.DRAW_X1=self.SIDEBAR_W; self.DRAW_X2=W-self.SIDEBAR_W

    def _fingers_up(self,lm):
        h,w=self.H,self.W
        pts=[(int(lm[i].x*w),int(lm[i].y*h)) for i in range(21)]
        up=[pts[TIP[0]][0]>pts[PIP[0]][0]]
        for i in range(1,5): up.append(pts[TIP[i]][1]<pts[PIP[i]][1])
        return up

    def _detect_gesture(self,lm):
        up=self._fingers_up(lm); n_up=sum(up)
        h,w=self.H,self.W
        def pt(i): return (int(lm[i].x*w),int(lm[i].y*h))
        thumb=pt(4); index=pt(8); wrist=pt(0)
        pinch=math.dist(thumb,index)
        if n_up==0: return "ERASER"
        if n_up>=4: return "OPEN"
        if up[1] and not up[2] and not up[3] and not up[4]:
            return "PINCH" if pinch<55 else "DRAW"
        if up[1] and up[2] and not up[3]: return "SELECT"
        if up[1] and up[2] and up[3] and not up[4]: return "THREE"
        if up[0] and not up[1] and not up[2] and not up[3]:
            if thumb[1]<wrist[1]-50: return "THUMB_UP"
            if thumb[1]>wrist[1]+50: return "THUMB_DOWN"
            return "OPEN"
        return "SELECT"

    def _stable_gesture(self,g):
        self._gesture_buffer.append(g)
        if len(self._gesture_buffer)==self._gesture_buffer.maxlen:
            from collections import Counter
            self._last_stable_gesture=Counter(self._gesture_buffer).most_common(1)[0][0]
        return self._last_stable_gesture

    def _smooth_pt(self,pt):
        self.smooth_points.append(pt)
        return (int(np.mean([p[0] for p in self.smooth_points])),
                int(np.mean([p[1] for p in self.smooth_points])))

    def _smooth_bs(self,s):
        self.smooth_brush.append(s); return int(np.mean(self.smooth_brush))

    def _stroke(self,pt,color,size):
        layer=self._get_layer()
        if self.prev_point: cv2.line(layer,self.prev_point,pt,color,size,cv2.LINE_AA)
        cv2.circle(layer,pt,size//2,color,-1,cv2.LINE_AA)
        self._set_layer(layer)
        if not self.prev_point and color!=(0,0,0):
            if len(self._paint_splashes)<self.cfg["max_paint_splashes"]:
                self._paint_splashes.append([pt[0],pt[1],size+4,color,0,14])

    def _apply_fill(self,pt):
        self._push_undo()
        result=flood_fill_smooth(self._get_layer(),pt,self.current_color,self.fill_tolerance)
        self._set_layer(result)
        if len(self._paint_splashes)<self.cfg["max_paint_splashes"]:
            self._paint_splashes.append([pt[0],pt[1],25,self.current_color,0,20])
        self._notify(f"Relleno (tol:{self.fill_tolerance})",UI["vivo_naranja"])

    def _check_btn_hover(self,pt,frame_bg=None):
        x,y=pt
        for name,(x1,y1,x2,y2) in self.buttons.items():
            if x1<=x<=x2 and y1<=y<=y2:
                if self._hover_btn==name:
                    self._hover_btn_frames+=1
                    self._btn_hover_progress=min(1.0,self._hover_btn_frames/self._hover_btn_thr)
                    if self._hover_btn_frames>=self._hover_btn_thr:
                        self._trigger_btn(name,frame_bg); self._hover_btn_frames=0
                else:
                    self._hover_btn=name; self._hover_btn_frames=0; self._btn_hover_progress=0
                return True
        self._hover_btn=None; self._hover_btn_frames=0; self._btn_hover_progress=0; return False

    def _trigger_btn(self,name,frame_bg=None):
        if   name=="UNDO":     self.undo()
        elif name=="REDO":     self.redo()
        elif name=="SAVE":     self.save_drawing(frame_bg)
        elif name=="PRINT":    self.print_drawing(frame_bg)
        elif name=="CLEAR":
            self._push_undo()
            if self.app_mode==APP_MODE_COLOR and self.color_image_orig is not None:
                self.color_layer=self.color_image_orig.copy(); self._notify("Imagen restaurada",UI["vivo_naranja"])
            else:
                self.canvas[:]=0; self._notify("Canvas limpiado",UI["vivo_rojo"])
        elif name=="BRUSH":  self.active_tool=TOOL_BRUSH;  self.eraser_mode=False; self._notify("Pincel",UI["tool_brush"])
        elif name=="FILL":   self.active_tool=TOOL_FILL;   self.eraser_mode=False; self._notify("Relleno",UI["tool_fill"])
        elif name=="ERASER": self.active_tool=TOOL_ERASER; self.eraser_mode=True;  self._notify("Borrador",UI["tool_eraser"])
        elif name=="OPEN_IMG":
            self.img_selector._load(); path=self.img_selector.show(self.W,self.H)
            if path: self.load_color_image(path)
        elif name=="FREE_MODE":  self._toggle_free_mode()
        elif name=="COLOR_PICKER": self._open_color_picker()

    def _open_color_picker(self):
        picker=ColorPicker(); result=picker.show(self.W,self.H)
        if result:
            self.current_color=result["bgr"]
            self.color_index=-1
            for i,c in enumerate(COLORS):
                if c["bgr"]==result["bgr"]: self.color_index=i; break
            self.eraser_mode=False; self.active_tool=TOOL_BRUSH
            self._notify(f"Color: {result['name']}",result["bgr"])

    def _toggle_free_mode(self):
        if self.app_mode==APP_MODE_FREE:
            self.mouse_ctrl.release_all(); self.app_mode=APP_MODE_PAINT
            self._free_bg_cache=None; self._notify("Modo: Pintura Libre",UI["mode_paint"])
        else:
            if not PYAUTOGUI_OK: self._notify("Instala: pip install pyautogui",UI["vivo_rojo"]); return
            self.mouse_ctrl.release_all(); self.app_mode=APP_MODE_FREE
            self._free_bg_cache=None; self._notify("MODO LIBRE - Controla el mouse!",UI["mode_free"])

    def _process_free_mode(self,lm,gesture):
        h,w=self.H,self.W
        def pt(i): return (int(lm[i].x*w),int(lm[i].y*h))
        index=pt(8); thumb=pt(4)
        pinch_dist=math.dist(thumb,index); is_pinching=pinch_dist<self.cfg["pinch_threshold"]
        self.mouse_ctrl.smooth_move(index[0],index[1])
        if gesture=="SELECT" and not is_pinching:
            a=self.mouse_ctrl.right_click()
        elif gesture in("DRAW","PINCH") or is_pinching:
            self.mouse_ctrl.handle_pinch(True,index[0],index[1])
        else:
            self.mouse_ctrl.handle_pinch(False,index[0],index[1])
        self.mouse_ctrl.tick()
        return {"index":index,"thumb":thumb,"pinch_dist":pinch_dist,
                "is_pinching":is_pinching,"is_dragging":self.mouse_ctrl.is_dragging}

    def _get_sky_base(self):
        """Fondo cielo vectorizado, construido una sola vez."""
        if self._sky_base is None:
            sky = np.zeros((self.H, self.W, 3), dtype=np.uint8)
            y_idx = np.arange(self.H, dtype=np.float32)/self.H
            sky[:,:,0] = (255*(1-y_idx)+230*y_idx).astype(np.uint8)[:,np.newaxis]
            sky[:,:,1] = (210*(1-y_idx)+245*y_idx).astype(np.uint8)[:,np.newaxis]
            sky[:,:,2] = (135*(1-y_idx)+255*y_idx).astype(np.uint8)[:,np.newaxis]
            self._sky_base = sky
        return self._sky_base

    def _merge_canvas_fast(self, frame):
        """Fondo con nubes cacheadas + canvas: mucho mas rapido."""
        # Redibujar nubes solo cada N frames
        if (self._sky_with_clouds is None or
                self._frame_counter - self._cloud_frame_cnt >= self._cloud_interval):
            sky = self._get_sky_base().copy()
            draw_clouds_fast(sky, time.time())
            self._sky_with_clouds = sky
            self._cloud_frame_cnt = self._frame_counter

        output = self._sky_with_clouds.copy()
        op = self.cfg["canvas_opacity"]
        if np.any(self.canvas):
            mask = (self.canvas.sum(axis=2) > 0)
            if np.any(mask):
                # Blend vectorizado sin loops
                canvas_roi = self.canvas[mask]
                sky_roi    = output[mask]
                output[mask] = (sky_roi*(1-op) + canvas_roi*op).astype(np.uint8)
        return output

    def _build_free_bg(self,frame):
        output = self._get_sky_base().copy()
        draw_clouds_fast(output, time.time())
        # Blend vectorizado
        cv2.addWeighted(frame,0.25,output,0.75,0,output)
        return output

    def _update_effects_fast(self, frame):
        """Efectos sin frame.copy(): particulas y splashes directos."""
        for p in self._particles:
            p.update(); p.draw(frame)

        alive=[]
        for s in self._paint_splashes:
            x,y,r,col,age,max_age=s
            if age<max_age:
                a=1.0-age/max_age
                cr=max(1,int(r*(1+age*0.3)))
                # Sin frame.copy(): dibujar directo con color atenuado
                dim_col = tuple(int(col[c]*a*0.6) for c in range(3))
                cv2.circle(frame,(x,y),cr,dim_col,-1,cv2.LINE_AA)
                s[4]+=1; alive.append(s)
        self._paint_splashes=alive

    def _draw_paint_blobs_fast(self, frame, t):
        """Manchas de pintura con cache de poligonos."""
        paint_colors=[(80,107,255),(80,202,254),(80,222,100),(251,219,72),
                      (60,159,255),(245,110,197),(157,107,255),(251,160,80)]
        blob_w=self.SIDEBAR_W//len(paint_colors)
        # Recalcular solo si han pasado suficientes ms (ondas lentas)
        t_bucket = int(t * 15)  # bucket de ~66ms
        if t_bucket != self._blob_t_last:
            self._blob_cache = {}
            self._blob_t_last = t_bucket
            for side_x in [0, self.W-self.SIDEBAR_W]:
                for i,pc in enumerate(paint_colors):
                    bx=side_x+i*blob_w; by=self.H-20
                    wave=int(6*math.sin(t*2.0+i*0.8))
                    peak=int(4*math.sin(t*2.5+i*1.1))
                    pts=np.array([[bx,self.H],[bx,by+wave],
                                  [bx+blob_w//2,by-10+peak],
                                  [bx+blob_w,by+wave],[bx+blob_w,self.H]],dtype=np.int32)
                    self._blob_cache[(side_x,i)] = (pts, pc)
        for (pts,pc) in self._blob_cache.values():
            cv2.fillPoly(frame,[pts],pc)

    # ==================================================================
    #  DRAW UI OPTIMIZADO
    # ==================================================================
    def _draw_ui(self,frame,gesture,fps):
        if not self.show_hud: return frame
        W,H=self.W,self.H
        is_free=(self.app_mode==APP_MODE_FREE)
        t=time.time()

        # Sidebars - copia O(1) desde cache pre-renderizado
        draw_glass_sidebar_fast(frame, 0,             self.SIDEBAR_W, H)
        draw_glass_sidebar_fast(frame, W-self.SIDEBAR_W, self.SIDEBAR_W, H)

        # Bordes neon - sin frame.copy()
        border_col=(0,206,209) if not is_free else (251,219,72)
        draw_glass_border_fast(frame, self.SIDEBAR_W,   0, H, border_col)
        draw_glass_border_fast(frame, W-self.SIDEBAR_W, 0, H, (255,20,147))

        # Manchas de pintura cacheadas
        self._draw_paint_blobs_fast(frame, t)

        # Header central
        header_h=52
        frame[0:header_h, self.SIDEBAR_W:W-self.SIDEBAR_W] = (18,14,24)
        frame[0:2, self.SIDEBAR_W:W-self.SIDEBAR_W] = (80,60,100)
        draw_gradient_bar(frame,self.SIDEBAR_W,header_h-2,W-self.SIDEBAR_W,header_h,(0,206,209),(255,20,147))

        # Panel titulo
        cv2.rectangle(frame,(4,4),(self.SIDEBAR_W-4,133),(40,34,55),-1)
        _stroke_rounded(frame,4,4,self.SIDEBAR_W-4,133,8,(80,60,100),1)
        cv2.rectangle(frame,(4,4),(self.SIDEBAR_W-4,6),(0,206,209),-1)
        draw_animated_title(frame,self.SIDEBAR_W//2,40,t)
        draw_gradient_bar(frame,8,82,self.SIDEBAR_W-8,84,(0,206,209),(255,20,147))
        put_text_centered(frame,"v5.2",self.SIDEBAR_W//2,98,0.38,(150,130,170),1)
        put_text_centered(frame,"GESTOS",self.SIDEBAR_W//2,116,0.38,(150,130,170),1)

        # Badge modo
        mode_labels={
            APP_MODE_PAINT:("* PINTURA",(50,205,50)),
            APP_MODE_COLOR:("* COLOREAR",(30,144,255)),
            APP_MODE_FREE: ("* LIBRE",(0,206,209)),
        }
        mode_txt,mode_col=mode_labels[self.app_mode]
        bx=self.SIDEBAR_W+14
        (btw,bth),_=cv2.getTextSize(mode_txt,cv2.FONT_HERSHEY_SIMPLEX,0.52,2)
        cv2.rectangle(frame,(bx-6,8),(bx+btw+8,header_h-8),(28,22,38),-1)
        _stroke_rounded(frame,bx-6,8,bx+btw+8,header_h-8,5,mode_col,2)
        cv2.putText(frame,mode_txt,(bx,header_h//2+8),cv2.FONT_HERSHEY_SIMPLEX,0.52,mode_col,2,cv2.LINE_AA)

        # Gesto
        GESTURE_ICONS={"DRAW":"DIBUJANDO","SELECT":"SELECCIONAR","ERASER":"BORRADOR",
                       "OPEN":"PAUSADO","PINCH":"GROSOR","THUMB_UP":"SGTE COLOR",
                       "THUMB_DOWN":"ANT COLOR","NONE":"Sin mano","THREE":"3 DEDOS"}
        g_label=GESTURE_ICONS.get(gesture,gesture)
        g_col=(50,205,50) if gesture=="DRAW" else \
              (254,202,80) if gesture in("SELECT","PINCH") else \
              (147,0,211)  if gesture=="ERASER" else (150,130,170)
        (gtw,_),_=cv2.getTextSize(g_label,cv2.FONT_HERSHEY_SIMPLEX,0.44,1)
        gx=W-self.SIDEBAR_W-gtw-16
        cv2.putText(frame,"Gesto:",(gx-58,header_h//2+7),cv2.FONT_HERSHEY_SIMPLEX,0.38,(150,130,170),1,cv2.LINE_AA)
        cv2.putText(frame,g_label,(gx,header_h//2+7),cv2.FONT_HERSHEY_SIMPLEX,0.44,g_col,1,cv2.LINE_AA)

        # FPS
        fps_col=(50,205,50) if fps>25 else (254,202,80)
        cv2.putText(frame,f"FPS:{int(fps)}",(W-self.SIDEBAR_W+8,header_h-10),
                    cv2.FONT_HERSHEY_SIMPLEX,0.42,fps_col,1,cv2.LINE_AA)

        # Botones izquierdos
        LEFT_BTN_INFO={
            "BRUSH":       ("PINCEL",  "B",UI["tool_brush"]),
            "FILL":        ("RELLENO", "R",UI["tool_fill"]),
            "ERASER":      ("BORRADOR","E",UI["tool_eraser"]),
            "COLOR_PICKER":("COLORES", "C",UI["tool_color"]),
        }
        for name,(x1,y1,x2,y2) in self.left_buttons.items():
            if name not in LEFT_BTN_INFO: continue
            label,icon,accent=LEFT_BTN_INFO[name]
            is_hov=(self._hover_btn==name)
            is_active=(name=="BRUSH"  and self.active_tool==TOOL_BRUSH) or \
                      (name=="FILL"   and self.active_tool==TOOL_FILL)  or \
                      (name=="ERASER" and self.active_tool==TOOL_ERASER)
            draw_glass_button_fast(frame,x1,y1,x2,y2,label,icon,accent,
                                   is_active,is_hov,
                                   self._btn_hover_progress if is_hov else 0.0,t)

        # Botones derechos
        RIGHT_BTN_INFO={
            "UNDO":     ("DESHACER","<",UI["tool_undo"]),
            "REDO":     ("REHACER", ">",UI["tool_redo"]),
            "CLEAR":    ("LIMPIAR", "X",UI["tool_clear"]),
            "SAVE":     ("GUARDAR", "S",UI["tool_save"]),
            "OPEN_IMG": ("ABRIR",   "O",UI["tool_open"]),
            "FREE_MODE":("LIBRE",   "L",UI["tool_free"]),
            "PRINT":    ("IMPRIMIR","P",UI["tool_print"]),
        }
        for name,(x1,y1,x2,y2) in self.right_buttons.items():
            if name not in RIGHT_BTN_INFO: continue
            label,icon,accent=RIGHT_BTN_INFO[name]
            is_hov=(self._hover_btn==name)
            is_active=(name=="FREE_MODE" and is_free)
            draw_glass_button_fast(frame,x1,y1,x2,y2,label,icon,accent,
                                   is_active,is_hov,
                                   self._btn_hover_progress if is_hov else 0.0,t)

        # Indicador de color actual
        col_indicator_y=self.left_buttons["COLOR_PICKER"][3]+14
        if col_indicator_y+30<H-55:
            put_text_centered(frame,"COLOR ACTUAL",self.SIDEBAR_W//2,col_indicator_y+8,0.32,(150,130,170),1)
            col_cx=self.SIDEBAR_W//2; col_cy=col_indicator_y+28
            cur=self.current_color
            if not self.eraser_mode:
                dim=tuple(max(0,int(c*0.3)) for c in cur)
                cv2.circle(frame,(col_cx,col_cy),18,dim,-1,cv2.LINE_AA)
                cv2.circle(frame,(col_cx,col_cy),14,cur,-1,cv2.LINE_AA)
                cv2.circle(frame,(col_cx,col_cy),14,(255,255,255),1,cv2.LINE_AA)
            else:
                cv2.circle(frame,(col_cx,col_cy),14,(200,180,150),-1,cv2.LINE_AA)
                cv2.putText(frame,"E",(col_cx-5,col_cy+5),cv2.FONT_HERSHEY_SIMPLEX,0.45,(50,50,50),2)

        # Notificacion - sin frame.copy()
        if self._notif_timer>0:
            self._notif_timer-=1
            nx=self.SIDEBAR_W+18; ny=H-55
            (nw,nh),_=cv2.getTextSize(self._notif,cv2.FONT_HERSHEY_SIMPLEX,0.58,2)
            _fill_rounded(frame,nx-10,ny-nh-10,nx+nw+10,ny+10,8,(18,14,24))
            _stroke_rounded(frame,nx-10,ny-nh-10,nx+nw+10,ny+10,8,self._notif_color,2)
            cv2.putText(frame,self._notif,(nx+1,ny+1),cv2.FONT_HERSHEY_SIMPLEX,0.58,(0,0,0),3,cv2.LINE_AA)
            cv2.putText(frame,self._notif,(nx,ny),cv2.FONT_HERSHEY_SIMPLEX,0.58,self._notif_color,2,cv2.LINE_AA)

        self._ui_update_counter+=1
        return frame

    def _draw_cursor(self,frame,pt,gesture):
        col=self.current_color if not self.eraser_mode else (180,160,130)
        r=self.brush_size+4
        if self.active_tool==TOOL_FILL and gesture=="DRAW":
            cv2.rectangle(frame,(pt[0]-14,pt[1]-8),(pt[0]+14,pt[1]+18),col,-1)
            cv2.rectangle(frame,(pt[0]-14,pt[1]-8),(pt[0]+14,pt[1]+18),(254,202,80),2)
            cv2.putText(frame,"F",(pt[0]-5,pt[1]+12),cv2.FONT_HERSHEY_SIMPLEX,0.55,(20,20,20),2,cv2.LINE_AA)
        elif self.active_tool==TOOL_ERASER or self.eraser_mode:
            er=self.brush_size*self.cfg["eraser_multiplier"]+4
            cv2.circle(frame,pt,er,(180,160,130),2,cv2.LINE_AA)
            cv2.line(frame,(pt[0]-er,pt[1]),(pt[0]+er,pt[1]),(180,160,130),1)
            cv2.line(frame,(pt[0],pt[1]-er),(pt[0],pt[1]+er),(180,160,130),1)
        elif gesture=="DRAW":
            draw_glow_circle_fast(frame,pt[0],pt[1],r,col,0.4)
            cv2.circle(frame,pt,4,(255,255,255),-1)
        elif gesture=="SELECT":
            cv2.drawMarker(frame,pt,(254,202,80),cv2.MARKER_CROSS,26,2,cv2.LINE_AA)
            cv2.circle(frame,pt,14,(254,202,80),1,cv2.LINE_AA)
        else:
            cv2.circle(frame,pt,12,(150,130,170),1,cv2.LINE_AA)
            cv2.circle(frame,pt,3,(150,130,170),-1)

    def _draw_free_cursor(self,output,info):
        idx=info["index"]; thumb=info["thumb"]
        dist=info["pinch_dist"]; is_p=info["is_pinching"]; is_d=info["is_dragging"]
        cv2.line(output,thumb,idx,(150,130,170),1,cv2.LINE_AA)
        if is_d:
            draw_glow_circle_fast(output,idx[0],idx[1],16,(60,159,255),0.5)
            cv2.putText(output,"DRAG",(idx[0]+22,idx[1]-8),cv2.FONT_HERSHEY_SIMPLEX,0.55,(60,159,255),2)
        elif is_p:
            draw_glow_circle_fast(output,idx[0],idx[1],14,(50,205,50),0.6)
        else:
            cv2.circle(output,idx,14,(0,206,209),2,cv2.LINE_AA)
            cv2.circle(output,idx,4,(0,206,209),-1)
        bx,by=self.SIDEBAR_W+20,self.H-60; bw=180
        thr=self.cfg["pinch_threshold"]; rel=float(np.clip(dist/(thr*2),0,1))
        filled=int(bw*(1-rel))
        cv2.putText(output,"PINCH",(bx,by-4),cv2.FONT_HERSHEY_SIMPLEX,0.40,(150,130,170),1,cv2.LINE_AA)
        cv2.rectangle(output,(bx,by),(bx+bw,by+10),(28,22,38),-1)
        cv2.rectangle(output,(bx,by),(bx+filled,by+10),(50,205,50) if is_p else (0,206,209),-1)
        _stroke_rounded(output,bx,by,bx+bw,by+10,2,(80,60,100),1)

    def run(self):
        cap=cv2.VideoCapture(self.cfg["camera_index"])
        cap.set(cv2.CAP_PROP_FRAME_WIDTH,self.W)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT,self.H)
        cap.set(cv2.CAP_PROP_FPS,60)
        cap.set(cv2.CAP_PROP_BUFFERSIZE,1)
        if not cap.isOpened(): print("[ERROR] No se pudo abrir la camara."); return

        win="Magic Paint v5.2 - OPTIMIZADO"
        cv2.namedWindow(win,cv2.WINDOW_NORMAL); cv2.resizeWindow(win,self.W,self.H)
        _print_banner()

        last_bg=None; gesture="NONE"; _lm_draw=None; _smooth_d=None; _free_info=None

        while True:
            ret,frame=cap.read()
            if not ret: print("[ERROR] Frame fallido."); break
            if self.cfg["flip_horizontal"]: frame=cv2.flip(frame,1)
            fh,fw=frame.shape[:2]
            if fw!=self.W or fh!=self.H: frame=cv2.resize(frame,(self.W,self.H))
            last_bg=frame.copy()

            now=time.time()
            self._fps_buf.append(1.0/max(now-self._last_t,1e-6)); self._last_t=now
            fps=float(np.mean(self._fps_buf))
            self._frame_counter+=1

            skip=self.cfg["skip_frames_free_mode"] if self.app_mode==APP_MODE_FREE \
                 else self.cfg["skip_frames_detection"]
            process_hands=(self._frame_counter%(skip+1)==0)

            if process_hands:
                rgb=cv2.cvtColor(frame,cv2.COLOR_BGR2RGB); rgb.flags.writeable=False
                res=self.hands.process(rgb); rgb.flags.writeable=True
                if res.multi_hand_landmarks:
                    self._hand_present=True; self._last_landmarks=res.multi_hand_landmarks[0]
                    lm=self._last_landmarks.landmark
                    ix=int(lm[8].x*self.W); iy=int(lm[8].y*self.H)
                    tx=int(lm[4].x*self.W); ty=int(lm[4].y*self.H)
                    pinch_d=math.dist((tx,ty),(ix,iy))
                    mn,mx=self.cfg["min_brush_size"],self.cfg["max_brush_size"]
                    self.brush_size=self._smooth_bs(int(mn+float(np.clip((pinch_d-20)/200,0,1))*(mx-mn)))
                    self._last_gesture=self._stable_gesture(self._detect_gesture(lm))
                else:
                    self._hand_present=False; self._last_landmarks=None
                    self._last_gesture="NONE"; self._gesture_buffer.clear(); self.smooth_points.clear()
            else:
                if not self._hand_present: self._last_gesture="NONE"

            if not self._hand_present:
                gesture="NONE"; _lm_draw=None; _smooth_d=None; _free_info=None
                self.drawing=False; self.prev_point=None; self._fill_done=False
                if self.app_mode==APP_MODE_FREE:
                    self.mouse_ctrl.handle_pinch(False,0,0); self.mouse_ctrl.tick()
            else:
                gesture=self._last_gesture; _lm_draw=self._last_landmarks
                if _lm_draw is not None:
                    lm=_lm_draw.landmark
                    _smooth_d=self._smooth_pt((int(lm[8].x*self.W),int(lm[8].y*self.H)))
                    if self.app_mode==APP_MODE_FREE:
                        _free_info=self._process_free_mode(lm,gesture)
                    else:
                        if gesture=="THUMB_UP":
                            self.color_index=(self.color_index+1)%len(COLORS)
                            self.current_color=COLORS[self.color_index]["bgr"]; self.eraser_mode=False
                            self._notify(f"Color: {COLORS[self.color_index]['name']}",COLORS[self.color_index]["bgr"])
                        elif gesture=="THUMB_DOWN":
                            self.color_index=(self.color_index-1)%len(COLORS)
                            self.current_color=COLORS[self.color_index]["bgr"]; self.eraser_mode=False
                            self._notify(f"Color: {COLORS[self.color_index]['name']}",COLORS[self.color_index]["bgr"])
                        elif gesture=="ERASER":
                            if self.active_tool!=TOOL_ERASER:
                                self.active_tool=TOOL_ERASER; self.eraser_mode=True
                                self._notify("Borrador activado",UI["tool_eraser"])
                        elif gesture=="OPEN": self.drawing=False; self.prev_point=None

                        if gesture in("SELECT","OPEN","PINCH"):
                            if _smooth_d: self._check_btn_hover(_smooth_d,last_bg)
                            self.drawing=False; self.prev_point=None; self._fill_done=False
                        elif gesture=="DRAW" and _smooth_d:
                            self._hover_btn=None; self._hover_btn_frames=0; self._btn_hover_progress=0
                            in_left =_smooth_d[0]<self.SIDEBAR_W
                            in_right=_smooth_d[0]>self.W-self.SIDEBAR_W
                            in_bl=any(x1<=_smooth_d[0]<=x2 and y1<=_smooth_d[1]<=y2 for x1,y1,x2,y2 in self.left_buttons.values())
                            in_br=any(x1<=_smooth_d[0]<=x2 and y1<=_smooth_d[1]<=y2 for x1,y1,x2,y2 in self.right_buttons.values())
                            blocked=in_left or in_right or in_bl or in_br or _smooth_d[1]<48
                            if not blocked:
                                if self.active_tool==TOOL_FILL:
                                    if not self._fill_done: self._apply_fill(_smooth_d); self._fill_done=True
                                    self.drawing=False; self.prev_point=None
                                elif self.active_tool==TOOL_ERASER or self.eraser_mode:
                                    if not self.drawing: self._push_undo(); self.drawing=True
                                    esize=self.brush_size*self.cfg["eraser_multiplier"]
                                    if self.app_mode==APP_MODE_COLOR and self.color_image_orig is not None:
                                        mask_e=np.zeros((self.H,self.W),dtype=np.uint8)
                                        cv2.circle(mask_e,_smooth_d,esize,255,-1)
                                        self.color_layer=np.where(np.stack([mask_e]*3,axis=-1)>0,
                                            self.color_image_orig,self.color_layer).astype(np.uint8)
                                    else: self._stroke(_smooth_d,(0,0,0),esize)
                                    self.prev_point=_smooth_d
                                else:
                                    if not self.drawing: self._push_undo(); self.drawing=True
                                    self._stroke(_smooth_d,self.current_color,self.brush_size)
                                    self.prev_point=_smooth_d
                            else: self.drawing=False; self.prev_point=None; self._fill_done=False
                        else: self.drawing=False; self.prev_point=None; self._fill_done=False

            # -- Renderizado ------------------------------------------
            if self.app_mode==APP_MODE_FREE:
                if(self._free_bg_cache is None or
                        self._frame_counter-self._free_bg_frame_cnt>=self._free_bg_interval):
                    self._free_bg_cache=self._build_free_bg(frame)
                    self._free_bg_frame_cnt=self._frame_counter
                output=self._free_bg_cache.copy()
            elif self.app_mode==APP_MODE_COLOR and self.color_layer is not None:
                output=cv2.addWeighted(self.color_layer,0.88,frame,0.12,0)
            else:
                output=self._merge_canvas_fast(frame)

            if self.app_mode!=APP_MODE_COLOR:
                self._update_effects_fast(output)

            if _lm_draw is not None and _smooth_d is not None and self._hand_present:
                self.mp_draw.draw_landmarks(output,_lm_draw,self.mp_hands.HAND_CONNECTIONS,
                    self.mp_draw_styles.DrawingSpec(color=(50,205,50),thickness=2,circle_radius=4),
                    self.mp_draw_styles.DrawingSpec(color=(0,206,209),thickness=2))
                if self.app_mode==APP_MODE_FREE and _free_info is not None:
                    self._draw_free_cursor(output,_free_info)
                else:
                    self._draw_cursor(output,_smooth_d,gesture)

            output=self._draw_ui(output,gesture,fps)
            cv2.imshow(win,output)

            key=cv2.waitKey(1)&0xFF
            if key in(ord('q'),27): self.mouse_ctrl.release_all(); break
            elif key==ord('1'):
                self.mouse_ctrl.release_all(); self.app_mode=APP_MODE_PAINT
                self._free_bg_cache=None; self._notify("Modo: Pintura Libre",UI["mode_paint"])
            elif key==ord('2'):
                if self.color_layer is not None:
                    self.mouse_ctrl.release_all(); self.app_mode=APP_MODE_COLOR
                    self._free_bg_cache=None; self._notify("Modo: Colorear",UI["mode_color"])
                else: self._notify("Carga una imagen primero (tecla O)",UI["vivo_rojo"])
            elif key==ord('3'): self._toggle_free_mode()
            elif key in(ord('o'),ord('O')):
                self.img_selector._load(); path=self.img_selector.show(self.W,self.H)
                if path: self.load_color_image(path)
            elif key in(ord('b'),ord('B')): self.active_tool=TOOL_BRUSH;  self.eraser_mode=False; self._notify("Pincel",UI["tool_brush"])
            elif key in(ord('k'),ord('K')): self.active_tool=TOOL_FILL;   self.eraser_mode=False; self._notify("Relleno",UI["tool_fill"])
            elif key in(ord('e'),ord('E')): self.active_tool=TOOL_ERASER; self.eraser_mode=True;  self._notify("Borrador",UI["tool_eraser"])
            elif key in(ord('c'),ord('C')):
                self._push_undo()
                if self.app_mode==APP_MODE_COLOR and self.color_image_orig is not None:
                    self.color_layer=self.color_image_orig.copy(); self._notify("Imagen restaurada",UI["vivo_naranja"])
                else: self.canvas[:]=0; self._notify("Canvas limpiado",UI["vivo_rojo"])
            elif key in(ord('r'),ord('R')): self.reset_color_image()
            elif key in(ord('h'),ord('H')): self.show_hud=not self.show_hud
            elif key in(ord('f'),ord('F')):
                self.fullscreen=not self.fullscreen
                cv2.setWindowProperty(win,cv2.WND_PROP_FULLSCREEN,
                    cv2.WINDOW_FULLSCREEN if self.fullscreen else cv2.WINDOW_NORMAL)
            elif key in(ord('s'),ord('S')): self.save_drawing(last_bg)
            elif key in(ord('p'),ord('P')): self.print_drawing(last_bg)
            elif key==26: self.undo()
            elif key==25: self.redo()
            elif key in(ord('+'),ord('=')): self.brush_size=min(self.brush_size+2,self.cfg["max_brush_size"])
            elif key==ord('-'): self.brush_size=max(self.brush_size-2,self.cfg["min_brush_size"])
            elif key==ord(']'):
                self.fill_tolerance=min(self.fill_tolerance+4,self.cfg["fill_tolerance_max"])
                self._notify(f"Tolerancia:{self.fill_tolerance}",UI["vivo_naranja"])
            elif key==ord('['):
                self.fill_tolerance=max(self.fill_tolerance-4,self.cfg["fill_tolerance_min"])
                self._notify(f"Tolerancia:{self.fill_tolerance}",UI["vivo_naranja"])

        cap.release(); self.hands.close(); cv2.destroyAllWindows()
        print(f"\n[OK] Obras guardadas en ./{self.cfg['save_dir']}/")


# =============================================================
#  SAMPLE IMAGES + BANNER + MAIN
# =============================================================
def create_sample_images(out_dir):
    os.makedirs(out_dir,exist_ok=True); W,H=800,600
    img=np.full((H,W,3),255,dtype=np.uint8); cx,cy=W//2,H//2
    for r in range(40,260,42): cv2.circle(img,(cx,cy),r,(0,0,0),2)
    for a in range(0,360,30):
        rd=math.radians(a)
        cv2.line(img,(int(cx+42*math.cos(rd)),int(cy+42*math.sin(rd))),
                     (int(cx+250*math.cos(rd)),int(cy+250*math.sin(rd))),(0,0,0),2)
    for a in range(0,360,45):
        rd=math.radians(a); px,py=int(cx+145*math.cos(rd)),int(cy+145*math.sin(rd))
        cv2.ellipse(img,(px,py),(36,20),a,0,360,(0,0,0),2)
    cv2.imwrite(os.path.join(out_dir,"mandala.png"),img)
    img=np.full((H,W,3),255,dtype=np.uint8)
    cv2.line(img,(0,H//2),(W,H//2),(0,0,0),2); cv2.circle(img,(130,110),72,(0,0,0),2)
    mts=np.array([[0,H//2],[160,185],[320,H//2],[510,170],[720,H//2],[W,H//2]])
    cv2.polylines(img,[mts],False,(0,0,0),3); cv2.imwrite(os.path.join(out_dir,"paisaje.png"),img)
    img=np.full((H,W,3),255,dtype=np.uint8)
    cv2.circle(img,(400,300),185,(0,0,0),3)
    for ex in [340,460]:
        cv2.circle(img,(ex,268),38,(0,0,0),3); cv2.circle(img,(ex,268),14,(0,0,0),-1)
    cv2.imwrite(os.path.join(out_dir,"gato.png"),img)
    print(f"[OK] Imagenes de ejemplo en '{out_dir}/'")

def _print_banner():
    print("="*68)
    print("   M A G I C   P A I N T  v5.2  -  OPTIMIZADO")
    print("   Universidad Politecnica del Carchi - Carrera de Computacion")
    print("="*68)
    print("  Modos:   [1] Pintura libre   [2] Colorear   [3] Modo Libre")
    print("  Herram:  [B] Pincel  [K] Fill  [E] Borrador")
    print("  Imagen:  [O] Abrir  [R] Restaurar  [S] Guardar  [P] Imprimir")
    print("  Colores: [C] Selector de colores (48 colores)")
    print("  Ctrl+Z Undo  |  Ctrl+Y Redo  |  H HUD  |  F Full  |  Q Salir")
    print("="*68)
    print("  OPTIMIZACIONES: 0 frame.copy() en UI, sidebar cacheada,")
    print("  nubes cada 4 frames, blobs cacheados, particulas reducidas")
    print("="*68)
    if not PYAUTOGUI_OK:
        print("  [!] pip install pyautogui  para Modo Libre")
        print("="*68)

def main():
    if len(sys.argv)>1 and sys.argv[1].lstrip('-').isdigit():
        CONFIG["camera_index"]=int(sys.argv[1])
    if "--gen-samples" in sys.argv:
        create_sample_images(CONFIG["images_dir"]); return
    total=sum(len(glob.glob(os.path.join(CONFIG["images_dir"],ext))) for ext in CONFIG["image_extensions"])
    if total==0:
        print("[INFO] Generando imagenes de ejemplo...")
        create_sample_images(CONFIG["images_dir"])
    VirtualPainter().run()

if __name__=="__main__":
    main()