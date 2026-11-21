"""Entorno RL instalar_panel de VIAZ para Isaac Lab (docs/contrato-entorno-rl.md).

Módulos sin Isaac (con tests en backend/tests/test_entorno_rl.py): robot, cinematica, agarre, exito,
corrida, tarea y oraculo. Módulos que necesitan Isaac Lab (solo corren en el pod): robot_isaac, entorno,
comun y los 4 comandos: entrenar, evaluar, grabar_clip y validar_robot.
"""
ID_TAREA = "Viaz-Instalar-Panel-v0"


def registrar() -> None:
    """Registra la tarea en gymnasium. Llamar después de crear la app de Isaac."""
    import gymnasium as gym

    if ID_TAREA not in gym.registry:
        # order_enforce=False: los scripts reinician el entorno de Isaac Lab directo, sin pasar por gymnasium.
        gym.register(id=ID_TAREA, entry_point="rl.entorno:InstalarPanelEnv", disable_env_checker=True, order_enforce=False)
