# Investigación: GPU y proveedor para Isaac Lab (demo VIAZ)

> Fecha: 2026-11-21, consultas entre 05:30 y 06:10 UTC. Revisado contra [`requerimientos.md`](requerimientos.md) v0.6.
> Etiquetas: **[medido]** = alguien lo corrió (con fuente), **[proveedor]** = lo dice NVIDIA o el proveedor, **[inferido]** = conclusión mía a partir de las fuentes.
> Las consultas a las API de RunPod y Vast.ai las corrí yo hoy. Los resultados son una foto del inventario: cambian cada hora.

## 0. Resumen en 6 líneas

1. **El bloqueo real no es la 5090, es el driver.** Isaac Sim 5.1 se cae con el driver 595 en todas las GPU RTX, no solo en Blackwell [proveedor].
2. **Hoy RunPod Secure Cloud solo tiene hosts con CUDA 13.2 (driver 595).** Con un pod de RunPod no puedes cambiar el driver. Isaac Sim 5.1 no es viable ahí hoy [medido por mí + inferido].
3. **Vast.ai sí deja filtrar por driver** y hoy tiene RTX 5090 y RTX PRO 6000 con driver 580 [medido por mí].
4. **Elección:** Vast.ai, **RTX PRO 6000 Blackwell (96 GB) con driver 580**, ~US$1,5/h. **Respaldo:** Vast.ai **RTX 5090 con driver 580**, US$0,49–0,76/h.
5. **Grabar clips con `--video` durante el entrenamiento cuesta caro:** el renderizado queda prendido todo el tiempo (~10× más lento por iteración en un reporte). Conviene grabar los clips reproduciendo checkpoints.
6. **Costo total estimado: 8–10 h de GPU activa (US$12–15), o ~21 h si el pod queda prendido de CP1 al freeze (~US$32)** con la PRO 6000. Las 4 h de entrenamiento alcanzan en cómputo; el riesgo es diseñar la recompensa, no la GPU.

## 1. Compatibilidad de GPU

### 1.1 Qué dice NVIDIA para Isaac Sim 5.1

| Nivel | GPU | VRAM | Driver Linux probado |
|---|---|---|---|
| Mínimo | GeForce RTX 4080 | 16 GB | 580.65.06 |
| Bueno | GeForce RTX 5080 | 16 GB | 580.65.06 |
| Ideal | RTX PRO 6000 Blackwell | 48 GB | 580.65.06 |

- La misma página dice: "GPUs without RT Cores (A100, H100) are not supported" [proveedor] (fuente 1).
- Isaac Sim 6.x pide el driver **595.58.03** y marca Ubuntu 22.04 como obsoleto [proveedor] (fuente 2).
- Isaac Lab 2.3.0 se construye sobre Isaac Sim 5.1 [proveedor] (fuente 3). Isaac Sim 5.0 ya trajo PyTorch `2.7.0+cu128` con soporte Blackwell [proveedor] (fuente 3).

### 1.2 El driver 595 rompe Isaac Sim 5.1 en todas las RTX

- Un ingeniero de NVIDIA lo confirma: el driver 595.x "is not validated for Isaac Sim 5.1.0" y causa caídas en `librtx.scenedb.plugin.so` al iniciar el renderer. Lo vieron en RTX 4070, 4090, 5070 Ti, 5080 y 5090, en Windows y Linux [proveedor] (fuentes 4 y 5).
- **Esto contradice una premisa del equipo.** `infraestructura.md` dice "evitar la rama 595 con Isaac Sim 5.1: hay caídas reportadas en Blackwell". La caída no es solo de Blackwell: también ocurre en Ada (RTX 4090) [proveedor].
- Un usuario con RTX 4090 y driver 570 reportó que la caída desaparece [medido] (fuente 6). Otro, en Windows, lo resolvió con 581.15 [medido] (fuente 5).
- Un repositorio probó `SimulationApp({"headless": True})` con Isaac Sim 5.1 y driver 610. Resultado: SIGSEGV al iniciar [medido] (fuente 7). **El modo headless no evita el problema del driver.**

### 1.3 La afirmación "Isaac Sim no corre en A100/H100"

| Uso | H100 / A100 | Etiqueta |
|---|---|---|
| Entrenamiento RL headless, política por estado, sin cámaras | **Funciona** en H100. PhysX corre en CUDA; los errores rojos de Vulkan al inicio no importan | [medido] H100 (fuente 8). A100: no probado por ellos |
| Cámaras, `TiledCamera`, `--video`, viewport | **No funciona** | [medido] H100: `ERROR_DEVICE_LOST` con cámaras (fuente 9). A100: caída en `createDLSSContext` (fuente 10) |
| URDF → USD | Falla en algunos servidores | [medido] (fuente 8) |
| Soporte oficial | Ninguno | [proveedor] (fuentes 1 y 9) |

