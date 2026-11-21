"""Copia local de modelos de Omniverse (USD + dependencias) para pods que no bajan bien desde S3.

    python espejo_assets.py --destino /workspace/isaac_assets Isaac/IsaacLab/Robots/Classic/Cartpole/cartpole.usd

Cada ruta relativa parte de RAIZ_REMOTA. Los archivos quedan en --destino con la misma ruta del servidor,
así basta con cambiar la raíz de assets de Isaac a <destino>/Assets/Isaac/5.1.
Los .mdl base (OmniPBR.mdl) no están en S3: vienen con Isaac Sim, y su FALLA se puede ignorar.
Necesita usd-core (pxr) en un Python aparte del de Isaac.
"""
import argparse
import subprocess
import urllib.parse
from pathlib import Path

from pxr import Sdf

RAIZ_REMOTA = "https://omniverse-content-production.s3-us-west-2.amazonaws.com/Assets/Isaac/5.1/"
EXT_USD = (".usd", ".usda", ".usdc")


def bajar(url: str, destino: Path) -> Path | None:
    p = destino / urllib.parse.urlparse(url).path.lstrip("/")
    if p.exists() and p.stat().st_size > 0:
        return p
    p.parent.mkdir(parents=True, exist_ok=True)
    r = subprocess.run(["curl", "-sfL", "--retry", "5", "--retry-connrefused", "-m", "600", "-o", str(p), url])
    if r.returncode != 0:
        p.unlink(missing_ok=True)
        print(f"FALLA {url}", flush=True)
        return None
    print(f"ok {p.stat().st_size:>10} {url}", flush=True)
    return p


def dependencias(capa: Sdf.Layer) -> set[str]:
    """Sublayers, referencias, payloads y atributos de tipo asset (texturas, materiales)."""
    deps = set(capa.GetCompositionAssetDependencies())

    def visitar(path: Sdf.Path) -> None:
        spec = capa.GetObjectAtPath(path)
        if not isinstance(spec, Sdf.AttributeSpec):
            return
        valor = spec.default
        valores = valor if isinstance(valor, Sdf.AssetPathArray) else [valor]
        deps.update(v.path for v in valores if isinstance(v, Sdf.AssetPath) and v.path)

    capa.Traverse(Sdf.Path.absoluteRootPath, visitar)
    return {d for d in deps if not d.startswith(("omniverse://", "anon:"))}


def espejar(semillas: list[str], destino: Path) -> None:
    pendientes = [s if s.startswith("http") else urllib.parse.urljoin(RAIZ_REMOTA, s) for s in semillas]
    vistos: set[str] = set()
    while pendientes:
        url = pendientes.pop()
        if url in vistos:
            continue
        vistos.add(url)
        p = bajar(url, destino)
        if p is None or not url.lower().endswith(EXT_USD):
            continue
        capa = Sdf.Layer.FindOrOpen(str(p))
        if capa is None:
            print(f"NO ABRE {p}", flush=True)
            continue
        pendientes += [urllib.parse.urljoin(url, d) for d in dependencias(capa)]
    print(f"listo: {len(vistos)} archivos revisados en {destino}", flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--destino", type=Path, default=Path("/workspace/isaac_assets"))
    ap.add_argument("semillas", nargs="+")
    a = ap.parse_args()
    espejar(a.semillas, a.destino)
