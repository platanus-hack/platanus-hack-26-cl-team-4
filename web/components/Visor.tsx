"use client";

// Visor 3D: genera la escena desde entorno.json, carga robot.urdf y reproduce trayectoria.json.
// Todo el contrato está en Z arriba (como Isaac); el grupo raíz lo rota a Y arriba (three.js).
import { OrbitControls } from "@react-three/drei";
import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { useEffect, useMemo, useRef, useState } from "react";
import * as THREE from "three";
import URDFLoader, { type URDFRobot } from "urdf-loader";

import { montarEscaneoPortada } from "@/components/EscaneoPortada";
import { cajasEscena } from "@/lib/escena";
import { numero } from "@/lib/formato";
import type { Entorno, Trayectoria } from "@/lib/tipos";

const PANEL_ESPESOR = 0.04;
const OFFSET_VENTOSA = 0.07; // centro del panel agarrado, medido desde el link efector

// Paleta de web/DISENO.md, en versión para luz de escena.
const COLOR = {
  cielo: "#cfe0ea",
  suelo: "#b98552",
  acero: "#8b96a1",
  poste: "#6e7a86",
  panel: "#1d3c6b",
};

interface Props {
  entorno: Entorno;
  tray: Trayectoria;
  urdf: string;
  /** Texto accesible que describe lo que muestra la escena. */
  descripcion?: string;
  activo?: boolean;
  reproducirAlCargar?: boolean;
  repetir?: boolean;
  encuadrarTrayectoria?: boolean;
}

export default function Visor({
  entorno, tray, urdf, descripcion = "Trayectoria del robot en el entorno 3D", activo = true, reproducirAlCargar = true,
  repetir = true, encuadrarTrayectoria = false,
}: Props) {
  const tiempo = useRef(0);
  const [reproduciendo, setReproduciendo] = useState(reproducirAlCargar);
  const [velocidad, setVelocidad] = useState(1);
  const [mostrado, setMostrado] = useState(0);
  const duracion = tray.frames.at(-1)?.t_s ?? 0;

  useEffect(() => {
    // Con movimiento reducido, el visor parte pausado en el final: todos los paneles instalados.
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      tiempo.current = duracion;
      setReproduciendo(false);
    }
    const id = setInterval(() => {
      setMostrado(tiempo.current);
      if (!repetir && tiempo.current >= duracion) setReproduciendo(false);
    }, 100);
    return () => clearInterval(id);
  }, [duracion, repetir]);

  const finalizado = !repetir && mostrado >= duracion;

  function cambiarReproduccion() {
    if (reproduciendo) {
      setReproduciendo(false);
      return;
    }
    if (finalizado) {
      tiempo.current = 0;
      setMostrado(0);
    }
    setReproduciendo(true);
  }

  const centro = useMemo(() => {
    const posiciones = tray.paneles.map((panel) => panel.pos_m[0]);
    if (encuadrarTrayectoria) {
      for (const cuadro of tray.frames) posiciones.push(cuadro.base.pos_m[0]);
    }
    if (!posiciones.length) return entorno.filas.largo_m / 2;
    const limites = posiciones.reduce(
      ([minimo, maximo], x) => [Math.min(minimo, x), Math.max(maximo, x)],
      [posiciones[0], posiciones[0]],
    );
    return (limites[0] + limites[1]) / 2;
  }, [tray, entorno.filas.largo_m, encuadrarTrayectoria]);

  return (
    <div className="visor">
      <div className="visor-lienzo" role="img" aria-label={descripcion}>
        {/* Cámara desde el pasillo del robot (Y > 0 en el contrato = Z < 0 en three), mirando hacia las filas */}
        <Canvas frameloop={activo ? "always" : "never"} shadows dpr={[1, 1.5]} camera={{ position: [centro - 4.8, 3.6, -7.6], fov: 42 }}>
          <EncuadreSegunPantalla
            objetivo={[centro, 1.0, encuadrarTrayectoria ? -1.1 : -0.6]}
            margen={encuadrarTrayectoria ? 1.12 : 1}
          />
          <color attach="background" args={[COLOR.cielo]} />
          <fog attach="fog" args={[COLOR.cielo, 30, 80]} />
          <hemisphereLight args={["#ffffff", "#9c7a55", 1.0]} />
          <directionalLight position={[12, 22, 6]} intensity={2.0} castShadow shadow-mapSize={[1024, 1024]}>
            <orthographicCamera attach="shadow-camera" args={[-20, 20, 20, -20, 1, 60]} />
          </directionalLight>
          <Escena entorno={entorno} tray={tray} urdf={urdf} tiempo={tiempo} reproduciendo={reproduciendo} velocidad={velocidad} repetir={repetir} />
          <OrbitControls makeDefault maxPolarAngle={Math.PI / 2.1} minDistance={4} maxDistance={40} />
        </Canvas>
      </div>
      <div className="visor-controles">
        <button type="button" className="boton-visor" onClick={cambiarReproduccion}>
          {reproduciendo ? "Pausar" : finalizado ? "Reproducir desde el inicio" : "Reproducir"}
        </button>
        <input
          type="range" min={0} max={duracion} step={0.01} value={mostrado}
          onChange={(ev) => { tiempo.current = Number(ev.target.value); setMostrado(tiempo.current); }}
          aria-label="Momento de la trayectoria"
        />
        <span className="visor-tiempo">{numero(mostrado)} de {numero(duracion)} s</span>
        <label className="visor-velocidad">
          <span className="sr">Velocidad</span>
          <select value={velocidad} onChange={(ev) => setVelocidad(Number(ev.target.value))}>
            {[0.5, 1, 2, 4].map((v) => <option key={v} value={v}>×{v}</option>)}
          </select>
        </label>
      </div>
    </div>
  );
}

