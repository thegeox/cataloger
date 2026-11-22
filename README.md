# Cataloger

Aplicación web para **catalogar imágenes con metadata** y **generar piezas a partir de plantillas**.

1. **Fuentes**: conecta repositorios de imágenes: carpeta local, Google Drive, OneDrive (ampliable).
2. **Campos de metadata**: define el esquema una sola vez (texto, número, fecha, sí/no, lista de opciones), con obligatorios y valores por defecto.
3. **Imágenes**: rellena la metadata imagen por imagen, en lote (selección múltiple) o importando un CSV/Excel exportado a CSV.
4. **Plantillas**: editor visual con zonas de imagen, textos y formas. Los textos aceptan campos `{{clave}}` que se sustituyen por la metadata de cada imagen.
5. **Exportar**: aplica una plantilla a muchas imágenes → **ZIP de PNG/JPG/WebP** (una pieza por imagen) o **catálogo PDF** (cuadrícula configurable).

```
backend/   FastAPI + SQLModel (SQLite) + Pillow + ReportLab
frontend/  React + TypeScript + Vite
```

## Puesta en marcha

Requisitos: Python 3.11+ y Node 20+.

```bash
# Backend
cd backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:create_app --factory --reload --port 8000

# Frontend (en otra terminal), con recarga en caliente en http://localhost:5173
cd frontend
npm install
npm run dev
```

Para servir todo desde un único puerto: `cd frontend && npm run build`. El backend sirve `frontend/dist` en http://localhost:8000.

Tests del backend: `cd backend && pytest`.

### Configuración (variables de entorno)

| Variable | Uso |
|---|---|
| `CATALOGER_DATA_DIR` | Carpeta de datos (base SQLite y caché de miniaturas). Por defecto `./data` |
| `CATALOGER_DATABASE_URL` | URL SQLAlchemy alternativa (p. ej. PostgreSQL) |
| `CATALOGER_CORS_ORIGINS` | Orígenes permitidos, separados por coma |
| `CATALOGER_GOOGLE_CLIENT_ID` / `_SECRET` | App OAuth de Google, para refrescar tokens de Drive |
| `CATALOGER_MICROSOFT_CLIENT_ID` / `_SECRET` | App de Azure AD, para refrescar tokens de OneDrive |

## Conectores

Todos implementan `Connector` (`backend/app/connectors/base.py`) con dos métodos: `list_images()` y `read_bytes(id)`. Para añadir otra fuente (Dropbox, S3, SharePoint, FTP…) se crea la clase y se registra en `connectors/__init__.py`. El formulario de la UI se genera a partir de `config_fields`.

- **Carpeta local**: ruta en la máquina donde corre el backend; subcarpetas opcionales. También permite subir imágenes desde el navegador.
- **Google Drive / OneDrive**: por ahora se pega un *access token* (y opcionalmente un *refresh token*) en el formulario. Con el client id/secret configurado, el token se renueva solo. Los secretos nunca se devuelven a la UI.

La sincronización es idempotente: añade las imágenes nuevas, actualiza las modificadas, quita las borradas y **conserva la metadata** existente.

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

El mismo lenguaje sirve para el **nombre de los archivos exportados** (p. ej. `{{sku}}-{{titulo|lower}}`) y para el **título de página del PDF** (`{{_page}}`, `{{_pages}}`).

Los textos con *“Reducir texto si no cabe”* bajan de tamaño hasta caber en su caja sin partir palabras. El lienzo del editor reproduce el cálculo, y **“Vista previa real”** muestra el render exacto del servidor.

## Importación CSV

- La columna de nombre de archivo puede llamarse `archivo`, `filename`, `imagen`, `nombre`… y coincide con o sin extensión.
- El resto de columnas se asocian a campos por clave **o** etiqueta, sin distinguir mayúsculas ni acentos.
- Detecta el separador (`,` `;` tab) y la codificación (UTF-8 o Windows-1252, típico de Excel).
- Números con formato `1.234,50` o `1,234.50`; fechas `AAAA-MM-DD` o `DD/MM/AAAA`.
- Devuelve un informe con las filas sin imagen, las columnas ignoradas y los errores de validación.

## Próximos pasos sugeridos

- Flujo OAuth completo en la UI (botón “Conectar con Google/Microsoft”) en lugar de pegar tokens.
- Más conectores: Dropbox, S3/Azure Blob, SharePoint.
- Exportaciones grandes en segundo plano, con progreso.
- Escribir la metadata también en EXIF/XMP de los archivos exportados.
- Fuentes tipográficas personalizadas y elementos de logo/imagen estática en plantillas.
- Usuarios y permisos.
