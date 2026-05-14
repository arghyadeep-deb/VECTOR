import { Z } from '../lib/zIndex'

export default function BackgroundGrid() {
  return (
    <>
      {/* Perspective grid SVG */}
      <svg
        style={{
          position: 'fixed',
          top: 0,
          left: 0,
          width: '100%',
          height: '100%',
          zIndex: Z.BACKGROUND,
          pointerEvents: 'none',
        }}
        viewBox="0 0 1000 600"
        preserveAspectRatio="xMidYMid slice"
      >
        <defs>
          <linearGradient id="fade" x1="0%" y1="0%" x2="0%" y2="100%">
            <stop offset="0%" stopColor="#003355" stopOpacity={0.04} />
            <stop offset="50%" stopColor="#003355" stopOpacity={0.1} />
            <stop offset="100%" stopColor="#003355" stopOpacity={0.04} />
          </linearGradient>
        </defs>
        {/* Horizontal perspective lines converging to center */}
        {Array.from({ length: 40 }).map((_, i) => {
          const y = i * 15
          const spread = 10 + i * 0.8
          return (
            <line
              key={`h${i}`}
              x1={500 - spread}
              y1={y}
              x2={500 + spread}
              y2={y}
              stroke="url(#fade)"
              strokeWidth={0.5}
            />
          )
        })}
        {/* Vertical perspective lines converging to center */}
        {Array.from({ length: 40 }).map((_, i) => {
          const x = i * 25 + 100
          const spreadTop = 0.5 + Math.abs(x - 500) * 0.15
          return (
            <line
              key={`v${i}`}
              x1={x}
              y1={300 - spreadTop}
              x2={x}
              y2={300 + spreadTop}
              stroke="url(#fade)"
              strokeWidth={0.5}
            />
          )
        })}
      </svg>

      {/* Hexagonal grid overlay */}
      <svg
        style={{
          position: 'fixed',
          top: 0,
          left: 0,
          width: '100%',
          height: '100%',
          zIndex: Z.BACKGROUND,
          pointerEvents: 'none',
          opacity: 0.12,
        }}
        width="100%"
        height="100%"
        xmlns="http://www.w3.org/2000/svg"
      >
        <defs>
          <pattern id="hex" width="40" height="69.28" patternUnits="userSpaceOnUse">
            <path
              d="M40 17.32L20 5.77 0 17.32v23.1l20 11.55 20-11.55zM20 63.5l-20-11.55v-7.7l20 11.55 20-11.55v7.7z"
              fill="none"
              stroke="#003d5c"
              strokeWidth={0.5}
            />
          </pattern>
        </defs>
        <rect width="100%" height="100%" fill="url(#hex)" />
      </svg>
    </>
  )
}