- **Conclusión:** la frase del equipo es falsa para el entrenamiento solo, pero cierta para VIAZ. RF-INT-13 y RF-INT-15 piden video renderizado por Isaac. Por eso necesitas una GPU RTX [inferido].
- Si los videos salieran de una reproducción de poses (viser o MuJoCo), una H100 bastaría. Ese camino cambia el producto. No lo recomiendo para este hackatón [inferido].

### 1.4 GPU candidatas con las versiones fijadas (Isaac Sim 5.1 + Isaac Lab 2.3 + driver 580)

| GPU | Arquitectura | VRAM | ¿Sirve con 5.1? | Riesgos conocidos |
|---|---|---|---|---|
| RTX 4090 | Ada | 24 GB | Sí. Hay benchmarks oficiales de Isaac Lab en 4090 [proveedor] (fuente 11) | 24 GB limita entornos con cámaras. Benchmarks medidos con Ryzen 7950X |
| L40S | Ada | 48 GB | Sí. NVIDIA probó Isaac Sim en L40S de AWS vía Brev [proveedor] (fuente 12) | Ninguno grave. El L40 rinde menos que la 4090 por CPU de servidor [medido] (fuente 11) |
| RTX 6000 Ada | Ada | 48 GB | Sí [inferido: misma arquitectura que L40S] | Sin reportes propios encontrados |
| RTX A6000 | Ampere | 48 GB | Probable. Está bajo el mínimo (RTX 4080) pero tiene núcleos RT [inferido] | Isaac Lab Arena reporta 6 h de Franka lift en A6000 [proveedor] (fuente 13) |
| L4 | Ada | 24 GB | Funciona, pero lento. En un test de cámara rindió la mitad que una 4090 [medido] (fuente 14) | Bajo el mínimo de 16 GB de rendimiento; CPU débil en las instancias |
| RTX PRO 6000 Blackwell | Blackwell sm_120 | 96 GB | Sí. Es el nivel "Ideal" de 5.1 [proveedor] (fuente 1). Isaac Sim 5.1 + Isaac Lab 2.3.1 entrenando en AWS g7e con driver 580.159.03 [medido] (fuente 15) | Blackwell: PhysX puede caer a CPU (error CUDA 719) según el driver [medido] (fuente 15) |
| RTX 5090 | Blackwell sm_120 | 32 GB | Sí, con driver 580. `TiledCamera` funciona en 5090 de escritorio (GB202) y se cuelga en la de notebook (GB203) [medido] (fuente 16) | Los mismos riesgos Blackwell |

- **Blackwell con 5.1:** funciona con driver 580 y PyTorch `cu128`. No necesitas Isaac Sim 6.x [medido] (fuentes 15 y 16). Instala PyTorch con `isaaclab.sh --install`, no a mano: el wheel por defecto es `cu126` y no trae sm_120 [medido] (fuente 15).
- **Ada es la opción más madura** para 5.1. Hoy no hay Ada con driver 580 en los proveedores revisados (ver §2) [medido por mí].

## 2. Proveedores

### 2.1 RunPod (medido por mí, 06:03 UTC)

Consulté la API GraphQL pública de RunPod (`lowestPrice` por tipo de GPU, Secure Cloud, con y sin filtro `allowedCudaVersions`).

| GPU | Precio Secure | Stock | Stock con CUDA 13.0 (driver 580) | Stock con CUDA 13.2 (driver 595) |
|---|---|---|---|---|
| RTX 5090 | — | **ninguno** | ninguno | ninguno |
| RTX 4090 | US$0,89/h | High | **ninguno** | High |
| L40S | US$1,09/h | Low | **ninguno** | Low |
| RTX 6000 Ada | US$1,09/h | Low | **ninguno** | ninguno |
| L4 | US$0,69/h | Low | **ninguno** | Low |
| A40 | US$0,59/h | High | **ninguno** | High |
| RTX PRO 6000 | US$2,69/h | High | **ninguno** | High |
| RTX A6000 | — | ninguno | ninguno | ninguno |