/** En pantallas más altas que anchas (celular), aleja la cámara para que entren el robot y las filas. */
function EncuadreSegunPantalla({ objetivo, margen }: { objetivo: [number, number, number]; margen: number }) {
  const { camera, size, controls } = useThree();
  const base = useRef<THREE.Vector3 | null>(null);
  const [ox, oy, oz] = objetivo; // dependencias numéricas: el arreglo se crea en cada render
  useEffect(() => {
    // Solo corre al cambiar el tamaño del lienzo, para no pelear con el usuario cuando mueve la cámara.
    if (!base.current) base.current = camera.position.clone();
    const aspecto = size.width / Math.max(size.height, 1);
    const vertical = aspecto < 1;
    const factor = Math.min(2.6, Math.max(margen, 1.6 / aspecto));
    const o = new THREE.Vector3(ox, oy, oz);
    const desde = base.current.clone().sub(o);
    // En vertical, la pantalla muestra poco de X: se corre el objetivo hacia el pasillo del robot (Z < 0)
    // para que entre todo su recorrido, del primer al último panel.
    if (vertical) o.add(new THREE.Vector3(-1.5, 0, -1.2));
    camera.position.copy(o).add(desde.multiplyScalar(factor));
    const orbit = controls as unknown as { target?: THREE.Vector3; update?: () => void } | null;
    if (orbit?.target) {
      orbit.target.copy(o);
      orbit.update?.();
    } else {
      camera.lookAt(o);
    }
  }, [camera, controls, size.width, size.height, ox, oy, oz, margen]);
  return null;
}

interface EscenaProps extends Pick<Props, "entorno" | "tray" | "urdf" | "repetir"> {
  progresoPortada?: CineProps["progreso"];
  tiempo: React.RefObject<number>;
  reproduciendo: boolean;
  velocidad: number;
}

