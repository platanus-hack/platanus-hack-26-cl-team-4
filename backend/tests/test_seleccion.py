"""Selección de robot v3: perfil de dominio, descarte por reglas y 1 a 3 finalistas (docs/agentes/seleccion-robot.md)."""
from __future__ import annotations

import copy
import json

import pytest

from viaz import agentes, catalogo
from viaz.agentes import perfiles, seleccion
from viaz.config import Config, cargar
from viaz.esquemas import validar


def _fixture(nombre: str) -> dict:
    return json.loads((agentes.FIXTURES / f"{nombre}.json").read_text(encoding="utf-8"))


@pytest.fixture
def entorno() -> dict:
    return _fixture("entorno")


@pytest.fixture
def tarea() -> dict:
    return _fixture("tarea")


@pytest.fixture
def fichas() -> dict[str, dict]:
    return catalogo.cargar()


@pytest.fixture
def requisitos(entorno, tarea, fichas) -> dict:
    return perfiles.requisitos(entorno, tarea, list(fichas.values()))


def _ids(filas: list[dict]) -> list[str]:
    return [f["id"] for f in filas]


# ---------- 1. Perfil de dominio ----------

def test_el_perfil_solar_da_los_requisitos_del_fixture(requisitos):
    assert validar("requisitos", requisitos) == _fixture("requisitos")


def test_con_pendiente_fuerte_solo_sirve_un_vehiculo_con_brazo(entorno, tarea, fichas):
    empinado = {**entorno, "terreno": {**entorno["terreno"], "pendiente_grados": 15}}
    req = perfiles.requisitos(empinado, tarea, list(fichas.values()))
    assert req["tipos_aceptados"] == ["vehiculo_con_brazo"]
    assert req["pendiente_grados"] == 15


def test_un_dominio_sin_perfil_da_un_error_claro(entorno, tarea, fichas):
    with pytest.raises(agentes.ErrorAgente, match="mina_subterranea"):
        perfiles.requisitos({**entorno, "tipo": "mina_subterranea"}, tarea, list(fichas.values()))


def test_el_perfil_no_cambia_sus_entradas(entorno, tarea, fichas):
    antes = copy.deepcopy((entorno, tarea, fichas))
    perfiles.requisitos(entorno, tarea, list(fichas.values()))
    assert (entorno, tarea, fichas) == antes


# ---------- 3. Descarte por reglas ----------

def _ficha_que_pasa(requisitos: dict) -> dict:
    base = copy.deepcopy(catalogo.cargar()["leapting-mmr"])
    assert seleccion.fallas(base, requisitos) == []
    return base


@pytest.mark.parametrize(("cambio", "esperado"), [
    ({"carga_util_kg": 20}, "carga útil de 20 kg menor que la mínima (32 kg)"),
    ({"efector": "pinza"}, "efector pinza no está entre los aceptados (ventosa)"),
    ({"tipo": "brazo_fijo"}, "tipo brazo_fijo no está entre los aceptados (base_movil_brazo, vehiculo_con_brazo)"),
    ({"alcance_m": 2.0}, "alcance de 2.0 m menor que el necesario (2.53 m)"),
])
def test_fallas_reporta_cada_requisito(requisitos, cambio, esperado):
    ficha = {**_ficha_que_pasa(requisitos), **cambio}
    assert seleccion.fallas(ficha, requisitos) == [esperado]


def test_fallas_no_nombra_el_dominio(requisitos):
    ficha = {**_ficha_que_pasa(requisitos), "carga_util_kg": 1, "efector": "pinza", "tipo": "brazo_fijo", "alcance_m": 0.5}
    texto = " ".join(seleccion.fallas(ficha, requisitos)).lower()
    assert len(seleccion.fallas(ficha, requisitos)) == 4
    for palabra in ("panel", "tubo", "solar", "parque"):
        assert palabra not in texto


def test_fallas_pide_una_fila_por_robot(requisitos):
    ficha = {**_ficha_que_pasa(requisitos), "id": "otro-robot"}
    with pytest.raises(agentes.ErrorAgente, match="otro-robot"):
        seleccion.fallas(ficha, requisitos)


def test_el_nucleo_de_fisica_sale_del_esquema(fichas):
    assert seleccion.NUCLEO_FISICA == ("largo_m", "ancho_m", "masa_kg", "altura_cubierta_m", "traccion")
    assert seleccion.tiene_nucleo(fichas["leapting-mmr"])
    assert not seleccion.tiene_nucleo(fichas["aes-maximo"])


def test_una_preferencia_desconocida_da_un_error_claro(requisitos, fichas):
    req = {**requisitos, "preferencias": [{"criterio": "mas_bonito", "descripcion": "x"}]}
    with pytest.raises(agentes.ErrorAgente, match="mas_bonito"):
        seleccion.por_reglas(req, list(fichas.values()), 3)


# ---------- 4. Selección por reglas ----------

