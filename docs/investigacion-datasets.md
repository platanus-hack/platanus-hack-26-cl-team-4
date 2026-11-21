# Investigación: datos públicos para el montaje de paneles solares

> Estado: **verificado el 2026-11-21**. Cada dato lleva su fuente.
> Un dato entra en este documento solo si lo leímos en la fuente misma: la página, el archivo o la API.
> Lo que no pudimos leer está en la sección 6, fuera de las tablas.

## 1. Resumen

- **No encontramos un dataset público de montaje de paneles.** Ningún video, teleoperación o trayectoria de un robot o una persona que pone un panel en la estructura.
  Hicimos 4 búsquedas web, que incluyen Hugging Face, Kaggle y arXiv (sección 5).
  Los fabricantes de robots publican cifras de rendimiento, pero no sus datos.
- **Sí hay datos para cada etapa de VIAZ.** Hay geometría de plantas (Entorno), rendimiento de robots reales (Tarea y Robot) y videos de trabajo industrial (Inteligencia).
- **Para el pitch (propuesta):** nadie publica datos de montaje. La simulación de VIAZ puede generar esos datos.

## 2. Etapa 1, Entorno: geometría de las plantas

| Fuente | Qué trae | Cómo se verificó |
|---|---|---|
| **USPVDB v4.0**, USGS + LBNL, abril 2026. [Metadata](https://energy.usgs.gov/uspvdb/assets/data/uspvdb_v4_0_20260414.xml), [página LBNL](https://eta-publications.lbl.gov/publications/us-large-scale-solar-photovoltaic) | 6.611 plantas de 1 MW o más, en 49 estados de EE. UU. más DC. Cada planta tiene un polígono dibujado alrededor de sus paneles, sobre imagen aérea de alta resolución. Campos: `p_axis` (tipo de eje), `p_tilt`, `p_azimuth`, `p_area`, `p_cap_ac`, `p_cap_dc`, `ylat`, `xlong`. **No trae** separación entre filas ni cantidad de módulos | Leímos los campos y el método en el XML de metadata. La página LBNL dice "6,611 facilities covering 49 states (plus the District of Columbia)" |
| **Multi-resolution dataset for photovoltaic panel segmentation**, Jiang et al., ESSD 2021. [Paper](https://essd.copernicus.org/articles/13/5389/2021/), [Zenodo](https://zenodo.org/records/5171712) | 3.716 muestras para segmentar paneles en imágenes. PV08 a ~0,8 m (satélite), PV03 a 0,3 m (avión) y PV01 a 0,1 m (dron). 7,0 GB, licencia CC-BY 4.0 | Leímos el paper y el registro de Zenodo |
| **A global inventory of solar photovoltaic generating units**, Kruitwagen et al. 2021. [Zenodo](https://zenodo.org/records/5005868) | 68.661 polígonos predichos de unidades generadoras solares en el mundo. Muestran el estado a fines de 2018. Licencia CC-BY 4.0 | Leímos el registro de Zenodo |

### Chile

| Fuente | Qué trae | Cómo se verificó |
|---|---|---|
| **Infotécnica**, Coordinador Eléctrico Nacional. [Página](https://infotecnica.coordinador.cl/instalaciones/centrales), [API](https://api-infotecnica.coordinador.cl/v1/centrales/extended/) | 1.224 centrales. **761 son solares** y 752 de ellas tienen `latitud` y `longitud`. Suman 13.305 en `potencia_maxima`. La API no nombra la unidad, pero los valores calzan con MW. La mayor es PFV CEME 1, en Antofagasta. Otros campos: región, comuna, propietario, fecha de inicio de operación. **No trae** tipo de estructura (tracker o fijo) | Descargamos la API pública el 2026-11-21 a las 02:00 y contamos los registros |
| **OpenInfraMap**, datos de OpenStreetMap. [Chile](https://openinframap.org/stats/area/Chile) | 735 plantas solares mapeadas, 10.932 MW. Son datos de voluntarios, no un registro oficial | Leímos la página, actualizada el 2026-11-20 |

**Cómo usarlo (propuesta):** una coordenada de Infotécnica más una imagen satelital da una planta chilena real para el demo. Con el dataset de Jiang se puede entrenar un modelo que marque los paneles en esa imagen.

## 3. Etapas 2 y 3, Tarea y Robot: robots reales de instalación

Todas las cifras de esta tabla son **declaraciones de cada fabricante**. Nadie las auditó por separado.

| Robot | Fabricante | Cifra publicada | Fuente |
|---|---|---|---|
| **Maximo 3.0** | AES (EE. UU.) | 100 MW instalados en Bellefield, Kern County, California, con 4 robots en paralelo. La rapidez técnica "consistently surpassed one module per minute". Cuadrillas con Maximo instalan hasta 24 módulos por hora de turno por persona | [Solar Power World, 2026-03-25](https://www.solarpowerworldonline.com/2026/03/robots-install-100-mw-of-solar-panels-on-1-gw-aes-project/) |
| Maximo 3.0 | AES | Más de 180.000 módulos instalados. Más de 500 instalaciones por día | [Robotics & Automation News, 2026-08-10](https://roboticsandautomationnews.com/2026/08/10/interview-with-maximos-nick-hegeman-180000-robotic-installations-of-solar-panels-and-counting/104039/) |
| **BUILDEX** (TrinaTracker) | Trina Solar (China) | Hasta 90 módulos por hora, 3 a 4 veces más rápido que a mano | [Comunicado PR Newswire, 2026-09-24](https://www.webull.com/news/15632505306743808) |
| **Buildex** (Trinabot) | Trinabot (China) | Hasta 60 módulos por hora | [pv magazine, 2025-08-26](https://www.pv-magazine.com/2025/08/26/trinabot-offers-installation-robots-for-large-pv-projects) |
| **Litian** | Leapting (China) | Hace el trabajo de 3 a 4 personas, en la planta Culcairn de Neoen, Australia | [RenewEconomy, 2025-04-24](https://reneweconomy.com.au/chinese-robot-does-job-of-three-to-four-humans-installing-thousands-of-panels-at-australian-solar-project/) |
| **Bison** | Beijing Relu Robotics (China) | Plataforma de orugas de 9 toneladas. Se usa en una planta de Argelia sin nombre | [pv magazine, 2026-07-17](https://www.pv-magazine.com/2026/07/17/ai-powered-9-ton-tracked-robot-for-large-scale-pv-construction/) |
| 4 robots de prueba | Sin nombre | Cada robot instala unos 100 paneles por hora, en una planta de 300 MW en Chamdo, Xizang | [China Daily, 2026-05-05](https://www.chinadaily.com.cn/a/202605/05/WS69f9a840a310d6866eb46ee3.html) |

**Cómo usarlo:**

- **Etapa 2, Tarea (RF-TAR-02).** El `ciclo_s: 60` de [`contrato-datos.md`](contrato-datos.md) calza con Maximo, que supera 1 módulo por minuto. La meta del demo tiene así una base real.
- **Etapa 3, Robot (RF-ROB-06).** El requerimiento pide al menos un robot de origen chino comprable en Chile. Aquí hay 4 candidatos chinos para [`backend/viaz/catalogo/robots/`](../backend/viaz/catalogo/robots/): BUILDEX, Buildex de Trinabot, Litian y Bison.
  - No verificamos si se pueden comprar en Chile. Ninguna fuente lo dice.
  - No sabemos si BUILDEX y Buildex son el mismo producto. Ninguna fuente lo dice.

## 4. Etapa 5, Inteligencia: datos de manipulación

Ninguno de estos datasets muestra paneles solares. Sirven como referencia o para pre-entrenar.

| Fuente | Qué trae | Cómo se verificó |
|---|---|---|
| **IndEgo**, NeurIPS 2025 D&B. [arXiv](https://arxiv.org/abs/2511.19684) | 3.460 grabaciones en primera persona, unas 197 horas, de escenarios industriales y trabajo colaborativo | Leímos la página de arXiv |
| **Egocentric-100K**, Build AI. [Hugging Face](https://huggingface.co/datasets/builddotai/Egocentric-100K) | 100.405 horas y 2.010.759 clips de trabajo manual en fábricas. Licencia Apache-2.0. Pide aceptar condiciones antes de bajar | Leímos la página del dataset |
| **Assembling Solar Panels by Dual Robot Arms Towards Full Autonomous Lunar Base Construction**. [arXiv](https://arxiv.org/abs/2601.05491) | 2 brazos robóticos que conectan paneles sobre una maqueta, para una base lunar. **No publica un dataset** | Leímos el resumen y el texto completo |

## 5. Búsquedas sin resultado

Buscamos un dataset de montaje de paneles con estas consultas, el 2026-11-21:

- "dataset solar panel installation robot manipulation video demonstrations module mounting"
- "photovoltaic module installation robot teleoperation dataset OR benchmark 2025 2026"
- "huggingface OR kaggle dataset "solar panel installation" robot OR video"
- "arXiv photovoltaic module installation robot learning dataset release imitation"

Ninguna dio un dataset de montaje. Los datasets solares que aparecen en los resultados son de **limpieza o inspección** de paneles.
Esto no prueba que no exista un dataset privado o poco conocido.

## 6. No confirmado

Estos datos aparecieron en búsquedas, pero no pudimos leerlos en la fuente. No los uses en el pitch hasta confirmarlos.

| Dato | Por qué no está confirmado |
|---|---|
| Una fila de tracker NX Horizon lleva 78 a 90 módulos | El PDF y la ficha técnica de Nextracker devolvieron 404 |
| La lista CEC de módulos no trae medidas ni peso | La página de la CEC no respondió |
| LBNL "Utility-Scale Solar 2026" cubre 1.989 proyectos | La página devolvió 403 |
| El inventario de Kruitwagen cubre plantas de más de 10 kW | El artículo de Nature pide login |
| Luminous Robotics entrena su robot con demostraciones de operadores | La página de AWS no mostró el texto |
| Lightwheel publicó 100.000 horas de video en primera persona | Su página de Hugging Face no muestra datasets públicos |
| Una cuadrilla manual instala 250 a 300 paneles por día | La entrevista de Maximo no trae esa cifra |
| Isaac Sim no trae un asset de panel solar ni de tracker | Solo vimos el índice de la documentación |
