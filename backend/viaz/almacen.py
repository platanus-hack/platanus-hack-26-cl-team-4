"""Almacén de archivos: disco local (desarrollo) o Cloudflare R2 (producción).

Claves: proyectos/<id>/videos/<archivo>, corridas/<id>/<archivo> y catalogo/encontrados/<id>.json
(fichas que trajo la búsqueda web, compartidas entre corridas).
Los archivos grandes no pasan por la API en producción: se suben y bajan con URLs firmadas.
"""
from __future__ import annotations

from pathlib import Path
from urllib.parse import quote

from .config import Config

VENCE_S = 24 * 3600


class Almacen:
    def leer(self, clave: str) -> bytes: ...
    def escribir(self, clave: str, datos: bytes, tipo: str = "application/octet-stream") -> None: ...
    def existe(self, clave: str) -> bool: ...
    def listar(self, prefijo: str) -> list[str]: ...
    def url_get(self, clave: str) -> str: ...
    def url_put(self, clave: str) -> str: ...


class AlmacenLocal(Almacen):
    """Archivos en disco. La API los sirve en /archivos/<clave> (GET y PUT). Solo para desarrollo."""

    def __init__(self, raiz: Path, url_publica: str):
        self.raiz = raiz.resolve()
        self.url = url_publica

    def ruta(self, clave: str) -> Path:
        p = (self.raiz / clave).resolve()
        if self.raiz not in p.parents:
            raise ValueError(f"clave fuera del almacén: {clave}")
        return p

    def leer(self, clave):
        return self.ruta(clave).read_bytes()

    def escribir(self, clave, datos, tipo="application/octet-stream"):
        p = self.ruta(clave)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(datos)

    def existe(self, clave):
        return self.ruta(clave).is_file()

    def listar(self, prefijo):
        """Claves de los archivos cuya clave empieza con `prefijo` (un prefijo que termina en / es una carpeta)."""
        carpeta = prefijo.rpartition("/")[0]
        base = self.ruta(carpeta) if carpeta else self.raiz
        if not base.is_dir():
            return []
        claves = (p.relative_to(self.raiz).as_posix() for p in base.rglob("*") if p.is_file())
        return sorted(c for c in claves if c.startswith(prefijo))

    def url_get(self, clave):
        return f"{self.url}/archivos/{quote(clave)}"

    def url_put(self, clave):
        return f"{self.url}/archivos/{quote(clave)}"


class AlmacenR2(Almacen):
    def __init__(self, cfg: Config):
        import boto3
        from botocore.config import Config as BotoConfig

        self.bucket = cfg.r2_bucket
        self.s3 = boto3.client(
            "s3", endpoint_url=cfg.r2_endpoint, region_name="auto",
            aws_access_key_id=cfg.r2_key_id, aws_secret_access_key=cfg.r2_secret,
            config=BotoConfig(signature_version="s3v4"),
        )

    def leer(self, clave):
        return self.s3.get_object(Bucket=self.bucket, Key=clave)["Body"].read()

    def escribir(self, clave, datos, tipo="application/octet-stream"):
        self.s3.put_object(Bucket=self.bucket, Key=clave, Body=datos, ContentType=tipo)

    def existe(self, clave):
        from botocore.exceptions import ClientError
        try:
            self.s3.head_object(Bucket=self.bucket, Key=clave)
            return True
        except ClientError:
            return False

    def listar(self, prefijo):
        paginas = self.s3.get_paginator("list_objects_v2").paginate(Bucket=self.bucket, Prefix=prefijo)
        return sorted(o["Key"] for p in paginas for o in p.get("Contents", []))

    def url_get(self, clave):
        return self.s3.generate_presigned_url("get_object", Params={"Bucket": self.bucket, "Key": clave}, ExpiresIn=VENCE_S)

    def url_put(self, clave):
        return self.s3.generate_presigned_url("put_object", Params={"Bucket": self.bucket, "Key": clave}, ExpiresIn=VENCE_S)


def crear(cfg: Config) -> Almacen:
    if cfg.almacen == "r2":
        return AlmacenR2(cfg)
    return AlmacenLocal(cfg.dir_local, cfg.url_publica)


def clave_corrida(corrida_id: str, archivo: str) -> str:
    return f"corridas/{corrida_id}/{archivo}"
