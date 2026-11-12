import { Link, NavLink, Outlet, Route, Routes } from 'react-router-dom'
import LicitacionDetailPage from './features/licitaciones/LicitacionDetailPage'
import LicitacionesListPage from './features/licitaciones/LicitacionesListPage'
import NuevaLicitacionPage from './features/licitaciones/NuevaLicitacionPage'
import PerfilPage from './features/perfil/PerfilPage'

const enlaces = [
  { to: '/', etiqueta: 'Licitaciones', fin: true },
  { to: '/perfil', etiqueta: 'Perfil de empresa', fin: false },
]

function RadarLogo() {
  return (
    <svg
      width="28"
      height="28"
      viewBox="0 0 24 24"
      fill="none"
      stroke="#2445C8"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <circle cx="12" cy="12" r="9" />
      <circle cx="12" cy="12" r="5" />
      <path d="M12 12l6-6" />
    </svg>
  )
}

function RootLayout() {
  return (
    <div className="min-h-screen">
      <header className="border-b border-border bg-surface">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center gap-6 px-6 py-3.5">
          <LinkOrLogo />
          <nav aria-label="Principal" className="flex flex-wrap gap-1">
            {enlaces.map((enlace) => (
              <NavLink
                key={enlace.to}
                to={enlace.to}
                end={enlace.fin}
                className={({ isActive }) =>
                  isActive
                    ? 'rounded-lg bg-accent-radar/10 px-3.5 py-2.5 font-semibold text-accent-radar'
                    : 'rounded-lg px-3.5 py-2.5 text-text hover:bg-background'
                }
              >
                {enlace.etiqueta}
              </NavLink>
            ))}
          </nav>
          <div className="ml-auto flex items-center gap-2 text-[13px] text-text-secondary">
            <span className="h-2 w-2 rounded-full bg-go" aria-hidden="true" />
            Modelo: deepseek-v4-flash · NaN Builders
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-7xl px-6 pb-12 pt-8">
        <Outlet />
      </main>
    </div>
  )
}

function LinkOrLogo() {
  return (
    <Link to="/" className="flex items-center gap-2.5">
      <RadarLogo />
      <span className="font-display text-xl font-bold text-text">Radar de Pliegos</span>
    </Link>
  )
}

function App() {
  return (
    <Routes>
      <Route element={<RootLayout />}>
        <Route index element={<LicitacionesListPage />} />
        <Route path="/licitaciones/nueva" element={<NuevaLicitacionPage />} />
        <Route path="/licitaciones/:id" element={<LicitacionDetailPage />} />
        <Route path="/perfil" element={<PerfilPage />} />
      </Route>
    </Routes>
  )
}

export default App
