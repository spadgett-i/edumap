# EduMap — de PDF académico a mapa conceptual interactivo

Aplicación web cliente-servidor (prototipo de tesis) que recibe un PDF académico, extrae su contenido,
identifica su estructura con **reglas y algoritmos deterministas** y lo reorganiza en un **mapa conceptual
interactivo** que se puede explorar, corregir y guardar.

* **Sin IA generativa.** No hay APIs de modelos de lenguaje, ni servicios externos, ni prompts. Con el mismo PDF
  y la misma configuración se obtiene siempre el mismo mapa (hay una prueba que lo verifica).
* **Sin inventar contenido.** Cada concepto y cada relación conserva el fragmento y la página del PDF de donde
  salió. Lo que el algoritmo no puede afirmar con evidencia se marca como **«Revisar»** (provisional).
* **Todo local.** Backend FastAPI + SQLite + Tesseract OCR en tu computadora. Nada se envía a la nube.

---

## 1. Estructura del proyecto

```
edumap/
├── README.md
├── samples/                          PDF de prueba (texto y versión «escaneada»)
├── backend/                          Python · FastAPI
│   ├── requirements.txt / requirements-dev.txt / .env.example / pytest.ini
│   ├── app/
│   │   ├── main.py                   crea la app, CORS, health, sirve el frontend compilado
│   │   ├── config.py                 límites y rutas (variables de entorno / .env)
│   │   ├── database.py               SQLite (documentos y proyectos)
│   │   ├── schemas.py                modelos Pydantic + validación del grafo
│   │   ├── routers/documents.py      subir, procesar, consultar estado, revisar texto
│   │   ├── routers/projects.py       biblioteca, leer/guardar/restablecer mapa, eliminar
│   │   └── services/
│   │       ├── pdf_extractor.py      Ruta A (PyMuPDF) y Ruta B (Tesseract OCR)
│   │       ├── structure.py          títulos, jerarquía, párrafos y listas
│   │       ├── concept_map.py        conceptos, relaciones y procedencia
│   │       ├── quiz.py               cuestionarios «completar la oración» (determinista)
│   │       ├── text_utils.py         oraciones, normalización, palabras vacías
│   │       └── pipeline.py           orquesta las 5 etapas y registra su estado real
│   └── tests/                        pytest (extracción, OCR, mapa, API, cuestionarios)
└── frontend/                         React · TypeScript · Vite · React Flow
    └── src/
        ├── pages/                    Home, Upload, Processing, Library, Editor, Quiz
        ├── components/               Shell, ConceptNode, NodePanel, QuizModule, Icon
        ├── lib/mapOps.ts             operaciones puras del mapa (con pruebas Vitest)
        ├── lib/quiz.ts               puntaje del cuestionario (con pruebas Vitest)
        ├── lib/router.ts             enrutado por hash (permite recargar y reabrir)
        ├── api.ts / types.ts         cliente REST y contrato de datos
        └── styles/                   theme.css (paleta y componentes) · editor.css
```

### Bibliotecas elegidas

| Biblioteca | Por qué |
|---|---|
| **PyMuPDF** | Extrae texto *con tamaño de fuente y negrita*, la mejor señal para detectar títulos. Rápida y local. |
| **pytesseract + Pillow** | Envoltorio de Tesseract OCR (el motor se instala aparte). Es OCR convencional, no generativo. |
| **FastAPI + Pydantic** | API REST con validación declarativa de los modelos y errores 422 claros. |
| **sqlite3 (estándar)** | Persistencia local sin ORM ni servidor: suficiente para un prototipo. |
| **React Flow (@xyflow/react)** | Zoom, desplazamiento, nodos personalizados y conexiones editables ya resueltos. |

No se usan NetworkX ni un ORM: el grafo es pequeño y se valida con Pydantic.

---

## 2. Instalación y ejecución

Requisitos: **Python 3.10+**, **Node.js 18+** y (opcional, solo para PDF escaneados) **Tesseract OCR**.

### 2.1 Tesseract OCR (opcional pero recomendado)

