'use client';
import Link from 'next/link';
import { usePathname } from 'next/navigation';

const NAV = [
  { href: '/',         icon: '◈', label: 'MAIN HUD',     id: 'MOD-001' },
  { href: '/3d',       icon: '✦', label: '3D VIEW',      id: 'MOD-3D'  },
  { href: '/agents',   icon: '⬡', label: 'AGENTS',       id: 'MOD-002' },
  { href: '/memory',   icon: '◎', label: 'MEMORY',       id: 'MOD-003' },
  { href: '/goals',    icon: '◇', label: 'GOALS',        id: 'MOD-004' },
  { href: '/council',  icon: '◈', label: 'COUNCIL',      id: 'MOD-005' },
  { href: '/security', icon: '⬡', label: 'SECURITY',     id: 'MOD-006' },
];

export default function Sidebar() {
  const path = usePathname();
  return (
    <aside className="sidebar">
      <div className="sidebar-logo">
        <div className="logo-text">
          <span className="status-dot" />
          V.E.C.T.O.R
        </div>
        <div className="logo-sub">COGNITIVE OPERATING SYSTEM</div>
      </div>

      <nav className="sidebar-nav">
        {NAV.map(({ href, icon, label, id }) => (
          <Link
            key={href}
            href={href}
            className={`nav-item ${path === href ? 'active' : ''}`}
          >
            <span className="nav-icon">{icon}</span>
            <span style={{ flex: 1 }}>{label}</span>
            <span style={{ fontFamily: 'var(--font-label)', fontSize: 8, color: 'var(--outline)', letterSpacing: '0.1em' }}>{id}</span>
          </Link>
        ))}
      </nav>

      <div className="sidebar-footer">
        <div style={{ color: 'var(--cyan-dim)', marginBottom: 2 }}>SYS STATUS</div>
        <div>BRAIN v1.0.0 · LOCAL</div>
        <div style={{ marginTop: 4, display: 'flex', gap: 6, alignItems: 'center' }}>
          <span className="dot dot-cyan" style={{ width: 5, height: 5 }} />
          <span>ALL SYSTEMS NOMINAL</span>
        </div>
      </div>
    </aside>
  );
}
