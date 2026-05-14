import { StrictMode, Suspense } from 'react'
import { createRoot } from 'react-dom/client'
import App from './App'
import ErrorBoundary from './components/ErrorBoundary'
import './styles.css'

if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
  document.body.classList.add('reduced-motion')
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ErrorBoundary>
      <Suspense fallback={<div style={{ position:'fixed', inset:0, background:'#020B18', display:'flex', alignItems:'center', justifyContent:'center', color:'#00CFFF', fontFamily:"'Orbitron', sans-serif", fontSize:14, letterSpacing:'0.2em' }}>INITIALIZING VECTOR...</div>}>
        <App />
      </Suspense>
    </ErrorBoundary>
  </StrictMode>,
)
