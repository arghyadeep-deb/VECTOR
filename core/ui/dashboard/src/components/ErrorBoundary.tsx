import { Component, type ReactNode, type ErrorInfo } from 'react'

interface Props { children: ReactNode }
interface State { hasError: boolean; error: Error | null; stack: string }

export default class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false, error: null, stack: '' }

  static getDerivedStateFromError(error: Error) { return { hasError: true, error } }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('[ErrorBoundary]', error, info.componentStack)
    this.setState({ stack: info.componentStack || '' })
  }

  render() {
    if (this.state.hasError) {
      return (
        <div style={{ position:'fixed', inset:0, background:'#020B18', display:'flex', flexDirection:'column', alignItems:'center', justifyContent:'center', gap:12, padding:40 }}>
          <div style={{ fontFamily:"'Orbitron', sans-serif", fontSize:24, color:'#4FC3F7', letterSpacing:'0.2em', border:'1px solid #4FC3F7', padding:'12px 24px' }}>
            SYSTEM ERROR
          </div>
          <div style={{ position:'fixed', top:4, right:8, fontFamily:"'JetBrains Mono', monospace", fontSize:8, color:'#004466' }}>BUILD_v3_Suspense+startTransition</div>
          <div style={{ fontFamily:"'JetBrains Mono', monospace", fontSize:12, color:'#ff3355', maxWidth:500, textAlign:'center', lineHeight:1.6 }}>
            {this.state.error?.message ?? 'Unknown error'}
          </div>
          {this.state.stack && (
            <div style={{ fontFamily:"'JetBrains Mono', monospace", fontSize:9, color:'#3388aa', maxWidth:700, textAlign:'left', lineHeight:1.5, marginTop:8, padding:12, border:'1px solid rgba(0,207,255,0.1)', overflow:'auto', maxHeight:200 }}>
              {this.state.stack}
            </div>
          )}
          <button onClick={() => window.location.reload()} style={{ background:'transparent', border:'1px solid #4FC3F7', color:'#4FC3F7', fontFamily:"'Orbitron', sans-serif", fontSize:12, padding:'10px 24px', cursor:'pointer', letterSpacing:'0.15em', marginTop:12 }}>
            RELOAD
          </button>
        </div>
      )
    }
    return this.props.children
  }
}
