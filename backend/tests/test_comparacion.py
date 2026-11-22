"""Paso 7 de la selección v3: el código ordena a los finalistas y escribe comparacion.json; el LLM solo explica."""
from __future__ import annotations

import pytest

from viaz import comparacion
from viaz.agentes import ErrorAgente
from viaz.esquemas import validar

CONDICIONES = {"escena": "escena.usd", "horas_entrenamiento": 2, "semillas": None,
               "tolerancia_pos_m": 0.05, "tolerancia_ang_grados": 5}


def _hija(robot_id: str, tasa: float | None, ciclo: float = 40.0, fisica: bool = True,
          fidelidad: str | None = None, error: str | None = None) -> comparacion.Hija:
    robot = {"id": robot_id, "nombre": robot_id.upper(), **({"fisica": {"largo_m": 3}} if fisica else {})}
    if error is not None:
        return comparacion.Hija(robot=robot, corrida_id=f"hija-{robot_id}", resultado=None, clon=None, error=error)
    resultado = {"fuente": "isaac", "metricas": {"tasa_exito": tasa, "ciclo_promedio_s": ciclo}}
    clon = {"robot_id": robot_id, **({"fidelidad": fidelidad} if fidelidad else {})}
    return comparacion.Hija(robot=robot, corrida_id=f"hija-{robot_id}", resultado=resultado, clon=clon, error=None)


def _ids(comp: dict) -> list[str]:
    return [f["id"] for f in comp["ranking"]]


def test_ordena_por_exito_y_luego_por_ciclo():
    comp = comparacion.comparar([_hija("b", 0.8, 30), _hija("a", 0.9, 60), _hija("c", 0.9, 50)], CONDICIONES)
    assert _ids(comp) == ["c", "a", "b"]
    assert [f["puesto"] for f in comp["ranking"]] == [1, 2, 3]
    assert comp["ganador"] == "c"
    validar("comparacion", comp)


def test_cada_fila_trae_el_nombre_del_robot():
    comp = comparacion.comparar([_hija("b", 0.8), _hija("a", 0.9)], CONDICIONES)
    assert [f["nombre"] for f in comp["ranking"]] == ["A", "B"]
    assert comp["explicacion"].startswith("A queda en el puesto 1")


def test_sin_nombre_la_fila_no_lo_trae():
    hija = _hija("a", 0.9)
    sin_nombre = comparacion.Hija(**{**hija._asdict(), "robot": {"id": "a"}})
    comp = comparacion.comparar([sin_nombre], CONDICIONES)
    assert "nombre" not in comp["ranking"][0]
    validar("comparacion", comp)


CAMPOS = ("tasa_exito", "ciclo_s", "ciclo_promedio_s", "corrida_id", "generico")


def test_los_textos_para_el_cliente_no_nombran_campos():
    hijas = [_hija("a", 0.9, fidelidad="verificado"), _hija("b", 0.8, fisica=False),
             _hija("c", None, error="falló")]
    comp = comparacion.comparar(hijas, CONDICIONES)
    textos = [comp["regla"], comp["explicacion"], *comp["advertencias"]]
    for t in textos:
        assert not any(c in t for c in CAMPOS), t
    assert comp["regla"].startswith("Gana el robot con mayor porcentaje de éxito")
    assert "menor tiempo de ciclo" in comp["regla"]


def test_empate_total_ordena_por_id():
    comp = comparacion.comparar([_hija("zeta", 0.9, 50), _hija("alfa", 0.9, 50)], CONDICIONES)
    assert _ids(comp) == ["alfa", "zeta"]


def test_sin_exitos_el_ciclo_es_nulo_y_va_al_final_del_empate():
    comp = comparacion.comparar([_hija("a", 0.0, 0.0), _hija("b", 0.0, 12.0)], CONDICIONES)
    assert [f["ciclo_s"] for f in comp["ranking"]] == [None, None]
    assert _ids(comp) == ["a", "b"]
    validar("comparacion", comp)


def test_una_hija_fallida_queda_fuera_y_tiene_advertencia():
    comp = comparacion.comparar([_hija("a", 0.7), _hija("b", None, error="el sim runner falló en entrenar")],
                                CONDICIONES)
    assert _ids(comp) == ["a"]
    aviso = next(x for x in comp["advertencias"] if "hija-b" in x)
    assert "b" in aviso and "el sim runner falló" in aviso
    validar("comparacion", comp)


