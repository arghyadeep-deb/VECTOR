import { useEffect, useState } from 'react'

export function useScramble(target: number, duration = 800): string {
  const [display, setDisplay] = useState('0')

  useEffect(() => {
    const start = performance.now()
    let rafId = 0

    const animate = (now: number) => {
      const elapsed = now - start
      const progress = Math.min(elapsed / duration, 1)
      const eased = 1 - Math.pow(1 - progress, 3)

      if (progress < 1) {
        const scrambleLen = Math.max(1, Math.round((1 - eased) * 8))
        const prefix = Math.round(target * eased).toString().slice(0, Math.max(1, Math.round(target.toString().length * eased)))
        let s = prefix
        for (let i = s.length; i < target.toString().length + 1; i++) {
          s += Math.floor(Math.random() * 10).toString()
        }
        setDisplay(s.slice(0, Math.max(prefix.length, 1)))
        rafId = requestAnimationFrame(animate)
      } else {
        setDisplay(Math.round(target).toString())
      }
    }

    rafId = requestAnimationFrame(animate)
    return () => cancelAnimationFrame(rafId)
  }, [target, duration])

  return display
}
