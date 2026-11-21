"""Agente monitor del entrenamiento (docs/agentes/monitor-entrenamiento.md).

- hitos(): iteración de primer éxito, 50 %, 90 % y mejor recompensa. Código, no LLM: los clips dependen de esto.
- chequear(): un chequeo con estado, evidencia y recomendación. Modo fijo = reglas; modo claude = Claude con el prompt.
- Avisos por Discord (VIAZ_DISCORD_WEBHOOK) con tope de 1 por tipo cada 30 min, salvo NaN (RF-MON-10).
"""
from __future__ import annotations

import json
import logging
import math
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

from .esquemas import esquema, sin_campos, validar

log = logging.getLogger("viaz.monitor")
META = 0.9
PRIMER_EXITO = 0.05   # éxito sostenido mínimo: evita que un acierto por azar marque el hito
VENTANA_MIN = 5
TOPE_AVISO_S = 30 * 60
EMOJI = {"divergiendo": "🔴", "nan": "🔴", "estancado": "🟡", "hito": "🟢", "fin": "🏁"}


def _num(v) -> float | None:
    return v if isinstance(v, (int, float)) and math.isfinite(v) else None


def _media(xs: list[float | None]) -> float | None:
    vals = [x for x in xs if x is not None]
    return sum(vals) / len(vals) if vals else None


def hitos(metricas: list[dict]) -> dict:
    h = {"version": 1, "primer_exito": None, "exito_50": None, "umbral_alcanzado": None, "mejor_recompensa": None,
         "mejor_tasa_exito": None, "ultima_iteracion": metricas[-1]["iteracion"] if metricas else 0}
    mejor_r = None
    for m in metricas:
        tasa, rec, it = _num(m.get("tasa_exito")), _num(m.get("recompensa_media")), m["iteracion"]
        if tasa is not None:
            if tasa >= PRIMER_EXITO and h["primer_exito"] is None:
                h["primer_exito"] = it
            if tasa >= 0.5 and h["exito_50"] is None:
                h["exito_50"] = it
            if tasa >= META and h["umbral_alcanzado"] is None:
                h["umbral_alcanzado"] = it
            if h["mejor_tasa_exito"] is None or tasa > h["mejor_tasa_exito"]:
                h["mejor_tasa_exito"] = round(tasa, 4)
        if rec is not None and (mejor_r is None or rec > mejor_r):
            mejor_r, h["mejor_recompensa"] = rec, it
    return h


def checkpoint_de(iteracion: int | None, ultima: int | None = None, cada: int = 50) -> str | None:
    """Checkpoint que contiene esa iteración: el siguiente múltiplo de `cada` (se guardan cada 50),
    sin pasarse de la última iteración (al detenerse, el entorno guarda un checkpoint ahí)."""
    if iteracion is None:
        return None
    it = math.ceil(iteracion / cada) * cada
    return f"model_{min(it, ultima) if ultima is not None else it}.pt"


def _mejor_iteracion(metricas: list[dict]) -> int | None:
    con_tasa = [m for m in metricas if _num(m.get("tasa_exito")) is not None]
    return max(con_tasa, key=lambda m: (m["tasa_exito"], m["iteracion"]))["iteracion"] if con_tasa else None


