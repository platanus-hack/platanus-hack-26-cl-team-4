"""Geometría de un parque solar desde una nube de puntos métrica. Solo numpy: se prueba sin GPU ni Isaac.

La usa sim/medir_entorno.py (agente Entorno, docs/agentes/mapeo-terreno.md). Entrada: puntos (N, 3) en metros, en
cualquier marco (MapAnything entrega el de la primera cámara, OpenCV), más la dirección "arriba" aproximada de la cámara.
Opcional: una etiqueta por punto (SAM 3) y los puntos de cada panel detectado.

Salida: un dict por campo de entorno.json con valor, error (±, en las unidades del campo), método y muestras.
Lo que no se puede medir no aparece: el agente lo estima y lo marca con confianza baja.

Pasos:
1. Suelo: RANSAC de un plano entre los puntos más bajos según "arriba". El marco nuevo tiene z = altura sobre el suelo.
2. Dirección de las filas: el ángulo que más concentra los puntos de estructura al proyectarlos sobre la normal.
3. Filas: picos del perfil transversal. Cantidad, separación (pitch) y largo visible.
4. Altura del tubo: superficie más alta cerca del eje de cada fila, menos el espesor del panel si la fila tiene paneles.
5. Panel: instancias de SAM 3 (cajas orientadas) o, sin SAM, el período de los paneles a lo largo de la fila.
6. Inclinación y tipo: plano de los paneles respecto del eje de la fila; postes en una línea = tracker.
7. Pendiente: ángulo entre el suelo y la vertical de la cámara. Es la medida menos precisa.
"""
from __future__ import annotations

import math

import numpy as np

# Etiquetas por punto (sim/medir_entorno.py las saca de SAM 3). 0: sin etiqueta.
SIN_ETIQUETA, PANEL, TUBO, POSTE, EXCLUIR = 0, 1, 2, 3, 4
# Geometría de generar_escena y plan: tubo de 10 cm, panel de 4 cm, 2 cm entre paneles.
TUBO_MEDIO_M = 0.05
PANEL_ESPESOR_M = 0.04
HOLGURA_PANEL_M = 0.02
# Error que se suma siempre: la escala de una reconstrucción sin referencias no es perfecta.
ERROR_ESCALA_REL = 0.02
# Error mínimo de las medidas del panel sin SAM 3 (banda y período): calibrado en la fase 0.
ERROR_PANEL_SIN_SAM_M = 0.2
# Tolerancia de cada campo: con este error la confianza baja a ~0,45 (confianza()).
TOLERANCIAS = {
    "filas.cantidad": 0.5,
    "filas.separacion_m": 0.3,
    "filas.largo_m": 3.0,
    "estructura.altura_m": 0.10,
    "estructura.inclinacion_grados": 3.0,
    "panel.largo_m": 0.08,
    "panel.ancho_m": 0.05,
    "terreno.pendiente_grados": 2.0,
}


class SinGeometria(RuntimeError):
    """La nube no alcanza para medir: pocos puntos, sin suelo o sin estructuras."""


def confianza(campo: str, error: float) -> float:
    """Confianza 0,1–0,95 a partir del error medido y la tolerancia del campo. Nunca 1."""
    tol = TOLERANCIAS.get(campo, 1.0)
    return round(float(np.clip(0.95 - 0.5 * error / tol, 0.1, 0.95)), 2)


def poner_confianza(campos: dict) -> None:
    for campo, v in campos.items():
        v["confianza"] = confianza(campo, v["error"])


def _campo(valor, error: float, metodo: str, muestras: int) -> dict:
    return {"valor": valor, "error": round(float(error), 3), "metodo": metodo, "muestras": int(muestras)}


# ---------- 1. suelo ----------

