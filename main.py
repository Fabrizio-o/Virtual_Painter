"""
main.py - Punto de entrada de Magic Paint
Contiene: _print_banner, create_sample_images, main()
"""
import cv2
import numpy as np
import math
import os
import sys
import glob

from config import CONFIG


def _print_banner():
    print("=" * 68)
    print("   M A G I C   P A I N T  v5.2")
    print("   Universidad Politecnica del Carchi - Carrera de Computacion")
    print("=" * 68)
    print("  Modos:   [1] Pintura libre   [2] Colorear")
    print("  Herram:  [B] Pincel  [K] Fill  [E] Borrador")
    print("  Imagen:  [O] Abrir  [R] Restaurar  [S] Guardar  [P] Imprimir")
    print("  Colores: [C] Selector de colores (48 colores)")
    print("  Ctrl+Z Undo  |  Ctrl+Y Redo  |  H HUD  |  F Full  |  Q Salir")
    print("=" * 68)
    print("  OPTIMIZACIONES: 0 frame.copy() en UI, sidebar cacheada,")
    print("  nubes cada 4 frames, blobs cacheados, particulas reducidas")
    print("=" * 68)


def create_sample_images(out_dir):
    """Genera tres imágenes de ejemplo para colorear."""
    os.makedirs(out_dir, exist_ok=True)
    W, H = 800, 600

    # ── Mandala ──────────────────────────────
    img = np.full((H, W, 3), 255, dtype=np.uint8)
    cx, cy = W // 2, H // 2
    for r in range(40, 260, 42):
        cv2.circle(img, (cx, cy), r, (0, 0, 0), 2)
    for a in range(0, 360, 30):
        rd = math.radians(a)
        cv2.line(
            img,
            (int(cx + 42*math.cos(rd)), int(cy + 42*math.sin(rd))),
            (int(cx + 250*math.cos(rd)), int(cy + 250*math.sin(rd))),
            (0, 0, 0), 2,
        )
    for a in range(0, 360, 45):
        rd = math.radians(a)
        px, py = int(cx + 145*math.cos(rd)), int(cy + 145*math.sin(rd))
        cv2.ellipse(img, (px, py), (36, 20), a, 0, 360, (0, 0, 0), 2)
    cv2.imwrite(os.path.join(out_dir, "mandala.png"), img)

    # ── Paisaje ──────────────────────────────
    img = np.full((H, W, 3), 255, dtype=np.uint8)
    cv2.line(img, (0, H//2), (W, H//2), (0, 0, 0), 2)
    cv2.circle(img, (130, 110), 72, (0, 0, 0), 2)
    mts = np.array([
        [0, H//2], [160, 185], [320, H//2],
        [510, 170], [720, H//2], [W, H//2],
    ])
    cv2.polylines(img, [mts], False, (0, 0, 0), 3)
    cv2.imwrite(os.path.join(out_dir, "paisaje.png"), img)

    # ── Gato ─────────────────────────────────
    img = np.full((H, W, 3), 255, dtype=np.uint8)
    cv2.circle(img, (400, 300), 185, (0, 0, 0), 3)
    for ex in [340, 460]:
        cv2.circle(img, (ex, 268), 38, (0, 0, 0), 3)
        cv2.circle(img, (ex, 268), 14, (0, 0, 0), -1)
    cv2.imwrite(os.path.join(out_dir, "gato.png"), img)

    print(f"[OK] Imágenes de ejemplo en '{out_dir}/'")


def main():
    # Índice de cámara opcional por argumento
    if len(sys.argv) > 1 and sys.argv[1].lstrip('-').isdigit():
        CONFIG["camera_index"] = int(sys.argv[1])

    # Generar sólo las imágenes de muestra
    if "--gen-samples" in sys.argv:
        create_sample_images(CONFIG["images_dir"])
        return

    # Auto-generar imágenes si no existe ninguna
    total = sum(
        len(glob.glob(os.path.join(CONFIG["images_dir"], ext)))
        for ext in CONFIG["image_extensions"]
    )
    if total == 0:
        print("[INFO] Generando imágenes de ejemplo...")
        create_sample_images(CONFIG["images_dir"])

    # Importación diferida para evitar ciclos
    from painter import VirtualPainter
    VirtualPainter().run()


if __name__ == "__main__":
    main()