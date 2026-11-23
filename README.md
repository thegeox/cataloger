# Cataloger

Aplicación web para **catalogar imágenes con metadata** y **generar piezas a partir de plantillas**.

1. **Fuentes**: conecta repositorios de imágenes: carpeta local, Google Drive, OneDrive (ampliable).
2. **Carpetas y esquemas**: cada carpeta define qué metadata se pide para sus fotos en un archivo `catalog.schema.json` (p. ej. *calzado* pide modelo y talla; *muebles*, medidas y acabado). Las subcarpetas lo heredan y pueden ampliarlo.
3. **Imágenes**: rellena la metadata foto por foto, en lote o importando un CSV. Los valores se guardan en `catalog.data.json`, dentro de la misma carpeta.
4. **Plantillas**: editor visual con zonas de imagen, textos y formas. Los textos aceptan campos `{{clave}}` que se sustituyen por la metadata de cada imagen.
5. **Exportar**: aplica una plantilla a muchas imágenes → **ZIP de PNG/JPG/WebP** (una pieza por imagen) o **catálogo PDF** (cuadrícula configurable).

```
backend/   FastAPI + SQLModel (SQLite) + Pillow + ReportLab
frontend/  React + TypeScript + Vite
```

## Puesta en marcha

Requisitos: **Python 3.11+** y **Node.js 20+**.

### 1. Descargar el código

```bash
git clone https://github.com/thegeox/cataloger.git
cd cataloger
git checkout claude/image-processing-metadata-7x95fh
```

### 2. Backend

macOS / Linux:

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Windows (PowerShell):

```powershell
cd backend
py -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 3. Frontend

En otra terminal:

```bash
cd frontend
npm install
npm run build
```

### 4. Arrancar

En la terminal del backend, con el entorno virtual activado:

```bash
uvicorn app.main:create_app --factory --port 8000
```

Abre **http://localhost:8000**.

> Para desarrollar el frontend con recarga en caliente, deja el backend corriendo y ejecuta `npm run dev` en `frontend/`; luego abre http://localhost:5173.

Tests del backend: `cd backend && pytest`.

### 5. Probar con el catálogo de ejemplo

`examples/catalogo/` incluye fotos de muestra:
- `calzado/`: con esquema y algunos valores ya cargados.
- `muebles/`: con la subcarpeta `sillas/`, que hereda el esquema, quita *medidas* y añade *altura de asiento*.
- `varios/`: sin esquema, para crearlo desde la app.

La app **escribe** en esa carpeta (`catalog.data.json`, `catalog.schema.json`). Si quieres conservar el ejemplo intacto, cópialo antes a otro lugar y usa la copia.

1. **Fuentes** → tipo *Carpeta local* → ruta absoluta de la carpeta, p. ej. `/Users/ana/cataloger/examples/catalogo` o `C:\Users\ana\cataloger\examples\catalogo` → *Agregar y sincronizar*.
2. **Carpetas y esquemas**: revisa la herencia en `muebles/sillas` y crea el esquema de `varios`.
3. **Imágenes**: *Importar CSV* con `examples/metadata-ejemplo.csv` y completa el resto a mano.
4. **Plantillas** → crea una desde un modelo e inserta campos como `{{modelo}}` o `{{precio|money:$}}`.
5. **Exportar** → catálogo PDF o ZIP de imágenes.

Los datos internos de la app (caché y base SQLite) se guardan en `backend/data/`. Se puede borrar en cualquier momento: la metadata real está en las carpetas.

### Configuración (variables de entorno)

| Variable | Uso |
|---|---|
| `CATALOGER_DATA_DIR` | Carpeta de datos (base SQLite y caché de miniaturas). Por defecto `./data` |
| `CATALOGER_DATABASE_URL` | URL SQLAlchemy alternativa (p. ej. PostgreSQL) |
| `CATALOGER_CORS_ORIGINS` | Orígenes permitidos, separados por coma |
| `CATALOGER_GOOGLE_CLIENT_ID` / `_SECRET` | App OAuth de Google, para refrescar tokens de Drive |
| `CATALOGER_MICROSOFT_CLIENT_ID` / `_SECRET` | App de Azure AD, para refrescar tokens de OneDrive |

## Metadata por carpeta

La metadata vive **en las carpetas**, no en la aplicación. La base de datos de la app es solo una caché que se reconstruye al sincronizar.

```
catalogo/
├── calzado/
│   ├── catalog.schema.json     ← qué campos se piden (lo escribes tú o la app)
│   ├── catalog.data.json       ← valores por foto (lo escribe la app)
│   └── oxford-negro.jpg
└── muebles/
    ├── catalog.schema.json
    ├── mesa-roble.jpg
    └── sillas/
        ├── catalog.schema.json ← hereda de muebles y añade/quita campos
        └── silla-nordica.jpg
