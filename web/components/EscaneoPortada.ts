import * as THREE from "three";

const coordenadaEscaneo = `
  vec3 mundo = (modelMatrix * vec4(transformed, 1.0)).xyz;
  vAlturaEscaneo = mundo.y - mundo.z * 0.36;
`;

export function montarEscaneoPortada(
  robot: THREE.Object3D,
  frente: THREE.IUniform<number>,
  escala: THREE.IUniform<number>,
) {
  const bordes = new THREE.LineBasicMaterial({ color: "#e5a954", transparent: true, depthWrite: false });
  bordes.onBeforeCompile = (shader) => {
    shader.uniforms.frenteEscaneo = frente;
    shader.vertexShader = `varying float vAlturaEscaneo;\n${shader.vertexShader}`
      .replace("#include <project_vertex>", `${coordenadaEscaneo}\n#include <project_vertex>`);
    shader.fragmentShader = `uniform float frenteEscaneo;\nvarying float vAlturaEscaneo;\n${shader.fragmentShader}`
      .replace("#include <opaque_fragment>", `
        float distancia = vAlturaEscaneo - frenteEscaneo;
        float franja = smoothstep(-0.28, 0.03, distancia) * (1.0 - smoothstep(0.28, 0.63, distancia));
        diffuseColor.a *= max(franja, smoothstep(-0.15, 0.23, distancia) * 0.18);
        if (diffuseColor.a < 0.02) discard;
        #include <opaque_fragment>
      `);
  };

  const materiales = new Map<THREE.Material, THREE.Material>();
  const mallas: { malla: THREE.Mesh; original: THREE.Material; linea: THREE.LineSegments }[] = [];
  robot.traverse((objeto) => {
    if (!(objeto instanceof THREE.Mesh) || Array.isArray(objeto.material)) return;
    const original: THREE.Material = objeto.material;
    let material = materiales.get(original);
    if (!material) {
      material = original.clone();
      material.customProgramCacheKey = () => "viaz-escaneo-portada";
      material.onBeforeCompile = (shader) => {
        shader.uniforms.frenteEscaneo = frente;
        shader.uniforms.escalaEscaneo = escala;
        shader.vertexShader = `varying float vAlturaEscaneo;\n${shader.vertexShader}`
          .replace("#include <project_vertex>", `${coordenadaEscaneo}\n#include <project_vertex>`);
        shader.fragmentShader = `uniform float frenteEscaneo;\nuniform float escalaEscaneo;\nvarying float vAlturaEscaneo;\n${shader.fragmentShader}`
          .replace("#include <opaque_fragment>", `
            float distancia = vAlturaEscaneo - frenteEscaneo;
            float metal = 1.0 - smoothstep(-0.28, 0.04, distancia);
            if (metal < 0.999) {
              vec2 celda = fract(gl_FragCoord.xy / (vec2(5.0, 6.0) * escalaEscaneo)) - 0.5;
              float luminancia = clamp(dot(outgoingLight, vec3(0.2126, 0.7152, 0.0722)), 0.0, 1.0);
              float glifo = 1.0 - smoothstep(0.17, 0.29,
                length(celda * vec2(1.5, mix(1.7, 0.75, luminancia))));
              float banda = smoothstep(0.10, 0.72, distancia);
              vec3 ambar = vec3(1.0, 0.58, 0.23);
              vec3 trama = mix(ambar, vec3(1.0, 0.88, 0.66), luminancia) * glifo * mix(0.65, 1.0, luminancia);
              vec3 contorno = mix(vec3(0.041, 0.030, 0.017), trama, 0.27);
              float luz = 1.0 - smoothstep(0.025, 0.095, abs(distancia));
              outgoingLight = mix(mix(contorno, trama + vec3(0.007, 0.009, 0.006), banda),
                outgoingLight, metal) + ambar * luz * 0.22;
            }
            #include <opaque_fragment>
          `);
      };
      materiales.set(original, material);
    }
    const linea = new THREE.LineSegments(new THREE.EdgesGeometry(objeto.geometry, 34), bordes);
    mallas.push({ malla: objeto, original, linea });
    objeto.material = material;
  });

  // Las aristas heredan la transformaci?n de cada eslab?n de la trayectoria.
  for (const { malla, linea } of mallas) malla.add(linea);

  return () => {
    for (const { malla, original, linea } of mallas) {
      malla.remove(linea);
      malla.material = original;
      linea.geometry.dispose();
    }
    materiales.forEach((material) => material.dispose());
    bordes.dispose();
  };
}
