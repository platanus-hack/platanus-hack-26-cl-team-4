"""Fase 1 del embudo de factibilidad: geometría de la tarea contra las cajas de entorno.json (viaz/geometria.py)."""
from __future__ import annotations

import copy
import json

import pytest

from viaz import agentes, geometria

PROYECTO = {"nombre": "Sala de prueba", "descripcion": "", "videos": []}


def _f(nombre):
    return json.loads((agentes.FIXTURES / f"{nombre}.json").read_text(encoding="utf-8"))


def _el(entorno, nombre):
    return next(e for e in entorno["elementos"] if e["nombre"] == nombre)


def test_la_sala_pasa_y_calcula_las_poses_meta():
    t = agentes.validar_tarea(_f("tarea_sala"), _f("entorno_sala"))
    g = t["geometria"]
    assert g["origen_pose"] == {"x_m": 2.2, "y_m": 2.0, "z_m": 0.75, "giro_grados": 15}
    assert g["destino_pose"] == {"x_m": 4.3, "y_m": 3.8, "z_m": 0.9, "giro_grados": 0}
    assert g["distancia_m"] == pytest.approx(2.766, abs=1e-3)   # hypot(2,1; 1,8)
    assert g["altura_max_m"] == pytest.approx(1.15)
    # La repisa a 0,9 m está dentro de un bloque sólido: se avisa, no se rechaza.
    assert any("bloque sólido" in a for a in t["advertencias"])
    assert any("inferida" in a for a in t["advertencias"])


def test_instalar_panel_no_tiene_geometria_generica():
    t = agentes.validar_tarea(_f("tarea"), _f("entorno"))
    assert t["geometria"]["destino_pose"] is None and t["advertencias"] == []


def test_huella_de_una_caja_girada():
    caja = {"forma": "caja", "rotacion_grados": 90, "dimensiones_m": {"largo_m": 2, "ancho_m": 1, "alto_m": 1},
            "posicion_m": {"x_m": 0, "y_m": 0, "z_m": 0}}
    assert geometria.huella(caja) == pytest.approx((-0.5, 0.5, -1, 1))


def _revisar(cambiar_entorno=None, cambiar_tarea=None):
    e, t = _f("entorno_sala"), _f("tarea_sala")
    if cambiar_entorno:
        cambiar_entorno(e)
    if cambiar_tarea:
        cambiar_tarea(t)
    return geometria.revisar(t, e)


def test_soporte_el_objeto_flota_sobre_el_origen():
    p, _, _ = _revisar(lambda e: _el(e, "caja_carton_1")["posicion_m"].update(z_m=1.2))
    assert any("no está sobre mesa_central" in x for x in p)


def test_encaje_el_objeto_no_cabe_en_el_destino():
    p, _, _ = _revisar(lambda e: _el(e, "caja_carton_1")["dimensiones_m"].update(largo_m=0.5, ancho_m=0.5))
    assert any("no cabe en estante" in x for x in p)


def test_encaje_admite_girar_el_objeto():
    # 0,3 × 0,4 en un destino de 1,2 × 0,4: cabe girándolo.
    p, _, _ = _revisar(lambda e: _el(e, "caja_carton_1")["dimensiones_m"].update(largo_m=0.3, ancho_m=0.4))
    assert not p


def test_despeje_otro_elemento_ocupa_el_destino():
    def poner_caja_encima(e):
        e["elementos"].append({"nombre": "florero", "categoria": "objeto_manipulable", "forma": "cilindro",
                               "dimensiones_m": {"largo_m": 0.2, "ancho_m": 0.2, "alto_m": 0.3},
                               "posicion_m": {"x_m": 4.3, "y_m": 3.8, "z_m": 1.8}, "rotacion_grados": 0,
                               "masa_kg": 1, "fijo": False})
    p, _, _ = _revisar(poner_caja_encima, lambda t: t["destino"].update(altura_m=None))
    assert any("florero ocupa el espacio sobre estante" in x for x in p)


def test_techo_el_objeto_no_cabe_bajo_el_techo():
    p, _, _ = _revisar(lambda e: e["espacio"].update(alto_m=1.0))
    assert any("sobre el techo" in x for x in p)


def test_altura_fuera_del_elemento():
    p, _, _ = _revisar(cambiar_tarea=lambda t: t["destino"].update(altura_m=2.5))
    assert any("fuera del elemento" in x for x in p)


def test_con_baja_confianza_el_problema_pasa_a_advertencia():
    def mal_medida(e):
        _el(e, "caja_carton_1")["posicion_m"].update(z_m=1.2)
        e["confianza"]["elementos.caja_carton_1"] = 0.3
    p, a, _ = _revisar(mal_medida)
    assert not p and any("no se rechaza" in x for x in a)


# ---------- Para qué es la tarea: pedido y preguntas al cliente ----------

def test_inferida_sin_preguntas_se_rechaza():
    t = _f("tarea_sala")
    t["pedido"]["preguntas"] = []
    _, problemas = agentes.completar_tarea(t, _f("entorno_sala"))
    assert any("preguntas está vacío" in p for p in problemas)


def test_sin_descripcion_del_cliente_la_tarea_no_puede_ser_del_cliente():
    t = _f("tarea_sala")
    t["pedido"] = {"origen": "cliente", "preguntas": []}
    _, problemas = agentes.completar_tarea(t, _f("entorno_sala"), descripcion_cliente="")
    assert any("la tarea es inferida" in p for p in problemas)
    _, problemas = agentes.completar_tarea(t, _f("entorno_sala"), descripcion_cliente="Ordenar las cajas en el estante")
    assert not problemas


def test_el_agente_ve_medidas_y_corrige_un_problema_geometrico(monkeypatch):
    sala = _f("tarea_sala")
    mala = copy.deepcopy(sala)
    mala["destino"]["altura_m"] = 2.5
    respuestas = [{**mala, "pila_paneles": None}, {**sala, "pila_paneles": None}]
    vistos = []

    def falso(**kw):
        vistos.append(kw["contenido"][-1]["text"])
        r = respuestas.pop(0)
        return {k: v for k, v in r.items() if k != "version"}

    monkeypatch.setattr(agentes, "pedir_json", falso)
    t = agentes.tarea("claude", "x", PROYECTO, _f("entorno_sala"), None)
    assert "tope a 1.8 m" in vistos[0]                   # la lista de elementos trae medidas
    assert "fuera del elemento" in vistos[1]             # el reintento trae el problema geométrico
    assert t["geometria"]["destino_pose"]["z_m"] == 0.9


def test_el_esquema_del_agente_no_pide_campos_del_codigo():
    esq = agentes.esquema_agente_tarea()
    assert not {"geometria", "advertencias"} & set(esq["properties"]) and "$defs" not in esq
    assert {"proposito", "pedido"} <= set(esq["required"])
