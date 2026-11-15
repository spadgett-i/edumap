import { Shell } from '../components/Shell'
import { paths } from '../lib/router'

const STEPS = [
  { title: 'Cargar PDF', text: 'Sube un documento académico desde tu computadora. Puede tener texto seleccionable o ser un escaneo.' },
  { title: 'Procesar contenido', text: 'El servidor extrae el texto, identifica títulos, párrafos y listas, y construye los conceptos y sus relaciones.' },
  { title: 'Explorar mapa', text: 'Despliega ramas, consulta de qué parte del PDF salió cada concepto y corrige lo que haga falta.' },
]

export function HomePage() {
  return (
    <Shell active="home" title="Inicio">
      <section className="hero">
        <h2>Convierte un PDF académico en un mapa conceptual que se puede explorar</h2>
        <p>
          EduMap lee el documento, reconoce su estructura y reorganiza la información en conceptos y relaciones.
          Cada nodo conserva el fragmento original del que salió, y todo se puede revisar y corregir a mano.
        </p>
        <div className="hero__actions">
          <a className="btn btn--primary btn--lg" href={paths.upload}>Crear mapa conceptual</a>
          <a className="btn btn--on-dark btn--lg" href={paths.library}>Abrir proyecto</a>
        </div>
      </section>

      <section className="section" aria-labelledby="how">
        <h2 id="how" className="section__title">Cómo funciona</h2>
        <ol className="steps">
          {STEPS.map((s, i) => (
            <li key={s.title} className="step">
              <span className="step__num">{i + 1}</span>
              <h3>{s.title}</h3>
              <p>{s.text}</p>
            </li>
          ))}
        </ol>
      </section>

      <section className="section notes">
        <div>
          <h3>Sin inteligencia artificial generativa</h3>
          <p>
            La transformación usa reglas sobre el formato y la redacción del documento. Con el mismo PDF obtienes
            siempre el mismo mapa. Lo que el algoritmo no puede afirmar con evidencia se marca como «Revisar».
          </p>
        </div>
        <div>
          <h3>Tus proyectos se guardan en este equipo</h3>
          <p>
            Los PDF y los mapas se almacenan en una base de datos local (SQLite). No se sincronizan con otros
            dispositivos ni se envían a servicios externos.
          </p>
        </div>
      </section>
    </Shell>
  )
}
