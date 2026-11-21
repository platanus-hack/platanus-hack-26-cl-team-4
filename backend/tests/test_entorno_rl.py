"""Partes del entorno RL que no necesitan Isaac: robot desde el URDF, cinemática, agarre, éxito y recompensa."""
from __future__ import annotations

import json
import math
import random
import sys
from pathlib import Path

import pytest

from viaz import urdf

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "sim"))
import viaz_escena  # noqa: E402
from rl import agarre, base_movil, carpeta_corrida, cinematica as cin, corrida, criterio, entrenar, exito, robot, tarea  # noqa: E402

ROBOTS = ("leapting-mmr", "aes-maximo")
CATALOGO = Path(__file__).resolve().parents[1] / "viaz" / "catalogo" / "robots"
SIN_GIRO = (1.0, 0.0, 0.0, 0.0)
VENTOSA_TAM = (0.6, 1.0)
PANEL_TAM = (1.13, 2.38, 0.04)


@pytest.fixture(params=ROBOTS)
def c(request, tmp_path) -> corrida.Corrida:
    return corrida.de_carpeta(carpeta_corrida.escribir(request.param, tmp_path))


def _tarea(c: corrida.Corrida) -> tarea.Tarea:
    return tarea.de_corrida(c)[1]


def _fisica(c: corrida.Corrida) -> dict | None:
    return json.loads((CATALOGO / f"{c.clon['robot_id']}.json").read_text(encoding="utf-8")).get("fisica")


def _giro(eje: int, grados: float):
    return cin.quat_eje(eje, math.radians(grados))


# ---------- robot desde robot.urdf ----------

def test_el_robot_sale_del_urdf_con_sus_limites_y_su_masa(c):
    alcance = c.clon["escala"]["alcance_m"]
    arts = c.robot.articulaciones
    assert [u.nombre for u in arts] == urdf.ARTICULACIONES
    for u in arts:   # RF-INT-23: torque y velocidad del URDF, por articulación
        assert (u.esfuerzo, u.velocidad) == (urdf.ESFUERZO_NM[u.nombre], urdf.VELOCIDAD_RAD_S)
        assert (u.inferior, u.superior) == (-urdf.LIMITE_RAD, urdf.LIMITE_RAD)
    assert c.robot.masa_kg == pytest.approx(urdf.masa_total(alcance, _fisica(c)), abs=0.1)
    geo = urdf.geometria(alcance, _fisica(c))
    assert (c.cadena.l1, c.cadena.l2, c.cadena.muneca) == pytest.approx((geo["l1_m"], geo["l2_m"], geo["muneca_m"]))
    assert (c.cadena.montaje_x, c.cadena.hombro_z, c.cadena.cubierta_z) == pytest.approx(
        (geo["montaje_x_m"], geo["hombro_z_m"], geo["cubierta_z_m"]))
    assert c.cadena.alcance == pytest.approx(alcance)


def test_dos_robots_del_catalogo_dan_brazos_distintos(tmp_path):
    a, b = (corrida.de_carpeta(carpeta_corrida.escribir(r, tmp_path / r)) for r in ROBOTS)
    assert a.cadena.l1 != b.cadena.l1 and a.carga_util_kg != b.carga_util_kg


def test_un_urdf_de_otra_familia_se_rechaza_con_el_nombre_de_la_articulacion():
    otro = urdf.generar("x", 2.4).replace('<origin xyz="0 0 0.3"/><axis xyz="0 1 0"/>', '<origin xyz="0 0 0.3"/><axis xyz="1 0 0"/>')
    with pytest.raises(ValueError, match="shoulder_lift"):
        robot.cadena(robot.leer_urdf(otro))


def test_sin_robot_urdf_en_la_carpeta_se_genera_el_mismo(c):
    (c.carpeta / "robot.urdf").unlink()
    assert corrida.de_carpeta(c.carpeta).cadena == c.cadena


