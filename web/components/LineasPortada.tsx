import { useId } from "react";

const curvas = Array.from({ length: 32 }, (_, i) => {
  const inicio = 245 + i * 12;
  const final = 625 + i * 14;
  return {
    d: `M -80 ${inicio} C 265 ${inicio + 104}, 475 ${444 + i * 5}, ${758 + i * 8} ${426 + i * 7} S 1240 ${final - 160}, 1520 ${final}`,
    opacidad: 0.44 + (i % 5) * 0.09,
  };
});

export default function LineasPortada({ visible }: { visible: boolean }) {
  const gradiente = useId();

  return (
    <svg
      className="portada-lineas"
      viewBox="0 0 1440 740"
      preserveAspectRatio="xMidYMid slice"
      fill="none"
      aria-hidden="true"
      focusable="false"
      data-visible={visible}
    >
      <defs>
        <linearGradient id={gradiente} gradientUnits="userSpaceOnUse" x1="0" x2="1440">
          <stop stopColor="#a96b25" stopOpacity=".19" />
          <stop offset=".32" stopColor="#c99049" stopOpacity=".40" />
          <stop offset=".69" stopColor="#f1bd63" stopOpacity=".55" />
          <stop offset="1" stopColor="#e5a655" stopOpacity=".36" />
        </linearGradient>
      </defs>
      {curvas.map(({ d, opacidad }) => (
        <path
          key={d}
          d={d}
          stroke={`url(#${gradiente})`}
          strokeWidth="1"
          strokeOpacity={opacidad}
          vectorEffect="non-scaling-stroke"
        />
      ))}
      {curvas.filter((_, i) => i % 3 === 0).map(({ d }, i) => (
        <path
          key={d}
          className="portada-lineas-trazo"
          d={d}
          pathLength="1"
          stroke="#eabd77"
          strokeWidth="1.25"
          vectorEffect="non-scaling-stroke"
          style={{ animationDelay: `${-i * 2.3}s`, animationDuration: `${23 + (i % 5) * 2}s` }}
        />
      ))}
    </svg>
  );
}