def test_todas_fallidas_es_error():
    with pytest.raises(ErrorAgente):
        comparacion.comparar([_hija("a", None, error="x"), _hija("b", None, error="y")], CONDICIONES)


def test_fidelidad_del_clon_o_de_la_ficha():
    comp = comparacion.comparar([_hija("a", 0.9, fidelidad="verificado"), _hija("b", 0.8, fisica=True),
                                 _hija("c", 0.7, fisica=False)], CONDICIONES)
    assert [f["fidelidad"] for f in comp["ranking"]] == ["verificado", "medido", "generico"]
    assert any("fidelidad distinta" in x for x in comp["advertencias"])


def test_misma_fidelidad_no_advierte():
    comp = comparacion.comparar([_hija("a", 0.9), _hija("b", 0.8)], CONDICIONES)
    assert not any("fidelidad" in x for x in comp["advertencias"])


def test_advierte_que_no_hay_semillas_fijas():
    comp = comparacion.comparar([_hija("a", 0.9), _hija("b", 0.8)], CONDICIONES)
    assert comp["condiciones"]["semillas"] is None
    assert any("semillas" in x for x in comp["advertencias"])


def test_advierte_metricas_del_entorno_simulado():
    hija = _hija("a", 0.9)
    simulada = comparacion.Hija(**{**hija._asdict(), "resultado": {**hija.resultado, "fuente": "simulado"}})
    comp = comparacion.comparar([simulada, _hija("b", 0.8)], CONDICIONES)
    assert any("simulado" in x for x in comp["advertencias"])


def test_condiciones_y_textos_fijos():
    comp = comparacion.comparar([_hija("a", 0.9), _hija("b", 0.8)], CONDICIONES)
    assert comp["condiciones"] == CONDICIONES
    assert comp["que_compara"] == list(comparacion.QUE_COMPARA)
    assert comp["que_no_compara"] == list(comparacion.QUE_NO_COMPARA)
    assert "5 cm" in comp["regla"] and comp["explicacion"]


def test_no_cambia_las_entradas():
    hijas = [_hija("b", 0.8), _hija("a", 0.9)]
    copia = [h._asdict() for h in hijas]
    comparacion.comparar(hijas, CONDICIONES)
    assert [h._asdict() for h in hijas] == copia


def test_explicacion_con_modelo_no_cambia_el_ranking(monkeypatch):
    comp = comparacion.comparar([_hija("a", 0.9), _hija("b", 0.8)], CONDICIONES)
    vistos: list[str] = []

    def modelo_falso(**kw):
        vistos.append(kw["contenido"][0]["text"])
        return {"explicacion": "a gana por mayor tasa de éxito."}

    monkeypatch.setattr(comparacion, "pedir_json", modelo_falso)
    explicada = comparacion.explicar("claude", "m", comp)
    assert explicada["explicacion"] == "a gana por mayor tasa de éxito."
    assert explicada["ranking"] == comp["ranking"] and explicada["ganador"] == comp["ganador"]
    assert '"ranking"' in vistos[0]
    validar("comparacion", explicada)


def test_explicacion_usa_la_plantilla_si_el_modelo_falla(monkeypatch):
    comp = comparacion.comparar([_hija("a", 0.9), _hija("b", 0.8)], CONDICIONES)

    def falla(**kw):
        raise ErrorAgente("sin red")

    monkeypatch.setattr(comparacion, "pedir_json", falla)
    assert comparacion.explicar("claude", "m", comp) == comp


def test_modo_fijo_no_llama_al_modelo(monkeypatch):
    comp = comparacion.comparar([_hija("a", 0.9), _hija("b", 0.8)], CONDICIONES)
    monkeypatch.setattr(comparacion, "pedir_json", lambda **kw: pytest.fail("no debe llamar al modelo"))
    assert comparacion.explicar("fijo", "m", comp) == comp


def test_el_prompt_no_nombra_el_dominio():
    texto = comparacion.SISTEMA_COMPARACION.lower()
    assert not any(p in texto for p in ("panel", "solar", "tracker", "tubo"))