def plano_ransac(p: np.ndarray, umbral: float = 0.05, iteraciones: int = 300, semilla: int = 0) -> tuple[np.ndarray, float, np.ndarray]:
    """Plano n·x + d = 0 con más puntos a menos de `umbral`. Devuelve (n unitario, d, máscara de inliers)."""
    if len(p) < 3:
        raise SinGeometria("menos de 3 puntos para el plano")
    rng = np.random.default_rng(semilla)
    mejor, mejor_n, mejor_d = None, None, 0.0
    for _ in range(iteraciones):
        a, b, c = p[rng.choice(len(p), 3, replace=False)]
        n = np.cross(b - a, c - a)
        norma = np.linalg.norm(n)
        if norma < 1e-9:
            continue
        n = n / norma
        d = -float(n @ a)
        dentro = np.abs(p @ n + d) < umbral
        if mejor is None or dentro.sum() > mejor.sum():
            mejor, mejor_n, mejor_d = dentro, n, d
    if mejor is None:
        raise SinGeometria("puntos colineales: no hay plano")
    # Ajuste final por mínimos cuadrados sobre los inliers.
    q = p[mejor]
    centro = q.mean(axis=0)
    _, _, vt = np.linalg.svd(q - centro, full_matrices=False)
    n = vt[2]
    if n @ mejor_n < 0:
        n = -n
    return n, -float(n @ centro), np.abs(p @ n - n @ centro) < umbral


def a_marco_suelo(puntos: np.ndarray, arriba: np.ndarray, percentil_bajo: float = 35.0) -> tuple[np.ndarray, np.ndarray, dict]:
    """Lleva los puntos a un marco con el suelo en z = 0 y z hacia arriba.

    arriba: dirección vertical aproximada en el marco de entrada (la cámara sostenida derecha).
    Devuelve (puntos en el marco del suelo, normal del suelo en el marco de entrada, info).
    """
    arriba = np.asarray(arriba, float) / np.linalg.norm(arriba)
    h = puntos @ arriba
    bajos = puntos[h <= np.percentile(h, percentil_bajo)]
    if len(bajos) < 50:
        raise SinGeometria("muy pocos puntos bajos para encontrar el suelo")
    n, d, _ = plano_ransac(bajos)
    if n @ arriba < 0:
        n, d = -n, -d
    # Base ortonormal con z = n.
    x = np.cross([0.0, 1.0, 0.0], n) if abs(n[1]) < 0.9 else np.cross([1.0, 0.0, 0.0], n)
    x /= np.linalg.norm(x)
    y = np.cross(n, x)
    r = np.stack([x, y, n])            # filas: ejes del marco nuevo
    origen = -d * n                     # punto del plano más cercano al origen
    local = (puntos - origen) @ r.T
    inliers = np.abs(local[:, 2]) < 0.05
    return local, n, {"puntos_suelo": int(inliers.sum()), "fraccion_suelo": round(float(inliers.mean()), 3)}


# ---------- 2 y 3. dirección y filas ----------

def _concentracion(proy: np.ndarray, bin_m: float = 0.05) -> float:
    if len(proy) == 0:
        return 0.0
    h, _ = np.histogram(proy, bins=max(4, int(np.ptp(proy) / bin_m) + 1))
    s = h.sum()
    return float((h.astype(float) ** 2).sum() / (s * s)) if s else 0.0


def direccion_filas(xy: np.ndarray) -> float:
    """Ángulo (rad) del eje de las filas en el plano del suelo: el que más concentra el perfil transversal."""
    if len(xy) < 20:
        raise SinGeometria("muy pocos puntos de estructura para la dirección de las filas")
    muestra = xy if len(xy) <= 60000 else xy[np.random.default_rng(1).choice(len(xy), 60000, replace=False)]

    def puntaje(t: float) -> float:
        normal = np.array([-math.sin(t), math.cos(t)])
        return _concentracion(muestra @ normal)

    gruesos = np.radians(np.arange(0.0, 180.0, 1.0))
    t0 = max(gruesos, key=puntaje)
    finos = t0 + np.radians(np.arange(-1.0, 1.0001, 0.1))
    return float(max(finos, key=puntaje)) % math.pi


