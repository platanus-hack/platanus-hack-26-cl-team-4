"""Compara medidas_entorno.json contra el entorno.json real de un video sintético (fase 0 del agente Entorno).

    python sim/comparar_medidas.py --verdad DIR/entorno.json --medidas DIR/medidas_entorno.json [--salida DIR/comparacion.json]

Imprime una tabla por campo: real, medido, error real, error que la medición declaró y si cae en la tolerancia.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import medir_geometria as mg


def comparar(verdad: dict, medidas: dict) -> dict:
    filas = []
    for campo, m in medidas.get("campos", {}).items():
        a, b = campo.split(".")
        real = verdad[a][b]
        if isinstance(real, str) or isinstance(m["valor"], str):
            error, dentro = (0.0 if real == m["valor"] else 1.0), real == m["valor"]
        else:
            error = abs(float(m["valor"]) - float(real))
            dentro = error <= mg.TOLERANCIAS.get(campo, float("inf"))
        filas.append({"campo": campo, "real": real, "medido": m["valor"], "error_real": round(error, 3),
                      "error_declarado": m["error"], "confianza": m.get("confianza"),
                      "tolerancia": mg.TOLERANCIAS.get(campo), "dentro": bool(dentro)})
    medidos = [f for f in filas if f["campo"] != "terreno.pendiente_grados"]
    return {"campos": filas, "dentro": sum(f["dentro"] for f in medidos), "total": len(medidos),
            "fuente": medidas.get("fuente"), "frames": medidas.get("frames"), "avisos": medidas.get("avisos", [])}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--verdad", required=True, type=Path)
    ap.add_argument("--medidas", required=True, type=Path)
    ap.add_argument("--salida", type=Path)
    a = ap.parse_args()
    r = comparar(json.loads(a.verdad.read_text(encoding="utf-8")), json.loads(a.medidas.read_text(encoding="utf-8")))
    print(f"{'campo':32} {'real':>14} {'medido':>14} {'error':>8} {'± decl.':>8} {'tol.':>6}  ok")
    for f in r["campos"]:
        print(f"{f['campo']:32} {str(f['real']):>14} {str(f['medido']):>14} {f['error_real']:>8} "
              f"{f['error_declarado']:>8} {str(f['tolerancia']):>6}  {'sí' if f['dentro'] else 'NO'}")
    print(f"dentro de tolerancia: {r['dentro']} de {r['total']} (sin contar la pendiente) · fuente {r['fuente']}")
    if a.salida:
        a.salida.write_text(json.dumps(r, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