def test_sin_clon_json_el_error_dice_que_falta(c):
    (c.carpeta / "clon.json").unlink()
    with pytest.raises(FileNotFoundError, match="clon.json"):
        corrida.de_carpeta(c.carpeta)


# ---------- cinemática ----------

def _directa_por_cadena(r: robot.Robot, q: list[float]):
    """Cinemática directa genérica: recorre las uniones del URDF. Sirve de referencia independiente."""
    pos, giro = (0.0, 0.0, 0.0), SIN_GIRO
    for u, ang in zip(r.articulaciones, q):
        d = cin.quat_rotar(giro, u.xyz)
        pos = tuple(pos[k] + d[k] for k in range(3))
        giro = cin.quat_mul(giro, cin.quat_eje(u.eje.index(1.0), ang))
    cara = cin.quat_rotar(giro, (0.0, 0.0, r.piezas[robot.ESLABON_VENTOSA].dims[2]))
    return tuple(pos[k] + cara[k] for k in range(3)), giro


def test_la_cinematica_directa_calza_con_la_cadena_del_urdf(c):
    azar = random.Random(3)
    for _ in range(50):
        q = [azar.uniform(-3.0, 3.0) for _ in range(6)]
        pos, giro = cin.directa(c.cadena, q)
        pos_ref, giro_ref = _directa_por_cadena(c.robot, q)
        assert pos == pytest.approx(pos_ref, abs=1e-9)
        assert abs(sum(a * b for a, b in zip(giro, giro_ref))) == pytest.approx(1.0, abs=1e-9)


def test_la_inversa_deja_la_ventosa_en_el_punto_mirando_hacia_abajo(c):
    azar = random.Random(5)
    for _ in range(50):
        punto = (azar.uniform(-0.6, 1.2), azar.uniform(-1.9, -0.6), azar.uniform(0.9, 1.9))
        rumbo = azar.uniform(-0.3, 0.3)
        q, alcanzable = cin.inversa(c.cadena, punto, rumbo, tarea.PAN_REF)
        assert alcanzable
        pos, giro = cin.directa(c.cadena, q)
        assert pos == pytest.approx(punto, abs=1e-9)
        assert cin.quat_rotar(giro, (0.0, 0.0, 1.0)) == pytest.approx((0.0, 0.0, -1.0), abs=1e-9)
        assert math.sin(cin.rumbo(giro) - rumbo) == pytest.approx(0.0, abs=1e-9)   # mismo rumbo, o girado 180°


def test_el_giro_hacia_la_pila_respeta_el_tope_del_urdf(c):
    q, alcanzable = cin.inversa(c.cadena, (-0.35, 0.0, 1.0), 0.0, tarea.PAN_REF)
    assert alcanzable and c.cadena.inferior[0] < q[0] < -3.0   # la pila queda en -pi: se toma desde el tope negativo
    pos, _ = cin.directa(c.cadena, q)
    assert math.hypot(pos[0] + 0.35, pos[1]) < 0.05              # el recorte del giro corre la ventosa unos cm


def test_un_punto_fuera_de_alcance_se_informa(c):
    _, alcanzable = cin.inversa(c.cadena, (0.45, -(c.cadena.alcance + 0.5), 1.5), 0.0, tarea.PAN_REF)
    assert not alcanzable


# ---------- recorrido de la tarea ----------

def test_el_recorrido_nominal_es_alcanzable_y_termina_con_el_panel_en_la_meta(c):
    t = _tarea(c)
    assert tarea.problemas_alcance(t, c.cadena) == []
    angulos = tarea.nominal(t, c.cadena)
    assert list(angulos) == list(tarea.PUNTOS)
    pos, _ = cin.directa(c.cadena, angulos["dejar"][0])
    meta_base = cin.a_base(t.meta, t.base, 0.0)
    assert pos == pytest.approx((meta_base[0], meta_base[1], meta_base[2] + t.panel_tam[2] / 2), abs=1e-6)
    arriba, _ = cin.directa(c.cadena, angulos["sobre_meta"][0])
    assert arriba[2] - t.panel_tam[2] > t.tubo_arriba_z + 0.1    # el panel pasa sobre el tubo


