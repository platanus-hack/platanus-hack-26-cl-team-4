"""Demo estático de la web (RF-WEB-08) y campos opcionales del entrenamiento en resultado.json."""
from __future__ import annotations

import copy
import json

import pytest

from viaz import demo
from viaz.esquemas import ErrorEsquema, validar


def test_demo_genera_todos_los_archivos_que_lee_la_web(tmp_path):
    meta = demo.generar(tmp_path)
    for archivo in ("entorno.json", "tarea.json", "robot.json", "clon.json", "resultado.json",
                    "trayectoria.json", "robot.urdf", "corrida.json"):
        assert (tmp_path / archivo).is_file(), archivo
    assert "robot.urdf" in meta["archivos"]
    robot = json.loads((tmp_path / "robot.json").read_text(encoding="utf-8"))
    assert "Modo fijo" not in robot["justificacion"]
    assert "2,4 m" in robot["justificacion"]  # coma decimal
    clon = json.loads((tmp_path / "clon.json").read_text(encoding="utf-8"))
    assert clon["validado_en_escena"] is True


def test_demo_versionado_esta_al_dia():
    """web/public/demo debe coincidir con lo que genera el código actual (salvo la fecha)."""
    carpeta = demo.RAIZ / "web" / "public" / "demo"
    if not carpeta.is_dir():
        pytest.skip("no hay demo versionado")
    actual = {f.name: f.read_text(encoding="utf-8") for f in carpeta.iterdir() if f.name != "corrida.json"}
    nuevo_dir = carpeta.parent / "_demo_test"
    try:
        demo.generar(nuevo_dir)
        nuevo = {f.name: f.read_text(encoding="utf-8") for f in nuevo_dir.iterdir() if f.name != "corrida.json"}
    finally:
        for f in nuevo_dir.glob("*"):
            f.unlink()
        nuevo_dir.rmdir()
    assert actual == nuevo, "regenera el demo: cd backend && python -m viaz.demo"


RESULTADO = {
    "version": 1, "metodo": "rl", "fuente": "isaac", "politica": "politica.pt",
    "metricas": {"paneles_instalados": 92, "intentos": 100, "tasa_exito": 0.92, "ciclo_promedio_s": 41.0},
    "video": "video.mp4", "notas": "",
}


def test_resultado_acepta_evaluacion_y_entrenamiento():
    r = copy.deepcopy(RESULTADO)
    r["evaluacion"] = {"episodios": 100, "exitos": 92, "tasa_exito": 0.92, "tolerancia": {"pos_m": 0.05, "ang_grados": 5}}
    r["entrenamiento"] = {"pasos_sim": 48_000_000, "tiempo_real_s": 2700, "num_entornos": 4096,
                          "video_rapido": "entrenamiento_rapido.mp4",
                          "curva": [{"paso": 0, "tasa_exito": 0.0}, {"paso": 48_000_000, "tasa_exito": 0.92}],
                          "hitos": [{"paso": 12_000_000, "texto": "llega al tubo"}]}
    validar("resultado", r)
    validar("resultado", RESULTADO)  # siguen siendo opcionales


def test_resultado_rechaza_evaluacion_incompleta():
    r = copy.deepcopy(RESULTADO)
    r["evaluacion"] = {"episodios": 100, "tasa_exito": 0.92}
    with pytest.raises(ErrorEsquema):
        validar("resultado", r)
