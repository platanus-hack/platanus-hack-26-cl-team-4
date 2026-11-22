"use client";

import { Canvas, useFrame, useLoader, useThree } from "@react-three/fiber";
import { useEffect, useLayoutEffect, useMemo, useRef } from "react";
import * as THREE from "three";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import { MeshoptDecoder } from "three/addons/libs/meshopt_decoder.module.js";

import { modeloPortadaUrl } from "@/lib/modelo-portada";
const tau = Math.PI * 2;

function materialConDigitos(
  original: THREE.MeshStandardMaterial,
  resolucion: THREE.Vector2,
  tiempo: THREE.IUniform<number>,
) {
  const material = original.clone();
  material.customProgramCacheKey = () => "viaz-digitos-portada";
  material.onBeforeCompile = (shader) => {
    shader.uniforms.resolucionViaz = { value: resolucion };
    shader.uniforms.tiempoViaz = tiempo;
    shader.fragmentShader = `
      uniform vec2 resolucionViaz;
      uniform float tiempoViaz;

      float ruidoViaz(vec2 semilla) {
        return fract(sin(dot(semilla, vec2(12.9898, 78.233))) * 4375.8545);
      }

      float glifoViaz(float digito) {
        if (digito < 1.0) return 31599.0;
        if (digito < 2.0) return 9879.0;
        if (digito < 3.0) return 31183.0;
        if (digito < 4.0) return 31207.0;
        if (digito < 5.0) return 23524.0;
        if (digito < 6.0) return 29671.0;
        if (digito < 7.0) return 29679.0;
        if (digito < 8.0) return 30866.0;
        if (digito < 9.0) return 31727.0;
        if (digito < 10.0) return 31719.0;
        if (digito < 11.0) return 11245.0; // A
        if (digito < 12.0) return 15083.0; // B
        if (digito < 13.0) return 25166.0; // C
        if (digito < 14.0) return 15211.0; // D
        if (digito < 15.0) return 29391.0; // E
        return 29385.0; // F
      }
      ${shader.fragmentShader}
    `.replace("#include <opaque_fragment>", `
      vec2 uvViaz = gl_FragCoord.xy / resolucionViaz;
      float corteViaz = uvViaz.x + (uvViaz.y - 0.5) * 0.34 - 0.50;
      if (corteViaz < 0.12) {
        float aspecto = resolucionViaz.x / resolucionViaz.y;
        vec2 raster = uvViaz * vec2(aspecto, 1.0) * mix(70.0, 105.0, smoothstep(1.0, 1.55, aspecto));
        vec2 celda = floor(raster);
        vec2 tinta = fract(raster) * vec2(4.0, 6.0) - vec2(0.5);
        float numero = floor(ruidoViaz(celda) * 10.0);
        float reloj = tiempoViaz * 0.38 + ruidoViaz(celda + vec2(31.0, 57.0));
        float fase = fract(reloj);
        float cambia = step(0.44, ruidoViaz(celda + vec2(71.0, 19.0))) * (1.0 - step(0.13, fase));
        if (cambia > 0.0) {
          float pulso = floor(reloj) * 2.0 + step(0.063, fase);
          float salto = 1.0 + floor(15.0 * ruidoViaz(celda + vec2(pulso, -pulso)));
          numero = mod(numero + salto, 16.0);
        }
        vec2 punto = floor(tinta);
        float bit = mod(floor(glifoViaz(numero) / exp2(punto.x + 3.0 * punto.y)), 2.0);
        float interior = step(0.0, tinta.x) * step(0.0, tinta.y) * (1.0 - step(3.0, tinta.x)) * (1.0 - step(5.0, tinta.y));
        float letra = bit * interior;
        float relieve = clamp(dot(outgoingLight, vec3(0.21, 0.72, 0.07)), 0.0, 1.0);
        float borde = pow(1.0 - abs(dot(normalize(normal), normalize(vViewPosition))), 3.1);
        vec3 ambar = vec3(1.0, 0.55, 0.21);
        vec3 digital = vec3(0.008, 0.011, 0.009) + ambar * (letra * (0.25 + 0.7 * relieve + 0.24 * cambia) + borde * 0.17);
        float metal = smoothstep(-0.052, 0.064, corteViaz);
        outgoingLight = mix(digital, outgoingLight, metal) + ambar * (1.0 - smoothstep(0.0, 0.045, abs(corteViaz))) * borde * 0.30;
      }
      #include <opaque_fragment>
    `);
  };
  return material;
}

