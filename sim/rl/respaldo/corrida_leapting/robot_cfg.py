"""robot_cfg.py generado por VIAZ desde ensamblaje.json. No editar a mano.

PARAMETROS: interfaz estable con el entorno RL (docs/contrato-entorno-rl.md §7).
crear_articulacion_cfg(): SIN PROBAR EN ISAAC. Si no calza con su entorno, usen solo PARAMETROS.
"""

PARAMETROS = {'robot_id': 'leapting-mmr',
 'base': {'asset': 'base_movil_simple', 'altura_cubierta_m': 0.8},
 'brazo': {'asset': 'ur10', 'escala_alcance': 2.192, 'esfuerzo_max_nm': 3705},
 'efector': {'asset': 'ventosa_larga'},
 'alcance_m': 3.1,
 'carga_util_kg': 100.0,
 'velocidad_max_rad_s': 2.0,
 'articulaciones': ['shoulder_pan', 'shoulder_lift', 'elbow', 'wrist_1', 'wrist_2', 'wrist_3'],
 'articulaciones_asset': ['shoulder_pan_joint',
                          'shoulder_lift_joint',
                          'elbow_joint',
                          'wrist_1_joint',
                          'wrist_2_joint',
                          'wrist_3_joint'],
 'isaaclab_cfg': {'modulo': 'isaaclab_assets.robots.universal_robots', 'nombre': 'UR10_CFG'}}


def crear_articulacion_cfg():
    """ArticulationCfg de Isaac Lab desde el asset del brazo, escalado y con límites de esfuerzo nuevos."""
    import importlib

    ref = PARAMETROS["isaaclab_cfg"]
    base_cfg = getattr(importlib.import_module(ref["modulo"]), ref["nombre"])
    cfg = base_cfg.copy()
    s = PARAMETROS["brazo"]["escala_alcance"]
    cfg.spawn.scale = (s, s, s)
    for actuador in cfg.actuators.values():
        for nombre in ("effort_limit", "effort_limit_sim"):
            if hasattr(actuador, nombre):
                setattr(actuador, nombre, PARAMETROS["brazo"]["esfuerzo_max_nm"])
        for nombre in ("velocity_limit", "velocity_limit_sim"):
            if hasattr(actuador, nombre):
                setattr(actuador, nombre, PARAMETROS["velocidad_max_rad_s"])
    return cfg