def _suavizar(h: np.ndarray, sigma_bins: float) -> np.ndarray:
    k = np.arange(-int(3 * sigma_bins), int(3 * sigma_bins) + 1)
    g = np.exp(-0.5 * (k / sigma_bins) ** 2)
    return np.convolve(h, g / g.sum(), mode="same")


# Dos filas no pueden estar más cerca que un panel más un pasillo angosto. Más cerca son los dos bordes de una fila
# con paneles vista en ángulo (cada borde se ve denso en la nube).
SEPARACION_MIN_FILAS_M = 2.6
# Altura típica de un celular en la mano de alguien que camina grabando.
ALTURA_CAMARA_MANO_M = 1.5
ERROR_ESCALA_CAMARA_REL = 0.08


def escala_por_camara(puntos: np.ndarray, arriba: np.ndarray, camaras: np.ndarray,
                      altura_real_m: float = ALTURA_CAMARA_MANO_M) -> tuple[float, float]:
    """Factor de escala para que las cámaras queden a `altura_real_m` sobre el suelo. Devuelve (factor, altura medida).

    Un video caminando con el celular siempre trae esta referencia: la reconstrucción sabe dónde estuvo la cámara
    respecto del suelo. Corrige el error de escala típico de una reconstrucción monocular (medido: ×0,64 en un video
    sintético de Isaac).
    """
    arriba = np.asarray(arriba, float) / np.linalg.norm(arriba)
    h = puntos @ arriba
    bajos = puntos[h <= np.percentile(h, 35)]
    n, d, _ = plano_ransac(bajos)
    if n @ arriba < 0:
        n, d = -n, -d
    alturas = np.asarray(camaras, float) @ n + d
    medida = float(np.median(alturas))
    if medida <= 0.05:
        raise SinGeometria(f"las cámaras quedan a {medida:.2f} m del suelo: no se puede escalar con su altura")
    return altura_real_m / medida, medida


def picos_filas(c: np.ndarray, separacion_min_m: float = SEPARACION_MIN_FILAS_M, bin_m: float = 0.05) -> list[float]:
    """Centros de las filas en la coordenada transversal c: picos del perfil, separados al menos separacion_min_m."""
    lo, hi = np.percentile(c, 0.5), np.percentile(c, 99.5)
    bordes = np.arange(lo - 1.0, hi + 1.0 + bin_m, bin_m)
    h, _ = np.histogram(c, bins=bordes)
    s = _suavizar(h.astype(float), 0.15 / bin_m)
    centros = (bordes[:-1] + bordes[1:]) / 2
    candidatos = [i for i in range(1, len(s) - 1) if s[i] >= s[i - 1] and s[i] >= s[i + 1] and s[i] >= 0.15 * s.max()]
    candidatos.sort(key=lambda i: -s[i])
    elegidos: list[float] = []
    for i in candidatos:
        if all(abs(centros[i] - e) >= separacion_min_m for e in elegidos):
            elegidos.append(float(centros[i]))
    # Centro de masa de los puntos cerca de cada pico: más fino que el bin.
    radio = separacion_min_m / 2
    finos = []
    for e in sorted(elegidos):
        cerca = c[np.abs(c - e) < radio]
        finos.append(float(np.median(cerca)) if len(cerca) else e)
    return finos


# ---------- medición completa ----------