def test_un_brazo_corto_recibe_un_problema_con_numeros(c):
    corto = robot.cadena(robot.leer_urdf(urdf.generar("corto", 1.6)))
    problemas = tarea.problemas_alcance(_tarea(c), corto)
    assert problemas and all("no llega" in p and " m" in p for p in problemas)
    assert any("1.30 m" in p for p in problemas)   # lo que estira ese brazo: l1 + l2


def test_el_oraculo_descuenta_el_desfase_del_agarre(c):
    t = _tarea(c)
    meta = cin.a_base(t.meta, t.base, 0.0)
    puntos = tarea.recorrido(t, t.panel_en_pila(4), 0.0, meta, 0.0, desfase=(0.03, -0.02, 0.0))
    (x, y, _), _ = puntos["dejar"]
    assert (x - meta[0], y - meta[1]) == pytest.approx((0.03, -0.02))


# ---------- agarre por succión virtual ----------

def _sobre_panel(separacion_m: float, corrimiento=(0.0, 0.0), inclinacion_grados: float = 0.0):
    """Ventosa mirando hacia abajo sobre un panel horizontal en el origen."""
    giro = cin.quat_mul(_giro(1, 180.0), _giro(0, inclinacion_grados))
    pos = (corrimiento[0], corrimiento[1], PANEL_TAM[2] / 2 + separacion_m)
    return pos, giro, (0.0, 0.0, 0.0), SIN_GIRO, VENTOSA_TAM, PANEL_TAM


def test_la_ventosa_sella_solo_cerca_alineada_y_sobre_el_panel():
    assert agarre.actualizar(False, True, *_sobre_panel(0.01))
    assert not agarre.actualizar(False, True, *_sobre_panel(0.03))                         # lejos
    assert not agarre.actualizar(False, True, *_sobre_panel(0.01, inclinacion_grados=10))  # inclinada
    assert not agarre.actualizar(False, True, *_sobre_panel(0.01, corrimiento=(0.3, 0.0)))  # una esquina fuera
    assert not agarre.actualizar(False, False, *_sobre_panel(0.01))                        # succión apagada


def test_un_panel_sellado_aguanta_hasta_la_distancia_de_ruptura():
    assert agarre.actualizar(True, True, *_sobre_panel(0.04))
    assert not agarre.actualizar(True, True, *_sobre_panel(0.06))
    assert not agarre.actualizar(True, False, *_sobre_panel(0.0))    # soltar = apagar la succión


def test_la_fuerza_de_la_ventosa_sale_de_la_carga_util_y_tira_el_panel_hacia_la_placa():
    fuerza = agarre.fuerza_ventosa_n(100.0)
    assert fuerza == pytest.approx(2 * 9.81 * 100.0)
    pos, giro, panel_pos, panel_giro, _, _ = _sobre_panel(0.0, corrimiento=(0.1, 0.0))
    f, torque = agarre.llave(fuerza, pos, giro, panel_pos, panel_giro)
    assert f == pytest.approx((0.0, 0.0, fuerza))                    # hacia arriba, hacia la placa
    assert torque == pytest.approx((0.0, -0.1 * fuerza, 0.0))        # aplicada en el centro de la placa, no del panel


# ---------- éxito ----------

def test_el_error_de_angulo_mide_rumbo_e_inclinacion_y_el_panel_es_simetrico():
    assert exito.error_angulo_grados(SIN_GIRO) == pytest.approx(0.0)
    assert exito.error_angulo_grados(_giro(2, 180.0)) == pytest.approx(0.0, abs=1e-5)
    assert exito.error_angulo_grados(_giro(2, 5.0)) == pytest.approx(5.0)
    assert exito.error_angulo_grados(_giro(2, 176.0)) == pytest.approx(4.0)
    assert exito.error_angulo_grados(_giro(0, 3.0)) == pytest.approx(3.0)


