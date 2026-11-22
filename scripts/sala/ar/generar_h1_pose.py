"""Malla del Unitree H1 de pie (cuadro 0 de baile.npz) → h1_pose.npz, el humanoide de la fila de escena.py.

    python generar_h1_pose.py <ruta>/baile.npz [--triangulos 14000]

Las mallas son las del modelo publicado del H1, simplificadas y unidas en una sola pieza. Y arriba, pies en y = 0,
centrado en x y z, mirando hacia +z. Necesita: numpy y fast-simplification.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np

TRIANGULOS = 14_000
SALIDA = Path(__file__).with_name("h1_pose.npz")


def _q_mul(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Producto de cuaterniones (w, x, y, z), con difusión sobre la primera dimensión."""
    aw, ax, ay, az = np.moveaxis(a, -1, 0)
    bw, bx, by, bz = np.moveaxis(b, -1, 0)
    return np.stack([aw * bw - ax * bx - ay * by - az * bz, aw * bx + ax * bw + ay * bz - az * by,
                     aw * by - ax * bz + ay * bw + az * bx, aw * bz + ax * by - ay * bx + az * bw], -1)


def _q_eje(eje, grados: float) -> np.ndarray:
    eje = np.asarray(eje, float) / np.linalg.norm(eje)
    m = np.radians(grados) / 2
    return np.array([np.cos(m), *(np.sin(m) * eje)])


def _rotar(q: np.ndarray, v: np.ndarray) -> np.ndarray:
    """Rota v (N, 3) por el cuaternión q (w, x, y, z)."""
    w, u = q[0], q[1:]
    return v + 2 * np.cross(u, np.cross(u, v) + w * v)


# Z arriba → Y arriba (−90° en X) y después el frente del robot (+X) hacia quien mira (+Z): −90° en Y.
GIRO = _q_mul(_q_eje((0, 1, 0), -90), _q_eje((1, 0, 0), -90))


def soldar(puntos: np.ndarray, caras: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Une los vértices repetidos (a 0,1 mm). Sin esto el simplificador no colapsa aristas y deja hoyos."""
    unicos, inverso = np.unique(np.round(puntos, 4), axis=0, return_inverse=True)
    caras = inverso.reshape(-1)[caras]
    buenas = (caras[:, 0] != caras[:, 1]) & (caras[:, 1] != caras[:, 2]) & (caras[:, 0] != caras[:, 2])
    return unicos.astype(np.float32), caras[buenas]


def mallas_en_pose(ruta: Path, objetivo: int) -> tuple[np.ndarray, np.ndarray]:
    """Suelda, simplifica y pone cada malla en la pose de su cuerpo en el cuadro 0. Devuelve (puntos, caras)."""
    import fast_simplification

    d = np.load(ruta)
    ids, vistas = [], set()
    for k in sorted(d.files):
        if k.startswith("malla_") and k.endswith("_puntos"):
            i = int(k.split("_")[1])
            clave = (int(d[f"malla_{i}_cuerpo"]), d[k].tobytes())
            if clave not in vistas:   # baile.npz trae cada malla dos veces, idénticas
                vistas.add(clave)
                ids.append(i)
    total = sum(len(d[f"malla_{i}_caras"]) for i in ids)
    razon = min(1.0, objetivo / max(total, 1))
    puntos, caras, base = [], [], 0
    for i in sorted(ids):
        p, c = soldar(d[f"malla_{i}_puntos"], d[f"malla_{i}_caras"])
        if razon < 0.98 and len(c) > 200:
            p, c = fast_simplification.simplify(p, c.astype(np.int32), target_reduction=1 - razon)
        cuerpo = int(d[f"malla_{i}_cuerpo"])
        q, t = d["quat"][0, cuerpo].astype(np.float64), d["pos"][0, cuerpo].astype(np.float64)
        puntos.append(_rotar(q, np.asarray(p, np.float64)) + t)
        caras.append(np.asarray(c, np.int64) + base)
        base += len(p)
    return np.concatenate(puntos), np.concatenate(caras)


def normales(p: np.ndarray, c: np.ndarray) -> np.ndarray:
    n = np.zeros_like(p)
    cara_n = np.cross(p[c[:, 1]] - p[c[:, 0]], p[c[:, 2]] - p[c[:, 0]])
    for k in range(3):
        np.add.at(n, c[:, k], cara_n)
    n = np.round(n / np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-12), 3)   # redondear comprime mejor
    largo = np.linalg.norm(n, axis=1)
    n[largo < 0.5] = (0, 1, 0)   # vértices que solo tocan triángulos degenerados
    return n / np.linalg.norm(n, axis=1, keepdims=True)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("baile", type=Path)
    ap.add_argument("--triangulos", type=int, default=TRIANGULOS)
    a = ap.parse_args()
    p, c = mallas_en_pose(a.baile, a.triangulos)
    p = _rotar(GIRO, p)
    minimo, maximo = p.min(0), p.max(0)
    p -= [(minimo[0] + maximo[0]) / 2, minimo[1], (minimo[2] + maximo[2]) / 2]
    np.savez_compressed(SALIDA, pos=np.round(p, 4).astype(np.float32), nor=normales(p, c).astype(np.float32),
                        idx=c.reshape(-1).astype(np.uint32))
    print(f"{len(c)} triángulos, {len(p)} vértices, alto {p[:, 1].max():.3f} m · "
          f"{SALIDA.name} {SALIDA.stat().st_size / 1e3:.0f} KB")


if __name__ == "__main__":
    main()