def medir(puntos: np.ndarray, arriba: np.ndarray, etiquetas: np.ndarray | None = None,
          instancias_panel: list[np.ndarray] | None = None, error_escala_rel: float = ERROR_ESCALA_REL) -> dict:
    """Mide un parque solar. Devuelve {"campos": {campo: {...}}, "avisos": [...], "diagnostico": {...}}.

    puntos: (N, 3) metros. arriba: vertical aproximada en ese marco. etiquetas: (N,) con PANEL, TUBO, POSTE, EXCLUIR o 0.
    instancias_panel: puntos 3D de cada panel que SAM 3 separó (en el mismo marco que `puntos`).
    """
    puntos = np.asarray(puntos, float)
    if len(puntos) < 500:
        raise SinGeometria(f"la nube tiene {len(puntos)} puntos: se necesitan al menos 500")
    if etiquetas is not None:
        etiquetas = np.asarray(etiquetas)
        quedan = etiquetas != EXCLUIR
        puntos, etiquetas = puntos[quedan], etiquetas[quedan]
    local, normal, info = a_marco_suelo(puntos, arriba)
    avisos: list[str] = []
    campos: dict[str, dict] = {}
    z = local[:, 2]

    # Estructura: lo que está entre 25 cm y 4,5 m sobre el suelo. Con etiquetas, solo panel, tubo y poste.
    estructura = (z > 0.25) & (z < 4.5)
    if etiquetas is not None and np.isin(etiquetas, (PANEL, TUBO, POSTE)).sum() > 200:
        estructura &= np.isin(etiquetas, (PANEL, TUBO, POSTE))
        metodo_base = "nube_metrica+sam3"
    else:
        metodo_base = "nube_metrica"
    e = local[estructura]
    if len(e) < 200:
        raise SinGeometria("no encontré estructuras sobre el suelo (tubos, postes o paneles)")
    # Tubos y postes etiquetados marcan la dirección mejor que los paneles (que son anchos).
    finos = e
    if etiquetas is not None:
        lineales = local[estructura & np.isin(etiquetas, (TUBO, POSTE))]
        if len(lineales) > 300:
            finos = lineales
    t = direccion_filas(finos[:, :2])
    eje = np.array([math.cos(t), math.sin(t)])
    normal_xy = np.array([-math.sin(t), math.cos(t)])
    a = e[:, :2] @ eje            # a lo largo de la fila
    c = e[:, :2] @ normal_xy      # transversal

    centros = picos_filas(finos[:, :2] @ normal_xy)
    n = len(centros)
    campos["filas.cantidad"] = _campo(n, 0.0 if n >= 1 else 1.0, f"{metodo_base}: picos del perfil transversal", len(e))
    if n >= 2:
        difs = np.diff(centros)
        sep = float(np.median(difs))
        err = (float(np.std(difs)) / math.sqrt(len(difs)) if len(difs) > 1 else 0.05) + error_escala_rel * sep
        campos["filas.separacion_m"] = _campo(round(sep, 3), err, f"{metodo_base}: distancia entre picos", len(difs))
    else:
        avisos.append("una sola fila visible: la separación entre filas no se puede medir")
    medio = (min(np.diff(centros)) / 2 if n >= 2 else 1.6)

    largos, alturas, inclinaciones, anchos_periodo, largos_banda, con_paneles = [], [], [], [], [], 0
    for centro in centros:
        en_fila = np.abs(c - centro) < min(medio, 1.6)
        if en_fila.sum() < 50:
            continue
        af, cf, zf = a[en_fila], c[en_fila] - centro, e[en_fila, 2]
        largos.append(float(np.percentile(af, 99.5) - np.percentile(af, 0.5)))
        # ¿La fila tiene paneles? Puntos altos que se alejan del eje más que el tubo.
        altos = zf > np.percentile(zf, 60)
        ancho_alto = float(np.percentile(np.abs(cf[altos]), 90)) if altos.any() else 0.0
        hay_paneles = ancho_alto > 0.5
        cerca_eje = np.abs(cf) < 0.25
        if cerca_eje.sum() < 10:
            continue
        tope = float(np.percentile(zf[cerca_eje], 97))
        if hay_paneles:
            con_paneles += 1
            alturas.append(tope - TUBO_MEDIO_M - PANEL_ESPESOR_M)
            banda = zf > tope - 0.12           # superficie de los paneles
            # Inclinación: pendiente de z contra la coordenada transversal, en la banda de paneles.
            cb, zb = cf[banda], zf[banda]
            if len(cb) > 30 and np.ptp(cb) > 0.5:
                inclinaciones.append(math.degrees(math.atan(np.polyfit(cb, zb, 1)[0])))
            # Largo del panel: ancho de la banda transversal. Ancho del panel: período a lo largo de la fila.
            largos_banda.append(float(np.percentile(cb, 99) - np.percentile(cb, 1)) / 0.98)
            periodo = _periodo(af[banda])
            if periodo is not None:
                anchos_periodo.append(periodo - HOLGURA_PANEL_M)
        else:
            alturas.append(tope - TUBO_MEDIO_M)

    if largos:
        largo = float(np.median(largos))
        campos["filas.largo_m"] = _campo(round(largo, 2), max(1.0, (0.1 + error_escala_rel) * largo),
                                         "largo visible de cada fila (cota inferior: el video puede no mostrarla entera)",
                                         len(largos))
    if alturas:
        alt = float(np.median(alturas))
        err = (float(np.std(alturas)) / math.sqrt(len(alturas)) if len(alturas) > 1 else 0.05) + error_escala_rel * alt + 0.02
        campos["estructura.altura_m"] = _campo(round(alt, 3), err, "superficie más alta sobre el eje de cada fila", len(alturas))
    if inclinaciones:
        inc = float(np.median(inclinaciones))
        err = (float(np.std(inclinaciones)) if len(inclinaciones) > 1 else 1.5) + 0.5
        campos["estructura.inclinacion_grados"] = _campo(round(inc, 1), err, "plano de los paneles contra el eje de la fila",
                                                         len(inclinaciones))
    elif con_paneles == 0:
        avisos.append("ninguna fila visible tiene paneles: inclinación y medidas del panel sin medir")

    # Tipo: en un tracker de un eje los postes van en una sola línea, bajo el tubo. Solo con SAM 3: en una nube sin
    # etiquetas los postes no se distinguen del ruido (medido en la fase 0: daba "fijo" en un tracker).
    bajos = (e[:, 2] > 0.3) & (e[:, 2] < 0.9)
    if not metodo_base.endswith("sam3"):
        avisos.append("estructura.tipo sin medir: sin SAM 3 los postes no se distinguen del ruido de la reconstrucción")
    elif bajos.sum() > 50 and n >= 1:
        dist = np.min(np.abs(c[bajos][:, None] - np.array(centros)[None, :]), axis=1)
        una_linea = float(np.mean(dist < 0.3))
        tipo = "tracker_1_eje" if una_linea > 0.6 and abs(campos.get("estructura.inclinacion_grados", {}).get("valor", 0)) < 20 else "fijo"
        campos["estructura.tipo"] = _campo(tipo, round(1 - una_linea, 2) if tipo == "tracker_1_eje" else round(una_linea, 2),
                                           f"postes en una línea bajo el eje: {una_linea:.0%} de los puntos bajos", int(bajos.sum()))

    _medir_panel(campos, avisos, instancias_panel, largos_banda, anchos_periodo, error_escala_rel)

    # Pendiente: ángulo entre la normal del suelo y la vertical de la cámara.
    arriba_u = np.asarray(arriba, float) / np.linalg.norm(arriba)
    pend = math.degrees(math.acos(float(np.clip(normal @ arriba_u, -1, 1))))
    campos["terreno.pendiente_grados"] = _campo(round(pend, 1), 4.0, "normal del suelo contra la vertical de la cámara (aprox.)", 1)
    if pend > 10:
        avisos.append(f"pendiente medida de {pend:.0f}°: puede ser la cámara inclinada, no el terreno")
    poner_confianza(campos)

    return {"campos": campos, "avisos": avisos,
            "diagnostico": {**info, "puntos": int(len(puntos)), "puntos_estructura": int(len(e)),
                            "direccion_filas_grados": round(math.degrees(t), 2),
                            "centros_filas_m": [round(x, 3) for x in centros], "filas_con_paneles": con_paneles}}


