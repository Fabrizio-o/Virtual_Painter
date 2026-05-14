"""
mouse_controller.py - Control del ratón mediante gestos en Modo Libre
"""
import time
import numpy as np
from collections import deque

try:
    import pyautogui
    pyautogui.FAILSAFE = False
    pyautogui.PAUSE    = 0.0
    PYAUTOGUI_OK = True
except ImportError:
    PYAUTOGUI_OK = False


class MouseController:
    """Mueve y hace clic con el ratón a partir de la posición del dedo índice."""

    __slots__ = (
        'cfg', 'cam_w', 'cam_h', 'scr_w', 'scr_h',
        '_sx', '_sy', '_alpha',
        'is_dragging', 'mouse_down', '_was_pinching',
        'drag_start_pos', '_pinch_frames',
        '_click_cd', '_rclick_cd', '_dclick_cd',
        '_pos_history', '_last_pinch_t', '_dclick_window',
    )

    def __init__(self, cfg, cam_w, cam_h):
        self.cfg   = cfg
        self.cam_w = cam_w
        self.cam_h = cam_h
        self.scr_w, self.scr_h = (
            pyautogui.size() if PYAUTOGUI_OK else (1920, 1080)
        )
        self._sx = self._sy = None
        self._alpha = 1.0 / max(cfg["mouse_smoothing"], 1)

        self.is_dragging    = False
        self.mouse_down     = False
        self._was_pinching  = False
        self.drag_start_pos = None
        self._pinch_frames  = 0

        self._click_cd  = 0
        self._rclick_cd = 0
        self._dclick_cd = 0

        self._pos_history  = deque(maxlen=5)
        self._last_pinch_t = 0.0
        self._dclick_window = 0.4

    # ──────────────────────────────────────────
    def tick(self):
        """Decrementa cooldowns cada frame."""
        for attr in ('_click_cd', '_rclick_cd', '_dclick_cd'):
            v = getattr(self, attr)
            if v > 0:
                setattr(self, attr, v-1)

    # ──────────────────────────────────────────
    def cam_to_screen(self, cx, cy):
        mg = self.cfg["mouse_zone_margin"]
        nx = float(np.clip((cx/self.cam_w - mg) / (1 - 2*mg), 0, 1))
        ny = float(np.clip((cy/self.cam_h - mg) / (1 - 2*mg), 0, 1))
        return int(nx * self.scr_w), int(ny * self.scr_h)

    def smooth_move(self, cx, cy):
        if not PYAUTOGUI_OK:
            return
        sx, sy = self.cam_to_screen(cx, cy)
        if self._sx is None:
            self._sx, self._sy = float(sx), float(sy)
        else:
            a = self._alpha
            self._sx = a*sx + (1-a)*self._sx
            self._sy = a*sy + (1-a)*self._sy
        self._pos_history.append((int(self._sx), int(self._sy)))
        if self.is_dragging:
            pyautogui.dragTo(int(self._sx), int(self._sy),
                             button='left', _pause=False)
        else:
            pyautogui.moveTo(int(self._sx), int(self._sy), _pause=False)

    # ──────────────────────────────────────────
    def handle_pinch(self, is_pinching, cx, cy):
        if not PYAUTOGUI_OK:
            return ""
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
                    self.mouse_down     = True
                    self.drag_start_pos = (
                        int(self._sx or cx), int(self._sy or cy)
                    )
                    action = "CLIC IZQ"
                self._last_pinch_t = now
            else:
                if (self.mouse_down and not self.is_dragging and
                        self._pinch_frames >= 6 and self.drag_start_pos):
                    if self._sx and (
                        abs(self._sx - self.drag_start_pos[0]) +
                        abs(self._sy - self.drag_start_pos[1])
                    ) > self.cfg["drag_min_move"]:
                        self.is_dragging = True
                        action = "ARRASTRANDO"
                if self.is_dragging:
                    action = "ARRASTRANDO"
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

    # ──────────────────────────────────────────
    def right_click(self):
        if not PYAUTOGUI_OK or self._rclick_cd > 0:
            return ""
        if self.is_dragging or self.mouse_down:
            pyautogui.mouseUp(button='left', _pause=False)
            self.is_dragging = self.mouse_down = False
        pyautogui.click(button='right', _pause=False)
        self._rclick_cd = self.cfg["right_click_cooldown"]
        return "CLIC DER"

    # ──────────────────────────────────────────
    def release_all(self):
        if not PYAUTOGUI_OK:
            return
        if self.mouse_down or self.is_dragging:
            try:
                pyautogui.mouseUp(button='left', _pause=False)
            except Exception:
                pass
        self.is_dragging   = False
        self.mouse_down    = False
        self._was_pinching = False
        self._pinch_frames = 0
        self._sx = self._sy = None

    # ──────────────────────────────────────────
    @property
    def screen_pos(self):
        return (int(self._sx), int(self._sy)) if self._sx is not None else None