```

**`catalog.schema.json`**

```json
{
  "categoria": "Calzado",
  "campos": [
    { "clave": "modelo", "etiqueta": "Modelo", "tipo": "texto", "obligatorio": true },
    { "clave": "talla", "etiqueta": "Talla", "tipo": "lista", "opciones": ["38", "39", "40"], "obligatorio": true },
    { "clave": "precio", "etiqueta": "Precio", "tipo": "numero" },
    { "clave": "material", "etiqueta": "Material", "tipo": "texto", "defecto": "Cuero" }
  ]
}
```

- Tipos: `texto`, `texto_largo`, `numero`, `fecha`, `si_no`, `lista`. También se aceptan las claves en inglés (`key`, `label`, `type`, `required`, `options`, `default`).
- `clave` es el nombre que se usa en las plantillas (`{{modelo}}`).
- **Herencia**: una subcarpeta sin archivo usa el esquema de la carpeta superior más cercana. Con archivo propio, *añade* sus campos a los heredados, *redefine* un campo si repite su clave, puede *quitar* heredados con `"quitar": ["medidas"]` o no heredar nada con `"heredar": false`.
- Una carpeta sin esquema (ni propio ni heredado) aparece como **“sin esquema”**. Desde *Carpetas y esquemas* se crea su archivo con un editor visual.

**`catalog.data.json`**: valores por nombre de archivo, solo de las fotos que están directamente en esa carpeta:

```json
{
  "oxford-negro.jpg": { "modelo": "Oxford", "talla": "42", "precio": 2150 }
}
```

- La app vuelve a leer el archivo antes de cada escritura, así que no pisa cambios hechos por otra persona o herramienta. Las claves que no están en el esquema se conservan.
- Si una foto desaparece y vuelve (o se mueve la carpeta entera), sus datos siguen en el archivo y se recuperan al sincronizar.
- Si el archivo tiene un JSON inválido, la app lo informa y **no escribe** en esa carpeta hasta que se corrija.
- Los valores por defecto del esquema se usan al renderizar mientras la foto no tenga un valor propio.

## Conectores

Todos implementan `Connector` (`backend/app/connectors/base.py`) con dos métodos: `list_images()` y `read_bytes(id)`. Para añadir otra fuente (Dropbox, S3, SharePoint, FTP…) se crea la clase y se registra en `connectors/__init__.py`. El formulario de la UI se genera a partir de `config_fields`.

- **Carpeta local**: ruta en la máquina donde corre el backend; subcarpetas opcionales. También permite subir imágenes desde el navegador.
- **Google Drive / OneDrive**: recorren subcarpetas. Como la app escribe los `catalog.*.json`, el token necesita permiso de **escritura** (Drive: alcance `drive`; OneDrive: `Files.ReadWrite`). Por ahora el *access token* (y opcionalmente un *refresh token*) se pega en el formulario; con el client id/secret configurado, el token se renueva solo. Los secretos nunca se devuelven a la UI.

Cada conector implementa también `read_text` y `write_text` para leer y escribir los archivos de metadata en cualquier carpeta.

## Lenguaje de plantillas

| Sintaxis | Resultado |
|---|---|
| `{{titulo}}` | valor del campo |
| `{{titulo\|upper}}`, `lower`, `title`, `trim` | transformaciones de texto |
| `{{precio\|money:$}}` | `$1,234.50` |
| `{{precio\|number:0}}` | `1,235` |
| `{{fecha\|date:%d/%m/%Y}}` | reformatea fechas ISO |
| `{{stock\|yesno:Disponible,Agotado}}` | booleanos |
| `{{sku\|default:Sin SKU}}` | valor alternativo si está vacío |
| `{{_name}}`, `{{_stem}}`, `{{_index}}`, `{{_count}}`, `{{_width}}`, `{{_height}}` | datos del archivo y del lote |
| `{{_category}}`, `{{_folder}}`, `{{_path}}` | categoría del esquema, nombre y ruta de la carpeta |

El mismo lenguaje sirve para el **nombre de los archivos exportados** (p. ej. `{{sku}}-{{titulo|lower}}`) y para el **título de página del PDF** (`{{_page}}`, `{{_pages}}`).

Los textos con *“Reducir texto si no cabe”* bajan de tamaño hasta caber en su caja sin partir palabras. El lienzo del editor reproduce el cálculo, y **“Vista previa real”** muestra el render exacto del servidor.

## Importación CSV

- La columna de nombre de archivo puede llamarse `archivo`, `filename`, `imagen`, `foto`, `nombre`… y coincide con o sin extensión, o con la ruta `carpeta/foto.jpg`.
- El resto de columnas se asocian a los campos **de la carpeta de cada foto** por clave o etiqueta, sin distinguir mayúsculas ni acentos. Un mismo CSV puede mezclar calzado y muebles.
- Los valores se escriben en el `catalog.data.json` de cada carpeta.
- Detecta el separador (`,` `;` tab) y la codificación (UTF-8 o Windows-1252, típico de Excel).
- Números con formato `1.234,50` o `1,234.50`; fechas `AAAA-MM-DD` o `DD/MM/AAAA`.
- Devuelve un informe con las filas sin imagen, las columnas ignoradas y los errores de validación.

## Próximos pasos sugeridos

- Flujo OAuth completo en la UI (botón “Conectar con Google/Microsoft”) en lugar de pegar tokens.
- Más conectores: Dropbox, S3/Azure Blob, SharePoint.
- Exportaciones grandes en segundo plano, con progreso.
- Escribir la metadata también en EXIF/XMP de los archivos exportados.
- Detectar fotos renombradas (por hash) para trasladar sus datos en `catalog.data.json`.
- Fuentes tipográficas personalizadas y elementos de logo/imagen estática en plantillas.
- Usuarios y permisos.