def _periodo(a: np.ndarray, bin_m: float = 0.02, rango=(0.8, 1.7)) -> float | None:
    """Período de los paneles a lo largo de la fila: primer pico de la autocorrelación de la densidad de puntos."""
    if len(a) < 100 or np.ptp(a) < 3 * rango[1]:
        return None
    h, _ = np.histogram(a, bins=int(np.ptp(a) / bin_m) + 1)
    h = h.astype(float)
    # Pasa-altos: quita la variación lenta de densidad (cámara más cerca o más lejos) y deja los bordes de los paneles.
    h = h - _suavizar(h, 0.25 / bin_m)
    ac = np.correlate(h, h, mode="full")[len(h) - 1:]
    if ac[0] <= 0:
        return None
    ac = ac / ac[0]
    lo, hi = int(rango[0] / bin_m), min(int(rango[1] / bin_m), len(ac) - 2)
    if hi <= lo:
        return None
    picos = [i for i in range(max(lo, 1), hi) if ac[i] >= ac[i - 1] and ac[i] >= ac[i + 1]]
    if not picos:
        return None
    i = max(picos, key=lambda k: ac[k])
    # El pico tiene que destacar del resto del rango: si no, los huecos entre paneles no se ven y no hay período.
    zona = ac[lo:hi]
    if ac[i] <= 0 or (ac[i] - np.median(zona)) < 3.0 * np.std(zona):
        return None
    # Interpolación parabólica del pico.
    y0, y1, y2 = ac[i - 1], ac[i], ac[i + 1]
    den = y0 - 2 * y1 + y2
    desfase = 0.5 * (y0 - y2) / den if den else 0.0
    return float((i + desfase) * bin_m)