def _colocado(**cambios) -> bool:
    caso = {"err_pos_m": 0.03, "err_ang_grados": 1.0, "err_altura_m": 0.0, "vel_m_s": 0.0, "giro_rad_s": 0.0,
            "sellada": False, "succion": False, "dist_ventosa_m": 0.2, "tol_pos_m": 0.05, "tol_ang_grados": 5.0}
    return bool(exito.colocado(**{**caso, **cambios}))


def test_exito_solo_con_el_panel_suelto_apoyado_en_tolerancia_y_la_ventosa_lejos():
    assert _colocado()
    assert not _colocado(err_pos_m=0.06)            # RF-INT-11: 6 cm no es éxito a 5 cm
    assert not _colocado(err_ang_grados=6.0)
    assert not _colocado(tol_pos_m=0.02)            # 3 cm es éxito a 5 cm y no a 2 cm
    assert not _colocado(sellada=True)              # todavía en la ventosa
    assert not _colocado(succion=True)
    assert not _colocado(dist_ventosa_m=0.05)       # el brazo no se alejó
    assert not _colocado(vel_m_s=0.2)               # el panel se mueve
    assert not _colocado(err_altura_m=0.05)         # no está apoyado en el tubo


# ---------- recompensa: diferencia de un potencial ----------

DIST_INICIAL_M = 3.3


def _p(dist_ventosa=1.0, err_pos=DIST_INICIAL_M, err_ang=0.0, sellada=0.0, en_meta=0.0) -> float:
    return exito.potencial(dist_ventosa, err_pos, err_ang, sellada, en_meta, DIST_INICIAL_M)


def test_el_potencial_sube_en_cada_etapa_de_la_tarea():
    lejos, sobre_la_pila = _p(dist_ventosa=1.0), _p(dist_ventosa=0.0)
    sellado, llevando = _p(dist_ventosa=0.0, sellada=1.0), _p(dist_ventosa=0.0, err_pos=0.5, sellada=1.0)
    en_meta_sellado = _p(dist_ventosa=0.0, err_pos=0.0, sellada=1.0)
    recien_soltado = _p(dist_ventosa=0.0, err_pos=0.0, en_meta=1.0)
    retirado = _p(dist_ventosa=0.3, err_pos=0.0, en_meta=1.0)
    etapas = [lejos, sobre_la_pila, sellado, llevando, en_meta_sellado, recien_soltado, retirado]
    # Cada etapa suma al menos 1 punto sobre la anterior: un empate deja a la política sin motivo para avanzar.
    assert all(b - a >= 1.0 for a, b in zip(etapas, etapas[1:])), etapas


def test_sostener_el_panel_sin_moverlo_no_paga():
    """El estancamiento de la corrida 178ab8fee014: sellar el panel y quedarse quieto pagaba 1 punto por segundo."""
    quieto = _p(dist_ventosa=0.0, sellada=1.0)
    assert quieto - quieto == 0.0
    un_metro_mas_cerca = _p(dist_ventosa=0.0, err_pos=DIST_INICIAL_M - 1.0, sellada=1.0)
    assert un_metro_mas_cerca - quieto == pytest.approx(exito.POTENCIAL["llevar"] / DIST_INICIAL_M)


def test_sellar_y_soltar_en_el_mismo_lugar_suma_cero():
    antes = _p(dist_ventosa=0.0)
    sellado = _p(dist_ventosa=0.0, sellada=1.0)
    assert (sellado - antes) + (antes - sellado) == 0.0


def test_soltar_el_panel_lejos_de_la_meta_resta():
    assert _p(dist_ventosa=0.5, err_pos=1.0, sellada=0.0) < _p(dist_ventosa=0.0, err_pos=1.0, sellada=1.0)