function Brazo({ girar, listo }: { girar: boolean; listo: () => void }) {
  const grupo = useRef<THREE.Group>(null);
  const { scene } = useLoader(GLTFLoader, modeloPortadaUrl, (loader) => loader.setMeshoptDecoder(MeshoptDecoder));
  const gl = useThree((estado) => estado.gl);
  const camera = useThree((estado) => estado.camera);
  const size = useThree((estado) => estado.size);
  const dpr = useThree((estado) => estado.viewport.dpr);
  const invalidar = useThree((estado) => estado.invalidate);
  const resolucion = useMemo(() => new THREE.Vector2(1, 1), []);
  const tiempo = useMemo(() => ({ value: 0 }), []);
  const { modelo, materiales } = useMemo(() => {
    const modelo = scene.clone(true);
    const materiales = new Map<THREE.MeshStandardMaterial, THREE.MeshStandardMaterial>();
    modelo.traverse((objeto) => {
      if (!(objeto instanceof THREE.Mesh) || !(objeto.material instanceof THREE.MeshStandardMaterial)) return;
      const original = objeto.material;
      let reemplazo = materiales.get(original);
      if (!reemplazo) {
        reemplazo = materialConDigitos(original, resolucion, tiempo);
        materiales.set(original, reemplazo);
      }
      objeto.material = reemplazo;
    });
    const limites = new THREE.Box3().setFromObject(modelo);
    const centro = limites.getCenter(new THREE.Vector3());
    const escala = 3.62 / limites.getSize(new THREE.Vector3()).y;
    modelo.scale.setScalar(escala);
    modelo.position.set(-centro.x * escala, -limites.min.y * escala, -centro.z * escala);
    return { modelo, materiales };
  }, [scene, resolucion, tiempo]);

  useEffect(() => () => materiales.forEach((m) => m.dispose()), [materiales]);
  useEffect(listo, [listo]);

  useLayoutEffect(() => {
    gl.getDrawingBufferSize(resolucion);
    if (camera instanceof THREE.PerspectiveCamera) {
      const aspecto = size.width / Math.max(size.height, 1);
      const distancia = Math.max(7.4, 6.5 / Math.max(aspecto, .5));
      camera.position.set(0, 2.45, distancia);
      camera.lookAt(0, 1.81, 0);
    }
  }, [gl, camera, size, dpr, resolucion]);

  useEffect(() => {
    if (!girar) return;
    const intervalo = window.setInterval(() => invalidar(), 1000 / 30);
    return () => window.clearInterval(intervalo);
  }, [girar, invalidar]);

  useFrame((_, delta) => {
    if (girar && grupo.current) {
      const paso = Math.min(delta, .05);
      tiempo.value += paso;
      grupo.current.rotation.y = (grupo.current.rotation.y + paso * .23) % tau;
    }
  });

  return (
    <group ref={grupo} rotation-y={-.30}>
      <primitive object={modelo} />
    </group>
  );
}

export default function BrazoPortada({ girar, listo }: { girar: boolean; listo: () => void }) {
  return (
    <Canvas
      aria-hidden="true"
      dpr={[1, 1.25]}
      frameloop="demand"
      camera={{ fov: 34, near: .1, far: 30 }}
      gl={{ antialias: true, alpha: true, powerPreference: "low-power" }}
    >
      <hemisphereLight args={["#e8f1ff", "#584022", 2.15]} />
      <directionalLight position={[4, 6, 4]} color="#fff8e9" intensity={3.35} />
      <directionalLight position={[-3, 2.6, -4]} color="#ffb567" intensity={3.20} />
      <directionalLight position={[0, 1.1, 4]} color="#afd7e0" intensity={.65} />
      <Brazo girar={girar} listo={listo} />
    </Canvas>
  );
}
