"use client";

// Visor 3D: genera la escena desde entorno.json, carga robot.urdf y reproduce trayectoria.json.
// Todo el contrato está en Z arriba (como Isaac); el grupo raíz lo rota a Y arriba (three.js).
import { OrbitControls } from "@react-three/drei";
import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { useEffect, useMemo, useRef, useState } from "react";
import * as THREE from "three";
import URDFLoader, { type URDFRobot } from "urdf-loader";

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
  descripcion: string;
}

export default function Visor({ entorno, tray, urdf, descripcion }: Props) {
  const tiempo = useRef(0);
  const [reproduciendo, setReproduciendo] = useState(true);
  const [velocidad, setVelocidad] = useState(1);
  const [mostrado, setMostrado] = useState(0);
  const duracion = tray.frames.at(-1)?.t_s ?? 0;

  useEffect(() => {
    // Con movimiento reducido, el visor parte pausado en el final: todos los paneles instalados.
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      tiempo.current = duracion;
      setReproduciendo(false);
    }
    const id = setInterval(() => setMostrado(tiempo.current), 100);
    return () => clearInterval(id);
  }, [duracion]);

  const xs = tray.paneles.map((p) => p.pos_m[0]);
  const centro = xs.length ? (Math.min(...xs) + Math.max(...xs)) / 2 : entorno.filas.largo_m / 2;

  return (
    <div className="visor">
      <div className="visor-lienzo" role="img" aria-label={descripcion}>
        {/* Cámara desde el pasillo del robot (Y > 0 en el contrato = Z < 0 en three), mirando hacia las filas */}
        <Canvas shadows dpr={[1, 2]} camera={{ position: [centro - 4.8, 3.6, -7.6], fov: 42 }}>
          <EncuadreSegunPantalla objetivo={[centro, 1.0, -0.6]} />
          <color attach="background" args={[COLOR.cielo]} />
          <fog attach="fog" args={[COLOR.cielo, 30, 80]} />
          <hemisphereLight args={["#ffffff", "#9c7a55", 1.0]} />
          <directionalLight position={[12, 22, 6]} intensity={2.0} castShadow shadow-mapSize={[2048, 2048]}>
            <orthographicCamera attach="shadow-camera" args={[-20, 20, 20, -20, 1, 60]} />
          </directionalLight>
          <Escena entorno={entorno} tray={tray} urdf={urdf} tiempo={tiempo} reproduciendo={reproduciendo} velocidad={velocidad} />
          <OrbitControls makeDefault maxPolarAngle={Math.PI / 2.1} minDistance={4} maxDistance={40} />
        </Canvas>
      </div>
      <div className="visor-controles">
        <button type="button" className="boton-visor" onClick={() => setReproduciendo((r) => !r)}>
          {reproduciendo ? "Pausar" : "Reproducir"}
        </button>
        <input
          type="range" min={0} max={duracion} step={0.01} value={mostrado}
          onChange={(ev) => { tiempo.current = Number(ev.target.value); setMostrado(tiempo.current); }}
          aria-label="Momento de la simulación"
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
function EncuadreSegunPantalla({ objetivo }: { objetivo: [number, number, number] }) {
  const { camera, size, controls } = useThree();
  const base = useRef<THREE.Vector3 | null>(null);
  const [ox, oy, oz] = objetivo; // dependencias numéricas: el arreglo se crea en cada render
  useEffect(() => {
    // Solo corre al cambiar el tamaño del lienzo, para no pelear con el usuario cuando mueve la cámara.
    if (!base.current) base.current = camera.position.clone();
    const aspecto = size.width / Math.max(size.height, 1);
    const vertical = aspecto < 1;
    const factor = Math.min(2.6, Math.max(1, 1.6 / aspecto));
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
  }, [camera, controls, size.width, size.height, ox, oy, oz]);
  return null;
}

interface EscenaProps extends Omit<Props, "descripcion"> {
  tiempo: React.RefObject<number>;
  reproduciendo: boolean;
  velocidad: number;
}

function Escena({ entorno, tray, urdf, tiempo, reproduciendo, velocidad }: EscenaProps) {
  const raiz = useRef<THREE.Group>(null);
  const base = useRef<THREE.Group>(null);
  const paneles = useRef<(THREE.Mesh | null)[]>([]);
  const robot = useMemo<URDFRobot>(() => new URDFLoader().parse(urdf), [urdf]);
  const cajas = useMemo(() => cajasEscena(entorno), [entorno]);
  const geoPanel = useMemo(
    () => new THREE.BoxGeometry(entorno.panel.ancho_m, entorno.panel.largo_m, PANEL_ESPESOR),
    [entorno],
  );

  useEffect(() => {
    robot.traverse((o) => { o.castShadow = true; });
  }, [robot]);

  const tmpV = useMemo(() => new THREE.Vector3(), []);
  const tmpQ = useMemo(() => new THREE.Quaternion(), []);
  const tmpQRaiz = useMemo(() => new THREE.Quaternion(), []);
  const ejeZ = useMemo(() => new THREE.Vector3(0, 0, 1), []);

  useFrame((_, dt) => {
    const duracion = tray.frames.at(-1)?.t_s ?? 0;
    if (reproduciendo) {
      tiempo.current = tiempo.current + dt * velocidad;
      if (tiempo.current > duracion + 2) tiempo.current = 0; // pausa breve al final y vuelve a empezar
    }
    const i = Math.min(tray.frames.length - 1, Math.max(0, Math.floor(tiempo.current * tray.fps)));
    const f = tray.frames[i];
    if (!f || !base.current || !raiz.current) return;

    const yaw = THREE.MathUtils.degToRad(f.base.yaw_grados);
    base.current.position.set(f.base.pos_m[0], f.base.pos_m[1], f.base.pos_m[2]);
    base.current.rotation.set(0, 0, yaw);
    tray.articulaciones.forEach((nombre, j) => robot.setJointValue(nombre, f.q[j]));
    raiz.current.updateMatrixWorld(true);

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
    nombre === "suelo" ? COLOR.suelo : nombre.includes("poste") ? COLOR.poste : COLOR.acero;

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
          <meshStandardMaterial color={COLOR.panel} metalness={0.5} roughness={0.25} />
        </mesh>
      ))}
    </group>
  );
}