- Probé también CUDA 12.4, 12.6, 12.8, 12.9, 13.1, 13.3, 13.4 y 14.0. Ninguna devolvió stock. **Todo el stock Secure de hoy está en hosts CUDA 13.2, o sea driver R595** [medido por mí]. La relación CUDA 13.0 = R580, 13.1 = R590, 13.2 = R595 es de NVIDIA [proveedor] (fuente 17).
- La consulta de Community Cloud devolvió vacío para todo. No pude ver su stock (ver "Qué no pude verificar").
- Precios de lista: 5090 US$1,39 Secure / desde US$0,69 Community; 4090 US$0,89 / 0,34; L40S US$1,09 / 0,79 [proveedor] (fuente 18). La página no muestra precios spot [proveedor] (fuente 18).
- **El pod es el contenedor.** No hay docker dentro del pod. Puedes usar `nvcr.io/nvidia/isaac-sim:x` como imagen del pod. Alguien lo hizo con Isaac Sim 6.1 en una 4090, driver 595.91: 12 s de arranque con la imagen ya en el host, 4 min 30 s de prueba completa, ~US$0,07 [medido] (fuente 14).
- **El host fija el driver.** Se filtra con `allowedCudaVersions` (coincidencia exacta) o `minCudaVersion` al crear el pod [proveedor] (fuente 19). No se puede bajar el driver.
- **Fallas conocidas:** sin UDP en la mayoría de los datacenters. Por eso WebRTC no funciona [medido] (fuente 14), y la imagen `isaac-lab:2.0.2` dejó `/workspace/isaaclab` vacío [medido] (fuente 20). La imagen de Isaac Sim no trae servidor SSH [medido] (fuente 14).
- **Persistencia:** network volume o volumen del pod en `/workspace` [proveedor] (fuente 20, pasos del reporte).
- **Veredicto:** con Isaac Sim 5.1, RunPod no sirve hoy. Sirve para el plan B 6.x (ver §2.6) [inferido].

### 2.2 Vast.ai (medido por mí, 06:05 UTC)

Consulté `console.vast.ai/api/v0/bundles` (on-demand, verificadas, 1 GPU). La consulta devolvió 64 ofertas.

| GPU | Driver | Ofertas | Precio mínimo | Detalle |
|---|---|---|---|---|
| RTX 5090 | **580** (580.178.04 / 580.119.02) | 9 | **US$0,49/h** | La mayoría con 30 GB de RAM. Una en California: 48 CPU, 108 GB RAM, 1,4 TB disco, 12 Gbps, **US$0,62/h** |
| RTX PRO 6000 S (servidor) | **580** (580.173.02 / 580.178.04) | 4 | **US$1,49/h** | 36–48 CPU, 125–176 GB RAM. Ojo: dos ofertas tienen 22–35 GB de disco |
| RTX 5090 | 595 / 610 / 615 | 14 | US$0,61/h | No sirven para 5.1 |
| RTX 4090 | 535–615 | 11 | US$0,35/h | **Ninguna con 580.** Hay una con 570 a US$0,46/h |
| RTX PRO 6000 WS | 595–620 | 13 | US$1,40/h | Ninguna con 580 |
| RTX 6000 Ada | 595 / 610 | 2 | US$0,39/h | Ninguna con 580 |

- **Filtro de driver:** existe el campo `driver_version` y `cuda_vers` en la búsqueda [proveedor] (fuente 21).
- **Contenedor o VM:** las instancias normales son contenedores Docker. También hay VM con KVM (`vms_enabled=true`), pero son menos máquinas y arrancan más lento [proveedor] (fuente 22). En mi foto, ninguna oferta con driver 580 era VM [medido por mí].
- **Vulkan en el contenedor:** hay que poner `-e NVIDIA_DRIVER_CAPABILITIES=compute,utility,graphics` en las "Docker create options" del template. Exportarlo después no sirve [medido por terceros] (fuente 23).
- **Fallas conocidas:** el NAT de Vast cambia los puertos, así que el livestream WebRTC no funciona. noVNC sí funcionó para un usuario [proveedor + medido] (fuente 24). Ya hubo una 5090 en Vast con driver 580.95.05 corriendo Isaac Sim 5.0 [medido] (fuente 24).
- **Persistencia:** el disco de la instancia se conserva al detenerla. Al reanudar, la GPU puede estar ocupada [inferido, no verificado en docs].

### 2.3 NVIDIA Brev

- Agrega ~30 nubes (AWS, Crusoe, Lambda, Nebius, MassedCompute vía Shadeform y otras) [medido por terceros] (fuente 25).
- L40S desde **US$1,06/h** (MassedCompute) hasta US$9,09/h; AWS g6e.2xlarge a US$2,69/h [proveedor] (fuente 26).
- Modo VM con Ubuntu 22.04, Docker y CUDA preinstalados, o modo contenedor [proveedor] (fuente 27).
- NVIDIA probó su launchable de Isaac Lab en **L40S de AWS**. En Crusoe falló el streaming. Costo citado del launchable: US$3,61/h [proveedor] (fuente 28). La guía de Isaac Sim para Brev recomienda 1× L40S [proveedor] (fuente 12).
- **Ventaja:** en VM puedes instalar el driver 580 tú mismo [inferido].
- **Riesgo:** no sé qué driver trae cada VM (ver "Qué no pude verificar").