* **Windows:** instala desde <https://github.com/UB-Mannheim/tesseract/wiki> y marca el idioma *Spanish* durante la
  instalación. Si no queda en el `PATH`, define `EDUMAP_TESSERACT_CMD=C:\Program Files\Tesseract-OCR\tesseract.exe`
  en `backend/.env`.
* **macOS:** `brew install tesseract tesseract-lang`
* **Ubuntu/Debian:** `sudo apt install tesseract-ocr tesseract-ocr-spa`

Sin Tesseract la app funciona con PDF de texto; con un escaneo mostrará un mensaje claro. Si falta el idioma
español se usa inglés y se avisa en el mapa.

### 2.2 Backend

```powershell
# Windows (PowerShell)
cd backend
py -m venv .venv
.venv\Scripts\Activate.ps1          # si lo bloquea: Set-ExecutionPolicy -Scope Process Bypass
pip install -r requirements-dev.txt
uvicorn app.main:app --reload --port 8000
```
```bash
# macOS / Linux
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
uvicorn app.main:app --reload --port 8000
```

La API queda en <http://127.0.0.1:8000> (documentación interactiva en `/docs`). Los datos se guardan en
`backend/data/` (base `edumap.db` y carpeta `uploads/`).

### 2.3 Frontend

```bash
cd frontend
npm install
npm run dev          # http://localhost:5173  (reenvía /api al backend)
```

**Alternativa de un solo puerto:** ejecuta `npm run build` y abre <http://127.0.0.1:8000>; el backend sirve el
frontend compilado (reinicia el backend si ya estaba abierto).

### 2.4 Variables de entorno (todas opcionales; ver `backend/.env.example`)

`EDUMAP_DATA_DIR`, `EDUMAP_MAX_UPLOAD_MB` (25), `EDUMAP_MAX_PAGES` (300), `EDUMAP_MAX_OCR_PAGES` (40),
`EDUMAP_OCR_LANGS` (`spa+eng`), `EDUMAP_TESSERACT_CMD`, `EDUMAP_CORS_ORIGINS`. El backend lee `backend/.env`
si existe; una variable ya definida en el sistema tiene prioridad.

### 2.5 Pruebas

```bash
cd backend  && pytest                 # extracción, OCR, mapa, validación, API, persistencia
cd frontend && npm test               # operaciones del mapa, puntaje y flujo completo del cuestionario (jsdom)
cd frontend && npm run build          # comprueba los tipos de TypeScript y compila
```
La prueba de OCR se omite sola si Tesseract no está instalado.

### 2.6 PDF de ejemplo

`samples/ejemplo_aprendizaje_multimedia.pdf` (texto) y `samples/ejemplo_escaneado.pdf` (las mismas páginas como
imagen, para probar OCR). Se regeneran con `python backend/tests/make_sample_pdf.py`.

---

## 3. Cómo se transforma el PDF (todo determinista)

1. **Recepción:** valida extensión, firma `%PDF-`, tamaño y que el archivo abra (rechaza PDF cifrados o dañados).
2. **Extracción**, página por página:
   * *Ruta A* — hay capa de texto: PyMuPDF devuelve líneas con tamaño y negrita. Se descartan encabezados/pies
     repetidos y números de página.
   * *Ruta B* — la página es una imagen: se renderiza a 300 dpi y se lee con Tesseract (local). La altura de cada
     línea sustituye al tamaño de fuente. Si el OCR no obtiene texto suficiente, el usuario puede **revisar o
     escribir el texto** y reprocesar, o cargar otro archivo.
3. **Estructura:** une líneas en párrafos, reconoce listas, omite la tabla de contenido y detecta títulos por
   tamaño de fuente, negrita, numeración (`2.1.3`) o mayúsculas. El nivel de cada título sale del ranking de
   estilos; el título del documento es el primer título de estilo único de la primera página.
