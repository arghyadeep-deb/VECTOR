import { Z } from '../lib/zIndex'

export default function DecorativeRing() {
  return (
    <div
      style={{
        position: 'fixed',
        bottom: -100,
        left: -750,
        width: 1000,
        height: 600,
        zIndex: Z.DECORATIONS,
        pointerEvents: 'none',
        overflow: 'hidden',
      }}
    >
      <svg
        viewBox="0 0 1000 600"
        style={{ position: 'absolute', top: 0, left: 0, width: '100%', height: '100%' }}
      >
        <ellipse cx={500} cy={300} rx={480} ry={180} fill="none" stroke="#1a6b8a" strokeWidth={1} opacity={0.4}>
          <animateTransform attributeName="transform" type="rotate" from="0 500 300" to="360 500 300" dur="20s" repeatCount="indefinite" />
        </ellipse>
        <ellipse cx={500} cy={300} rx={360} ry={120} fill="none" stroke="#1a6b8a" strokeWidth={1} opacity={0.3}>
          <animateTransform attributeName="transform" type="rotate" from="360 500 300" to="0 500 300" dur="15s" repeatCount="indefinite" />
        </ellipse>
        <ellipse cx={500} cy={300} rx={240} ry={80} fill="none" stroke="#1a6b8a" strokeWidth={1} opacity={0.25}>
          <animateTransform attributeName="transform" type="rotate" from="0 500 300" to="360 500 300" dur="10s" repeatCount="indefinite" />
        </ellipse>
      </svg>
    </div>
  )
}
