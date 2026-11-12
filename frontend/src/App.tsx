import { Route, Routes } from 'react-router-dom'

function Home() {
  return (
    <main className="min-h-screen p-8">
      <h1 className="font-display text-2xl font-semibold text-text">Radar de Pliegos</h1>
      <p className="mt-2 text-text-secondary">La IA prepara, la persona decide.</p>
    </main>
  )
}

function App() {
  return (
    <Routes>
      <Route path="/" element={<Home />} />
    </Routes>
  )
}

export default App