def test_por_reglas_en_el_catalogo_real(entorno, tarea, fichas):
    r = agentes.seleccionar("fijo", "x", entorno, tarea, fichas)
    sel = validar("seleccion", r.seleccion)
    assert _ids(sel["finalistas"]) == ["leapting-mmr", "relu-bison"]
    assert [f["puesto"] for f in sel["finalistas"]] == [1, 2]
    assert _ids(sel["descartados"]) == ["trinatracker-buildex-e"]
    assert "alcance" in sel["descartados"][0]["fallas"][0]
    assert _ids(sel["alternativas"]) == ["aes-maximo", "viaz-instalador-ficticio"]
    assert sel["busqueda"]["estado"] == "omitida" and sel["encontrados"] == []
    assert sel["requisitos"] == "requisitos.json"
    esperado = _fixture("seleccion")
    for campo in ("finalistas", "alternativas", "descartados"):
        assert _ids(sel[campo]) == _ids(esperado[campo])
    assert sel["descartados"] == esperado["descartados"]


def test_el_demo_sigue_eligiendo_el_leapting(entorno, tarea, fichas):
    r = agentes.seleccionar("fijo", "x", entorno, tarea, fichas)
    assert r.robots_por_puesto[0]["id"] == "leapting-mmr"
    assert _ids(r.robots_por_puesto) == _ids(r.seleccion["finalistas"])


def test_con_tope_1_el_segundo_queda_como_alternativa(entorno, tarea, fichas):
    sel = agentes.seleccionar("fijo", "x", entorno, tarea, fichas, max_finalistas=1).seleccion
    assert _ids(sel["finalistas"]) == ["leapting-mmr"]
    assert _ids(sel["alternativas"]) == ["relu-bison", "aes-maximo", "viaz-instalador-ficticio"]
    assert "tope" in sel["alternativas"][0]["por_que_no"]


@pytest.mark.parametrize("tope", [0, 4])
def test_un_tope_fuera_de_rango_se_rechaza(entorno, tarea, fichas, tope, monkeypatch):
    with pytest.raises(ValueError, match="VIAZ_MAX_FINALISTAS"):
        agentes.seleccionar("fijo", "x", entorno, tarea, fichas, max_finalistas=tope)
    monkeypatch.setenv("VIAZ_MAX_FINALISTAS", str(tope))
    with pytest.raises(ValueError, match="VIAZ_MAX_FINALISTAS"):
        cargar()


def test_el_tope_se_lee_de_la_configuracion(monkeypatch):
    assert Config().max_finalistas == 3
    monkeypatch.setenv("VIAZ_MAX_FINALISTAS", "2")
    assert cargar().max_finalistas == 2
    monkeypatch.setenv("VIAZ_MAX_FINALISTAS", "dos")
    with pytest.raises(ValueError, match="VIAZ_MAX_FINALISTAS"):
        cargar()


def test_si_nadie_pasa_hay_un_finalista_que_lo_dice(entorno, tarea, fichas):
    pesado = {**entorno, "panel": {**entorno["panel"], "peso_kg": 500}}
    r = agentes.seleccionar("fijo", "x", pesado, tarea, fichas)
    sel = validar("seleccion", r.seleccion)
    assert len(sel["finalistas"]) == 1 and sel["alternativas"] == []
    primera = sel["finalistas"][0]["justificacion"].split(". ")[0]
    assert primera.startswith("Ningún candidato cumple los requisitos obligatorios")
    assert "carga útil" in primera
    fallas = {d["id"]: d["fallas"] for d in sel["descartados"]}
    assert len(fallas[sel["finalistas"][0]["id"]]) == min(len(f) for f in fallas.values())
    assert len(r.robots_por_puesto) == 1


def test_un_candidato_sin_nucleo_nunca_es_finalista(entorno, tarea, fichas):
    solo_sin_nucleo = {i: fichas[i] for i in ("aes-maximo", "viaz-instalador-ficticio")}
    with pytest.raises(agentes.ErrorAgente, match="núcleo"):
        agentes.seleccionar("fijo", "x", entorno, tarea, solo_sin_nucleo)
    sel = agentes.seleccionar("fijo", "x", entorno, tarea, fichas).seleccion
    assert all(seleccion.tiene_nucleo(fichas[f["id"]]) for f in sel["finalistas"])


def test_la_seleccion_no_cambia_sus_entradas(entorno, tarea, fichas):
    antes = copy.deepcopy((entorno, tarea, fichas))
    agentes.seleccionar("fijo", "x", entorno, tarea, fichas)
    assert (entorno, tarea, fichas) == antes


# ---------- robot.json por finalista ----------