def _medir_panel(campos: dict, avisos: list, instancias: list[np.ndarray] | None, largos_banda: list, anchos_periodo: list,
                 error_escala_rel: float = ERROR_ESCALA_REL) -> None:
    largos, anchos, metodo = [], [], ""
    if instancias:
        for q in instancias:
            if len(q) < 30:
                continue
            q = q - q.mean(axis=0)
            _, _, vt = np.linalg.svd(q, full_matrices=False)
            # Percentiles 2–98 para ignorar puntos sueltos. Sobre una cara muestreada pareja cubren el 96 % del lado.
            ext = [float(np.percentile(q @ v, 98) - np.percentile(q @ v, 2)) / 0.96 for v in vt[:2]]
            l, w = max(ext), min(ext)
            if 0.6 <= l <= 3.0 and 0.4 <= w <= 2.0:
                largos.append(l)
                anchos.append(w)
        metodo = "cajas orientadas de los paneles de SAM 3"
    # Sin cajas de SAM 3, el largo sale del ancho de la banda de paneles. En una nube real la banda se ensancha
    # (ruido y vista oblicua): en la fase 0 dio +33 %. Ese error mínimo deja la confianza baja y el agente decide.
    error_minimo = 0.0
    if len(anchos) < 3:
        largos, anchos = largos_banda, anchos_periodo
        metodo = "ancho de la banda de paneles y período a lo largo de la fila"
        error_minimo = ERROR_PANEL_SIN_SAM_M
    for campo, vals in (("panel.largo_m", largos), ("panel.ancho_m", anchos)):
        if not vals:
            avisos.append(f"{campo} sin medir")
            continue
        v = float(np.median(vals))
        mad = float(np.median(np.abs(np.array(vals) - v))) * 1.4826
        err = max(error_minimo, (mad / math.sqrt(len(vals)) if len(vals) > 1 else 0.04) + error_escala_rel * v)
        campos[campo] = _campo(round(v, 3), err, metodo, len(vals))
    ancho = campos.get("panel.ancho_m", {}).get("valor")
    if ancho is not None and not 0.9 <= ancho <= 1.4:
        avisos.append(f"el panel mide {ancho:.2f} m de ancho: la escala de la reconstrucción puede estar mal "
                      "(un panel estándar mide 1,0 a 1,3 m)")