### 2.4 Lambda

- 1 GPU: A6000 48 GB a US$1,09/h, A10 24 GB a US$1,29/h, Quadro RTX 6000 a US$0,69/h. No ofrece L40S, RTX 6000 Ada ni RTX PRO 6000 [proveedor] (fuente 29).
- Son VM: el driver se puede cambiar [inferido]. La A6000 queda bajo el mínimo de NVIDIA [inferido].

### 2.5 AWS g6e y GCP g2

| Instancia | GPU | Precio on-demand | Spot | Fuente |
|---|---|---|---|---|
| AWS g6e.xlarge (4 vCPU, 32 GB) | L40S | US$1,86/h (us-east-1) | US$1,58/h | [proveedor] fuente 30 |
| AWS g6e.2xlarge (8 vCPU, 64 GB) | L40S | US$2,24/h | US$1,08–2,04/h según región | [proveedor] fuente 31 |
| GCP g2-standard-4 | L4 | US$0,70/h | US$0,37–0,42/h | [proveedor] fuente 32 |

- Ambas son VM. Tú instalas el driver 580 y el NVIDIA Container Toolkit [inferido].
- **GCP:** la imagen de GPU trae un driver solo de cómputo. Las cámaras salieron en blanco hasta instalar las librerías de gráficos. Además hace falta `--runtime=nvidia` y `NVIDIA_DRIVER_CAPABILITIES=all`. El primer render con un driver nuevo tardó ~10 min compilando shaders [medido] (fuente 14).
- **AWS:** las cuentas nuevas suelen tener cuota 0 para instancias G. Pedirla puede tardar [inferido, no verificado].
- AWS g7e (RTX PRO 6000 Server) corre 5.1 + Isaac Lab 2.3.1 con driver 580.159.03 [medido] (fuente 15). No busqué su precio.

### 2.6 Plan B del equipo: Isaac Sim 6.x con driver 595

- Isaac Sim 6.1 corresponde a Isaac Lab 3.0.0-EA, y 6.2 a Isaac Lab 3.0.0-GA [proveedor] (fuente 33). Isaac Lab 3.0 apunta a Isaac Sim 6.2, Python 3.12 y PyTorch con CUDA 13.0 [proveedor] (fuente 34).
- **No es un cambio de versión, es una migración.** Isaac Lab 3.0 cambia los cuaterniones de WXYZ a XYZW. Además los `.data.*` devuelven `ProxyArray`, los `train.py` por librería desaparecen y `RecordVideo` se reemplaza por `VideoRecorderCfg` [proveedor] (fuentes 34 y 35).
- **El repo ya usa APIs 2.x:** `sim/prueba_fisica.py` usa cuaterniones WXYZ. `sim/plan.py` escribe `quat: [1,0,0,0]`. `sim/isaac_comun.py` importa `isaacsim.core.utils`, que Isaac Sim 6.0 marca como obsoleto [medido por mí en el repo; proveedor] (fuente 35).
- **Veredicto:** el plan B cuesta horas de migración en pleno hackatón. Es mejor buscar un host con driver 580 [inferido].

## 3. Elección

| | Proveedor | GPU | Precio | Por qué |
|---|---|---|---|---|
| **Principal** | Vast.ai, filtro `driver_version` 580.x, `disk_space>=200`, `cpu_ram>=64` | **RTX PRO 6000 Blackwell (S), 96 GB** | ~US$1,49–1,58/h | Es la GPU "Ideal" de NVIDIA para 5.1. Hay un reporte de 5.1 + Isaac Lab 2.3.1 entrenando en esta GPU con driver 580. 96 GB dejan espacio para cámaras, Claude Code y el MCP en el mismo pod. Hosts con 125–176 GB de RAM |
| **Respaldo** | Vast.ai, mismo filtro | **RTX 5090, 32 GB** | US$0,49–0,76/h (US$0,62 la de 108 GB RAM) | Es la GPU que el equipo pidió. Existe hoy con driver 580. La mayoría trae 30 GB de RAM: elige la de ≥64 GB |
| **Si Vast falla** | Brev en modo VM (L40S de AWS u otra) o AWS g6e.2xlarge | L40S, 48 GB | US$1,06–2,69/h | Ada es lo más maduro. En VM tú instalas el driver 580 |
| **Último recurso** | RunPod Secure | RTX 4090 o L40S | US$0,89 / 1,09/h | Funciona con Isaac Sim 6.x + driver 595 (medido en 6.1). Exige migrar a Isaac Lab 3.0 |

Detalles para el pod principal [inferido, salvo donde se cita]:

1. **Revisa el driver antes de pagar horas:** `nvidia-smi` debe mostrar 580.x y CUDA 13.0.
2. **Revisa Vulkan:** `vulkaninfo --summary` debe ver la GPU. Si no, recrea la instancia con `graphics` en `NVIDIA_DRIVER_CAPABILITIES` (fuente 23).
3. **Imagen:** `nvcr.io/nvidia/isaac-sim:5.1.0` corre como usuario 1234 sin root (fuente 36). Si el SSH de Vast choca con eso, usa una imagen base de CUDA y `pip install 'isaacsim[all,extscache]==5.1.0'`, como en la fuente 15.
4. **Prueba PhysX en GPU:** en Blackwell, confirma que no hay error 719 ni caída a CPU. La prueba de la fuente 15 es `Isaac-Ant-v0`, 20 iteraciones, ≥300 000 pasos/s.
5. **Sin livestream:** para mirar la escena usa noVNC o videos grabados. WebRTC no pasa por el NAT de Vast (fuente 24).
6. **Guarda la caché de shaders** en el disco de la instancia. Si cambias de host, la pagas de nuevo.

## 4. Tiempos reales

| Paso | Número | Etiqueta y fuente |
|---|---|---|
| Tamaño de `isaac-sim:5.1.0` | 15,1 GB (`docker images`, ingeniero NVIDIA); 14,0 GB en otro reporte; "~23 GB" en otro | [proveedor] fuente 37; [medido] fuentes 7 y 38 |
| Descarga de la imagen | No encontré una medición. A 500 Mbps son ~4 min; los hosts de Vast vistos tenían 370 Mbps–65 Gbps | [inferido] |
| Arranque con la imagen ya en el host | 12 s (RunPod, 6.1) | [medido] fuente 14 |
| Primer arranque (con instalación de shaders) | **263 s** en `SimulationApp` standalone; 31,5 s el async | [proveedor] fuente 39 |
| Arranque con shaders en caché | 4,4 s standalone; 6,3 s async | [proveedor] fuente 39 |
| Primer render con driver nuevo | ~10 min compilando shaders (GCP) | [medido] fuente 14 |
| Primer ejemplo de Isaac Lab | "de varios minutos a más de 10" la primera vez | [medido] fuente 15 |
| Franka lift, 4096 entornos, 1500 iteraciones | **12–13 min** en RTX PRO 4000 Blackwell | [medido] fuente 40 |
| Franka lift (log de 2024) | 0,42 s por iteración, 234 626 pasos/s → ~10,5 min para 1500 iteraciones | [medido] fuente 41 |
| Franka lift, 4096 entornos, 1500 iteraciones | 4090, 3 semillas por experimento; tiempo no publicado | [medido] fuente 42 |
| Franka lift (Isaac Lab Arena) | ~6 h, 12 000 iteraciones, 512 entornos, A6000 | [proveedor] fuente 13 |
| Franka reach | ~10 min en DGX Spark | [proveedor] fuente 43 |
| Pick con ventosa, robot propio, 4096 entornos | ~5 h y ~US$17 en AWS g6 (L4) | [medido] fuente 14b |
| Franka cabinet (estado) | 1 GPU 5090 ≈ 2 GPU RTX PRO 6000 de servidor, por la CPU de un solo núcleo | [medido] fuente 44 |
| Caída de rendimiento con cámaras | Cartpole en 4090: 510 000 FPS (estado, 4096 entornos) vs 32 000 FPS (RGB, 1024 entornos), ~16× menos. VRAM: 3,3 GB vs 16,7 GB | [proveedor] fuente 11 |
| Caída con `--video` en entrenamiento | ~10 s por iteración vs ~1 s sin video (Isaac Lab develop, Isaac Sim 6.0, Newton). Grabar "equivale a prender el renderizado durante el entrenamiento" | [medido] fuente 45; [proveedor] fuente 46 |
| Render de cámara | 34,8 fps estéreo 480×288 en 4090 (RunPod) | [medido] fuente 14 |
| Render de un video corto | No encontré una medición. Con ~30 fps de render, 60 s de video a 30 fps son ~1 min, más ~1–5 min de arranque | [inferido] |

**Lectura de los números** [inferido]:

- Franka lift usa ~150 M pasos (1500 × 24 pasos × 4096). A 200 000 pasos/s eso es ~12 min. Coincide con los 12–13 min medidos.
- El éxito no está garantizado. Con las mismas 1500 iteraciones, una configuración aprendió a levantar y otra no (fuente 40). Un empuje de cubo hecho desde cero llegó a 23 % de éxito (fuente 42).

## 5. Horas de GPU del plan actual