function Escena({ entorno, tray, urdf, tiempo, reproduciendo, velocidad, progresoPortada, repetir = true }: EscenaProps) {
  const tecnica = Boolean(progresoPortada);
  const invalidate = useThree((estado) => estado.invalidate);
  const frenteEscaneo = useRef({ value: -0.65 });
  const escalaEscaneo = useRef({ value: 1 });
  const raiz = useRef<THREE.Group>(null);
  const base = useRef<THREE.Group>(null);
  const paneles = useRef<(THREE.Mesh | null)[]>([]);
  const robot = useMemo<URDFRobot>(() => new URDFLoader().parse(urdf), [urdf]);
  const ultimoCuadro = useRef<Trayectoria["frames"][number] | undefined>(undefined);
  const cajas = useMemo(() => cajasEscena(entorno), [entorno]);
  const geoPanel = useMemo(
    () => new THREE.BoxGeometry(entorno.panel.ancho_m, entorno.panel.largo_m, PANEL_ESPESOR),
    [entorno],
  );

  useEffect(() => {
    ultimoCuadro.current = undefined;
    robot.traverse((o) => { o.castShadow = true; });
  }, [robot]);

  useEffect(() => {
    if (!progresoPortada) return;
    const desmontar = montarEscaneoPortada(robot, frenteEscaneo.current, escalaEscaneo.current);
    invalidate();
    return desmontar;
  }, [robot, progresoPortada, invalidate]);

  const tmpV = useMemo(() => new THREE.Vector3(), []);
  const tmpQ = useMemo(() => new THREE.Quaternion(), []);
  const tmpQRaiz = useMemo(() => new THREE.Quaternion(), []);
  const ejeZ = useMemo(() => new THREE.Vector3(0, 0, 1), []);

  useFrame(({ gl }, dt) => {
    if (progresoPortada) {
      const p = progresoPortada.current;
      const inicio = THREE.MathUtils.smoothstep(p, .23, .41);
      const cierre = THREE.MathUtils.smoothstep(p, .46, .61);
      frenteEscaneo.current.value = -.65 + 2.65 * inicio + 2.20 * cierre;
      escalaEscaneo.current.value = gl.getPixelRatio();
    }

    const duracion = tray.frames.at(-1)?.t_s ?? 0;
    if (reproduciendo) {
      tiempo.current = tiempo.current + dt * velocidad;
      if (repetir) {
        if (tiempo.current > duracion + 2) tiempo.current = 0;
      } else {
        tiempo.current = Math.min(tiempo.current, duracion);
      }
    }
    const ultimo = tray.frames.length - 1;
    const i = tiempo.current >= duracion
      ? ultimo
      : Math.min(ultimo, Math.max(0, Math.floor(tiempo.current * tray.fps)));
    const f = tray.frames[i];
    if (!f || !base.current || !raiz.current || ultimoCuadro.current === f) return;
    ultimoCuadro.current = f;

    const yaw = THREE.MathUtils.degToRad(f.base.yaw_grados);
    base.current.position.set(f.base.pos_m[0], f.base.pos_m[1], f.base.pos_m[2]);
    base.current.rotation.set(0, 0, yaw);
    tray.articulaciones.forEach((nombre, j) => robot.setJointValue(nombre, f.q[j]));

    const instalados = new Set(f.instalados);
    const enPila = tray.paneles.map((p) => p.id).filter((id) => !instalados.has(id) && id !== f.agarre).sort((a, b) => b - a);
    const efector = robot.links["efector"];

    tray.paneles.forEach((p) => {
      const m = paneles.current[p.id];
      if (!m) return;
      if (instalados.has(p.id)) {
        m.position.set(...p.pos_m);
        m.quaternion.set(p.quat[1], p.quat[2], p.quat[3], p.quat[0]); // contrato w,x,y,z -> three x,y,z,w
      } else if (f.agarre === p.id && efector) {
        efector.localToWorld(tmpV.set(0, 0, OFFSET_VENTOSA));
        raiz.current!.worldToLocal(tmpV);
        m.position.copy(tmpV);
        efector.getWorldQuaternion(tmpQ);
        raiz.current!.getWorldQuaternion(tmpQRaiz);
        m.quaternion.copy(tmpQRaiz.invert().multiply(tmpQ));
      } else {
        const nivel = enPila.indexOf(p.id);
        const [px, py, pz] = tray.pila.pos_m;
        const c = Math.cos(yaw), s = Math.sin(yaw);
        m.position.set(
          f.base.pos_m[0] + c * px - s * py,
          f.base.pos_m[1] + s * px + c * py,
          pz + (nivel + 0.5) * tray.pila.paso_m,
        );
        m.quaternion.setFromAxisAngle(ejeZ, yaw);
      }
    });
  });

  const colorCaja = (nombre: string) =>
    tecnica
      ? nombre === "suelo" ? "#222721" : "#9aa195"
      : nombre === "suelo" ? COLOR.suelo : nombre.includes("poste") ? COLOR.poste : COLOR.acero;

  return (
    <group ref={raiz} rotation={[-Math.PI / 2, 0, 0]}>
      {cajas.map((c) => (
        <mesh key={c.nombre} position={c.centro} receiveShadow castShadow={c.nombre !== "suelo"}>
          <boxGeometry args={c.tam} />
          <meshStandardMaterial color={colorCaja(c.nombre)} roughness={c.nombre === "suelo" ? 1 : 0.5} metalness={c.nombre === "suelo" ? 0 : 0.6} />
        </mesh>
      ))}
      <group ref={base}>
        <primitive object={robot} />
      </group>
      {tray.paneles.map((p) => (
        <mesh key={p.id} ref={(m) => { paneles.current[p.id] = m; }} geometry={geoPanel} castShadow receiveShadow>
          <meshStandardMaterial color={tecnica ? "#b18442" : COLOR.panel} metalness={0.5} roughness={0.25} />
        </mesh>
      ))}
    </group>
  );
}

