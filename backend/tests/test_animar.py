"""Tarea animar_evento: un dominio nuevo que entra solo con su perfil (RF-GEN-03), sin tocar los agentes."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from viaz import agentes, monitor, orquestador
from viaz.agentes import perfiles
from viaz.esquemas import validar

FIXTURES = Path(__file__).resolve().parents[1] / "viaz" / "fixtures"
CATALOGO = Path(__file__).resolve().parents[1] / "viaz" / "catalogo" / "robots"


def _fixture(n: str) -> dict:
    return json.loads((FIXTURES / f"{n}.json").read_text(encoding="utf-8"))


def _catalogo() -> dict[str, dict]:
    return {f["id"]: f for f in (json.loads(p.read_text(encoding="utf-8")) for p in CATALOGO.glob("*.json"))}


def test_el_lugar_del_pitch_y_su_tarea_validan_y_calzan():
    entorno = validar("entorno", _fixture("entorno_evento"))
    tarea = agentes.validar_tarea(_fixture("tarea_animar"), entorno)
    assert tarea["tarea"] == "animar_evento" and len(tarea["animacion"]["puntos"]) == 4


def test_animar_exige_su_bloque_y_las_otras_tareas_no_lo_aceptan():
    t = _fixture("tarea_animar")
    del t["animacion"]
    with pytest.raises(Exception):
        validar("tarea", t)
    sala = _fixture("tarea_sala")
    sala["animacion"] = _fixture("tarea_animar")["animacion"]
    with pytest.raises(Exception):
        validar("tarea", sala)


def test_un_tramo_que_cruza_las_sillas_se_rechaza_con_el_nombre_del_elemento():
    t = _fixture("tarea_animar")
    t["animacion"]["puntos"][1] = {"nombre": "entre_sillas", "x_m": 7.0, "y_m": 6.0}
    problemas = perfiles.problemas_animar(t, _fixture("entorno_evento"))
    assert any("sillas_bloque_1" in p for p in problemas)
    with pytest.raises(agentes.ErrorAgente, match="sillas_bloque_1"):
        agentes.validar_tarea(t, _fixture("entorno_evento"))


def test_un_punto_fuera_de_la_sala_se_rechaza():
    t = _fixture("tarea_animar")
    t["animacion"]["puntos"][-1]["x_m"] = 30
    assert any("fuera del espacio" in p for p in perfiles.problemas_animar(t, _fixture("entorno_evento")))


def test_la_tarea_pone_requisitos_fisicos_y_no_elige_el_tipo_de_robot():
    req = perfiles.requisitos(_fixture("entorno_evento"), _fixture("tarea_animar"), list(_catalogo().values()))
    assert req["dominio"] == "animar_evento" and req["objeto"] is None and req["carga_min_kg"] == 0
    assert {"humanoide", "base_movil_brazo", "vehiculo_con_brazo"} <= set(req["tipos_aceptados"])
    assert "brazo_fijo" not in req["tipos_aceptados"]                     # animar exige moverse por la sala
    assert req["ancho_max_m"] == 1.0                                      # frente a la tarima: 1 m libre - 0,5 m por lado
    assert "caminar" in req["capacidades_deseadas"]                       # preferencia, no filtro
    assert any("confianza" in a for a in req["advertencias"])             # medidas estimadas desde el video


def test_la_seleccion_descarta_solo_por_tamano_y_deja_la_decision_al_agente():
    sel = agentes.seleccionar("fijo", "", _fixture("entorno_evento"), _fixture("tarea_animar"), _catalogo(),
                              max_finalistas=3)
    fallas = {d["id"]: " ".join(d["fallas"]) for d in sel.seleccion["descartados"]}
    assert not any("tipo" in f or "efector" in f for f in fallas.values())   # ninguno cae por tipo ni por efector
    assert all("ancho" in fallas[r] for r in ("leapting-mmr", "relu-bison", "trinatracker-buildex-e"))  # no caben
    assert "modelo_sim" in fallas["aes-maximo"]                              # cabría, pero VIAZ no lo puede simular aún
    assert sel.robots_por_puesto[0]["id"] == "unitree-h1"


def test_un_robot_con_ruedas_y_modelo_publicado_competiria_con_el_humanoide():
    cat = _catalogo()
    ruedas = {**cat["aes-maximo"], "id": "base-ruedas-prueba", "modelo_sim": cat["unitree-h1"]["modelo_sim"]}
    sel = agentes.seleccionar("fijo", "", _fixture("entorno_evento"), _fixture("tarea_animar"),
                              {**cat, ruedas["id"]: ruedas}, max_finalistas=3)
    ids = [f["id"] for f in sel.seleccion["finalistas"]] + [a["id"] for a in sel.seleccion["alternativas"]]
    assert {"unitree-h1", "base-ruedas-prueba"} <= set(ids)


def test_dos_tareas_dos_selecciones_independientes():
    """Un robot para instalar paneles y otro para animar el evento: cada corrida elige el suyo."""
    cat = _catalogo()
    solar = agentes.seleccionar("fijo", "", _fixture("entorno"), _fixture("tarea"), cat)
    fiesta = agentes.seleccionar("fijo", "", _fixture("entorno_evento"), _fixture("tarea_animar"), cat)
    assert solar.robots_por_puesto[0]["id"] != fiesta.robots_por_puesto[0]["id"]
    assert solar.robots_por_puesto[0]["tipo"] != "humanoide"


def test_el_perfil_solar_sigue_igual():
    req = perfiles.requisitos(_fixture("entorno"), _fixture("tarea"), list(_catalogo().values()))
    assert req["dominio"] == "solar" and "humanoide" not in req["tipos_aceptados"]


def test_un_entorno_sin_perfil_y_una_tarea_sin_perfil_dan_un_error_que_nombra_las_dos():
    with pytest.raises(agentes.ErrorAgente, match="tomar_y_dejar"):
        perfiles.requisitos(_fixture("entorno_sala"), _fixture("tarea_sala"), [])


def test_el_clon_de_un_modelo_del_fabricante_no_necesita_piezas_ni_geometria():
    clon = {"version": 1, "robot_id": "unitree-h1", "usd": "Isaac/IsaacLab/Robots/Unitree/H1/h1.usd", "urdf": None,
            "modelo": _catalogo()["unitree-h1"]["modelo_sim"], "escala": {"alcance_m": 0.6, "carga_util_kg": 30},
            "diferencias_con_real": [], "validado_en_escena": False}
    validar("clon", clon)
    sin_modelo = copy.deepcopy(clon)
    del sin_modelo["modelo"]
    with pytest.raises(Exception):
        validar("clon", sin_modelo)   # un clon ensamblado sigue necesitando piezas y geometría


def test_el_monitor_y_discord_nombran_la_tarea_y_la_tolerancia_de_la_corrida():
    t = _fixture("tarea_animar")
    assert "animar_evento" in monitor.meta_de(t) and "50 cm" in monitor.meta_de(t)
    av = monitor.Avisador("", tarea=t)
    ch = {"estado": "mejorando", "hito": "primer_exito", "recomendacion": "seguir", "detalle": "ok", "iteracion": 10,
          "evidencia": {"tiempo_usado_h": 0.1, "recompensa_media": 1.0, "tendencia_recompensa": None, "tasa_exito": 0.2}}
    texto = av.mensaje(ch, 1.0)
    assert "animar_evento" in texto and "50 cm, 30°" in texto and "instalar_panel" not in texto