Supuestos [inferido]: PRO 6000 en Vast a US$1,55/h; 5090 a US$0,62/h. Los clips se graban reproduciendo checkpoints, no con `--video` durante todo el entrenamiento.

| Fase | GPU activa | Cómo sale el número |
|---|---|---|
| Prueba de humo (driver, Vulkan, Isaac Sim, Ant/Cartpole, cuRobo, video a R2) | 1,0 h | Descarga ~5 min + primer arranque ~5 min + Isaac Lab ~10 min + depuración del template |
| Validación del constructor (`generar_escena`, `validar_clon`, ida y vuelta de desarrollo) | 1,5–2 h | Cada corrida arranca en ~5 s con caché, más la escena; muchas corridas cortas |
| Ajuste de la recompensa (`instalar_panel`) | 2–3 h | 4–6 corridas de 20–30 min. Es tarea más difícil que Franka lift: panel de 32 kg, apoyo con tolerancia de 5 cm y 5° |
| Entrenamiento final | 1–1,5 h | Una corrida 4–6× más larga que Franka lift |
| Clips de entrenamiento (`entrenamiento_rapido.mp4`) | 0,15 h | 4 checkpoints (inicio, `primer_exito`, `exito_50`, `umbral_alcanzado`) × 1–2 min de render cada uno |
| Evaluación (100 episodios, RF-INT-14) | 0,1 h | 100 episodios en paralelo: segundos de simulación + arranque |
| `video.mp4` final | 0,2 h | Render + arranque. La base avanza con el controlador programado (RF-INT-18) y el brazo instala 3–5 paneles |
| **Total GPU activa** | **6–8 h** | |
| Margen para repetir el entrenamiento 1 vez (§ supuestos de requerimientos) | +2 h | |
| **Total con margen** | **8–10 h** | **PRO 6000: US$12–16. 5090: US$5–6** |
| **Pod prendido de CP1 a freeze (~21 h)** | 21 h | **PRO 6000: ~US$33. 5090: ~US$13** |

- **El costo real lo pone el tiempo ocioso, no el entrenamiento** [inferido]. Aun así, US$33 es poco frente a perder el host con driver 580. Recomiendo no apagar el pod entre CP1 y el freeze. Al apagarlo, la GPU puede quedar arrendada por otro (§2.2).
- **¿4 h de entrenamiento alcanzan?** En cómputo, sí. 4 h a ~200 000 pasos/s dan ~2 900 M pasos, unas 20 veces Franka lift [inferido]. El riesgo es otro: una recompensa mal diseñada no converge con más horas (fuente 40). Reparte las 4 h en corridas cortas con criterio de corte. Mantén el planificador (RF-INT-01) como respaldo real.

## 6. Supuestos del equipo que las fuentes contradicen

| Documento | Supuesto | Qué dicen las fuentes |
|---|---|---|
| `infraestructura.md` §1 | "Isaac Sim no corre en A100/H100" | Entrenamiento headless por estado sí corre en H100. Cámaras y video no. La conclusión (usar RTX) sigue en pie por RF-INT-13/15 (fuentes 8–10) |
| `infraestructura.md` §1 | "Evitar 595 con 5.1: caídas en Blackwell" | La caída con 595 ocurre en todas las RTX, también en Ada (fuentes 4 y 5) |
| `infraestructura.md` §2 | "RunPod o Vast.ai" con 5090 | RunPod Secure no tiene 5090 y todo su stock de hoy está en driver 595 (medido por mí). Vast sí tiene 5090 y PRO 6000 con 580 |
| `infraestructura.md` §1, plan B | "Pasar a Isaac Sim 6.x con driver 595" | 6.x implica Isaac Lab 3.0, con cuaterniones XYZW y otras APIs. El código de `sim/` usa APIs 2.x (fuentes 33–35) |
| `infraestructura.md` §2 | RAM mínima 32 GB | Muchas 5090 de Vast traen 30 GB. Filtra por ≥64 GB (medido por mí) |
| `infraestructura.md` §1 | Livestream WebRTC para depurar | No funciona en RunPod (sin UDP) ni en Vast (NAT). Usa noVNC o videos (fuentes 14 y 24) |
| `requerimientos.md` RF-INT-12, RNF-10 | "En la 5090" | El requisito real es una RTX con driver 580. La GPU puede ser otra |
| `requerimientos.md` RF-INT-13 vs `plan-entrenamiento.md` §2.3 | Clips durante el entrenamiento vs "headless sin cámaras" | `--video` deja el render prendido todo el entrenamiento: ~10× más lento por iteración en un reporte (fuentes 45 y 46). Graba los clips desde checkpoints |
| `plan-entrenamiento.md` §2.4 | Pods spot para entrenar | RunPod Secure no muestra precio spot hoy (medido por mí; fuente 18) |
| `infraestructura.md` §3 vs `agentes/mcp-isaac-sim.md` | "La clave de Claude no vive en el pod" vs Claude Code corriendo en el pod | Contradicción interna del equipo, no de las fuentes. Hay que decidir una |

