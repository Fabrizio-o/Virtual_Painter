"""
╔══════════════════════════════════════════════════════════════════╗
║          ADVANCED VIRTUAL PAINTER CON GESTOS DE MANO            ║
║                Python + OpenCV + MediaPipe                       ║
║                      Versión 2.0                                 ║
╚══════════════════════════════════════════════════════════════════╝

Controles de gestos:
  • Solo índice extendido     → Dibujar
  • 2+ dedos extendidos       → Pausar / Selección de UI
  • Puño cerrado              → Modo borrador
  • Mano abierta (5 dedos)    → Mover sin dibujar
  • Pinch (pulgar+índice)     → Ajustar grosor del pincel
  • Pulgar arriba (thumb up)  → Siguiente color
  • Pulgar abajo (thumb down) → Color anterior

Teclas de teclado:
  • Ctrl+Z  → Undo
  • Ctrl+Y  → Redo
  • Ctrl+S  → Guardar imagen
  • C       → Limpiar canvas
  • H       → Mostrar/Ocultar HUD
  • F       → Pantalla completa
  • Q / ESC → Salir
"""

import cv2
import mediapipe as mp
import numpy as np
import os
import time
import math
from collections import deque
from datetime import datetime

# ─────────────────────────────────────────────
#  CONFIGURACIÓN GLOBAL
# ─────────────────────────────────────────────
CONFIG = {
    "camera_index": 0,
    "width": 1280,
    "height": 720,
    "flip_horizontal": True,

    # Canvas
    "default_brush_size": 8,
    "min_brush_size": 2,
    "max_brush_size": 60,
    "eraser_multiplier": 4,       # El borrador es N veces el pincel
    "canvas_opacity": 0.75,        # Opacidad del canvas sobre la cámara

    # Suavizado
    "smoothing_points": 5,         # Puntos para promedio deslizante
    "gesture_smoothing": 8,        # Frames para estabilizar gestos

    # UI
    "palette_height": 90,
    "ui_margin": 12,
    "show_hud": True,
    "hud_alpha": 0.80,

    # Undo/Redo
    "max_undo_steps": 40,

    # Guardar
    "save_dir": "paintings",
    "save_format": "png",          # png o jpg

    # Landmarks de MediaPipe
    "detection_confidence": 0.75,
    "tracking_confidence": 0.75,
}

# ─────────────────────────────────────────────
#  PALETA DE COLORES (BGR)
# ─────────────────────────────────────────────
COLORS = [
    {"name": "Negro",    "bgr": (0,   0,   0  )},
    {"name": "Blanco",   "bgr": (255, 255, 255)},
    {"name": "Rojo",     "bgr": (0,   0,   220)},
    {"name": "Naranja",  "bgr": (0,   120, 255)},
    {"name": "Amarillo", "bgr": (0,   220, 220)},
    {"name": "Verde",    "bgr": (0,   200, 60 )},
    {"name": "Cian",     "bgr": (220, 200, 0  )},
    {"name": "Azul",     "bgr": (230, 80,  0  )},
    {"name": "Magenta",  "bgr": (200, 0,   200)},
    {"name": "Morado",   "bgr": (160, 0,   120)},
    {"name": "Rosa",     "bgr": (160, 100, 240)},
    {"name": "Marrón",   "bgr": (30,  80,  140)},
]

# ─────────────────────────────────────────────
#  ÍNDICES DE LANDMARKS MEDIAPIPE
# ─────────────────────────────────────────────
TIP   = [4, 8, 12, 16, 20]   # Puntas: pulgar, índice, medio, anular, meñique
PIP   = [3, 6, 10, 14, 18]   # Segunda articulación (proximal)
MCP   = [2, 5, 9,  13, 17]   # Nudillos (metacarpofalángicas)
WRIST = 0

