import { useMemo } from 'react'

interface SparklineProps {
  width?: number
  height?: number
  color?: string
  data?: number[]
  seed?: number
}

function seededRand(n: number): number {
  const x = Math.sin(n * 9301 + 49297) * 49297
  return x - Math.floor(x)
}

export default function Sparkline({ width = 30, height = 14, color = '#4FC3F7', data, seed = 0 }: SparklineProps) {
  const points = useMemo(() => {
    if (data && data.length >= 2) {
      return data.map((v, i) => [(i / (data.length - 1)) * width, height - (v / 1000) * height] as [number, number])
    }
    const pts: [number, number][] = []
    for (let i = 0; i < 8; i++) {
      pts.push([(i / 7) * width, seededRand(i + seed + 1) * height])
    }
    return pts
  }, [width, height, data, seed])

  const d = points.map((p, i) => `${i === 0 ? 'M' : 'L'} ${p[0]} ${p[1]}`).join(' ')

  return (
    <svg width={width} height={height} style={{ flexShrink: 0 }}>
      <path d={d} fill="none" stroke={color} strokeWidth={1} opacity={0.5} />
      {points.map((p, i) => (
        <circle key={i} cx={p[0]} cy={p[1]} r={1} fill={color} opacity={0.3} />
      ))}
    </svg>
  )
}