## Fuentes

1. Isaac Sim 5.1 requirements: https://docs.isaacsim.omniverse.nvidia.com/5.1.0/installation/requirements.html
2. Isaac Sim (6.x) requirements: https://docs.isaacsim.omniverse.nvidia.com/latest/installation/requirements.html
3. Isaac Lab 2.3 release notes: https://isaac-sim.github.io/IsaacLab/v2.3.0/source/refs/release_notes.html
4. Foro NVIDIA, 5.1 + RTX 4090 + driver 595.71: https://forums.developer.nvidia.com/t/isaac-sim-5-1-0-crashes-on-startup-with-rtx-4090-on-ubuntu-24-04-4-segfaulting-in-librtx-scenedb-plugin-so-after-iommu-was-disabled/371957/4
5. IsaacSim #517 y #602 (595 no validado; 4070/4090/5070 Ti/5080/5090): https://github.com/isaac-sim/IsaacSim/issues/517 , https://github.com/isaac-sim/IsaacSim/issues/602
6. IsaacSim #586 (4090, 595.58 → 570 sin caída): https://github.com/isaac-sim/IsaacSim/issues/586
7. drone-sim, 5.1 headless SIGSEGV con driver 610, imagen 14,0 GB: https://github.com/teapotlaboratories/drone-sim/blob/main/docs/history/isaac/driver-decision.md
8. Isaac Lab en H100 (guía y tabla): https://github.com/Kyk0/isaaclab-h100 , https://kyry.me/isaaclab-h100/
9. IsaacLab #4271, H100 incompatible con TiledCamera: https://github.com/isaac-sim/IsaacLab/issues/4271
10. IsaacLab #3421, cámaras en A100: https://github.com/isaac-sim/IsaacLab/issues/3421
11. Isaac Lab performance benchmarks (4090, L40): https://isaac-sim.github.io/IsaacLab/main/source/overview/reinforcement-learning/performance_benchmarks.html ; discusión 4090 vs L40: https://github.com/isaac-sim/IsaacLab/discussions/1310
12. Isaac Sim en Brev (L40S): https://docs.isaacsim.omniverse.nvidia.com/6.0.0/installation/install_advanced_cloud_setup_brev.html
13. Isaac Lab Arena, Franka lift: https://isaac-sim.github.io/IsaacLab-Arena/main/pages/example_workflows/reinforcement_learning/index.html
14. Isaac Sim en GCP y RunPod (4090, L4, tiempos): https://butt2rflow.github.io/en/posts/isaac-sim-pc-and-cloud/
14b. Pick con ventosa en L4, 5 h: https://zenn.dev/aws_japan/articles/428a16622a29f8
15. Isaac Sim 5.1 + Isaac Lab 2.3.1 en RTX PRO 6000 (AWS g7e): https://velog.io/@ooswoo120/RTX-PRO-6000-Blackwellsm120%EC%97%90%EC%84%9C-Isaac-Sim-5.1-Isaac-Lab-2.3.1-%ED%99%98%EA%B2%BD
16. IsaacLab #5001 y #4951, TiledCamera en 5090: https://github.com/isaac-sim/IsaacLab/issues/5001 , https://github.com/isaac-sim/IsaacLab/issues/4951
17. CUDA toolkit release notes (13.0 = R580, 13.1 = R590, 13.2 = R595): https://docs.nvidia.com/cuda/cuda-toolkit-release-notes/index.html
18. RunPod pricing: https://www.runpod.io/pricing
19. RunPod, crear pod (`allowedCudaVersions`, `minCudaVersion`): https://docs.runpod.io/api-reference-v2/pods/create-a-pod
20. IsaacLab #2271, contenedor sin UDP en RunPod: https://github.com/isaac-sim/IsaacLab/issues/2271
21. Vast.ai, campos de búsqueda: https://docs.vast.ai/cli/reference/search-instances
22. Vast.ai, VM: https://docs.vast.ai/guides/instances/virtual-machines
23. Template ProtoMotions + Isaac Lab (Vulkan en contenedor, Vast): https://github.com/carlosdp/protomotions-isaaclab-template
24. IsaacSim discusión #597, Vast.ai, 5090 con 580.95.05, WebRTC y NAT: https://github.com/isaac-sim/IsaacSim/discussions/597
25. Brev como agregador: https://vramcalculator.com/rent-a-gpu-for-ai/
26. Consola de Brev (precios L40S): https://brev.nvidia.com/environment/new/public
27. Brev launchables: https://docs.nvidia.com/brev/latest/concepts/launchables
28. NVIDIA, Isaac Sim e Isaac Lab en Brev (video): https://www.youtube.com/watch?v=ta-1RJzcDNs
29. Lambda pricing: https://lambda.com/pricing
30. AWS g6e.xlarge: https://gpuledger.dev/instances/aws/g6e-xlarge/
31. AWS g6e.2xlarge: https://gpuledger.dev/instances/aws/g6e-2xlarge/
32. GCP g2 (L4): https://tanod.dev/gpu/
33. Compatibilidad Isaac Sim / Isaac Lab: https://docs.isaacsim.omniverse.nvidia.com/latest/installation/compatibility.html
34. Isaac Lab v3.0.0: https://github.com/isaac-sim/IsaacLab/releases/tag/v3.0.0
35. Migración a Isaac Lab 3.0: https://docs.nvidia.com/isaaclab/isaac-lab/migrating-to-3-0
36. Isaac Sim 5.1, instalación en contenedor: https://docs.isaacsim.omniverse.nvidia.com/5.1.0/installation/install_container.html
37. IsaacSim discusión #270 (imagen 15,1 GB): https://github.com/isaac-sim/IsaacSim/discussions/270
38. 5.1 en dos RTX PRO 6000 (imagen ~23 GB, 595 rompe Blackwell): https://udion.xyz/musings/installing-isaac-sim-510-on-a-dual-blackwell-rtx-pro-6000-workstation
39. Isaac Sim 5.1 benchmarks (tiempos de arranque): https://docs.isaacsim.omniverse.nvidia.com/5.1.0/reference_material/benchmarks.html
40. Rikei, Franka lift en 12–13 min: https://note.com/rikei_nbd/n/n3b21d6368d41?hl=en
41. IsaacLab #204 (log de Franka lift): https://github.com/isaac-sim/IsaacLab/issues/204
42. Franka lift en 4090: https://github.com/Gukdoli/franka-lift-reward-study ; empuje de cubo: https://huggingface.co/hhmm1122/Franka-cube-isaaclab
43. Arm, Franka reach en DGX Spark: https://learn.arm.com/learning-paths/laptops-and-desktops/dgx_spark_isaac_robotics2/1_7dof_robot_arm/
44. Paper de Isaac Lab, §4.1: https://arxiv.org/html/2511.04831
45. IsaacLab #6605, `--video` lento: https://github.com/isaac-sim/IsaacLab/issues/6605
46. Isaac Lab 2.3, grabar clips en entrenamiento: https://docs.nvidia.com/isaaclab/2.3/getting-started/how-to-guides/recording-video-clips-during-training.md
47. Consultas propias (2026-11-21 06:03–06:05 UTC): `POST https://api.runpod.io/graphql` (`gpuTypes { lowestPrice(input:{gpuCount:1, secureCloud:true, allowedCudaVersions:[...]}) }`) y `GET https://console.vast.ai/api/v0/bundles/?q=...`. Las respuestas no están en el repo: son una foto del inventario de esa hora.

