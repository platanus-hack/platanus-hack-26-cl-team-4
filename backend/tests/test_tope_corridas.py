"""Tope de corridas activas en POST /proyectos/{pid}/corridas (VIAZ_MAX_CORRIDAS_ACTIVAS)."""
from __future__ import annotations

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from viaz import db
from viaz.api import create_app
from viaz.config import Config


def _cliente(tmp_path, tope: int) -> tuple[TestClient, str]:
    cfg = Config(db_url=f"sqlite:///{tmp_path / 'v.db'}", dir_local=tmp_path / "a", worker_token="t",
                 admin_token="adm", agentes="fijo", max_corridas_activas=tope)
    cli = TestClient(create_app(cfg))
    pid = cli.post("/proyectos", json={"nombre": "parque"}).json()["id"]
    return cli, pid


def _poner_estado(cli: TestClient, cid: str, estado: str) -> None:
    with cli.app.state.eng.begin() as cx:
        cx.execute(db.corridas.update().where(db.corridas.c.id == cid).values(estado=estado))


def test_con_tope_2_y_2_activas_la_tercera_da_429(tmp_path):
    cli, pid = _cliente(tmp_path, 2)
    assert cli.post(f"/proyectos/{pid}/corridas").status_code == 201
    assert cli.post(f"/proyectos/{pid}/corridas").status_code == 201
    r = cli.post(f"/proyectos/{pid}/corridas")
    assert r.status_code == 429
    assert "corridas" in r.json()["detail"]


def test_una_corrida_lista_libera_cupo(tmp_path):
    cli, pid = _cliente(tmp_path, 2)
    primera = cli.post(f"/proyectos/{pid}/corridas").json()["corrida_id"]
    segunda = cli.post(f"/proyectos/{pid}/corridas").json()["corrida_id"]
    _poner_estado(cli, primera, "listo")
    _poner_estado(cli, segunda, "error")
    assert cli.post(f"/proyectos/{pid}/corridas").status_code == 201
    assert cli.post(f"/proyectos/{pid}/corridas").status_code == 201


def test_las_hijas_no_cuentan_para_el_tope(tmp_path):
    cli, pid = _cliente(tmp_path, 2)
    padre = cli.post(f"/proyectos/{pid}/corridas").json()["corrida_id"]
    with cli.app.state.eng.begin() as cx:
        cx.execute(db.corridas.insert().values(id="hija", proyecto_id=pid, estado="entrenando", etapas=[],
                                               padre_id=padre))
    assert cli.post(f"/proyectos/{pid}/corridas").status_code == 201


def test_una_corrida_trabada_fuera_de_la_ventana_no_cuenta(tmp_path):
    cli, pid = _cliente(tmp_path, 2)
    trabada = cli.post(f"/proyectos/{pid}/corridas").json()["corrida_id"]
    cli.post(f"/proyectos/{pid}/corridas")
    with cli.app.state.eng.begin() as cx:
        cx.execute(db.corridas.update().where(db.corridas.c.id == trabada)
                   .values(estado="entrenando", actualizado=db.ahora() - timedelta(hours=7)))
    assert cli.post(f"/proyectos/{pid}/corridas").status_code == 201
    assert cli.post(f"/proyectos/{pid}/corridas").status_code == 429


def test_ventana_por_defecto_es_6_horas(monkeypatch):
    monkeypatch.delenv("VIAZ_VENTANA_CORRIDAS_H", raising=False)
    assert Config().ventana_corridas_h == 6


@pytest.mark.parametrize("valor", ["0", "169", "seis"])
def test_ventana_invalida_falla_al_leer_la_config(monkeypatch, valor):
    monkeypatch.setenv("VIAZ_VENTANA_CORRIDAS_H", valor)
    with pytest.raises(ValueError, match="VIAZ_VENTANA_CORRIDAS_H"):
        Config()


def test_con_tope_0_no_hay_limite(tmp_path):
    cli, pid = _cliente(tmp_path, 0)
    for _ in range(5):
        assert cli.post(f"/proyectos/{pid}/corridas").status_code == 201


def test_por_defecto_no_hay_tope(monkeypatch):
    monkeypatch.delenv("VIAZ_MAX_CORRIDAS_ACTIVAS", raising=False)
    assert Config().max_corridas_activas == 0


@pytest.mark.parametrize("valor", ["-1", "dos", "1.5"])
def test_valor_invalido_falla_al_leer_la_config(monkeypatch, valor):
    monkeypatch.setenv("VIAZ_MAX_CORRIDAS_ACTIVAS", valor)
    with pytest.raises(ValueError, match="VIAZ_MAX_CORRIDAS_ACTIVAS"):
        Config()


def test_tokens_siguen_igual(tmp_path):
    cli, _ = _cliente(tmp_path, 0)
    assert cli.post("/corridas/x/detener").status_code == 401
    assert cli.post("/corridas/x/detener", headers={"Authorization": "Bearer otro"}).status_code == 401
    assert cli.post("/corridas/x/detener", headers={"Authorization": "Bearer adm"}).status_code == 404
