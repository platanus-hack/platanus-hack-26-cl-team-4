"use client";

// Visor 3D: genera la escena desde entorno.json, carga robot.urdf y reproduce trayectoria.json.
// Todo el contrato está en Z arriba (como Isaac); el grupo raíz lo rota a Y arriba (three.js).
import { OrbitControls } from "@react-three/drei";
import { Canvas, useFrame } from "@react-three/fiber";
import { useEffect, useMemo, useRef, useState } from "react";
import * as THREE from "three";
import URDFLoader, { type URDFRobot } from "urdf-loader";

import { cajasEscena } from "@/lib/escena";
import type { Entorno, Trayectoria } from "@/lib/tipos";

const PANEL_ESPESOR = 0.04;
const OFFSET_VENTOSA = 0.07; // centro del panel agarrado, medido desde el link efector

interface Props {
  entorno: Entorno;
  tray: Trayectoria;
  urdf: string;
}

export default function Visor({ entorno, tray, urdf }: Props) {
  const tiempo = useRef(0);
  const [reproduciendo, setReproduciendo] = useState(true);
  const [velocidad, setVelocidad] = useState(1);
  const [mostrado, setMostrado] = useState(0);
  const duracion = tray.frames.at(-1)?.t_s ?? 0;

  useEffect(() => {
    const id = setInterval(() => setMostrado(tiempo.current), 100);
    return () => clearInterval(id);
  }, []);

  const xs = tray.paneles.map((p) => p.pos_m[0]);
  const centro = xs.length ? (Math.min(...xs) + Math.max(...xs)) / 2 : entorno.filas.largo_m / 2;

  return (
    <div className="visor">
      <div className="lienzo">
        <Canvas shadows camera={{ position: [centro - 6, 6, 10], fov: 45 }}>
          <color attach="background" args={["#cfe3f2"]} />
          <hemisphereLight args={["#ffffff", "#8a7a60", 0.9]} />
          <directionalLight position={[10, 20, 5]} intensity={1.6} castShadow />
          <Escena entorno={entorno} tray={tray} urdf={urdf} tiempo={tiempo} reproduciendo={reproduciendo} velocidad={velocidad} />
          <OrbitControls target={[centro, 1, 0]} maxPolarAngle={Math.PI / 2.05} />
        </Canvas>
      </div>
      <div className="controles">
        <button onClick={() => setReproduciendo((r) => !r)}>{reproduciendo ? "Pausa" : "Reproducir"}</button>
        <input
          type="range" min={0} max={duracion} step={0.01} value={mostrado}
          onChange={(ev) => { tiempo.current = Number(ev.target.value); setMostrado(tiempo.current); }}
          aria-label="Tiempo de la simulación"
        />
        <span className="tiempo">{mostrado.toFixed(1)} / {duracion.toFixed(1)} s</span>
        <select value={velocidad} onChange={(ev) => setVelocidad(Number(ev.target.value))} aria-label="Velocidad">
          {[0.5, 1, 2, 4].map((v) => <option key={v} value={v}>×{v}</option>)}
        </select>
      </div>
    </div>
  );
}

interface EscenaProps extends Props {
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

  useFrame((_, dt) => {
    const duracion = tray.frames.at(-1)?.t_s ?? 0;
    if (reproduciendo) {
      tiempo.current = tiempo.current + dt * velocidad;
      if (tiempo.current > duracion + 1.5) tiempo.current = 0; // vuelve a empezar
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
        m.quaternion.setFromAxisAngle(new THREE.Vector3(0, 0, 1), yaw);
      }
    });
  });

  return (
    <group ref={raiz} rotation={[-Math.PI / 2, 0, 0]}>
      {cajas.map((c) => (
        <mesh key={c.nombre} position={c.centro} receiveShadow castShadow={c.nombre !== "suelo"}>
          <boxGeometry args={c.tam} />
          <meshStandardMaterial color={c.color} />
        </mesh>
      ))}
      <group ref={base}>
        <primitive object={robot} />
      </group>
      {tray.paneles.map((p) => (
        <mesh key={p.id} ref={(m) => { paneles.current[p.id] = m; }} geometry={geoPanel} castShadow>
          <meshStandardMaterial color="#14306b" metalness={0.4} roughness={0.35} />
        </mesh>
      ))}
    </group>
  );
}
