import type { Metadata } from 'next'
import './globals.css'

export const metadata: Metadata = {
  title: 'V.E.C.T.O.R. — Cognitive OS Dashboard',
  description: 'Virtual Entity for Cognitive Tasks & Operational Reasoning — Mission Control Interface',
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  )
}