4. **Conceptos y relaciones** (`concept_map.py`):

   | Elemento | Regla | Relación |
   |---|---|---|
   | Raíz | título del documento | — |
   | Sección | cada título/subtítulo | «contiene» |
   | Definición | «X **se define como** / **es un** / **consiste en** / **se denomina** …» y «Término: explicación» | el propio conector |
   | Lista | cada elemento (si es largo se recorta y se marca *Revisar*) | «incluye» |
   | Término clave | palabras/frases repetidas que aparecen como frases nominales | «término clave» (*Revisar*) |
   | Relación transversal explícita | dos conceptos en una misma oración unidos por un conector («afecta a», «reduce», «se compone de»…) | el conector, con su oración de origen |
   | Relación transversal por co-mención | un concepto menciona a otro sin conector claro | «se relaciona con» (*Revisar*) |

   El algoritmo **no comprende** el texto: no resume, no parafrasea y no completa lo que falta. La sección
   «Referencias» no se convierte en conceptos.
5. **Persistencia:** el mapa (validado) se guarda en SQLite junto con una copia **original** para poder restablecerlo.

### Cuestionarios (completar la oración)

Desde el mapa o la biblioteca, el botón **Cuestionario** genera preguntas de opción múltiple con la misma
lógica determinista del mapa (`backend/app/services/quiz.py`):

1. **Oraciones clave** del texto extraído: definiciones explícitas («X es un…», «X se define como…», «X consiste
   en…», «X se denomina…»), elementos «Término: explicación» y relaciones explícitas entre dos conceptos
   («A afecta a B», «A reduce B»…).
2. **Pregunta:** se oculta el término principal (o la entidad objeto de la relación) y se reemplaza por `______`.
   La oración es **real**, tomada del documento; nunca se redacta una nueva.
3. **Respuesta correcta:** el término ocultado.
4. **Distractores:** otros conceptos del mismo documento (los del mapa conceptual), con longitud parecida, sin
   aparecer en la propia oración y sin ser variantes del mismo término (singular/plural, parte del otro).
   Si no hay tres distractores razonables, la pregunta **no se genera**.
5. **Opciones mezcladas** con una semilla derivada del contenido del documento: parecen aleatorias, pero el mismo
   documento siempre produce el mismo cuestionario y el mismo orden.

```jsonc
[{ "id": "pregunta-001",
   "pregunta": "El ______ es un sistema de procesamiento que recibe imágenes e ilustraciones.",
   "opciones": ["Mapa conceptual", "Canal auditivo", "Carga pertinente", "Canal visual"],
   "respuestaCorrecta": "Canal visual",
   // extras de procedencia (para la retroalimentación):
   "tipo": "definicion", "seccion": "Canales de procesamiento", "paginaOrigen": 1,
   "oracionOriginal": "El canal visual es un sistema de procesamiento que recibe imágenes e ilustraciones." }]
```

En pantalla (`QuizModule.tsx`): una pregunta a la vez, **retroalimentación inmediata** (correcto en azul con ✓,
incorrecto en rojo con ✕, y se muestra la respuesta correcta y la oración original con su página), barra de
progreso real y **puntaje final** («8/10 aciertos») con la lista «Para repasar», **Reintentar**, **Repasar solo las
falladas** y **Volver al mapa conceptual**. Las respuestas se evalúan en el navegador; el servidor solo genera las
preguntas. El puntaje no se guarda.

El texto base (párrafos y listas con su página y sección) se guarda al procesar el PDF. Los proyectos creados antes de
este módulo lo reconstruyen la primera vez que piden un cuestionario (la base SQLite se migra sola).

### Modelo de datos (resumen)

```jsonc
{ "id": "proyecto-…", "documentId": "documento-…", "title": "…",
  "nodes": [{ "id": "concepto-001", "label": "…", "description": "…", "sourcePage": 1, "sourceText": "…",
              "parentId": null, "kind": "root|section|definition|list_item|keyword|manual", "provisional": false }],
  "edges": [{ "id": "relacion-001", "source": "…", "target": "…", "label": "contiene",
              "kind": "hierarchy|explicit|cross|manual", "provisional": false, "sourceText": "…", "sourcePage": 1 }],
  "warnings": ["…"], "meta": { "algorithm": "edumap-reglas-1", "extractionMethod": "text" } }
```
Se valida que: los ids sean únicos, toda relación tenga origen y destino existentes, haya una sola raíz y la
jerarquía no tenga ciclos. Las aristas jerárquicas se mantienen siempre alineadas con `parentId`.

