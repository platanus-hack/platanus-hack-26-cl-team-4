"""Piezas visuales con detalle para elementos de entorno.json que traen `detalle` (sillas, tarima, pantalla...).

Solo apariencia. La colisión de cada elemento sigue siendo su caja de entorno.json (generar_escena._elemento), que
queda invisible cuando hay detalle: mallas visuales detalladas y colisión simple, por separado (sim/CLAUDE.md).
Todas las medidas salen de dimensiones_m del elemento; las proporciones internas (asiento, respaldo, patas) son
supuestos de diseño anotados en DIMENSIONES.

Marco local de cada elemento: centro de la planta en (0, 0), suelo del elemento en z = 0, X a lo largo, Y a lo ancho.
El elemento se gira y traslada entero (xformOp del Xform padre).
"""
from __future__ import annotations

# Supuestos de diseño de las piezas (no salen de los archivos de entrada; se registran aquí).
DIMENSIONES = {
    "silla": {"paso_x_m": 0.55, "paso_y_m": 0.52, "asiento_m": 0.44, "alto_asiento_m": 0.46, "espesor_m": 0.03,
              "respaldo_alto_m": 0.40, "pata_m": 0.025},
    "tarima": {"canto_m": 0.04},
    "pantalla": {"marco_m": 0.05},
    "mesa_alta": {"cubierta_m": 0.03, "pie_radio_m": 0.035, "base_radio_m": 0.25},
    "graderia": {"escalones": 2},
    "letras": {"espesor_m": 0.12},
}
DETALLES = ("sillas", "tarima", "pantalla", "mesa_alta", "graderia", "parlante", "letras")
# Aspectos visuales que usan las piezas: (color, rugosidad, metal). Se suman a generar_escena.ASPECTOS.
ASPECTOS = {
    "plastico_negro": ((0.05, 0.05, 0.055), 0.55, 0.0),
    "metal_negro": ((0.08, 0.08, 0.09), 0.35, 0.8),
    "pantalla_led": ((0.02, 0.03, 0.06), 0.15, 0.0),
    "blanco_mate": ((0.88, 0.87, 0.84), 0.7, 0.0),
    "tela_parlante": ((0.10, 0.10, 0.11), 0.9, 0.0),
}


def _v(t) -> str:
    return ", ".join(f"{x:.4f}" for x in t)


def _caja(nombre: str, centro, tam, aspecto: str) -> str:
    return f'''
        def Cube "{nombre}" (prepend apiSchemas = ["MaterialBindingAPI"])
        {{
            double size = 1
            double3 xformOp:translate = ({_v(centro)})
            float3 xformOp:scale = ({_v(tam)})
            uniform token[] xformOpOrder = ["xformOp:translate", "xformOp:scale"]
            rel material:binding = </World/Materiales/Vis{aspecto.capitalize()}>
        }}'''


def _cilindro(nombre: str, centro, radio: float, alto: float, aspecto: str) -> str:
    return f'''
        def Cylinder "{nombre}" (prepend apiSchemas = ["MaterialBindingAPI"])
        {{
            double radius = {radio:.4f}
            double height = {alto:.4f}
            uniform token axis = "Z"
            double3 xformOp:translate = ({_v(centro)})
            uniform token[] xformOpOrder = ["xformOp:translate"]
            rel material:binding = </World/Materiales/Vis{aspecto.capitalize()}>
        }}'''


def _silla(k: str, x: float, y: float) -> str:
    """Silla de plástico negro con patas de metal. Mira a -X (hacia la tarima del ejemplo, en x menor)."""
    s = DIMENSIONES["silla"]
    a, h, e, p = s["asiento_m"], s["alto_asiento_m"], s["espesor_m"], s["pata_m"]
    partes = [_caja(f"S{k}_asiento", (x, y, h), (a, a, e), "plastico_negro"),
              _caja(f"S{k}_respaldo", (x + a / 2 - e / 2, y, h + s["respaldo_alto_m"] / 2), (e, a, s["respaldo_alto_m"]),
                    "plastico_negro")]
    for i, (dx, dy) in enumerate(((1, 1), (1, -1), (-1, 1), (-1, -1))):
        partes.append(_cilindro(f"S{k}_pata{i}", (x + dx * (a / 2 - p), y + dy * (a / 2 - p), h / 2), p / 2, h,
                                "metal_negro"))
    return "".join(partes)