# ─────────────────────────────────────────────
#  CLASE PRINCIPAL: VirtualPainter
# ─────────────────────────────────────────────
class VirtualPainter:
    def __init__(self):
        self.cfg = CONFIG
        self.W = self.cfg["width"]
        self.H = self.cfg["height"]

        # ── Canvas principal (BGRA para transparencia)
        self.canvas = np.zeros((self.H, self.W, 3), dtype=np.uint8)

        # ── Estado de dibujo
        self.drawing = False
        self.prev_point = None
        self.brush_size = self.cfg["default_brush_size"]
        self.eraser_mode = False
        self.color_index = 0
        self.current_color = COLORS[0]["bgr"]
        self.show_hud = self.cfg["show_hud"]
        self.fullscreen = False

        # ── Suavizado de trayectoria
        self.smooth_points = deque(maxlen=self.cfg["smoothing_points"])
        self.smooth_brush  = deque(maxlen=10)

        # ── Undo / Redo
        self.undo_stack = deque(maxlen=self.cfg["max_undo_steps"])
        self.redo_stack = deque(maxlen=self.cfg["max_undo_steps"])
        self._push_undo()

        # ── Detección de gestos estabilizada
        self._gesture_buffer = deque(maxlen=self.cfg["gesture_smoothing"])
        self._last_stable_gesture = "NONE"

        # ── Hover sobre paleta
        self._hover_color_idx = -1
        self._hover_frames    = 0
        self._hover_threshold = 18   # frames en hover para confirmar selección

        # ── Hover sobre botones UI
        self._hover_btn = None
        self._hover_btn_frames = 0
        self._hover_btn_threshold = 20

        # ── FPS
        self._fps_buffer = deque(maxlen=30)
        self._last_time  = time.time()

        # ── MediaPipe
        self.mp_hands = mp.solutions.hands
        self.hands = self.mp_hands.Hands(
            static_image_mode=False,
            max_num_hands=1,
            min_detection_confidence=self.cfg["detection_confidence"],
            min_tracking_confidence=self.cfg["tracking_confidence"],
        )
        self.mp_draw = mp.solutions.drawing_utils
        self.mp_draw_styles = mp.solutions.drawing_styles

        # ── Directorio de guardado
        os.makedirs(self.cfg["save_dir"], exist_ok=True)

        # ── Construir regiones de la UI
        self._build_ui_regions()

    # ─────────────────────────────────────────
    #  CONSTRUCCIÓN DE LA UI
    # ─────────────────────────────────────────
    def _build_ui_regions(self):
        """Calcula las posiciones de la paleta y botones."""
        W, H = self.W, self.H
        ph = self.cfg["palette_height"]
        mg = self.cfg["ui_margin"]
        n  = len(COLORS)
        swatch_w = (W - 2 * mg) // n

        # Swatches de color
        self.color_rects = []
        for i, c in enumerate(COLORS):
            x1 = mg + i * swatch_w
            x2 = x1 + swatch_w - 4
            y1 = mg
            y2 = mg + ph - 8
            self.color_rects.append((x1, y1, x2, y2))

        # Botones de acción (parte derecha superior)
        btn_w, btn_h = 110, 40
        btn_x = W - btn_w - mg
        self.buttons = {
            "CLEAR":  (btn_x, mg,           btn_x + btn_w, mg + btn_h),
            "UNDO":   (btn_x, mg + 48,      btn_x + btn_w, mg + 48 + btn_h),
            "REDO":   (btn_x, mg + 96,      btn_x + btn_w, mg + 96 + btn_h),
            "SAVE":   (btn_x, mg + 144,     btn_x + btn_w, mg + 144 + btn_h),
            "ERASER": (btn_x, mg + 192,     btn_x + btn_w, mg + 192 + btn_h),
        }

    # ─────────────────────────────────────────
    #  UNDO / REDO
    # ─────────────────────────────────────────
    def _push_undo(self):
        self.undo_stack.append(self.canvas.copy())
        self.redo_stack.clear()

    def undo(self):
        if len(self.undo_stack) > 1:
            self.redo_stack.append(self.undo_stack.pop())
            self.canvas = self.undo_stack[-1].copy()

    def redo(self):
        if self.redo_stack:
            state = self.redo_stack.pop()
            self.undo_stack.append(state)
            self.canvas = state.copy()

    # ─────────────────────────────────────────
    #  GUARDAR IMAGEN
    # ─────────────────────────────────────────
    def save_drawing(self, frame_bg=None):
        ts   = datetime.now().strftime("%Y%m%d_%H%M%S")
        ext  = self.cfg["save_format"]
        path = os.path.join(self.cfg["save_dir"], f"painting_{ts}.{ext}")
        if frame_bg is not None:
            merged = self._merge_canvas_on_frame(frame_bg)
            cv2.imwrite(path, merged)
        else:
            cv2.imwrite(path, self.canvas)
        print(f"[💾] Guardado: {path}")
        return path

    # ─────────────────────────────────────────
    #  DETECCIÓN DE DEDOS EXTENDIDOS
    # ─────────────────────────────────────────
    def _fingers_up(self, lm):
        """
        Devuelve lista booleana [pulgar, índice, medio, anular, meñique].
        True = dedo extendido.
        """
        h, w = self.H, self.W
        pts = [(int(lm[i].x * w), int(lm[i].y * h)) for i in range(21)]

        fingers = []

        # Pulgar: comparar x en lugar de y (orientación lateral)
        if pts[TIP[0]][0] > pts[PIP[0]][0]:   # mano derecha espejada
            fingers.append(True)
        else:
            fingers.append(False)

        # Resto de dedos
        for i in range(1, 5):
            fingers.append(pts[TIP[i]][1] < pts[PIP[i]][1])

        return fingers

    # ─────────────────────────────────────────
    #  RECONOCIMIENTO DE GESTOS
    # ─────────────────────────────────────────
    def _detect_gesture(self, lm):
        """
        Clasifica el gesto de la mano.
        Retorna: DRAW | SELECT | ERASER | OPEN | THUMB_UP | THUMB_DOWN | PINCH
        """
        fingers = self._fingers_up(lm)
        n_up    = sum(fingers)
        h, w    = self.H, self.W

        def pt(idx):
            return (int(lm[idx].x * w), int(lm[idx].y * h))

        # Puntos clave
        thumb_tip = pt(4)
        index_tip = pt(8)
        wrist     = pt(0)
        middle_mcp= pt(9)

        # Distancia pulgar-índice (pinch)
        pinch_dist = math.dist(thumb_tip, index_tip)

        # ── Puño cerrado (todos hacia abajo)
        if n_up == 0:
            return "ERASER"

        # ── Mano abierta
        if n_up >= 4:
            return "OPEN"

        # ── Solo índice → Dibujar
        if fingers[1] and not fingers[2] and not fingers[3] and not fingers[4]:
            # Verificar si hay pinch (pulgar cerca del índice)
            if pinch_dist < 55:
                return "PINCH"
            return "DRAW"

        # ── Índice y medio → Selección
        if fingers[1] and fingers[2] and not fingers[3]:
            return "SELECT"

        # ── Pulgar arriba
        if fingers[0] and not fingers[1] and not fingers[2] and not fingers[3]:
            # Pulgar apunta hacia arriba
            if thumb_tip[1] < wrist[1] - 50:
                return "THUMB_UP"
            return "OPEN"

        # ── Pulgar abajo (mano invertida)
        if fingers[0] and not fingers[1] and not fingers[2] and not fingers[3]:
            if thumb_tip[1] > wrist[1] + 50:
                return "THUMB_DOWN"

        return "SELECT"

    def _stable_gesture(self, gesture):
        """Suaviza el gesto para evitar cambios bruscos."""
        self._gesture_buffer.append(gesture)
        if len(self._gesture_buffer) == self._gesture_buffer.maxlen:
            # El gesto más frecuente en el buffer
            from collections import Counter
            most_common = Counter(self._gesture_buffer).most_common(1)[0][0]
            self._last_stable_gesture = most_common
        return self._last_stable_gesture

    # ─────────────────────────────────────────
    #  OBTENER PUNTO SUAVIZADO
    # ─────────────────────────────────────────
    def _get_smooth_point(self, pt):
        self.smooth_points.append(pt)
        xs = [p[0] for p in self.smooth_points]
        ys = [p[1] for p in self.smooth_points]
        return (int(np.mean(xs)), int(np.mean(ys)))

    def _get_smooth_brush(self, size):
        self.smooth_brush.append(size)
        return int(np.mean(self.smooth_brush))

    # ─────────────────────────────────────────
    #  DIBUJO EN CANVAS
    # ─────────────────────────────────────────
    def _draw_stroke(self, pt, color, size):
        if self.prev_point is not None:
            cv2.line(self.canvas, self.prev_point, pt, color, size,
                     lineType=cv2.LINE_AA)
        cv2.circle(self.canvas, pt, size // 2, color, -1, lineType=cv2.LINE_AA)

    # ─────────────────────────────────────────
    #  INTERACCIÓN CON BOTONES
    # ─────────────────────────────────────────
    def _check_button_hover(self, pt, frame_bg=None):
        """Comprueba si la punta del dedo está sobre un botón."""
        x, y = pt
        for name, (x1, y1, x2, y2) in self.buttons.items():
            if x1 <= x <= x2 and y1 <= y <= y2:
                if self._hover_btn == name:
                    self._hover_btn_frames += 1
                    if self._hover_btn_frames >= self._hover_btn_threshold:
                        self._trigger_button(name, frame_bg)
                        self._hover_btn_frames = 0
                else:
                    self._hover_btn = name
                    self._hover_btn_frames = 0
                return True
        self._hover_btn = None
        self._hover_btn_frames = 0
        return False

    def _trigger_button(self, name, frame_bg=None):
        if name == "CLEAR":
            self._push_undo()
            self.canvas[:] = 0
            print("[🗑️] Canvas limpiado")
        elif name == "UNDO":
            self.undo()
        elif name == "REDO":
            self.redo()
        elif name == "SAVE":
            self.save_drawing(frame_bg)
        elif name == "ERASER":
            self.eraser_mode = not self.eraser_mode

    # ─────────────────────────────────────────
    #  INTERACCIÓN CON PALETA DE COLORES
    # ─────────────────────────────────────────
    def _check_color_hover(self, pt):
        x, y = pt
        ph = self.cfg["palette_height"]
        mg = self.cfg["ui_margin"]
        if y < mg + ph:
            for i, (x1, y1, x2, y2) in enumerate(self.color_rects):
                if x1 <= x <= x2 and y1 <= y <= y2:
                    if self._hover_color_idx == i:
                        self._hover_frames += 1
                        if self._hover_frames >= self._hover_threshold:
                            self.color_index = i
                            self.current_color = COLORS[i]["bgr"]
                            self.eraser_mode = False
                            self._hover_frames = 0
                            print(f"[🎨] Color: {COLORS[i]['name']}")
                    else:
                        self._hover_color_idx = i
                        self._hover_frames = 0
                    return True
        self._hover_color_idx = -1
        self._hover_frames = 0
        return False

    # ─────────────────────────────────────────
    #  FUSIONAR CANVAS + CÁMARA
    # ─────────────────────────────────────────
    def _merge_canvas_on_frame(self, frame):
        """Superpone el canvas sobre el frame con opacidad."""
        opacity = self.cfg["canvas_opacity"]
        mask = (self.canvas.sum(axis=2) > 0).astype(np.uint8)
        mask3 = np.stack([mask]*3, axis=-1)
        blended = frame.copy()
        blended = np.where(mask3,
                           cv2.addWeighted(frame, 1 - opacity, self.canvas, opacity, 0),
                           frame)
        return blended.astype(np.uint8)

    # ─────────────────────────────────────────
    #  DIBUJO DE LA UI (HUD)
    # ─────────────────────────────────────────
    def _draw_ui(self, frame, gesture, fps):
        if not self.show_hud:
            return frame

        W, H   = self.W, self.H
        ph     = self.cfg["palette_height"]
        mg     = self.cfg["ui_margin"]
        alpha  = self.cfg["hud_alpha"]

        overlay = frame.copy()

        # ── Fondo semitransparente de la paleta
        cv2.rectangle(overlay, (0, 0), (W, ph + mg * 2 + 4), (20, 20, 20), -1)
        frame = cv2.addWeighted(overlay, 1 - alpha, frame, alpha, 0)

        # ── Swatches de color
        for i, (c, (x1, y1, x2, y2)) in enumerate(zip(COLORS, self.color_rects)):
            bgr = c["bgr"]
            selected = (i == self.color_index)
            hover    = (i == self._hover_color_idx)

            # Sombra
            cv2.rectangle(frame, (x1+3, y1+3), (x2+3, y2+3), (0,0,0), -1)
            # Swatch principal
            cv2.rectangle(frame, (x1, y1), (x2, y2), bgr, -1)

            # Borde
            border_color = (255, 255, 255) if selected else (80, 80, 80)
            border_thick = 3 if selected else 1
            if hover:
                border_color = (200, 200, 50)
                border_thick = 2
            cv2.rectangle(frame, (x1, y1), (x2, y2), border_color, border_thick)

            # Indicador de selección (punto blanco/negro)
            if selected:
                dot_c = (0,0,0) if sum(bgr) > 380 else (255,255,255)
                cx, cy = (x1+x2)//2, (y1+y2)//2
                cv2.circle(frame, (cx, cy+12), 5, dot_c, -1)

            # Barra de progreso para hover
            if hover and self._hover_frames > 0:
                prog = int((x2 - x1) * self._hover_frames / self._hover_threshold)
                cv2.rectangle(frame, (x1, y2-5), (x1+prog, y2), (255,255,100), -1)

        # ── Botones de acción
        btn_labels = {
            "CLEAR":  ("🗑 CLEAR",  (50, 50, 50)),
            "UNDO":   ("↩ UNDO",   (50, 50, 80)),
            "REDO":   ("↪ REDO",   (50, 80, 50)),
            "SAVE":   ("💾 SAVE",   (50, 80, 80)),
            "ERASER": ("⚪ BORRAR" if not self.eraser_mode else "✏ PINCEL",
                       (80, 50, 50) if self.eraser_mode else (50, 50, 50)),
        }
        for name, (x1, y1, x2, y2) in self.buttons.items():
            label, bg = btn_labels[name]
            is_hover = (self._hover_btn == name)
            bg_col = (80, 100, 80) if is_hover else bg
            cv2.rectangle(frame, (x1, y1), (x2, y2), bg_col, -1)
            cv2.rectangle(frame, (x1, y1), (x2, y2),
                          (200,200,200) if is_hover else (100,100,100), 1)
            # Texto en botón
            text = name
            cv2.putText(frame, text, (x1+8, y1+26),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55,
                        (220,220,220), 1, cv2.LINE_AA)
            # Barra de progreso del hover
            if is_hover and self._hover_btn_frames > 0:
                prog = int((x2-x1) * self._hover_btn_frames / self._hover_btn_threshold)
                cv2.rectangle(frame, (x1, y2-4), (x1+prog, y2), (100, 220, 100), -1)

        # ── Panel de información (esquina inferior izquierda)
        info_x, info_y = 12, H - 170
        panel_w = 320
        overlay2 = frame.copy()
        cv2.rectangle(overlay2, (info_x-8, info_y-8),
                      (info_x + panel_w, H - 12), (15, 15, 15), -1)
        frame = cv2.addWeighted(overlay2, 0.75, frame, 0.25, 0)

        def info_text(txt, y_off, color=(200, 200, 200), scale=0.55, thick=1):
            cv2.putText(frame, txt, (info_x, info_y + y_off),
                        cv2.FONT_HERSHEY_SIMPLEX, scale, color, thick, cv2.LINE_AA)

        # Color actual
        color_name = COLORS[self.color_index]["name"] if not self.eraser_mode else "Borrador"
        cv2.rectangle(frame, (info_x, info_y), (info_x+28, info_y+28),
                      self.current_color, -1)
        cv2.rectangle(frame, (info_x, info_y), (info_x+28, info_y+28), (180,180,180), 1)
        info_text(f"  Color: {color_name}", 20)

        mode_str = "BORRADOR" if self.eraser_mode else gesture
        mode_col = (50, 50, 220) if self.eraser_mode else (50, 220, 50)
        info_text(f"Modo:   {mode_str}", 48, mode_col, scale=0.55, thick=2)
        info_text(f"Grosor: {self.brush_size}px", 72)
        info_text(f"Undo:   {len(self.undo_stack)-1} / Redo: {len(self.redo_stack)}", 96)
        info_text(f"FPS:    {fps:.1f}", 120, (80, 220, 80))

        # Indicador de tamaño del pincel
        preview_x = info_x + panel_w - 50
        preview_y = info_y + 50
        preview_r = min(self.brush_size, 40)
        col = (200,200,200) if self.eraser_mode else self.current_color
        cv2.circle(frame, (preview_x, preview_y), preview_r, col, -1)
        cv2.circle(frame, (preview_x, preview_y), preview_r, (180,180,180), 1)

        # ── Leyenda de gestos (esquina inferior derecha)
        legend_x = W - 260
        legend_y = H - 200
        overlay3 = frame.copy()
        cv2.rectangle(overlay3, (legend_x - 8, legend_y - 8),
                      (W - 8, H - 12), (15, 15, 15), -1)
        frame = cv2.addWeighted(overlay3, 0.70, frame, 0.30, 0)

        gestures = [
            ("☝  Solo índice", "Dibujar"),
            ("✌  Dos dedos",   "Seleccionar"),
            ("✊  Puño",        "Borrador"),
            ("✋  Mano abierta","Pausar"),
            ("🤏  Pinch",       "Tamaño"),
            ("👍  Pulgar ↑",    "Sig. color"),
        ]
        cv2.putText(frame, "GESTOS", (legend_x, legend_y + 4),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (150,200,255), 1, cv2.LINE_AA)
        for j, (g, desc) in enumerate(gestures):
            yy = legend_y + 26 + j * 27
            cv2.putText(frame, g, (legend_x, yy),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, (200, 200, 200), 1, cv2.LINE_AA)
            cv2.putText(frame, desc, (legend_x + 130, yy),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, (100, 220, 100), 1, cv2.LINE_AA)

        return frame

    # ─────────────────────────────────────────
    #  DIBUJO DE LANDMARKS DE LA MANO
    # ─────────────────────────────────────────
    def _draw_landmarks(self, frame, hand_landmarks):
        self.mp_draw.draw_landmarks(
            frame,
            hand_landmarks,
            self.mp_hands.HAND_CONNECTIONS,
            self.mp_draw_styles.get_default_hand_landmarks_style(),
            self.mp_draw_styles.get_default_hand_connections_style(),
        )

    # ─────────────────────────────────────────
    #  CURSOR VIRTUAL EN LA PUNTA DEL DEDO
    # ─────────────────────────────────────────
    def _draw_cursor(self, frame, pt, gesture):
        r = self.brush_size + 4
        color = (200, 200, 200) if self.eraser_mode else self.current_color

        if self.eraser_mode:
            r = self.brush_size * self.cfg["eraser_multiplier"] + 4
            cv2.circle(frame, pt, r, (200, 200, 200), 2, cv2.LINE_AA)
            cv2.line(frame, (pt[0]-r, pt[1]), (pt[0]+r, pt[1]), (200,200,200), 1)
            cv2.line(frame, (pt[0], pt[1]-r), (pt[0], pt[1]+r), (200,200,200), 1)
        elif gesture == "DRAW":
            cv2.circle(frame, pt, r, color, 2, cv2.LINE_AA)
            cv2.circle(frame, pt, 3, (255,255,255), -1)
        elif gesture == "SELECT":
            cv2.drawMarker(frame, pt, (200,200,50),
                           cv2.MARKER_CROSS, 20, 2, cv2.LINE_AA)
        else:
            cv2.circle(frame, pt, 10, (150,150,150), 1, cv2.LINE_AA)

    # ─────────────────────────────────────────
    #  BUCLE PRINCIPAL
    # ─────────────────────────────────────────
    def run(self):
        cap = cv2.VideoCapture(self.cfg["camera_index"])
        cap.set(cv2.CAP_PROP_FRAME_WIDTH,  self.W)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.H)
        cap.set(cv2.CAP_PROP_FPS, 60)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

        if not cap.isOpened():
            print("❌ No se pudo abrir la cámara.")
            return

        win_name = "🎨 Advanced Virtual Painter"
        cv2.namedWindow(win_name, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(win_name, self.W, self.H)

        print("=" * 60)
        print("  ADVANCED VIRTUAL PAINTER — Listo para usar")
        print("=" * 60)
        print("  Gestos: ☝ Dibujar | ✌ Seleccionar | ✊ Borrador")
        print("  Teclas: H=HUD | C=Clear | Ctrl+Z=Undo | Q=Salir")
        print("=" * 60)

        # Variable para el frame actual (para guardar con cámara)
        last_frame_bg = None
        gesture = "NONE"

        while True:
            ret, frame = cap.read()
            if not ret:
                print("❌ Error leyendo frame de cámara.")
                break

            # Espejo horizontal
            if self.cfg["flip_horizontal"]:
                frame = cv2.flip(frame, 1)

            # Redimensionar si es necesario
            fh, fw = frame.shape[:2]
            if fw != self.W or fh != self.H:
                frame = cv2.resize(frame, (self.W, self.H))

            last_frame_bg = frame.copy()

            # ── FPS
            now = time.time()
            self._fps_buffer.append(1.0 / max(now - self._last_time, 1e-6))
            self._last_time = now
            fps = np.mean(self._fps_buffer)

            # ── Detección de mano
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            rgb.flags.writeable = False
            results = self.hands.process(rgb)
            rgb.flags.writeable = True

            if results.multi_hand_landmarks:
                for hand_landmarks in results.multi_hand_landmarks:
                    lm = hand_landmarks.landmark

                    # Punta del índice
                    ix = int(lm[8].x * self.W)
                    iy = int(lm[8].y * self.H)
                    index_tip = (ix, iy)

                    # Distancia pinch (pulgar-índice)
                    tx = int(lm[4].x * self.W)
                    ty = int(lm[4].y * self.H)
                    pinch_dist = math.dist((tx, ty), (ix, iy))

                    # Actualizar tamaño de pincel con pinch
                    min_b = self.cfg["min_brush_size"]
                    max_b = self.cfg["max_brush_size"]
                    norm_pinch = np.clip((pinch_dist - 20) / 200, 0, 1)
                    raw_brush  = int(min_b + norm_pinch * (max_b - min_b))
                    self.brush_size = self._get_smooth_brush(raw_brush)

                    # Detectar gesto estabilizado
                    raw_gesture = self._detect_gesture(lm)
                    gesture     = self._stable_gesture(raw_gesture)

                    # Punto suavizado
                    smooth_pt = self._get_smooth_point(index_tip)

                    # ── Gestos especiales
                    if gesture == "THUMB_UP":
                        self.color_index = (self.color_index + 1) % len(COLORS)
                        self.current_color = COLORS[self.color_index]["bgr"]
                        self.eraser_mode = False

                    elif gesture == "THUMB_DOWN":
                        self.color_index = (self.color_index - 1) % len(COLORS)
                        self.current_color = COLORS[self.color_index]["bgr"]
                        self.eraser_mode = False

                    elif gesture == "ERASER":
                        self.eraser_mode = True

                    elif gesture == "OPEN":
                        # Mano abierta: pausa
                        self.drawing   = False
                        self.prev_point = None
                        self.eraser_mode = False

                    # ── Interacción con UI en modo SELECT/OPEN
                    if gesture in ("SELECT", "OPEN", "PINCH"):
                        on_palette = self._check_color_hover(smooth_pt)
                        on_button  = self._check_button_hover(smooth_pt, last_frame_bg)
                        self.drawing   = False
                        self.prev_point = None

                    # ── Dibujar
                    elif gesture == "DRAW":
                        self._check_color_hover(smooth_pt)
                        self._hover_btn = None
                        self._hover_btn_frames = 0

                        # ¿Está en la zona de la paleta?
                        ph = self.cfg["palette_height"]
                        mg = self.cfg["ui_margin"]
                        in_palette = smooth_pt[1] < ph + mg * 2

                        if not in_palette:
                            if not self.drawing:
                                self._push_undo()
                                self.drawing = True

                            color = (0, 0, 0) if self.eraser_mode else self.current_color
                            size  = (self.brush_size * self.cfg["eraser_multiplier"]
                                     if self.eraser_mode else self.brush_size)
                            self._draw_stroke(smooth_pt, color, size)
                            self.prev_point = smooth_pt
                        else:
                            self.drawing    = False
                            self.prev_point = None

                    else:
                        self.drawing    = False
                        self.prev_point = None

                    # Dibujar landmarks
                    self._draw_landmarks(frame, hand_landmarks)

                    # Cursor virtual
                    self._draw_cursor(frame, smooth_pt, gesture)

            else:
                # Sin mano detectada
                self.drawing    = False
                self.prev_point = None
                self.smooth_points.clear()
                self._gesture_buffer.clear()
                gesture = "NONE"

            # ── Fusionar canvas con frame
            output = self._merge_canvas_on_frame(frame)

            # ── Dibujar HUD
            output = self._draw_ui(output, gesture, fps)

            # ── Mostrar
            cv2.imshow(win_name, output)

            # ── Teclas
            key = cv2.waitKey(1) & 0xFF
            if key == ord('q') or key == 27:   # Q o ESC
                break
            elif key == ord('c') or key == ord('C'):
                self._push_undo()
                self.canvas[:] = 0
                print("[🗑️] Canvas limpiado")
            elif key == ord('h') or key == ord('H'):
                self.show_hud = not self.show_hud
            elif key == ord('f') or key == ord('F'):
                self.fullscreen = not self.fullscreen
                flag = cv2.WINDOW_FULLSCREEN if self.fullscreen else cv2.WINDOW_NORMAL
                cv2.setWindowProperty(win_name, cv2.WND_PROP_FULLSCREEN,
                                      cv2.WINDOW_FULLSCREEN if self.fullscreen
                                      else cv2.WINDOW_NORMAL)
            elif key == ord('s') or key == ord('S'):
                self.save_drawing(last_frame_bg)
            elif key == 26:    # Ctrl+Z
                self.undo()
            elif key == 25:    # Ctrl+Y
                self.redo()
            elif key == ord('+') or key == ord('='):
                self.brush_size = min(self.brush_size + 2, self.cfg["max_brush_size"])
            elif key == ord('-'):
                self.brush_size = max(self.brush_size - 2, self.cfg["min_brush_size"])

        # ── Limpieza
        cap.release()
        self.hands.close()
        cv2.destroyAllWindows()
        print("\n[👋] ¡Hasta luego! Tus dibujos están en ./" + self.cfg["save_dir"])


# ─────────────────────────────────────────────
#  PUNTO DE ENTRADA
# ─────────────────────────────────────────────
def main():
    import sys

    # Soporte para argumento de índice de cámara
    if len(sys.argv) > 1:
        try:
            CONFIG["camera_index"] = int(sys.argv[1])
        except ValueError:
            pass

    painter = VirtualPainter()
    painter.run()


if __name__ == "__main__":
    main()