## Qué no pude verificar

- **Stock de RunPod Community Cloud.** La consulta con `secureCloud:false` devolvió vacío para todas las GPU. Puede ser un error de mi consulta. Un reporte de octubre dice que ese día no había 4090 Community con driver 595 (fuente 14). Revísalo en la consola, con el filtro "CUDA Versions".
- **Si el filtro CUDA de RunPod refleja la realidad.** Que todo el stock sea exactamente 13.2 es plausible pero raro. Confírmalo creando un pod y corriendo `nvidia-smi`.
- **Si 5.1 se cae con driver 595 en modo headless sin cámaras.** NVIDIA reporta la caída al iniciar el renderer RTX. La fuente 7 la vio en headless con driver 610. No encontré una prueba exacta con 595 + headless + solo física.
- **Si la imagen `isaac-sim:5.1.0` (usuario 1234, sin SSH) arranca bien como template de Vast** y deja entrar por SSH. No hay reporte.
- **Tiempo de descarga de la imagen** y tiempo de render de un video corto en las GPU elegidas. No hay mediciones públicas.
- **Driver que traen las VM de Brev** y si se puede cambiar sin perder la instancia.
- **Cuota de GPU en cuentas nuevas de AWS** y precio de AWS g7e.
- **Persistencia en Vast al detener una instancia:** si el disco queda y si otra persona puede tomar la GPU.
- **Tiempo de PPO para la tarea real** (panel de 32 kg sobre un tubo). Solo hay tareas parecidas y más fáciles. El número del §5 es una estimación.
- **Si algún servidor MCP de Isaac Sim funciona con 5.1 headless en un contenedor.** No lo investigué.