def test_alejar_el_panel_de_la_meta_resta_y_el_potencial_esta_acotado():
    assert _p(err_pos=DIST_INICIAL_M + 1.0) < _p()
    total = sum(exito.POTENCIAL.values())
    assert -exito.POTENCIAL["llevar"] <= _p(err_pos=100.0) and _p(dist_ventosa=0.3, err_pos=0.0, en_meta=1.0) <= total


def test_terminar_con_exito_rinde_mas_que_todo_el_avance():
    assert exito.PREMIO_EXITO > sum(exito.POTENCIAL.values())
    assert exito.CASTIGO_FALLA < 0
    assert exito.CASTIGO_CHOQUE == -exito.PREMIO_EXITO      # un choque borra un éxito
    assert exito.costo(0.0, 0.0) == 0.0 and exito.costo(1.0, 1.0) < 0


# ---------- recorrido con una ventosa más larga que el ancho del panel ----------

def test_la_ventosa_larga_se_cruza_sobre_el_panel_y_la_que_no_cabe_se_rechaza():
    assert tarea.giro_agarre((0.6, 1.0), PANEL_TAM) == 0.0
    assert tarea.giro_agarre((1.9, 0.5), PANEL_TAM) == pytest.approx(math.pi / 2)
    with pytest.raises(ValueError, match="no cabe"):
        tarea.giro_agarre((2.5, 1.5), PANEL_TAM)


def test_en_cada_punto_del_recorrido_la_ventosa_puede_sellar_el_panel(c):
    t = _tarea(c)
    for nombre, (q, alcanzable) in tarea.nominal(t, c.cadena).items():
        pos, giro = cin.directa(c.cadena, q)
        assert alcanzable, nombre
        panel = (pos[0], pos[1], pos[2] - t.panel_tam[2] / 2)
        assert agarre.actualizar(False, True, pos, giro, panel, SIN_GIRO, c.cadena.ventosa, t.panel_tam), nombre


def test_la_base_queda_fuera_del_panel_instalado(c):
    t = _tarea(c)
    medio_ancho = c.clon["geometria"].get("medio_ancho_m", 0.5)
    assert t.base[1] - medio_ancho > t.meta[1] + t.panel_tam[1] / 2


# ---------- entrenar: ayuda de inicio y reanudación ----------

def test_la_ayuda_de_inicio_depende_del_exito_sin_ayuda_y_no_del_reloj():
    assert entrenar.fraccion_asistida(0.0) == entrenar.ASISTIDO_INICIAL
    assert 0 < entrenar.fraccion_asistida(entrenar.EXITO_SIN_AYUDA / 2) < entrenar.ASISTIDO_INICIAL
    assert entrenar.fraccion_asistida(entrenar.EXITO_SIN_AYUDA) == 0.0
    assert entrenar.fraccion_asistida(1.0) == 0.0


def test_el_premio_a_la_exploracion_baja_junto_con_la_ayuda_de_inicio():
    assert entrenar.coef_entropia(entrenar.ASISTIDO_INICIAL, 0.005) == 0.005
    assert entrenar.coef_entropia(entrenar.ASISTIDO_INICIAL / 2, 0.005) == pytest.approx(0.0025)
    assert entrenar.coef_entropia(0.0, 0.005) == entrenar.ENTROPIA_SIN_AYUDA == 0.0


def test_el_promedio_movil_no_cambia_en_una_iteracion_sin_episodios():
    assert entrenar.promedio_movil(0.2, None) == 0.2
    assert 0.2 < entrenar.promedio_movil(0.2, 1.0) < 1.0


def test_reanudar_sigue_los_pasos_y_el_tiempo_del_checkpoint(tmp_path):
    filas = [{"iteracion": i, "pasos": i * 100, "tiempo_s": float(i)} for i in range(74)]
    (tmp_path / "metricas.jsonl").write_text("".join(json.dumps(f) + "\n" for f in filas) + '{"iteracion": 74, "pa', encoding="utf-8")
    assert entrenar.linea_previa(tmp_path, 50) == filas[50]     # el pod murió en la 73: se retoma desde model_50
    assert entrenar.linea_previa(tmp_path / "vacio", 50) == {"pasos": 0, "tiempo_s": 0.0}


