"""
painter.py - Clase principal VirtualPainter de Magic Paint
Contiene: lógica de gestos, canvas, efectos visuales y renderizado.
"""
import cv2
import mediapipe as mp
import numpy as np
import os
import math
import time
from collections import deque, Counter
from datetime import datetime

from config import (
    CONFIG, UI, COLORS,
    APP_MODE_PAINT, APP_MODE_COLOR,
    TOOL_BRUSH, TOOL_FILL, TOOL_ERASER,
    TIP, PIP,
)
from ui_helpers import (
    _build_sidebar_strip, draw_glass_sidebar_fast,
    draw_glass_border_fast, draw_glass_button_fast,
    draw_animated_title, draw_gradient_bar, draw_glow_circle_fast,
    draw_clouds_fast, draw_rounded_rect, draw_neon_border,
    put_text_centered, _fill_rounded, _stroke_rounded, _lerp_color,
)
from tools import flood_fill_smooth, ColorPicker, ImageSelector


class VirtualPainter:

    # ──────────────────────────────────────────
    #  PARTÍCULA
    # ──────────────────────────────────────────
    class Particle:
        __slots__ = ('x', 'y', 'vx', 'vy', 'r', 'col', 'life', 'age', 'W', 'H')

        def __init__(self, W, H):
            self.reset(W, H)

        def reset(self, W, H):
            self.x   = float(np.random.randint(0, W))
            self.y   = float(np.random.randint(0, H))
            self.vx  = float(np.random.uniform(-1.2,  1.2))
            self.vy  = float(np.random.uniform(-2.0, -0.4))
            self.r   = int(np.random.randint(2, 5))
            colors   = [UI["vivo_cyan"], UI["vivo_verde"], UI["vivo_rosa"],
                        UI["vivo_naranja"], UI["vivo_amarillo"], UI["vivo_morado"]]
            self.col  = colors[np.random.randint(0, len(colors))]
            self.life = int(np.random.randint(60, 150))
            self.age  = 0
            self.W    = W
            self.H    = H

        def update(self):
            self.x  += self.vx
            self.y  += self.vy
            self.vy += 0.04
            self.age += 1
            if self.age > self.life or self.y > self.H+10 or \
               self.x < 0 or self.x > self.W:
                self.reset(self.W, self.H)

        def draw(self, frame):
            if self.age >= self.life:
                return
            r = max(1, int(self.r * (1.0 - self.age/self.life)))
            cv2.circle(frame, (int(self.x), int(self.y)), r, self.col, -1, cv2.LINE_AA)

    # ──────────────────────────────────────────
    #  INIT
    # ──────────────────────────────────────────
    def __init__(self):
        self.cfg = CONFIG
        self.W   = self.cfg["width"]
        self.H   = self.cfg["height"]

        # Modos y herramientas
        self.app_mode   = APP_MODE_PAINT
        self.active_tool = TOOL_BRUSH

        # Canvas y capa de coloreo
        self.canvas           = np.zeros((self.H, self.W, 3), dtype=np.uint8)
        self.color_image_orig = None
        self.color_layer      = None
        self.color_image_path = None
        self.fill_tolerance   = self.cfg["fill_tolerance"]

        # Estado de dibujo
        self.drawing    = False
        self.prev_point = None
        self.brush_size = self.cfg["default_brush_size"]
        self.eraser_mode = False

        # Color activo
        self.color_index   = 2
        self.current_color = COLORS[2]["bgr"]

        # Opciones de vista
        self.show_hud   = self.cfg["show_hud"]
        self.fullscreen = False

        # Suavizado
        self.smooth_points = deque(maxlen=self.cfg["smoothing_points"])
        self.smooth_brush  = deque(maxlen=10)

        # Undo / redo
        self.undo_stack = deque(maxlen=self.cfg["max_undo_steps"])
        self.redo_stack = deque(maxlen=self.cfg["max_undo_steps"])
        self._push_undo()

        # Gestos
        self._gesture_buffer     = deque(maxlen=self.cfg["gesture_smoothing"])
        self._last_stable_gesture = "NONE"
        self._fill_done           = False

        # Hover de botones
        self._hover_btn         = None
        self._hover_btn_frames  = 0
        self._hover_btn_thr     = 20
        self._btn_hover_progress = 0

        # Notificaciones
        self._notif       = ""
        self._notif_timer = 0
        self._notif_color = UI["vivo_verde"]

        # Efectos visuales
        self._paint_splashes = []
        self._particles = [
            self.Particle(self.W, self.H)
            for _ in range(self.cfg["particle_count"])
        ]

        # FPS y frames
        self._fps_buf      = deque(maxlen=30)
        self._last_t       = time.time()
        self._frame_counter = 0

        # Landmarks y gestos
        self._last_landmarks = None
        self._last_gesture   = "NONE"
        self._hand_present   = False

        # Caches de fondo (sky + nubes)
        self._sky_base        = None
        self._cloud_frame_cnt = -1
        self._cloud_interval  = self.cfg["cloud_redraw_interval"]
        self._sky_with_clouds = None

        # Cache de blobs de pintura
        self._blob_cache  = {}
        self._blob_t_last = -99

        # Logo UPEC
        self._upec_logo = None
        logo_path = self.cfg.get("upec_logo_path", "")
        if os.path.isfile(logo_path):
            logo_raw = cv2.imread(logo_path, cv2.IMREAD_UNCHANGED)
            if logo_raw is not None:
                self._upec_logo = logo_raw

        # MediaPipe
        self.mp_hands = mp.solutions.hands
        self.hands    = self.mp_hands.Hands(
            static_image_mode=False,
            max_num_hands=1,
            min_detection_confidence=self.cfg["detection_confidence"],
            min_tracking_confidence=self.cfg["tracking_confidence"],
        )
        self.mp_draw        = mp.solutions.drawing_utils
        self.mp_draw_styles = mp.solutions.drawing_styles

        # Directorios y selectores
        os.makedirs(self.cfg["images_dir"], exist_ok=True)
        os.makedirs(self.cfg["save_dir"],   exist_ok=True)
        self.img_selector = ImageSelector(
            self.cfg["images_dir"], self.cfg["image_extensions"]
        )

        # Construir UI
        self._build_ui()
        self._ui_update_counter = 0
        _build_sidebar_strip(self.SIDEBAR_W, self.H)   # warm-up caché

    # ──────────────────────────────────────────
    #  NOTIFICACIONES Y CAPAS
    # ──────────────────────────────────────────
    def _notify(self, msg, color=None, dur=90):
        self._notif       = msg
        self._notif_timer = dur
        self._notif_color = color or UI["vivo_verde"]

    def _get_layer(self):
        if self.app_mode == APP_MODE_COLOR and self.color_layer is not None:
            return self.color_layer
        return self.canvas

    def _set_layer(self, d):
        if self.app_mode == APP_MODE_COLOR and self.color_layer is not None:
            self.color_layer = d
        else:
            self.canvas = d

    # ──────────────────────────────────────────
    #  UNDO / REDO
    # ──────────────────────────────────────────
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

    # ──────────────────────────────────────────
    #  IMAGEN PARA COLOREAR
    # ──────────────────────────────────────────
    def load_color_image(self, path):
        img = cv2.imread(path)
        if img is None:
            self._notify("Error abriendo imagen", UI["vivo_rojo"])
            return False
        draw_start_x = self.SIDEBAR_W
        draw_end_x   = self.W - self.SIDEBAR_W
        img_resized  = cv2.resize(
            img, (draw_end_x - draw_start_x, self.H),
            interpolation=cv2.INTER_AREA
        )
        full_canvas = np.zeros((self.H, self.W, 3), dtype=np.uint8)
        full_canvas[:, draw_start_x:draw_end_x] = img_resized
        self.color_image_orig = full_canvas.copy()
        self.color_layer      = full_canvas.copy()
        self.color_image_path = path
        self.app_mode         = APP_MODE_COLOR
        self.undo_stack.clear()
        self.redo_stack.clear()
        self._push_undo()
        self._notify(f"Imagen: {os.path.basename(path)}", UI["vivo_cyan"])
        return True

    def reset_color_image(self):
        if self.color_image_orig is not None:
            self._push_undo()
            self.color_layer = self.color_image_orig.copy()
            self._notify("Imagen restaurada", UI["vivo_naranja"])

    # ──────────────────────────────────────────
    #  GUARDAR E IMPRIMIR
    # ──────────────────────────────────────────
    def save_drawing(self, frame_bg=None):
        ts  = datetime.now().strftime("%Y%m%d_%H%M%S")
        ext = self.cfg["save_format"]
        if self.app_mode == APP_MODE_COLOR and self.color_layer is not None:
            save_img = self.color_layer[:, self.SIDEBAR_W:self.W-self.SIDEBAR_W]
            gray     = cv2.cvtColor(save_img, cv2.COLOR_BGR2GRAY)
            _, thresh = cv2.threshold(gray, 1, 255, cv2.THRESH_BINARY)
            coords   = cv2.findNonZero(thresh)
            if coords is not None:
                x, y, w, h = cv2.boundingRect(coords)
                save_img   = save_img[y:y+h, x:x+w]
            path = os.path.join(self.cfg["save_dir"], f"colored_{ts}.{ext}")
            cv2.imwrite(path, save_img)
        elif frame_bg is not None:
            path = os.path.join(self.cfg["save_dir"], f"painting_{ts}.{ext}")
            cv2.imwrite(path, self._merge_canvas_fast(frame_bg))
        else:
            path = os.path.join(self.cfg["save_dir"], f"canvas_{ts}.{ext}")
            cv2.imwrite(path, self.canvas)
        self._notify("Guardado!", UI["vivo_verde"])
        print(f"[OK] {path}")
        return path

    def print_drawing(self, frame_bg=None):
        if self.app_mode == APP_MODE_COLOR and self.color_layer is not None:
            art = self.color_layer[:, self.SIDEBAR_W:self.W-self.SIDEBAR_W].copy()
        elif frame_bg is not None:
            merged = self._merge_canvas_fast(frame_bg)
            art    = merged[:, self.SIDEBAR_W:self.W-self.SIDEBAR_W].copy()
        else:
            art = self.canvas.copy()

        PRINT_W = 1240; ART_H = 900
        art_h_orig, art_w_orig = art.shape[:2]
        art_resized = cv2.resize(
            art, (PRINT_W, int(art_h_orig * PRINT_W / art_w_orig)),
            interpolation=cv2.INTER_LANCZOS4
        )
        if art_resized.shape[0] > ART_H:
            art_resized = art_resized[:ART_H, :]
        elif art_resized.shape[0] < ART_H:
            pad = np.full((ART_H - art_resized.shape[0], PRINT_W, 3), 255, dtype=np.uint8)
            art_resized = np.vstack([art_resized, pad])

        HEADER_H = 160
        header   = np.full((HEADER_H, PRINT_W, 3), 255, dtype=np.uint8)
        cv2.rectangle(header, (0, 0), (PRINT_W, 8),           (0, 120, 50), -1)
        cv2.line(header, (0, HEADER_H-4), (PRINT_W, HEADER_H-4), (0, 120, 50), 3)

        logo_x = 20; text_x = logo_x
        if self._upec_logo is not None:
            lh, lw = self._upec_logo.shape[:2]
            logo_h_target = HEADER_H - 30
            lw_new  = int(lw * logo_h_target / lh)
            logo_r  = cv2.resize(self._upec_logo, (lw_new, logo_h_target),
                                 interpolation=cv2.INTER_AREA)
            ly1, ly2 = 15, 15 + logo_h_target
            lx1, lx2 = logo_x, logo_x + lw_new
            if logo_r.shape[2] == 4:
                alpha_ch = logo_r[:, :, 3:4] / 255.0
                rgb      = logo_r[:, :, :3]
                bg_roi   = header[ly1:ly2, lx1:lx2]
                header[ly1:ly2, lx1:lx2] = (
                    rgb * alpha_ch + bg_roi * (1 - alpha_ch)
                ).astype(np.uint8)
            else:
                header[ly1:ly2, lx1:lx2] = logo_r
            text_x = lx2 + 30

        font        = cv2.FONT_HERSHEY_SIMPLEX
        available_w = PRINT_W - text_x - 20
        center_x    = text_x + available_w // 2
        for title, y, fs, th, col in [
            ("UNIVERSIDAD POLITECNICA ESTATAL DEL CARCHI",
             55, 0.95, 2, (0, 100, 40)),
            ("CARRERA DE COMPUTACION",
             92, 0.75, 2, (30, 80, 30)),
            ("Feria Agroalimentaria, Tecnologica y Turistica Sostenible UPEC - Pintura con Gestos de Mano",
             122, 0.55, 1, (80, 80, 80)),
        ]:
            (tw, _), _ = cv2.getTextSize(title, font, fs, th)
            cv2.putText(header, title, (center_x - tw//2, y),
                        font, fs, col, th, cv2.LINE_AA)

        date_str = datetime.now().strftime("%d/%m/%Y  %H:%M")
        (twd, _), _ = cv2.getTextSize(date_str, font, 0.44, 1)
        cv2.putText(header, date_str, (PRINT_W - twd - 20, 148),
                    font, 0.44, (120, 120, 120), 1, cv2.LINE_AA)

        FOOTER_H = 40
        footer   = np.full((FOOTER_H, PRINT_W, 3), 255, dtype=np.uint8)
        cv2.rectangle(footer, (0, 0), (PRINT_W, 4), (0, 120, 50), -1)
        put_text_centered(
            footer,
            "UNIVERSIDAD POLITECNICA ESTATAL DEL CARCHI - UPEC  |  www.upec.edu.ec",
            PRINT_W//2, 26, 0.42, (80, 80, 80), 1
        )

        page = np.vstack([header, art_resized, footer])
        ts   = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_path = os.path.join(self.cfg["save_dir"], f"impresion_upec_{ts}.png")
        cv2.imwrite(out_path, page)

        preview_scale = min(1.0, 900 / page.shape[0])
        preview_w = int(page.shape[1] * preview_scale)
        preview_h = int(page.shape[0] * preview_scale)
        preview   = cv2.resize(page, (preview_w, preview_h), interpolation=cv2.INTER_AREA)
        banner_h  = 36
        banner    = np.full((banner_h, preview_w, 3), (30, 30, 30), dtype=np.uint8)
        cv2.putText(
            banner,
            f"Guardado: {out_path}   |   Ctrl+P para imprimir   |   ESC para cerrar",
            (10, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.44, (200, 230, 200), 1, cv2.LINE_AA
        )
        win_print = "Vista Previa de Impresion - ESC para cerrar"
        cv2.namedWindow(win_print, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(win_print, preview_w, preview_h + banner_h)
        cv2.imshow(win_print, np.vstack([banner, preview]))
        self._notify("Impresion guardada!", UI["tool_print"])
        print(f"[OK] {out_path}")
        return out_path

    # ──────────────────────────────────────────
    #  CONSTRUCCIÓN DE UI
    # ──────────────────────────────────────────
    def _build_ui(self):
        W, H = self.W, self.H
        self.SIDEBAR_W = 165
        self.SIDEBAR_H = H
        BTN_W = 148; BTN_H = 50; BTN_X = 8; BTN_GAP = 7; start_y = 145

        def btn_y(i):
            return start_y + i*(BTN_H + BTN_GAP)

        self.left_buttons = {
            "BRUSH":        (BTN_X, btn_y(0), BTN_X+BTN_W, btn_y(0)+BTN_H),
            "FILL":         (BTN_X, btn_y(1), BTN_X+BTN_W, btn_y(1)+BTN_H),
            "ERASER":       (BTN_X, btn_y(2), BTN_X+BTN_W, btn_y(2)+BTN_H),
            "COLOR_PICKER": (BTN_X, btn_y(3), BTN_X+BTN_W, btn_y(3)+BTN_H),
        }
        right_x = W - BTN_W - 8
        self.right_buttons = {
            "UNDO":     (right_x, btn_y(0), right_x+BTN_W, btn_y(0)+BTN_H),
            "REDO":     (right_x, btn_y(1), right_x+BTN_W, btn_y(1)+BTN_H),
            "CLEAR":    (right_x, btn_y(2), right_x+BTN_W, btn_y(2)+BTN_H),
            "SAVE":     (right_x, btn_y(3), right_x+BTN_W, btn_y(3)+BTN_H),
            "OPEN_IMG": (right_x, btn_y(4), right_x+BTN_W, btn_y(4)+BTN_H),
            "PRINT":    (right_x, btn_y(5), right_x+BTN_W, btn_y(5)+BTN_H),
        }
        self.buttons  = {**self.left_buttons, **self.right_buttons}
        self.DRAW_X1  = self.SIDEBAR_W
        self.DRAW_X2  = W - self.SIDEBAR_W

    # ──────────────────────────────────────────
    #  DETECCIÓN DE GESTOS
    # ──────────────────────────────────────────
    def _fingers_up(self, lm):
        h, w = self.H, self.W
        pts  = [(int(lm[i].x*w), int(lm[i].y*h)) for i in range(21)]
        up   = [pts[TIP[0]][0] > pts[PIP[0]][0]]
        for i in range(1, 5):
            up.append(pts[TIP[i]][1] < pts[PIP[i]][1])
        return up

    def _detect_gesture(self, lm):
        up   = self._fingers_up(lm)
        n_up = sum(up)
        h, w = self.H, self.W

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
            self._last_stable_gesture = (
                Counter(self._gesture_buffer).most_common(1)[0][0]
            )
        return self._last_stable_gesture

    # ──────────────────────────────────────────
    #  SUAVIZADO
    # ──────────────────────────────────────────
    def _smooth_pt(self, pt):
        self.smooth_points.append(pt)
        return (
            int(np.mean([p[0] for p in self.smooth_points])),
            int(np.mean([p[1] for p in self.smooth_points])),
        )

    def _smooth_bs(self, s):
        self.smooth_brush.append(s)
        return int(np.mean(self.smooth_brush))

    # ──────────────────────────────────────────
    #  TRAZO Y RELLENO
    # ──────────────────────────────────────────
    def _stroke(self, pt, color, size):
        layer = self._get_layer()
        if self.prev_point:
            cv2.line(layer, self.prev_point, pt, color, size, cv2.LINE_AA)
        cv2.circle(layer, pt, size//2, color, -1, cv2.LINE_AA)
        self._set_layer(layer)
        if not self.prev_point and color != (0, 0, 0):
            if len(self._paint_splashes) < self.cfg["max_paint_splashes"]:
                self._paint_splashes.append([pt[0], pt[1], size+4, color, 0, 14])

    def _apply_fill(self, pt):
        self._push_undo()
        result = flood_fill_smooth(
            self._get_layer(), pt, self.current_color, self.fill_tolerance
        )
        self._set_layer(result)
        if len(self._paint_splashes) < self.cfg["max_paint_splashes"]:
            self._paint_splashes.append([pt[0], pt[1], 25, self.current_color, 0, 20])
        self._notify(f"Relleno (tol:{self.fill_tolerance})", UI["vivo_naranja"])

    # ──────────────────────────────────────────
    #  HOVER DE BOTONES
    # ──────────────────────────────────────────
    def _check_btn_hover(self, pt, frame_bg=None):
        x, y = pt
        for name, (x1, y1, x2, y2) in self.buttons.items():
            if x1 <= x <= x2 and y1 <= y <= y2:
                if self._hover_btn == name:
                    self._hover_btn_frames   += 1
                    self._btn_hover_progress  = min(
                        1.0, self._hover_btn_frames / self._hover_btn_thr
                    )
                    if self._hover_btn_frames >= self._hover_btn_thr:
                        self._trigger_btn(name, frame_bg)
                        self._hover_btn_frames = 0
                else:
                    self._hover_btn          = name
                    self._hover_btn_frames   = 0
                    self._btn_hover_progress = 0
                return True
        self._hover_btn          = None
        self._hover_btn_frames   = 0
        self._btn_hover_progress = 0
        return False

    def _trigger_btn(self, name, frame_bg=None):
        if   name == "UNDO":      self.undo()
        elif name == "REDO":      self.redo()
        elif name == "SAVE":      self.save_drawing(frame_bg)
        elif name == "PRINT":     self.print_drawing(frame_bg)
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
            self._notify("Pincel", UI["tool_brush"])
        elif name == "FILL":
            self.active_tool = TOOL_FILL;   self.eraser_mode = False
            self._notify("Relleno", UI["tool_fill"])
        elif name == "ERASER":
            self.active_tool = TOOL_ERASER; self.eraser_mode = True
            self._notify("Borrador", UI["tool_eraser"])
        elif name == "OPEN_IMG":
            self.img_selector._load()
            path = self.img_selector.show(self.W, self.H)
            if path:
                self.load_color_image(path)
        elif name == "COLOR_PICKER": self._open_color_picker()

    def _open_color_picker(self):
        picker = ColorPicker()
        result = picker.show(self.W, self.H)
        if result:
            self.current_color = result["bgr"]
            self.color_index   = -1
            for i, c in enumerate(COLORS):
                if c["bgr"] == result["bgr"]:
                    self.color_index = i; break
            self.eraser_mode = False
            self.active_tool = TOOL_BRUSH
            self._notify(f"Color: {result['name']}", result["bgr"])

    # ──────────────────────────────────────────
    #  RENDER: FONDO Y CANVAS
    # ──────────────────────────────────────────
    def _get_sky_base(self):
        if self._sky_base is None:
            sky   = np.zeros((self.H, self.W, 3), dtype=np.uint8)
            y_idx = np.arange(self.H, dtype=np.float32) / self.H
            sky[:, :, 0] = (255*(1-y_idx) + 230*y_idx).astype(np.uint8)[:, np.newaxis]
            sky[:, :, 1] = (210*(1-y_idx) + 245*y_idx).astype(np.uint8)[:, np.newaxis]
            sky[:, :, 2] = (135*(1-y_idx) + 255*y_idx).astype(np.uint8)[:, np.newaxis]
            self._sky_base = sky
        return self._sky_base

    def _merge_canvas_fast(self, frame):
        if self._sky_with_clouds is None:
            self._sky_with_clouds = self._get_sky_base().copy()

        output = self._sky_with_clouds.copy()
        op     = self.cfg["canvas_opacity"]
        if np.any(self.canvas):
            mask = (self.canvas.sum(axis=2) > 0)
            if np.any(mask):
                output[mask] = (
                    output[mask] * (1-op) + self.canvas[mask] * op
                ).astype(np.uint8)
        return output

    # ──────────────────────────────────────────
    #  EFECTOS VISUALES
    # ──────────────────────────────────────────
    def _update_effects_fast(self, frame):
        for p in self._particles:
            p.update(); p.draw(frame)

        alive = []
        for s in self._paint_splashes:
            x, y, r, col, age, max_age = s
            if age < max_age:
                a       = 1.0 - age / max_age
                cr      = max(1, int(r * (1 + age*0.3)))
                dim_col = tuple(int(col[c] * a * 0.6) for c in range(3))
                cv2.circle(frame, (x, y), cr, dim_col, -1, cv2.LINE_AA)
                s[4] += 1
                alive.append(s)
        self._paint_splashes = alive

    def _draw_paint_blobs_fast(self, frame, t):
        paint_colors = [
            (80, 107, 255), (80, 202, 254), (80, 222, 100), (251, 219,  72),
            (60, 159, 255), (245, 110, 197), (157, 107, 255), (251, 160, 80),
        ]
        blob_w   = self.SIDEBAR_W // len(paint_colors)
        t_bucket = int(t * 15)
        if t_bucket != self._blob_t_last:
            self._blob_cache  = {}
            self._blob_t_last = t_bucket
            for side_x in [0, self.W - self.SIDEBAR_W]:
                for i, pc in enumerate(paint_colors):
                    bx   = side_x + i*blob_w; by = self.H - 20
                    wave = int(6  * math.sin(t*2.0 + i*0.8))
                    peak = int(4  * math.sin(t*2.5 + i*1.1))
                    pts  = np.array([
                        [bx,            self.H],
                        [bx,            by + wave],
                        [bx + blob_w//2, by - 10 + peak],
                        [bx + blob_w,   by + wave],
                        [bx + blob_w,   self.H],
                    ], dtype=np.int32)
                    self._blob_cache[(side_x, i)] = (pts, pc)
        for pts, pc in self._blob_cache.values():
            cv2.fillPoly(frame, [pts], pc)

    # ──────────────────────────────────────────
    #  DIBUJAR UI
    # ──────────────────────────────────────────
    def _draw_ui(self, frame, gesture, fps):
        if not self.show_hud:
            return frame
        W, H = self.W, self.H
        t = time.time()

        # Sidebars
        draw_glass_sidebar_fast(frame, 0,               self.SIDEBAR_W, H)
        draw_glass_sidebar_fast(frame, W-self.SIDEBAR_W, self.SIDEBAR_W, H)

        # Bordes neon
        draw_glass_border_fast(frame, self.SIDEBAR_W,   0, H, (0, 206, 209))
        draw_glass_border_fast(frame, W-self.SIDEBAR_W, 0, H, (255, 20, 147))

        # Manchas de pintura
        self._draw_paint_blobs_fast(frame, t)

        # Header central
        header_h = 52
        frame[0:header_h, self.SIDEBAR_W:W-self.SIDEBAR_W] = (18, 14, 24)
        frame[0:2,         self.SIDEBAR_W:W-self.SIDEBAR_W] = (80, 60, 100)
        draw_gradient_bar(frame, self.SIDEBAR_W, header_h-2, W-self.SIDEBAR_W,
                          header_h, (0, 206, 209), (255, 20, 147))

        # Panel título (sidebar izquierda)
        cv2.rectangle(frame, (4, 4), (self.SIDEBAR_W-4, 133), (40, 34, 55), -1)
        _stroke_rounded(frame, 4, 4, self.SIDEBAR_W-4, 133, 8, (80, 60, 100), 1)
        cv2.rectangle(frame, (4, 4), (self.SIDEBAR_W-4, 6), (0, 206, 209), -1)
        draw_animated_title(frame, self.SIDEBAR_W//2, 40, t)
        draw_gradient_bar(frame, 8, 82, self.SIDEBAR_W-8, 84,
                          (0, 206, 209), (255, 20, 147))
        put_text_centered(frame, "v5.2",     self.SIDEBAR_W//2, 98,  0.38, (150, 130, 170), 1)
        put_text_centered(frame, "GESTOS",   self.SIDEBAR_W//2, 116, 0.38, (150, 130, 170), 1)

        # Badge de modo
        mode_labels = {
            APP_MODE_PAINT: ("* PINTURA",  (50,  205,  50)),
            APP_MODE_COLOR: ("* COLOREAR", (30,  144, 255)),
        }
        mode_txt, mode_col = mode_labels.get(self.app_mode, ("* PINTURA", (50, 205, 50)))
        bx = self.SIDEBAR_W + 14
        (btw, bth), _ = cv2.getTextSize(mode_txt, cv2.FONT_HERSHEY_SIMPLEX, 0.52, 2)
        cv2.rectangle(frame, (bx-6, 8), (bx+btw+8, header_h-8), (28, 22, 38), -1)
        _stroke_rounded(frame, bx-6, 8, bx+btw+8, header_h-8, 5, mode_col, 2)
        cv2.putText(frame, mode_txt, (bx, header_h//2+8),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.52, mode_col, 2, cv2.LINE_AA)

        # Gesto actual
        GESTURE_ICONS = {
            "DRAW":       "DIBUJANDO",  "SELECT":     "SELECCIONAR",
            "ERASER":     "BORRADOR",   "OPEN":       "PAUSADO",
            "PINCH":      "GROSOR",     "THUMB_UP":   "SGTE COLOR",
            "THUMB_DOWN": "ANT COLOR",  "NONE":       "Sin mano",
            "THREE":      "3 DEDOS",
        }
        g_label = GESTURE_ICONS.get(gesture, gesture)
        g_col   = (50, 205, 50)   if gesture == "DRAW" else \
                  (254, 202, 80)  if gesture in ("SELECT", "PINCH") else \
                  (147, 0,   211) if gesture == "ERASER" else (150, 130, 170)
        (gtw, _), _ = cv2.getTextSize(g_label, cv2.FONT_HERSHEY_SIMPLEX, 0.44, 1)
        gx = W - self.SIDEBAR_W - gtw - 16
        cv2.putText(frame, "Gesto:",  (gx-58, header_h//2+7),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.38, (150, 130, 170), 1, cv2.LINE_AA)
        cv2.putText(frame, g_label,   (gx,    header_h//2+7),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.44, g_col, 1, cv2.LINE_AA)

        # FPS
        fps_col = (50, 205, 50) if fps > 25 else (254, 202, 80)
        cv2.putText(frame, f"FPS:{int(fps)}",
                    (W-self.SIDEBAR_W+8, header_h-10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.42, fps_col, 1, cv2.LINE_AA)

        # Botones izquierdos
        LEFT_BTN_INFO = {
            "BRUSH":        ("PINCEL",   "B", UI["tool_brush"]),
            "FILL":         ("RELLENO",  "R", UI["tool_fill"]),
            "ERASER":       ("BORRADOR", "E", UI["tool_eraser"]),
            "COLOR_PICKER": ("COLORES",  "C", UI["tool_color"]),
        }
        for name, (x1, y1, x2, y2) in self.left_buttons.items():
            if name not in LEFT_BTN_INFO:
                continue
            label, icon, accent = LEFT_BTN_INFO[name]
            is_hov    = (self._hover_btn == name)
            is_active = (
                (name == "BRUSH"  and self.active_tool == TOOL_BRUSH)  or
                (name == "FILL"   and self.active_tool == TOOL_FILL)   or
                (name == "ERASER" and self.active_tool == TOOL_ERASER)
            )
            draw_glass_button_fast(
                frame, x1, y1, x2, y2, label, icon, accent,
                is_active, is_hov,
                self._btn_hover_progress if is_hov else 0.0, t
            )

        # Botones derechos
        RIGHT_BTN_INFO = {
            "UNDO":     ("DESHACER", "<", UI["tool_undo"]),
            "REDO":     ("REHACER",  ">", UI["tool_redo"]),
            "CLEAR":    ("LIMPIAR",  "X", UI["tool_clear"]),
            "SAVE":     ("GUARDAR",  "S", UI["tool_save"]),
            "OPEN_IMG": ("ABRIR",    "O", UI["tool_open"]),
            "PRINT":    ("IMPRIMIR", "P", UI["tool_print"]),
        }
        for name, (x1, y1, x2, y2) in self.right_buttons.items():
            if name not in RIGHT_BTN_INFO:
                continue
            label, icon, accent = RIGHT_BTN_INFO[name]
            is_hov    = (self._hover_btn == name)
            is_active = False
            draw_glass_button_fast(
                frame, x1, y1, x2, y2, label, icon, accent,
                is_active, is_hov,
                self._btn_hover_progress if is_hov else 0.0, t
            )

        # Indicador de color actual
        col_indicator_y = self.left_buttons["COLOR_PICKER"][3] + 14
        if col_indicator_y + 30 < H - 55:
            put_text_centered(frame, "COLOR ACTUAL",
                              self.SIDEBAR_W//2, col_indicator_y+8, 0.32, (150, 130, 170), 1)
            col_cx = self.SIDEBAR_W//2; col_cy = col_indicator_y + 28
            cur = self.current_color
            if not self.eraser_mode:
                dim = tuple(max(0, int(c*0.3)) for c in cur)
                cv2.circle(frame, (col_cx, col_cy), 18, dim, -1, cv2.LINE_AA)
                cv2.circle(frame, (col_cx, col_cy), 14, cur, -1, cv2.LINE_AA)
                cv2.circle(frame, (col_cx, col_cy), 14, (255,255,255), 1, cv2.LINE_AA)
            else:
                cv2.circle(frame, (col_cx, col_cy), 14, (200, 180, 150), -1, cv2.LINE_AA)
                cv2.putText(frame, "E",
                            (col_cx-5, col_cy+5),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.45, (50, 50, 50), 2)

        # Notificación
        if self._notif_timer > 0:
            self._notif_timer -= 1
            nx = self.SIDEBAR_W + 18; ny = H - 55
            (nw, nh), _ = cv2.getTextSize(self._notif, cv2.FONT_HERSHEY_SIMPLEX, 0.58, 2)
            _fill_rounded(frame, nx-10, ny-nh-10, nx+nw+10, ny+10, 8, (18, 14, 24))
            _stroke_rounded(frame, nx-10, ny-nh-10, nx+nw+10, ny+10, 8, self._notif_color, 2)
            cv2.putText(frame, self._notif, (nx+1, ny+1),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.58, (0,0,0), 3, cv2.LINE_AA)
            cv2.putText(frame, self._notif, (nx, ny),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.58, self._notif_color, 2, cv2.LINE_AA)

        self._ui_update_counter += 1
        return frame

    # ──────────────────────────────────────────
    #  CURSOR
    # ──────────────────────────────────────────
    def _draw_cursor(self, frame, pt, gesture):
        col = self.current_color if not self.eraser_mode else (180, 160, 130)
        r   = self.brush_size + 4
        if self.active_tool == TOOL_FILL and gesture == "DRAW":
            cv2.rectangle(frame, (pt[0]-14, pt[1]-8), (pt[0]+14, pt[1]+18), col, -1)
            cv2.rectangle(frame, (pt[0]-14, pt[1]-8), (pt[0]+14, pt[1]+18), (254,202,80), 2)
            cv2.putText(frame, "F", (pt[0]-5, pt[1]+12),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, (20,20,20), 2, cv2.LINE_AA)
        elif self.active_tool == TOOL_ERASER or self.eraser_mode:
            er = self.brush_size * self.cfg["eraser_multiplier"] + 4
            cv2.circle(frame, pt, er, (180, 160, 130), 2, cv2.LINE_AA)
            cv2.line(frame, (pt[0]-er, pt[1]), (pt[0]+er, pt[1]), (180,160,130), 1)
            cv2.line(frame, (pt[0], pt[1]-er), (pt[0], pt[1]+er), (180,160,130), 1)
        elif gesture == "DRAW":
            draw_glow_circle_fast(frame, pt[0], pt[1], r, col, 0.4)
            cv2.circle(frame, pt, 4, (255,255,255), -1)
        elif gesture == "SELECT":
            cv2.drawMarker(frame, pt, (254,202,80), cv2.MARKER_CROSS, 26, 2, cv2.LINE_AA)
            cv2.circle(frame, pt, 14, (254,202,80), 1, cv2.LINE_AA)
        else:
            cv2.circle(frame, pt, 12, (150,130,170), 1, cv2.LINE_AA)
            cv2.circle(frame, pt, 3,  (150,130,170), -1)

    # ──────────────────────────────────────────
    #  BUCLE PRINCIPAL
    # ──────────────────────────────────────────
    def run(self):
        cap = cv2.VideoCapture(self.cfg["camera_index"])
        cap.set(cv2.CAP_PROP_FRAME_WIDTH,  self.W)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.H)
        cap.set(cv2.CAP_PROP_FPS,          60)
        cap.set(cv2.CAP_PROP_BUFFERSIZE,   1)
        if not cap.isOpened():
            print("[ERROR] No se pudo abrir la camara."); return

        win = "Magic Paint v5.2 - OPTIMIZADO"
        cv2.namedWindow(win, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(win, self.W, self.H)

        from main import _print_banner
        _print_banner()

        last_bg = None; gesture = "NONE"
        _lm_draw = None; _smooth_d = None

        while True:
            ret, frame = cap.read()
            if not ret:
                print("[ERROR] Frame fallido."); break
            if self.cfg["flip_horizontal"]:
                frame = cv2.flip(frame, 1)
            fh, fw = frame.shape[:2]
            if fw != self.W or fh != self.H:
                frame = cv2.resize(frame, (self.W, self.H))
            last_bg = frame.copy()

            now = time.time()
            self._fps_buf.append(1.0 / max(now - self._last_t, 1e-6))
            self._last_t = now
            fps = float(np.mean(self._fps_buf))
            self._frame_counter += 1

            skip = self.cfg["skip_frames_detection"]
            process_hands = (self._frame_counter % (skip+1) == 0)

            if process_hands:
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                rgb.flags.writeable = False
                res = self.hands.process(rgb)
                rgb.flags.writeable = True
                if res.multi_hand_landmarks:
                    self._hand_present   = True
                    self._last_landmarks = res.multi_hand_landmarks[0]
                    lm  = self._last_landmarks.landmark
                    ix  = int(lm[8].x * self.W); iy = int(lm[8].y * self.H)
                    tx  = int(lm[4].x * self.W); ty = int(lm[4].y * self.H)
                    pinch_d = math.dist((tx, ty), (ix, iy))
                    mn, mx  = self.cfg["min_brush_size"], self.cfg["max_brush_size"]
                    self.brush_size = self._smooth_bs(
                        int(mn + float(np.clip((pinch_d-20)/200, 0, 1)) * (mx-mn))
                    )
                    self._last_gesture = self._stable_gesture(
                        self._detect_gesture(lm)
                    )
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
                gesture  = "NONE"; _lm_draw = None; _smooth_d = None
                self.drawing = False; self.prev_point = None; self._fill_done = False
            else:
                gesture  = self._last_gesture
                _lm_draw = self._last_landmarks
                if _lm_draw is not None:
                    lm       = _lm_draw.landmark
                    _smooth_d = self._smooth_pt(
                        (int(lm[8].x*self.W), int(lm[8].y*self.H))
                    )
                    if gesture == "THUMB_UP":
                        self.color_index = (self.color_index + 1) % len(COLORS)
                        self.current_color = COLORS[self.color_index]["bgr"]
                        self.eraser_mode   = False
                        self._notify(
                            f"Color: {COLORS[self.color_index]['name']}",
                            COLORS[self.color_index]["bgr"]
                        )
                    elif gesture == "THUMB_DOWN":
                        self.color_index = (self.color_index - 1) % len(COLORS)
                        self.current_color = COLORS[self.color_index]["bgr"]
                        self.eraser_mode   = False
                        self._notify(
                            f"Color: {COLORS[self.color_index]['name']}",
                            COLORS[self.color_index]["bgr"]
                        )
                    elif gesture == "ERASER":
                        if self.active_tool != TOOL_ERASER:
                            self.active_tool = TOOL_ERASER
                            self.eraser_mode = True
                            self._notify("Borrador activado", UI["tool_eraser"])
                    elif gesture == "OPEN":
                        self.drawing = False; self.prev_point = None

                    if gesture in ("SELECT", "OPEN", "PINCH"):
                        if _smooth_d:
                            self._check_btn_hover(_smooth_d, last_bg)
                        self.drawing = False; self.prev_point = None
                        self._fill_done = False
                    elif gesture == "DRAW" and _smooth_d:
                        self._hover_btn          = None
                        self._hover_btn_frames   = 0
                        self._btn_hover_progress = 0
                        in_left  = _smooth_d[0] < self.SIDEBAR_W
                        in_right = _smooth_d[0] > self.W - self.SIDEBAR_W
                        in_bl    = any(
                            x1 <= _smooth_d[0] <= x2 and y1 <= _smooth_d[1] <= y2
                            for x1, y1, x2, y2 in self.left_buttons.values()
                        )
                        in_br    = any(
                            x1 <= _smooth_d[0] <= x2 and y1 <= _smooth_d[1] <= y2
                            for x1, y1, x2, y2 in self.right_buttons.values()
                        )
                        blocked = in_left or in_right or in_bl or in_br or _smooth_d[1] < 48
                        if not blocked:
                            if self.active_tool == TOOL_FILL:
                                if not self._fill_done:
                                    self._apply_fill(_smooth_d)
                                    self._fill_done = True
                                self.drawing    = False
                                self.prev_point = None
                            elif self.active_tool == TOOL_ERASER or self.eraser_mode:
                                if not self.drawing:
                                    self._push_undo(); self.drawing = True
                                esize = self.brush_size * self.cfg["eraser_multiplier"]
                                if (self.app_mode == APP_MODE_COLOR and
                                        self.color_image_orig is not None):
                                    mask_e = np.zeros((self.H, self.W), dtype=np.uint8)
                                    cv2.circle(mask_e, _smooth_d, esize, 255, -1)
                                    self.color_layer = np.where(
                                        np.stack([mask_e]*3, axis=-1) > 0,
                                        self.color_image_orig, self.color_layer
                                    ).astype(np.uint8)
                                else:
                                    self._stroke(_smooth_d, (0,0,0), esize)
                                self.prev_point = _smooth_d
                            else:
                                if not self.drawing:
                                    self._push_undo(); self.drawing = True
                                self._stroke(_smooth_d, self.current_color, self.brush_size)
                                self.prev_point = _smooth_d
                        else:
                            self.drawing    = False
                            self.prev_point = None
                            self._fill_done = False
                    else:
                        self.drawing    = False
                        self.prev_point = None
                        self._fill_done = False

            # ── Renderizado ────────────────────────
            if self.app_mode == APP_MODE_COLOR and self.color_layer is not None:
                output = cv2.addWeighted(self.color_layer, 0.88, frame, 0.12, 0)
            else:
                output = self._merge_canvas_fast(frame)

            self._update_effects_fast(output)

            if _lm_draw is not None and _smooth_d is not None and self._hand_present:
                self.mp_draw.draw_landmarks(
                    output, _lm_draw, self.mp_hands.HAND_CONNECTIONS,
                    self.mp_draw_styles.DrawingSpec(
                        color=(50,205,50), thickness=2, circle_radius=4),
                    self.mp_draw_styles.DrawingSpec(
                        color=(0,206,209), thickness=2),
                )
                self._draw_cursor(output, _smooth_d, gesture)

            output = self._draw_ui(output, gesture, fps)
            cv2.imshow(win, output)

            # ── Teclado ────────────────────────────
            key = cv2.waitKey(1) & 0xFF
            if key in (ord('q'), 27):
                break
            elif key == ord('1'):
                self.app_mode = APP_MODE_PAINT
                self._notify("Modo: Pintura Libre", UI["mode_paint"])
            elif key == ord('2'):
                if self.color_layer is not None:
                    self.app_mode = APP_MODE_COLOR
                    self._notify("Modo: Colorear", UI["mode_color"])
                else:
                    self._notify("Carga una imagen primero (tecla O)", UI["vivo_rojo"])
            elif key in (ord('o'), ord('O')):
                self.img_selector._load()
                path = self.img_selector.show(self.W, self.H)
                if path: self.load_color_image(path)
            elif key in (ord('b'), ord('B')):
                self.active_tool = TOOL_BRUSH; self.eraser_mode = False
                self._notify("Pincel", UI["tool_brush"])
            elif key in (ord('k'), ord('K')):
                self.active_tool = TOOL_FILL; self.eraser_mode = False
                self._notify("Relleno", UI["tool_fill"])
            elif key in (ord('e'), ord('E')):
                self.active_tool = TOOL_ERASER; self.eraser_mode = True
                self._notify("Borrador", UI["tool_eraser"])
            elif key in (ord('c'), ord('C')):
                self._push_undo()
                if self.app_mode == APP_MODE_COLOR and self.color_image_orig is not None:
                    self.color_layer = self.color_image_orig.copy()
                    self._notify("Imagen restaurada", UI["vivo_naranja"])
                else:
                    self.canvas[:] = 0
                    self._notify("Canvas limpiado", UI["vivo_rojo"])
            elif key in (ord('r'), ord('R')): self.reset_color_image()
            elif key in (ord('h'), ord('H')): self.show_hud = not self.show_hud
            elif key in (ord('f'), ord('F')):
                self.fullscreen = not self.fullscreen
                cv2.setWindowProperty(
                    win, cv2.WND_PROP_FULLSCREEN,
                    cv2.WINDOW_FULLSCREEN if self.fullscreen else cv2.WINDOW_NORMAL
                )
            elif key in (ord('s'), ord('S')): self.save_drawing(last_bg)
            elif key in (ord('p'), ord('P')): self.print_drawing(last_bg)
            elif key == 26: self.undo()
            elif key == 25: self.redo()
            elif key in (ord('+'), ord('=')):
                self.brush_size = min(self.brush_size + 2, self.cfg["max_brush_size"])
            elif key == ord('-'):
                self.brush_size = max(self.brush_size - 2, self.cfg["min_brush_size"])
            elif key == ord(']'):
                self.fill_tolerance = min(
                    self.fill_tolerance + 4, self.cfg["fill_tolerance_max"])
                self._notify(f"Tolerancia:{self.fill_tolerance}", UI["vivo_naranja"])
            elif key == ord('['):
                self.fill_tolerance = max(
                    self.fill_tolerance - 4, self.cfg["fill_tolerance_min"])
                self._notify(f"Tolerancia:{self.fill_tolerance}", UI["vivo_naranja"])

        cap.release()
        self.hands.close()
        cv2.destroyAllWindows()
        print(f"\n[OK] Obras guardadas en ./{self.cfg['save_dir']}/")