### API REST

| Método y ruta | Función |
|---|---|
| `POST /api/documents` | Sube un PDF (multipart, campo `file`) |
| `POST /api/documents/{id}/process` | Inicia el procesamiento (202; corre en segundo plano) |
| `GET  /api/documents/{id}` | Estado real de cada etapa, método de lectura, mensaje de error |
| `GET/PUT /api/documents/{id}/text` | Texto extraído / texto revisado a mano (cuando el OCR no basta) |
| `GET  /api/projects` | Biblioteca |
| `GET/PUT /api/projects/{id}/map` | Leer / guardar el mapa (PUT valida el grafo) |
| `POST /api/projects/{id}/map/reset` | Restablece el mapa generado originalmente |
| `POST /api/projects/{id}/quiz` | Genera el cuestionario (cuerpo opcional `{"maxPreguntas": 10}`, 1–30). Devuelve un arreglo de preguntas |
| `DELETE /api/projects/{id}` | Elimina proyecto y PDF |
| `GET  /api/health` | Límites y disponibilidad de OCR |

Desplegar o contraer nodos, hacer zoom y editar ocurren **en el navegador**; solo «Guardar» llama al servidor.

### Seguridad básica

Solo PDF (extensión + firma + apertura real) · límite de tamaño con lectura en bloques · nombres internos
generados por el servidor (`documento-<uuid>.pdf`); el nombre original solo se muestra · ninguna ruta del usuario
llega al disco · el texto extraído nunca se ejecuta (React lo escapa) · consultas SQL parametrizadas · el servidor
decide `id` y `documentId` del mapa al guardar · los errores de extracción/OCR se devuelven como mensajes claros.

---

## 4. Estado del prototipo

**Implementado y probado:** carga y validación · extracción con texto y con OCR · estructura y mapa · mapa
interactivo (expandir/contraer, zoom, centrar, ver fragmento de origen, editar texto y relaciones, agregar/
eliminar conceptos y relaciones, cambiar el padre, guardar, restablecer) · biblioteca (abrir/eliminar) ·
reapertura de proyectos guardados · **cuestionarios** (generación, práctica, retroalimentación y puntaje).

**Limitaciones conocidas**

* El orden de lectura es el del contenido del PDF; en PDF de varias columnas con un orden interno atípico
  podrían mezclarse columnas. Tablas, figuras y fórmulas no se interpretan.
* Las definiciones y los conectores están definidos para **español**; en otros idiomas habrá menos conceptos.
* En OCR los títulos se infieren por altura de línea y numeración: es menos fiable que con texto (el mapa lo avisa).
* Los nodos se acomodan automáticamente (no se arrastran). Las relaciones se crean arrastrando entre puntos de conexión.
* Un solo usuario local: no hay cuentas ni roles. «Docente» y «estudiante» usan la misma interfaz
  (el docente crea el mapa; el estudiante lo consulta desde la biblioteca).
* Los proyectos viven solo en este equipo (SQLite local); no hay sincronización.
* **Cuestionarios:** solo hay preguntas donde el texto trae definiciones o relaciones explícitas; un documento sin ellas
  da un cuestionario vacío (con aviso) en vez de preguntas inventadas. Los distractores son conceptos del mismo
  documento, no se comprueba su coherencia gramatical (p. ej. género del artículo) ni se garantiza que sean
  semánticamente incorrectos en todos los contextos. Se genera desde el documento, no desde las ediciones del mapa
  (salvo que las etiquetas editadas se usan como posibles distractores).

**No implementado (a propósito):** tarjetas de estudio, texto estructurado, apoyos visuales y audio.
La arquitectura está preparada: esos módulos partirían del mismo `ConceptMap`/texto extraído, como nuevos servicios en
`backend/app/services/`, nuevos routers y nuevas pantallas, con plantillas y reglas deterministas.