# ---------- secuencia de paneles y base móvil (RF-INT-18) ----------

def test_la_secuencia_instala_los_paneles_que_caben_en_el_tramo_de_tubo(c):
    t = _tarea(c)
    ancho = c.entorno["panel"]["ancho_m"]
    assert t.paneles == 4                                   # 4 slots de 1,15 m desde x = 2 m en un tramo de 7 m
    assert t.paso_slot == pytest.approx(ancho + 0.02)
    assert t.meta_k(t.paneles - 1)[0] + ancho / 2 <= viaz_escena.generar_escena.POSTE_CADA_M
    assert t.meta_k(t.paneles)[0] + ancho / 2 > viaz_escena.generar_escena.POSTE_CADA_M


def test_cada_panel_de_la_secuencia_tiene_su_slot_su_parada_y_su_altura_de_pila(c):
    t = _tarea(c)
    for k in range(t.paneles):
        meta, base = t.meta_k(k), t.base_k(k)
        assert meta[0] - t.meta[0] == pytest.approx(k * t.paso_slot)
        assert meta[1:] == t.meta[1:]
        assert cin.a_base(meta, base, 0.0) == pytest.approx(cin.a_base(t.meta, t.base, 0.0))   # la base ve el slot igual
        arriba = t.panel_en_pila(t.en_pila - 1 - k)
        assert arriba[2] == pytest.approx(t.cubierta_z + (t.en_pila - k - 0.5) * t.panel_tam[2])   # quedan en_pila - k
        assert all(alcanzable for _, alcanzable in tarea.nominal(t, c.cadena, k).values())
        assert t.dist_inicial_k(k) == pytest.approx(math.dist(cin.a_mundo(arriba, t.base, 0.0), t.meta))


def test_los_paneles_instalados_son_los_cuerpos_que_salieron_de_arriba_de_la_pila(c):
    t = _tarea(c)
    slots = [t.slot_del_cuerpo(j) for j in range(t.en_pila - 1)]    # cuerpos de la pila, sin el que se instala
    assert slots == list(range(t.en_pila - 2, -1, -1))              # el de más arriba va al slot 0
    for k in range(t.paneles):
        instalados = [j for j, s in enumerate(slots) if s < k]
        assert len(instalados) == k                                 # con el panel k hay k paneles en el tubo
        assert len(slots) - len(instalados) + 1 == t.en_pila - k    # y el resto sigue en la pila


def test_la_base_se_detiene_donde_sus_piezas_altas_no_tocan_los_paneles_instalados(c):
    t = _tarea(c)
    ruido = viaz_escena.fisica.rangos_variacion(c.entorno)
    borde = t.meta[1] + t.panel_tam[1] / 2
    argumentos = (borde, t.tubo_arriba_z, ruido["base_pos_m"], ruido["base_yaw_grados"])
    assert base_movil.margen_lateral_m(c.robot, t.base[1], *argumentos) == 0.0     # con el margen ya caben
    sin_margen = viaz_escena.plan.distancia_pasillo(c.entorno, c.clon["geometria"])
    assert t.base[1] - sin_margen == pytest.approx(base_movil.margen_lateral_m(c.robot, sin_margen, *argumentos))
    assert tarea.problemas_alcance(t, c.cadena) == []                               # y el brazo todavía llega


def test_el_gabinete_del_leapting_obliga_a_alejar_la_base(tmp_path):
    c = corrida.de_carpeta(carpeta_corrida.escribir("leapting-mmr", tmp_path))
    t = _tarea(c)
    sin_margen = viaz_escena.plan.distancia_pasillo(c.entorno, c.clon["geometria"])
    # Gabinete de 1,6 m de ancho y 2 m de alto, 1,57 m detrás del centro: con -15 cm y 5° entra 13 cm en los paneles.
    assert t.base[1] - sin_margen == pytest.approx(0.156, abs=0.005)


