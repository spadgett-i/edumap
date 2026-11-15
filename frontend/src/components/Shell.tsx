import type { ReactNode } from 'react'
import { paths } from '../lib/router'
import { Icon, Logo, type IconName } from './Icon'

export type NavKey = 'home' | 'upload' | 'library'

const NAV: { key: NavKey; label: string; href: string; icon: IconName }[] = [
  { key: 'home', label: 'Inicio', href: paths.home, icon: 'home' },
  { key: 'upload', label: 'Crear mapa conceptual', href: paths.upload, icon: 'plus' },
  { key: 'library', label: 'Biblioteca de proyectos', href: paths.library, icon: 'folder' },
]

/** Barra lateral + barra superior + área de trabajo. */
export function Shell({ active, title, actions, children, flush = false }: {
  active: NavKey
  title: string
  actions?: ReactNode
  children: ReactNode
  flush?: boolean // el área de trabajo ocupa todo el espacio (editor)
}) {
  return (
    <div className="shell">
      <aside className="sidebar">
        <a className="brand" href={paths.home} aria-label="EduMap, ir al inicio">
          <Logo />
          <span>EduMap</span>
        </a>
        <nav aria-label="Navegación principal">
          {NAV.map((item) => (
            <a key={item.key} href={item.href} className={`nav-link${item.key === active ? ' is-active' : ''}`}
              aria-current={item.key === active ? 'page' : undefined}>
              <Icon name={item.icon} />
              <span>{item.label}</span>
            </a>
          ))}
        </nav>
        <p className="sidebar__note">
          El contenido se procesa en este equipo con reglas y algoritmos deterministas. No se usa IA generativa.
        </p>
      </aside>
      <div className="main">
        <header className="topbar">
          <div className="topbar__title">
            <span className="topbar__project">EduMap</span>
            <span className="topbar__sep" aria-hidden="true">/</span>
            <h1 title={title}>{title}</h1>
          </div>
          <div className="topbar__actions">{actions}</div>
        </header>
        <main className={flush ? 'work work--flush' : 'work'}>{children}</main>
      </div>
    </div>
  )
}
