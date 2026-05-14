const PANEL_BG = 'rgba(5, 13, 26, 0.88)'

export function panelStyle(): React.CSSProperties {
  return {
    border: '1px solid rgba(0,212,255,0.08)',
    boxShadow: '0 0 20px rgba(0,212,255,0.06), inset 0 0 30px rgba(0,212,255,0.02)',
    background: PANEL_BG,
  }
}

export function panelHeader(): React.CSSProperties {
  return {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: '8px 12px',
    borderBottom: '1px solid rgba(0,212,255,0.08)',
    fontFamily: "'Orbitron', sans-serif",
    fontSize: 9,
    color: '#1a6688',
    letterSpacing: '0.12em',
    textTransform: 'uppercase' as const,
  }
}