def test_las_copias_se_separan_lo_que_ocupa_la_base_al_recorrer_la_secuencia(c):
    t = _tarea(c)
    atras, adelante = base_movil.largo_base_m(c.robot)
    recorrido = (t.paneles - 1) * t.paso_slot
    espaciado = base_movil.espaciado_copias_m(c.robot, recorrido, viaz_escena.ESPACIADO_ENV_M)
    frente_en_el_ultimo_panel = t.base_k(t.paneles - 1)[0] + adelante
    cola_de_la_copia_vecina = espaciado + t.base[0] + atras
    assert cola_de_la_copia_vecina - frente_en_el_ultimo_panel >= 1.0 - 1e-6     # queda 1 m libre
    assert espaciado >= viaz_escena.ESPACIADO_ENV_M                               # y el tramo de tubo sigue cabiendo
    assert base_movil.espaciado_copias_m(c.robot, 0.0, 99.0) == 99.0


def test_la_base_parte_y_llega_detenida_y_no_pasa_su_velocidad_ni_su_aceleracion():
    v, a, dt = base_movil.VEL_BASE_M_S, base_movil.ACEL_BASE_M_S2, 1 / 30
    for distancia in (0.05, 0.4, 1.15, 3.0):
        duracion = base_movil.duracion_s(distancia)
        pasos = int(duracion / dt) + 2
        x = [base_movil.avance_m(i * dt, distancia) for i in range(pasos + 1)]
        vel = [(b - a_) / dt for a_, b in zip(x, x[1:])]
        assert x[0] == 0.0 and x[-1] == pytest.approx(distancia)
        assert all(b >= a_ - 1e-12 for a_, b in zip(x, x[1:]))                       # nunca retrocede
        assert max(vel) <= v + 1e-6 and vel[0] <= a * dt + 1e-6 and vel[-1] <= a * dt + 1e-6
        assert all(abs(b - a_) / dt <= a + 1e-6 for a_, b in zip(vel, vel[1:]))
        assert base_movil.avance_m(-1.0, distancia) == 0.0
        assert base_movil.avance_m(duracion + 5.0, distancia) == pytest.approx(distancia)


def test_un_viaje_largo_va_en_trapecio_y_uno_corto_en_triangulo():
    v, a = base_movil.VEL_BASE_M_S, base_movil.ACEL_BASE_M_S2
    assert base_movil.duracion_s(3.0) == pytest.approx(2 * v / a + (3.0 - v * v / a) / v)   # llega a su velocidad
    assert base_movil.duracion_s(0.2) == pytest.approx(2 * math.sqrt(0.2 / a))             # no alcanza a llegar
    assert base_movil.duracion_s(0.0) == pytest.approx(0.0, abs=1e-6)


def test_el_viaje_es_una_recta_entre_dos_puntos_de_montaje_y_corrige_el_rumbo(c):
    t = _tarea(c)
    inicio = (*t.base_k(0)[:2], math.radians(3.0))
    fin = (t.base_k(1)[0] + 0.1, t.base_k(1)[1] - 0.05, math.radians(-2.0))
    duracion = base_movil.duracion_s(math.dist(inicio[:2], fin[:2]))
    assert base_movil.pose_en_viaje(inicio, fin, 0.0) == pytest.approx(inicio)
    assert base_movil.pose_en_viaje(inicio, fin, duracion) == pytest.approx(fin)
    x, y, rumbo = base_movil.pose_en_viaje(inicio, fin, duracion / 2)
    assert (x, y, rumbo) == pytest.approx(tuple((p + q) / 2 for p, q in zip(inicio, fin)))   # a mitad de tiempo, mitad de camino
    assert (y - inicio[1]) * (fin[0] - inicio[0]) == pytest.approx((x - inicio[0]) * (fin[1] - inicio[1]))