def test_cada_robot_json_valida_y_lista_a_todos_los_demas(entorno, tarea, fichas):
    r = agentes.seleccionar("fijo", "x", entorno, tarea, fichas)
    for robot in r.robots_por_puesto:
        validar("robot", robot)
        ficha = fichas[robot["id"]]
        assert {k: robot[k] for k in ficha} == ficha
        assert sorted(_ids(robot["alternativas"])) == sorted(set(fichas) - {robot["id"]})
    segundo = {a["id"]: a["por_que_no"] for a in r.robots_por_puesto[1]["alternativas"]}
    assert segundo["leapting-mmr"] == "finalista 1"
    assert segundo["trinatracker-buildex-e"].startswith("alcance de 2.5 m")
    assert r.robots_por_puesto[0]["justificacion"] == r.seleccion["finalistas"][0]["justificacion"]


# ---------- 4. Selección con el modelo (falso: no llama a la API) ----------

BUENA = {
    "finalistas": [
        {"id": "leapting-mmr", "puesto": 1, "justificacion": "Primero."},
        {"id": "relu-bison", "puesto": 2, "justificacion": "Segundo."},
    ],
    "alternativas": [
        {"id": "aes-maximo", "por_que_no": "sin núcleo"},
        {"id": "viaz-instalador-ficticio", "por_que_no": "ficticio"},
    ],
}


def _con_modelo(monkeypatch, respuesta: dict) -> list[dict]:
    llamadas: list[dict] = []

    def falso(**kw):
        llamadas.append(kw)
        return copy.deepcopy(respuesta)
    monkeypatch.setattr(agentes, "pedir_json", falso)
    return llamadas


def test_el_modelo_elige_entre_los_que_pasan(monkeypatch, entorno, tarea, fichas):
    llamadas = _con_modelo(monkeypatch, BUENA)
    r = agentes.seleccionar("claude", "modelo-x", entorno, tarea, fichas)
    sel = validar("seleccion", r.seleccion)
    assert sel["finalistas"] == BUENA["finalistas"] and sel["alternativas"] == BUENA["alternativas"]
    assert _ids(sel["descartados"]) == ["trinatracker-buildex-e"]
    assert _ids(r.robots_por_puesto) == ["leapting-mmr", "relu-bison"]
    assert r.robots_por_puesto[0]["carga_util_kg"] == fichas["leapting-mmr"]["carga_util_kg"]
    esquema = llamadas[0]["esquema"]
    ids = esquema["properties"]["finalistas"]["items"]["properties"]["id"]["enum"]
    assert sorted(ids) == ["aes-maximo", "leapting-mmr", "relu-bison", "viaz-instalador-ficticio"]
    texto = llamadas[0]["contenido"][-1]["text"]
    assert "requisitos.json" in texto and "trinatracker-buildex-e" not in texto.split("Candidatos")[1]


def _cambiada(**cambios) -> dict:
    return {**copy.deepcopy(BUENA), **cambios}


@pytest.mark.parametrize(("respuesta", "motivo"), [
    (_cambiada(finalistas=[{"id": "trinatracker-buildex-e", "puesto": 1, "justificacion": "x"},
                           *BUENA["finalistas"][1:]]), "candidato"),
    (_cambiada(finalistas=[{**BUENA["finalistas"][0]}, {**BUENA["finalistas"][1], "puesto": 1}]), "puesto"),
    (_cambiada(finalistas=[*BUENA["finalistas"], {"id": "aes-maximo", "puesto": 3, "justificacion": "x"}],
               alternativas=BUENA["alternativas"][1:]), "núcleo"),
    (_cambiada(finalistas=[{"id": i, "puesto": n, "justificacion": "x"} for n, i in enumerate(
        ["leapting-mmr", "relu-bison", "aes-maximo", "viaz-instalador-ficticio"], 1)], alternativas=[]), "finalistas"),
    (_cambiada(alternativas=BUENA["alternativas"][:1]), "viaz-instalador-ficticio"),
    (_cambiada(alternativas=[*BUENA["alternativas"], {"id": "relu-bison", "por_que_no": "x"}]), "relu-bison"),
])
def test_el_codigo_rechaza_una_respuesta_fuera_de_contrato(monkeypatch, entorno, tarea, fichas, respuesta, motivo):
    _con_modelo(monkeypatch, respuesta)
    with pytest.raises(agentes.ErrorAgente, match=motivo):
        agentes.seleccionar("claude", "modelo-x", entorno, tarea, fichas)


def test_si_nadie_pasa_el_codigo_decide_y_el_modelo_explica(monkeypatch, entorno, tarea, fichas):
    pesado = {**entorno, "panel": {**entorno["panel"], "peso_kg": 500}}
    esperado = agentes.seleccionar("fijo", "x", pesado, tarea, fichas).seleccion["finalistas"][0]["id"]
    llamadas = _con_modelo(monkeypatch, {"justificacion": "Ningún candidato cumple. Explicación."})
    sel = agentes.seleccionar("claude", "modelo-x", pesado, tarea, fichas).seleccion
    assert sel["finalistas"] == [{"id": esperado, "puesto": 1, "justificacion": "Ningún candidato cumple. Explicación."}]
    assert list(llamadas[0]["esquema"]["properties"]) == ["justificacion"]
