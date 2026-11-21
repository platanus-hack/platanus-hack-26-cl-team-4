"""Utilidades compartidas por los scripts de Isaac Sim. SIN PROBAR EN ISAAC: verificar en el pod.

Se importa DESPUÉS de crear SimulationApp (los módulos omni/isaacsim no existen antes).
Escrito para Isaac Sim 5.x; si la versión del pod cambia nombres de módulos, el error aparece aquí.
"""
from __future__ import annotations

from pathlib import Path


def abrir_escena(escena: Path):
    from isaacsim.core.utils.stage import open_stage

    if not open_stage(str(escena)):
        raise RuntimeError(f"no pude abrir {escena}")


def importar_urdf(urdf: Path, prim: str = "/World/robot") -> str:
    """Importa el clon. Base no fija: la movemos con set_world_pose en cada frame (base cinemática)."""
    import omni.kit.commands
    from isaacsim.core.utils.extensions import enable_extension

    enable_extension("isaacsim.asset.importer.urdf")
    _, cfg = omni.kit.commands.execute("URDFCreateImportConfig")
    cfg.merge_fixed_joints = False
    cfg.fix_base = False
    cfg.make_default_prim = False
    cfg.create_physics_scene = False
    ok, ruta = omni.kit.commands.execute("URDFParseAndImportFile", urdf_path=str(urdf), import_config=cfg,
                                         dest_path="", get_articulation_root=True)
    if not ok or not ruta:
        raise RuntimeError(f"falló la importación de {urdf}")
    return ruta