def chequeo_reglas(nuevas: list[dict], todas: list[dict], previos: list[dict], horas_max: float,
                   hitos_antes: dict | None = None) -> dict:
    """Chequeo determinista (modo fijo y respaldo si Claude falla). Mismas reglas que el prompt."""
    ahora = datetime.now(timezone.utc).isoformat(timespec="seconds")
    ventana = nuevas if len(nuevas) >= VENTANA_MIN else todas[-max(VENTANA_MIN, 20):]
    ultima = todas[-1] if todas else {}
    usado_h = round(float(ultima.get("tiempo_s") or 0) / 3600, 2)
    base = {"version": 1, "t": ahora, "iteracion": int(ultima.get("iteracion", 0)),
            "evidencia": {"recompensa_media": _num(ultima.get("recompensa_media")), "tasa_exito": _num(ultima.get("tasa_exito")),
                          "tendencia_recompensa": None, "tiempo_usado_h": usado_h,
                          "tiempo_restante_h": round(max(0.0, horas_max - usado_h), 2)},
            "hito": None, "checkpoint_recomendado": checkpoint_de(_mejor_iteracion(todas), ultima.get("iteracion"))}
    if not nuevas:
        return {**base, "estado": "estancado", "recomendacion": "revisar",
                "detalle": "No llegaron métricas nuevas desde el último chequeo: revisen si el pod sigue vivo."}
    if any(m.get("nan") or any(isinstance(v, float) and not math.isfinite(v) for v in m.values()) for m in nuevas):
        return {**base, "estado": "divergiendo", "recomendacion": "detener",
                "detalle": "Apareció NaN en las métricas: el sistema detiene el entrenamiento y guarda un checkpoint."}
    cuarto = max(1, len(ventana) // 4)
    r0 = _media([_num(m.get("recompensa_media")) for m in ventana[:cuarto]])
    r1 = _media([_num(m.get("recompensa_media")) for m in ventana[-cuarto:]])
    t0 = _media([_num(m.get("tasa_exito")) for m in ventana[:cuarto]]) or 0.0
    t1 = _media([_num(m.get("tasa_exito")) for m in ventana[-cuarto:]]) or 0.0
    tend = round((r1 - r0) / abs(r0), 3) if r0 not in (None, 0) and r1 is not None else None
    base["evidencia"]["tendencia_recompensa"] = tend
    tasa = base["evidencia"]["tasa_exito"] or 0.0
    seguidos_90 = sum(1 for _ in _cola(previos, lambda c: (c["evidencia"].get("tasa_exito") or 0) >= META))
    if (tasa >= META and seguidos_90 >= 2) or usado_h >= horas_max:
        estado, rec = "terminado", "detener"
        detalle = (f"Éxito {tasa:.0%} sobre la meta de 90 % en 3 chequeos seguidos." if usado_h < horas_max
                   else f"Se acabó el tiempo ({usado_h} h de {horas_max} h). Mejor éxito: {max(tasa, t1):.0%}.")
    elif tend is not None and tend < -0.2:
        estado, rec = "divergiendo", "detener" if previos and previos[-1]["estado"] == "divergiendo" else "revisar"
        detalle = f"La recompensa cayó {abs(tend):.0%} en la ventana ({r0:.1f} → {r1:.1f}). Éxito: {t0:.0%} → {t1:.0%}."
    elif (tend is None or abs(tend) < 0.02) and abs(t1 - t0) < 0.02 and tasa < META:
        estancados = sum(1 for _ in _cola(previos, lambda c: c["estado"] == "estancado"))
        estado, rec = "estancado", "ajustar" if estancados >= 2 else "seguir"
        detalle = (f"Éxito plano en {tasa:.0%} ({estancados + 1} chequeo(s) seguido(s)). "
                   + ("Propongo bajar la tasa de aprendizaje a la mitad o volver al mejor checkpoint." if rec == "ajustar" else ""))
    else:
        estado, rec = "mejorando", "seguir"
        detalle = f"El éxito pasó de {t0:.0%} a {t1:.0%}" + (f" y la recompensa {tend:+.0%}." if tend is not None else ".")
    if estado == "mejorando" and usado_h >= 1 and t1 > t0:
        ritmo = (t1 - t0) / max(1e-6, (float(ventana[-1].get("tiempo_s") or 0) - float(ventana[0].get("tiempo_s") or 0)) / 3600)
        if ritmo > 0:
            falta_h = (META - tasa) / ritmo
            detalle += (f" Al ritmo actual, 90 % llega en ~{falta_h:.1f} h: dentro del tiempo." if falta_h <= base["evidencia"]["tiempo_restante_h"]
                        else f" Al ritmo actual, 90 % llega en ~{falta_h:.1f} h: NO alcanza en las {base['evidencia']['tiempo_restante_h']} h restantes.")
    h_ahora, h_antes = hitos(todas), hitos_antes or {}
    for nombre in ("umbral_alcanzado", "exito_50", "primer_exito", "mejor_recompensa"):
        if h_ahora.get(nombre) is not None and h_antes.get(nombre) is None:
            base["hito"] = nombre
            break
    if estado == "terminado":
        base["hito"] = "fin"
    return validar("monitoreo", {**base, "estado": estado, "recomendacion": rec, "detalle": detalle})


def _cola(previos: list[dict], cond):
    """Chequeos consecutivos al final de `previos` que cumplen `cond`."""
    for c in reversed(previos):
        if not cond(c):
            return
        yield c


def esquema_agente() -> dict:
    esq = sin_campos(esquema("monitoreo"), ["version", "t"])
    esq["properties"]["hito"] = {"enum": ["ninguno", "primer_exito", "exito_50", "mejor_recompensa", "umbral_alcanzado", "fin"]}
    esq["properties"]["checkpoint_recomendado"] = {"type": "string", "description": "Nombre del checkpoint o 'ninguno'"}
    return esq


def chequear(modo: str, modelo: str, nuevas: list[dict], todas: list[dict], previos: list[dict], horas_max: float,
             hitos_antes: dict | None = None) -> dict:
    """Un chequeo. En modo claude, si Claude falla, usa las reglas: el monitor nunca frena el entrenamiento."""
    reglas = chequeo_reglas(nuevas, todas, previos, horas_max, hitos_antes)
    if modo != "claude" or reglas["estado"] == "divergiendo" and "NaN" in reglas["detalle"]:
        return reglas
    try:
        from .agentes.base import pedir_json
        from .agentes import _prompt
        texto = (f"Meta: 90 % de éxito a 5 cm y 5°. Tiempo máximo: {horas_max} h.\n"
                 f"Métricas nuevas ({len(nuevas)} iteraciones):\n{json.dumps(nuevas[-200:], ensure_ascii=False)}\n\n"
                 f"Chequeos anteriores:\n{json.dumps(previos[-5:], ensure_ascii=False)}\n\n"
                 f"Hitos calculados por el sistema: {json.dumps(hitos(todas), ensure_ascii=False)}\n"
                 f"Chequeo por reglas (referencia): {json.dumps(reglas, ensure_ascii=False)}")
        r = pedir_json(modelo=modelo, sistema=_prompt("monitor"), esquema=esquema_agente(),
                       contenido=[{"type": "text", "text": texto}], effort="medium")
        r["hito"] = None if r["hito"] == "ninguno" else r["hito"]
        r["checkpoint_recomendado"] = None if r["checkpoint_recomendado"] in ("", "ninguno") else r["checkpoint_recomendado"]
        # La evidencia numérica sale de las métricas, no del modelo (contrato §4.2).
        return validar("monitoreo", {**r, "version": 1, "t": reglas["t"], "iteracion": reglas["iteracion"],
                                     "evidencia": reglas["evidencia"]})
    except Exception as e:  # noqa: BLE001
        log.warning("el monitor con Claude falló, uso reglas: %s", e)
        return reglas


# ---------- avisos por Discord ----------

@dataclass
class Avisador:
    webhook: str
    ultimo: dict[str, float] = field(default_factory=dict)
    enviados: list[str] = field(default_factory=list)  # para tests y registro

    def tipo_de(self, c: dict) -> str | None:
        if c["estado"] == "divergiendo":
            return "nan" if "NaN" in c["detalle"] else "divergiendo"
        if c["estado"] == "estancado" and c["recomendacion"] == "ajustar":
            return "estancado"
        if c["hito"] == "fin" or c["estado"] == "terminado":
            return "fin"
        if c["hito"] in ("primer_exito", "exito_50", "umbral_alcanzado"):
            return "hito"
        return None

    def mensaje(self, c: dict, horas_max: float) -> str:
        tipo = self.tipo_de(c) or "hito"
        e = c["evidencia"]
        titulo = {"hito": f"HITO: {c['hito']}", "fin": "FIN DEL ENTRENAMIENTO"}.get(tipo, c["estado"].upper())
        lineas = [f"{EMOJI[tipo]} VIAZ · entrenamiento instalar_panel · {titulo}",
                  f"Iteración {c['iteracion']} · {e['tiempo_usado_h']} h de {horas_max} h"]
        if e["recompensa_media"] is not None:
            lineas.append(f"Recompensa media: {e['recompensa_media']:.1f}"
                          + (f" ({e['tendencia_recompensa']:+.0%} en la ventana)" if e["tendencia_recompensa"] is not None else ""))
        if e["tasa_exito"] is not None:
            lineas.append(f"Tasa de éxito (5 cm, 5°): {e['tasa_exito']:.0%}")
        lineas.append(c["detalle"])
        if c["recomendacion"] in ("ajustar", "detener") and tipo != "nan":
            lineas.append(f"Recomendación: {c['recomendacion']}"
                          + (f" · checkpoint {c['checkpoint_recomendado']}" if c["checkpoint_recomendado"] else ""))
            lineas.append("Responde en el canal antes de aplicar el cambio.")
        return "\n".join(lineas)

    def avisar(self, c: dict, horas_max: float) -> bool:
        tipo = self.tipo_de(c)
        if tipo is None:
            return False
        ahora = time.monotonic()
        if tipo not in ("nan", "fin") and ahora - self.ultimo.get(tipo, -1e9) < TOPE_AVISO_S:
            return False
        texto = self.mensaje(c, horas_max)
        self.ultimo[tipo] = ahora
        self.enviados.append(texto)
        if not self.webhook:
            log.info("aviso (sin VIAZ_DISCORD_WEBHOOK):\n%s", texto)
            return True
        import requests
        for _ in range(2):  # un reintento (contrato §6)
            try:
                requests.post(self.webhook, json={"content": texto[:1900]}, timeout=10).raise_for_status()
                return True
            except requests.RequestException as e:
                log.warning("Discord no respondió: %s", e)
        return False