def sillas(largo: float, ancho: float, alto: float) -> str:
    s = DIMENSIONES["silla"]
    filas = max(1, int(largo // s["paso_x_m"]))
    columnas = max(1, int(ancho // s["paso_y_m"]))
    x0 = -(filas - 1) * s["paso_x_m"] / 2
    y0 = -(columnas - 1) * s["paso_y_m"] / 2
    return "".join(_silla(f"{i:02d}_{j:02d}", x0 + i * s["paso_x_m"], y0 + j * s["paso_y_m"])
                   for i in range(filas) for j in range(columnas))


def tarima(largo: float, ancho: float, alto: float) -> str:
    c = DIMENSIONES["tarima"]["canto_m"]
    return (_caja("Cuerpo", (0, 0, (alto - c) / 2), (largo, ancho, alto - c), "madera")
            + _caja("Cubierta", (0, 0, alto - c / 2), (largo + 0.02, ancho + 0.02, c), "madera"))


def pantalla(largo: float, ancho: float, alto: float) -> str:
    m = DIMENSIONES["pantalla"]["marco_m"]
    # La cara emisora mira a +X (hacia el público del ejemplo). El marco envuelve la cara.
    return (_caja("Marco", (0, 0, alto / 2), (largo, ancho, alto), "metal_negro")
            + _caja("Cara", (largo / 2 + 0.002, 0, alto / 2), (0.004, ancho - 2 * m, alto - 2 * m), "pantalla_led"))


def mesa_alta(largo: float, ancho: float, alto: float) -> str:
    d = DIMENSIONES["mesa_alta"]
    r = max(largo, ancho) / 2
    return (_cilindro("Cubierta", (0, 0, alto - d["cubierta_m"] / 2), r, d["cubierta_m"], "madera")
            + _cilindro("Pie", (0, 0, alto / 2), d["pie_radio_m"], alto, "metal_negro")
            + _cilindro("Base", (0, 0, 0.01), d["base_radio_m"], 0.02, "metal_negro"))


def graderia(largo: float, ancho: float, alto: float) -> str:
    n = DIMENSIONES["graderia"]["escalones"]
    partes = []
    for k in range(n):   # escalones que suben hacia +Y (contra la pared del ejemplo)
        prof = ancho * (n - k) / n
        h = alto * (k + 1) / n
        partes.append(_caja(f"Escalon{k}", (0, ancho / 2 - prof / 2, h / 2), (largo, prof, h), "madera"))
    return "".join(partes)


def parlante(largo: float, ancho: float, alto: float) -> str:
    return (_caja("Gabinete", (0, 0, alto / 2), (largo, ancho, alto), "metal_negro")
            + _caja("Rejilla", (-largo / 2 - 0.002, 0, alto / 2), (0.004, ancho * 0.85, alto * 0.9), "tela_parlante"))


def letras(largo: float, ancho: float, alto: float) -> str:
    """Letras corpóreas genéricas: bloques blancos separados, sin copiar una marca."""
    e = DIMENSIONES["letras"]["espesor_m"]
    n = 3
    ancho_letra = ancho / (n + (n - 1) * 0.25)
    return "".join(_caja(f"Letra{k}", (0, -ancho / 2 + ancho_letra / 2 + k * ancho_letra * 1.25, alto / 2),
                         (e, ancho_letra, alto * (0.8 if k % 2 else 1.0)), "blanco_mate") for k in range(n))


GENERADORES = {"sillas": sillas, "tarima": tarima, "pantalla": pantalla, "mesa_alta": mesa_alta,
               "graderia": graderia, "parlante": parlante, "letras": letras}


def visual(el: dict) -> str:
    """Las piezas del elemento, en su marco local. Vacío si no trae `detalle` conocido."""
    d = el["dimensiones_m"]
    gen = GENERADORES.get(el.get("detalle") or "")
    return gen(d["largo_m"], d["ancho_m"], d["alto_m"]) if gen else ""