def test_el_viaje_acepta_un_valor_por_entorno():
    torch = pytest.importorskip("torch")
    distancias = torch.tensor([0.0, 0.2, 1.15, 3.0])
    tiempos = torch.tensor([0.5, 0.5, 1.0, 10.0])
    lote = base_movil.avance_m(tiempos, distancias)
    for k in range(4):
        assert float(lote[k]) == pytest.approx(base_movil.avance_m(float(tiempos[k]), float(distancias[k])), abs=1e-6)


# ---------- criterio de parada del entrenamiento ----------

def _iteraciones(n: int, exito: float, choques: float = 0.0, caidas: float = 0.0, episodios: int = 1000) -> list[dict]:
    return [{"episodios_sin_ayuda": episodios, "exitos_sin_ayuda": round(exito * episodios), "episodios_con_ayuda": 0,
             "choques": round(choques * episodios), "caidas": round(caidas * episodios)} for _ in range(n)]


def test_el_criterio_pide_exito_pocos_choques_y_pocas_caidas_a_la_vez():
    assert criterio.cumple(criterio.medias(_iteraciones(20, 0.96, 0.008, 0.004)))
    assert not criterio.cumple(criterio.medias(_iteraciones(20, 0.94, 0.0, 0.0)))        # falta éxito
    assert not criterio.cumple(criterio.medias(_iteraciones(20, 0.97, 0.012, 0.0)))      # sobran choques
    assert not criterio.cumple(criterio.medias(_iteraciones(20, 0.97, 0.0, 0.006)))      # sobran caídas
    assert not criterio.cumple(criterio.medias(_iteraciones(19, 1.0)))                   # falta ventana


def test_la_media_movil_suma_episodios_y_solo_mira_la_ventana():
    filas = _iteraciones(30, 0.0) + _iteraciones(19, 1.0) + _iteraciones(1, 0.0, episodios=10)
    m = criterio.medias(filas)
    assert m["exito"] == pytest.approx(19000 / 19010)        # la iteración con 10 episodios casi no pesa
    asistidos = [{**f, "episodios_sin_ayuda": 0, "exitos_sin_ayuda": 0, "episodios_con_ayuda": 500} for f in _iteraciones(20, 0.0, 0.02)]
    assert criterio.medias(asistidos) == {"exito": 0.0, "choques": pytest.approx(0.04), "caidas": 0.0}


def test_el_criterio_tiene_que_sostenerse_veinte_iteraciones_seguidas():
    filas, racha, rachas = [], 0, []
    for fila in _iteraciones(45, 0.97) + _iteraciones(1, 0.0) + _iteraciones(25, 0.97):
        filas.append(fila)
        racha = criterio.racha(racha, criterio.medias(filas))
        rachas.append(racha)
    assert rachas[18] == 0 and rachas[19] == 1                # la ventana se llena en la iteración 20
    assert rachas[38] == criterio.RACHA                       # 20 ventanas seguidas: cumplido
    assert rachas[45] == 0                                    # una iteración en 0 % baja la media de 95 %: la racha parte de nuevo
    assert max(rachas[45:]) < criterio.RACHA


def test_despues_de_cumplir_sigue_mientras_la_curva_sube_y_para_en_la_meseta():
    mejor, desde = 0.0, 0
    for exito in (0.95, 0.96, 0.961, 0.97):                  # 0,961 no cuenta: sube menos de 0,2 puntos
        mejor, desde = criterio.sin_mejora(mejor, desde, exito)
    assert (mejor, desde) == (0.97, 0)
    for _ in range(criterio.PACIENCIA):
        assert not criterio.terminar(criterio.RACHA, desde)
        mejor, desde = criterio.sin_mejora(mejor, desde, 0.97)
    assert criterio.terminar(criterio.RACHA, desde)
    assert not criterio.terminar(criterio.RACHA - 1, desde)   # sin el criterio sostenido no para por meseta