interface CineProps extends Pick<Props, "entorno" | "tray" | "urdf"> {
  progreso: React.RefObject<number>;
  fijo?: boolean;
}

export function LienzoPortada({ entorno, tray, urdf, progreso, fijo = false }: CineProps) {
  const tiempo = useRef(0);

  return (
    <Canvas frameloop={fijo ? "demand" : "always"} dpr={[1, 1.4]} camera={{ fov: 40, near: 0.1, far: 140 }} gl={{ powerPreference: "high-performance" }}>
      <color attach="background" args={["#181d18"]} />
      <fog attach="fog" args={["#181d18", 26, 63]} />
      <hemisphereLight args={["#d9e7de", "#51462f", 1.6]} />
      <directionalLight position={[-8, 14, -10]} intensity={2.8} color="#f7d6a5" />
      <gridHelper args={[80, 80, "#545c4d", "#3a4135"]} position={[10, 0.015, 3]} />
      <CamaraPortada tray={tray} progreso={progreso} tiempo={tiempo} fijo={fijo} />
      <Escena entorno={entorno} tray={tray} urdf={urdf} tiempo={tiempo} reproduciendo={false} velocidad={1} progresoPortada={progreso} />
    </Canvas>
  );
}

function CamaraPortada({ tray, progreso, tiempo, fijo }: Pick<CineProps, "tray" | "progreso" | "fijo"> & { tiempo: React.RefObject<number> }) {
  const { camera, size } = useThree();
  const { inicio, cierre, punto } = useMemo(() => {
    const agarre = tray.frames.findIndex((frame) => frame.agarre !== null);
    const panel = agarre >= 0 ? tray.frames[agarre].agarre : null;
    const puesta = panel === null ? undefined : tray.frames.slice(agarre).find((frame) => frame.instalados.includes(panel));
    const ubicacion = (tray.paneles.find((p) => p.id === panel) ?? tray.paneles[0])?.pos_m;
    return {
      inicio: Math.max(0, (tray.frames[agarre]?.t_s ?? 0) - 1.15),
      cierre: Math.min(tray.frames.at(-1)?.t_s ?? 0, (puesta?.t_s ?? 9) + 0.65),
      punto: ubicacion?.[0] ?? 2.5,
    };
  }, [tray]);

  useFrame(() => {
    const p = progreso.current;
    const llegada = THREE.MathUtils.smoothstep(p, .18, .51);
    const detalle = THREE.MathUtils.smoothstep(p, .55, .88);
    const accion = THREE.MathUtils.clamp((p - .5) / .38, 0, 1);
    const estrecho = size.width / Math.max(1, size.height) < 1.5;
    tiempo.current = THREE.MathUtils.lerp(inicio, cierre, accion);

    if (camera instanceof THREE.PerspectiveCamera) {
      const enfoque = THREE.MathUtils.smoothstep(p, .24, .4) *
        (1 - THREE.MathUtils.smoothstep(p, .48, .66));
      camera.fov = fijo ? 43 : 40 - (estrecho ? 5 : 9) * enfoque;
      const fovVertical = THREE.MathUtils.degToRad(camera.fov);
      camera.filmOffset = (fijo ? 0 : -(0.29 + 0.42 * detalle)) *
        Math.tan(fovVertical / 2) * camera.aspect * camera.getFilmWidth();
      camera.updateProjectionMatrix();
    }

    if (fijo) {
      const i = Math.min(tray.frames.length - 1, Math.floor(tiempo.current * tray.fps));
      const [x, y, z] = tray.frames[i]?.base.pos_m ?? [punto, 0, 0];
      camera.position.set(x + 2.45, z + 2.7, -y - 3.9);
      camera.lookAt(x, z + 1.04, -y);
      return;
    }

    camera.position.set(
      punto + 12 - 12 * llegada - .9 * detalle,
      20 - 15.5 * llegada - 1.2 * detalle,
      -21 + 13 * llegada + (estrecho ? .35 : 1.2) * detalle,
    );
    camera.lookAt(
      punto + 4 - 5.2 * llegada - (estrecho ? 0.6 : 1.3) * detalle,
      .65 + .5 * llegada,
      .8 - 1.6 * llegada,
    );
  }, -1);

  return null;
}
