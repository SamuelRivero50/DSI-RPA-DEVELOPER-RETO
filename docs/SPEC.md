# Spec: consolidación diaria de cuentas médicas

Prueba técnica RPA Developer (DSI Factory) · Documento para el agente de código · Decisiones validadas por el autor

> **Nota de sincronización (2026-10-24):** Esta spec fue el punto de partida del diseño. Si algo difiere de la implementación, mandan el código y el README.

## 0. Reglas de trabajo para el agente

- El código es del autor y deberá explicarlo y modificarlo en vivo en la entrevista. Escribe código simple, legible y pequeño, sin abstracciones que esta spec no pida.
- Sigue la spec al pie de la letra. Si algo es ambiguo o crees que está mal, dilo y propón opciones; no decidas en silencio.
- No uses `Protocol`, clases abstractas ni contenedores de inyección. Las dependencias se pasan como parámetros y los tests usan objetos falsos (duck typing).
- Commits pequeños, uno por pieza (sección 13).
- No escribas `BITACORA.md`: la redacta el autor. Crea solo la plantilla (sección 15) y avísale de cualquier error tuyo que corrijas, para que lo anote.
- Python 3.11 o superior. Ejecución: `requests` y `openpyxl`. Desarrollo: `pytest` y `ruff`.

## 1. Objetivo y requisitos del enunciado

Proceso de madrugada, sin supervisión: lee el CSV diario de cuentas médicas, consulta `https://jsonplaceholder.typicode.com/posts/{id}` por cada identificador y deja un Excel consolidado para auditoría.

| Req. | Enunciado | Sección |
| --- | --- | --- |
| R1 | Leer el CSV tal como llega, sin arreglarlo a mano | 3 |
| R2 | Consultar la API por identificador | 5 |
| R3 | Excel de salida con el resultado de cada consulta | 8 |
| R4 | Ningún identificador que falle detiene el proceso | 4, 11 |
| R5 | Re-ejecutable y reanudable | 6, 11 |
| R6 | Distinguir error de negocio de error técnico | 4 |
| R7 | Reintentos con espera creciente y frontera explicada | 5 |
| R8 | Resumen al final de cada ejecución, por causa | 11 |
| R9 | Archivo de log | 10 |
| R10 | README con runbook | 14 |
| R11 | Configuración fuera del código | 9 |
| R12 | Decisión sobre repetidos, documentada | 3.3 |
| R13 | BITACORA.md | 15 |

Fuera de alcance (va a «Pendiente y por qué» en el README): otros formatos de CSV (solo una columna `id_cuenta`; si cambia, falla con mensaje claro), concurrencia, cortacircuitos, bloqueo de instancia única, puertos y adaptadores formales, 404 transitorios, identidad por contenido (un archivo idéntico conserva el hash, no se reconsulta y mantiene el nombre de la primera carga; la mejora sería incluir la fecha de recepción en la identidad) y purga de datos viejos.

## 2. Decisiones de diseño (resumen)

| Tema | Decisión | Motivo |
| --- | --- | --- |
| Arquitectura | Pipeline por etapas: leer, normalizar y deduplicar, cargar estado, resolver, exportar, resumir | Cada decisión vive en un solo lugar |
| Repetidos | Una consulta y una fila por id único, con columna `apariciones`; la causa de la repetición no se interpreta | El id es la clave de negocio y la API es determinista; la repetición se conserva para auditoría |
| Datos inválidos | Se auditan: aparecen en el Excel como `DATO_INVALIDO` y no se envían a la API | Auditoría debe ver todo lo recibido |
| Estado | SQLite, una base, una tabla, PK `(archivo_hash, id)` | Unicidad y escrituras atómicas por estructura |
| Identidad del archivo | SHA-256 del contenido | El nombre puede ser siempre `cuentas.csv` |
| Reintentos | Bucle propio, espera exponencial con jitter, respeta `Retry-After` | Sin dependencias, fácil de explicar |
| Fallos | Sin cortacircuitos: cada id agota su ciclo | R4 al pie de la letra |
| Excel | Se regenera siempre desde la base y se reemplaza de forma atómica | Sin duplicados ni archivos a medias |
| Configuración | TOML con `tomllib`, validado al arrancar | Sin dependencias |
| Ejecución | Secuencial | Simple y amable con la API |

## 3. Entrada y normalización

### 3.1 Lectura (`adapters/csv_reader.py`)

- Leer los bytes y calcular SHA-256: `archivo_hash` (64 hex) y `hash8` (los 8 primeros).
- Decodificar con `entrada.codificacion` (`utf-8-sig` por defecto). Si no decodifica: error fatal (salida 2); no adivinar la codificación.
- Parsear con `csv.reader`. La primera línea es el encabezado y, tras `strip()`, debe contener la columna configurada (`id_cuenta`). Si falta: error fatal (salida 2).
- `linea_origen` = `reader.line_num` (la del encabezado es la 1).

### 3.2 Normalización (`steps/normalize.py`, función pura)

- `valor_original` = campo tal como lo entrega el parser (las comillas de `"42"` ya las quita el parser).
- Fila vacía o campo vacío tras `strip()`: línea en blanco; se ignora y se cuenta.
- `texto = valor_original.strip()`. Si es ASCII y solo dígitos (`[0-9]+`): válido, `id = str(int(texto))` (007 pasa a 7). El `0` es válido en formato y se consulta (se espera 404).
- Cualquier otro valor (`abc`, `-5`, `3.5`): `DATO_INVALIDO`, causa `FORMATO_INVALIDO`, `id = texto`.
- Deduplicar por `id`: se conserva la primera aparición (`linea_origen`, `valor_original`) y `apariciones` cuenta todas.
- Salida: lista ordenada por `linea_origen` y estadísticas: `lineas_con_datos`, `lineas_en_blanco`, `repeticiones_ignoradas` (suma de apariciones menos 1) y la lista de repetidos (id y apariciones).
- CSV con solo encabezado: WARNING, 0 ids, Excel vacío con su hoja Resumen, salida 0.

### 3.3 Decisión sobre repetidos (para el README)

Una consulta y una fila por identificador único, con `apariciones`. Razones: el identificador es la clave de negocio y la API devuelve lo mismo, así que reconsultar no aporta; una fila por id mantiene la clave única y hace trivial la idempotencia; el conteo se conserva sin interpretarlo (puede deberse a un error de origen o a una re-radicación; decide auditoría). Descartado: consultar y escribir cada ocurrencia (duplica trabajo y filas) y deduplicar en silencio (pierde trazabilidad). No se afirma que un repetido sea un doble cobro.

## 4. Estados y causas

| Estado | Tipo | ¿Final? | ¿Se consulta en otra ejecución? |
| --- | --- | --- | --- |
| PENDIENTE | transitorio | no | sí |
| OK | resultado | sí | no |
| NO\_ENCONTRADO | negocio | sí | no |
| DATO\_INVALIDO | calidad de dato | sí | no |
| ERROR\_TECNICO | técnico | no | sí |

Causas: `NO_ENCONTRADO` → HTTP\_404. `DATO_INVALIDO` → FORMATO\_INVALIDO. `ERROR_TECNICO` → TIMEOUT, CONEXION, HTTP\_5XX, HTTP\_429, HTTP\_4XX, RESPUESTA\_INVALIDA, ERROR\_INESPERADO. `OK` → sin causa.

Suposición a declarar en el README: un 404 se trata como definitivo (la API de ejemplo es estática y R5 pide no reconsultar lo resuelto); en un sistema con replicación podría ser transitorio.

Error inesperado: el procesamiento de cada id va envuelto en `try/except Exception`; marca `ERROR_TECNICO` con causa `ERROR_INESPERADO`, registra el traceback y sigue con el siguiente. No capturar `BaseException`: Ctrl+C y SIGTERM detienen el proceso y el estado queda a salvo.

## 5. Consulta y reintentos

`adapters/api_client.py`: un GET con `requests.Session` y timeouts de conexión y lectura. Devuelve la respuesta o deja subir la excepción de `requests`. No clasifica ni reintenta.

`steps/resolve.py` clasifica y reintenta:

| Situación | ¿Reintenta? | Estado | Causa |
| --- | --- | --- | --- |
| 200 con JSON cuyo `id` coincide con el pedido | n/a | OK |  |
| 404 | No | NO\_ENCONTRADO | HTTP\_404 |
| `Timeout` | Sí | ERROR\_TECNICO | TIMEOUT |
| `ConnectionError` | Sí | ERROR\_TECNICO | CONEXION |
| Cualquier 5xx | Sí | ERROR\_TECNICO | HTTP\_5XX |
| 429 | Sí | ERROR\_TECNICO | HTTP\_429 |
| 200 sin JSON válido o sin el id esperado | Sí | ERROR\_TECNICO | RESPUESTA\_INVALIDA |
| Otros 4xx | No, dentro de la ejecución | ERROR\_TECNICO | HTTP\_4XX |
| Código fuera de la tabla (1xx, 3xx, 2xx distinto de 200) | No | ERROR\_TECNICO | ERROR\_INESPERADO (`detalle_error` = `HTTP inesperado <código>`) |
| Otra excepción de `requests` | No | ERROR\_TECNICO | ERROR\_INESPERADO |

Un timeout de conexión (`ConnectTimeout`) se clasifica como `TIMEOUT`: `Timeout` se comprueba antes que `ConnectionError`.

Frontera (para el README): se reintenta lo que puede cambiar al volver a preguntar (red, timeouts, 5xx, 429, respuestas corruptas). No se reintenta lo determinista dentro de la ejecución (404, datos inválidos, otros 4xx, códigos fuera de la tabla y errores inesperados). Todo `ERROR_TECNICO` se vuelve a intentar en la siguiente ejecución.

`Retry-After` se respeta en cualquier respuesta reintentable, no solo en 429, tanto en segundos como en fecha HTTP. Si es inválido o negativo, se ignora y se usa la espera normal.

Espera: `max_intentos` en total (por defecto 4: uno inicial y tres reintentos). Antes del intento siguiente, `tope = min(espera_maxima_s, espera_base_s * factor ** (n - 1))` y `espera = tope / 2 + random.uniform(0, tope / 2)` (jitter parcial: la espera siempre crece hasta el techo). Si llega `Retry-After` válido (segundos o fecha HTTP): `espera = min(retry_after, retry_after_maximo_s)`. `sleep` y `uniform` se inyectan como parámetros con valores por defecto, para que los tests no esperen.

`intentos` = número de peticiones HTTP realizadas. Cada intento fallido se registra como WARNING (id, intento n/max, causa, espera). Se mapean `userId` → `user_id`, `title` → `titulo`, `body` → `cuerpo`. `resolve` devuelve un `Resultado(estado, causa, user_id, titulo, cuerpo, intentos, detalle_error)`.

## 6. Estado en SQLite (`adapters/repository.py`)

```sql
CREATE TABLE IF NOT EXISTS resultados (
  archivo_hash   TEXT NOT NULL,
  id             TEXT NOT NULL,
  archivo_nombre TEXT NOT NULL,
  linea_origen   INTEGER NOT NULL,
  valor_original TEXT NOT NULL,
  estado         TEXT NOT NULL CHECK (estado IN ('PENDIENTE','OK','NO_ENCONTRADO','DATO_INVALIDO','ERROR_TECNICO')),
  causa          TEXT,
  apariciones    INTEGER NOT NULL DEFAULT 1,
  user_id        INTEGER,
  titulo         TEXT,
  cuerpo         TEXT,
  intentos       INTEGER NOT NULL DEFAULT 0,
  detalle_error  TEXT,
  creado_en      TEXT NOT NULL,
  actualizado_en TEXT NOT NULL,
  PRIMARY KEY (archivo_hash, id)
);
```

- `PRAGMA journal_mode=WAL; PRAGMA synchronous=FULL;`. Commit tras cada id resuelto.
- Marcas de tiempo: ISO-8601 con zona horaria local (`datetime.now().astimezone().isoformat(timespec='seconds')`).
- Todo el acceso pasa por el repositorio, y toda consulta filtra por `archivo_hash`. Ninguna otra parte escribe SQL.
- Operaciones: `cargar_filas(hash, nombre, filas)` (una transacción con `INSERT OR IGNORE`: válidas como PENDIENTE, inválidas como DATO\_INVALIDO final), `pendientes(hash)` (estado PENDIENTE o ERROR\_TECNICO, ordenados por `linea_origen`), `guardar(hash, id, resultado)`, `filas(hash)`, `conteos(hash)`.

## 7. Arquitectura y estructura

```
src/cuentas_pipeline/
├── cli.py                 # argparse, lee el TOML, crea las piezas y devuelve el código de salida
├── __main__.py            # llama a `cli.main` y ejecuta `sys.exit`
├── logging_setup.py
├── pipeline.py            # orquestador; recibe repo, cliente y escritor como parámetros
├── core/
│   ├── models.py          # FilaCuenta, Resultado, ResumenEjecucion, Estado, Causa (Enum)
│   └── config.py          # dataclasses de configuración + validación; no lee archivos
├── steps/                 # lógica sin I/O propio
│   ├── normalize.py
│   ├── resolve.py
│   └── summary.py
└── adapters/              # todo lo que toca el exterior
    ├── csv_reader.py
    ├── api_client.py
    ├── repository.py
    └── excel_writer.py
```

Reglas de importación: `core` no importa nada del proyecto; `steps` y `adapters` solo `core`; `pipeline` solo `core` y `steps`; `cli` puede importar todo. `cli.py` lee el TOML con `tomllib`, construye las dataclasses y devuelve el código de salida; `__main__.py` llama a `sys.exit(main())`. Cada componente recibe solo su sección de configuración, con una excepción conocida: `pipeline.ejecutar` recibe la `Config` completa. Es una desviación respecto a la regla de bajo acoplamiento; la mejora futura es que reciba solo las secciones que necesita.

Dónde cambiar qué (cambios en vivo): política de repetidos → `normalize.py`; qué se reintenta y la espera → `resolve.py`; columnas y colores del Excel → `excel_writer.py`; parámetros → `config.toml`; códigos de salida → `cli.py`; texto del resumen → `summary.py`.

## 8. Excel de salida (`adapters/excel_writer.py`)

- Archivo: `consolidado_<YYYY-MM-DD>_<hash8>.xlsx` en `salida.carpeta`; la fecha es la de `MIN(creado_en)` del archivo de entrada.
- Se genera siempre al final de la ejecución, desde la base (aunque queden pendientes). Se escribe en un archivo temporal de la misma carpeta y se renombra con `os.replace`.
- Hoja `Resultados`, una fila por id único y ordenada por `linea_origen`. Orden real de columnas: `linea_origen`, `valor_original`, `id_cuenta` (entero si es válido, vacío en el Excel si no), `estado`, `causa`, `apariciones`, `intentos`, `detalle_error`, `consultado_en` (= `actualizado_en`), `user_id`, `titulo`, `cuerpo`. Encabezados visibles, en ese orden: «Línea origen», «Valor original», «ID cuenta», «Estado», «Causa», «Apariciones», «Intentos», «Detalle del error», «Consultado en», «ID usuario», «Título» y «Cuerpo».
- Formato de `Resultados`: encabezado de altura 28 con banda oscura `404040`, texto blanco en negrita, centrado y con ajuste de línea; autofiltro; anchos fijos 12, 16, 11, 18, 22, 13, 10, 24, 20, 12, 40 y 70; filas de datos de altura 20 con alineación vertical centrada y sin ajuste de línea en Título ni Cuerpo. `Línea origen`, `ID cuenta`, `Apariciones`, `Intentos` e `ID usuario` se centran; el resto queda a la izquierda. La celda `Estado` lleva el color de estado (verde claro para OK, amarillo para NO\_ENCONTRADO, naranja para DATO\_INVALIDO, rojo claro para ERROR\_TECNICO y gris para PENDIENTE); las filas con estado distinto de OK llevan además un relleno suave de la misma familia, y las OK no llevan relleno de fila. `Consultado en` se muestra como `AAAA-MM-DD HH:MM:SS` en hora local, sin T ni zona; en SQLite se guarda ISO-8601 con zona. Panel congelado en `D2`; impresión horizontal ajustada a una página de ancho con la fila 1 repetida; al abrir el archivo queda activa `Resultados`. `valor_original` se escribe como texto aunque parezca número, para conservar el valor recibido.
- Seguridad: todo texto de origen externo (CSV o API) se escribe como texto. Si empieza por `=`, `+`, `-` o `@`, se fuerza `cell.data_type = 's'` para que no se interprete como fórmula.
- Hoja `Resumen`: título «Resumen del archivo». Bloque Archivo (`Nombre`, `Hash`, `Primera carga`, `Generado en`); bloque Entrada (`Líneas con datos`, `Líneas en blanco ignoradas`, `Repeticiones ignoradas`, `Identificadores únicos`); tabla Resultado por estado (`Estado`/`Total` con los cinco estados y una fila `Total`); tabla Errores técnicos por causa (`Causa`/`Total`, o «Sin errores técnicos»); tabla Repetidos (`Id`/`Apariciones`, o «Sin repetidos»).

## 9. Configuración (`config.toml`)

```toml
[entrada]
archivo = 'cuentas.csv'          # también por --input
columna = 'id_cuenta'
codificacion = 'utf-8-sig'

[api]
url_base = 'https://jsonplaceholder.typicode.com/posts'
timeout_conexion_s = 5
timeout_lectura_s = 10
pausa_entre_consultas_s = 0

[reintentos]
max_intentos = 4
espera_base_s = 1.0
factor = 2.0
espera_maxima_s = 30.0
retry_after_maximo_s = 60.0

[salida]
carpeta = 'salida'
base_datos = 'estado/estado.db'

[log]
archivo = 'logs/proceso.log'
nivel = 'INFO'
max_bytes = 5242880
copias = 5
```

Valores por defecto en dataclasses inmutables; el TOML los sobreescribe; se valida todo al arrancar (tipos, rangos, `max_intentos >= 1`) y se falla rápido con mensaje claro. Las credenciales futuras irían en variables de entorno, nunca en el TOML.

## 10. Logging (`logging_setup.py`)

- `logging` estándar: `RotatingFileHandler` más consola. Formato de texto: marca de tiempo, nivel, módulo y mensaje con pares `clave=valor` (`id=42 estado=OK intentos=1`).
- INFO: inicio (archivo, `hash8`, ruta del config y `url_base`), resultado de cada id, resumen final. WARNING: cada intento fallido y avisos de entrada. ERROR: cada id que termina en `ERROR_TECNICO` y los errores fatales (con traceback). La configuración completa se registra en DEBUG.
- Nunca se registran cuerpos de respuesta: son datos de cuentas médicas. Solo id, estado, causa e intentos.

## 11. Flujo, resumen y códigos de salida

Flujo de `pipeline.py` (secuencial):

1. Cargar configuración y configurar el log.
2. Leer el archivo, calcular el hash y parsear (3.1).
3. Normalizar y deduplicar (3.2).
4. Abrir el repositorio y `cargar_filas` en una transacción.
5. Obtener `pendientes`; contar como «reutilizados» los ids ya resueltos con la API en ejecuciones anteriores (`OK` y `NO_ENCONTRADO`). `DATO_INVALIDO` nunca se consulta y no cuenta.
6. Para cada pendiente: resolver con reintentos (sección 5), `guardar` y commit; pausa configurable entre consultas. Excepción inesperada: sección 4.
7. Generar el Excel desde la base (siempre).
8. Construir el resumen y mostrarlo en consola y log.
9. Calcular el código de salida.

Resumen de la ejecución (consola y log, misma plantilla): archivo y `hash8`; el Excel muestra el hash completo. Incluye entrada (líneas con datos, en blanco, repeticiones ignoradas con sus ids y conteos, ids únicos); resultado por estado; errores técnicos por causa; solo esta ejecución (consultados, reutilizados, reintentos totales, duración); ruta del Excel.

| Salida | Significado |
| --- | --- |
| 0 | Terminó y no queda nada por resolver (NO\_ENCONTRADO y DATO\_INVALIDO son resultados de negocio) |
| 1 | Terminó, pero quedan `ERROR_TECNICO` o `PENDIENTE`; el Excel se genera completo, con esas filas incluidas, y conviene relanzar |
| 2 | Fallo fatal: configuración inválida, CSV ausente o ilegible, columna ausente, error de base de datos o del Excel, o cualquier excepción no controlada |

`cli.py` captura `Exception` en el nivel superior, registra el traceback y devuelve 2. `__main__.py` llama a `sys.exit(main())`. Interfaz: `python -m cuentas_pipeline --input ruta/cuentas.csv [--config config.toml]`.

## 12. Pruebas mínimas (`pytest`)

- `test_normalize.py`: el CSV del reto produce los ids únicos esperados, con `apariciones` correctas; conserva `valor_original` tal como llega (para la línea ` 23`, el valor es `" 23"`) y solo normaliza el id a `23`; el parser quita las comillas de `"42"`; línea en blanco ignorada y `abc` como `DATO_INVALIDO`.
- `test_resolve.py` (cliente falso, `sleep` registrado): un 404 se resuelve en un solo intento; un 500 seguido de 200 termina en `OK`; un 429 respeta `Retry-After`; un timeout repetido agota los intentos y queda en `ERROR_TECNICO`; la espera crece y respeta el techo.
- `test_pipeline.py` (SQLite en carpeta temporal y cliente falso): una segunda ejecución hace cero llamadas; los `ERROR_TECNICO` se reintentan al relanzar; una excepción inesperada en un id no detiene a los demás; el Excel tiene una fila por id único; una celda con texto que empieza por `=` queda como texto.

## 13. Orden de implementación

- P0 (imprescindible): commits 1 a 14, 16 y 18 (estructura, modelos, configuración, lectura, normalización, cliente, clasificación y reintentos, repositorio, pipeline, CLI y logging, Excel de resultados, resumen en consola y log, README, runbook y plantilla de bitácora).
- P1: commit 17 (hoja `Resumen` del Excel) y los tests que acompañan a cada commit; si falta tiempo, son lo primero que se recorta después de P2.
- P2: commit 15 (colores y formato del Excel) y `ejemplo_salida/`.

### Commits atómicos

Cada commit deja `pytest` y `ruff` en verde. El test de cada pieza se escribe en su mismo commit, no al final.

| # | Mensaje del commit | Contenido | Test |
| --- | --- | --- | --- |
| 1 | `chore: estructura del paquete` | `pyproject.toml`, `.gitignore`, configuración de `ruff`, carpetas vacías |  |
| 2 | `feat(core): estados, causas y modelos` | `Estado`, `Causa`, `FilaCuenta`, `Resultado`, `ResumenEjecucion` |  |
| 3 | `feat(config): configuración validada` | dataclasses con validación y `config.toml` |  |
| 4 | `chore: añade cuentas.csv del reto` | archivo byte a byte, comprobado con `cat -A` |  |
| 5 | `feat(adapters): lector de CSV` | bytes, SHA-256, decodificación y encabezado |  |
| 6 | `feat(steps): normalización y deduplicación` | reglas de la sección 3.2 | `test_normalize.py` |
| 7 | `feat(adapters): cliente HTTP` | un GET con timeouts |  |
| 8 | `feat(steps): clasificación de respuestas` | la tabla de la sección 5 | primera parte de `test_resolve.py` |
| 9 | `feat(steps): reintentos con backoff` | espera con jitter, `Retry-After` y `sleep` inyectado | segunda parte de `test_resolve.py` |
| 10 | `feat(adapters): repositorio, esquema y carga` | DDL, pragmas, `cargar_filas`, `pendientes` |  |
| 11 | `feat(adapters): repositorio, guardado y consultas` | `guardar`, `filas`, `conteos` |  |
| 12 | `feat: pipeline sin Excel` | flujo con `try/except` por id y reanudación | `test_pipeline.py`: idempotencia, reanudación y fallo inesperado |
| 13 | `feat: CLI, logging y códigos de salida` | `argparse`, `logging_setup`, salidas 0, 1 y 2 |  |
| 14 | `feat(adapters): Excel, hoja Resultados` | escritura atómica y anti-inyección | comprobaciones en `test_pipeline.py` |
| 15 | `feat(adapters): colores y formato del Excel` | relleno por estado, filtros y fila congelada |  |
| 16 | `feat(steps): resumen de la ejecución` | texto para consola y log |  |
| 17 | `feat(adapters): hoja Resumen` | estado del archivo en el Excel |  |
| 18 | `docs: README, runbook y bitácora` | puede dividirse en 2 o 3 commits: uso y configuración, decisiones y runbook, plantilla de bitácora |  |

### Paradas de revisión

El agente se detiene solo en cinco puntos:

1. Tras el commit 6, normalización: comparar con la sección 16 (20 líneas con datos, 1 en blanco, 17 ids únicos, 3 repeticiones ignoradas y `abc` como `DATO_INVALIDO`) y comprobar con `cat -A` que `cuentas.csv` está byte a byte como el enunciado.
2. Tras el commit 9, clasificación y reintentos: es la lógica que más pesa en la evaluación y la que más pueden pedir cambiar en vivo.
3. Tras el commit 13, primera ejecución real contra la API (todavía sin Excel): comprobar que `0`, `101` y `150` dan 404 y hacer las pruebas manuales de dos ejecuciones seguidas y de Ctrl+C a mitad.
4. Tras el commit 17, Excel y resumen completos.
5. Al terminar: README, runbook y plantilla de bitácora.

Instrucción al agente: detente para revisión solo después de los commits 6, 9, 13 y 17 y al terminar. Antes de cada parada, muestra cómo ejecutar lo construido hasta ese punto. Si algo de la spec es ambiguo o crees que está mal, dilo antes de decidir (sección 0).

## 14. README y runbook

Contenido obligatorio: 1) qué hace, con el flujo en una línea y un enlace a `BITACORA.md`; 2) requisitos; 3) instalación; 4) tabla de configuración con significado y valores por defecto; 5) ejecución, con ejemplo de cron y del Programador de tareas; 6) salidas: columnas del Excel, base de datos, log y códigos de salida; 7) decisiones de diseño, empezando por los repetidos (3.3), y luego la frontera de reintentos (sección 5), idempotencia y reanudación, el 404 definitivo, la ausencia de cortacircuitos y el log sin cuerpos; 8) runbook; 9) cómo correr los tests; 10) «Pendiente y por qué» (lo fuera de alcance de la sección 1, retención de archivos y los límites conocidos), que es la última sección.

Runbook de las 3 a.m. Primeros cinco minutos: mirar el código de salida y las últimas líneas del log (resumen final).

| Síntoma | Causa probable | Acción |
| --- | --- | --- |
| Salida 2: archivo no encontrado | No llegó el CSV | Avisar al responsable de la clínica; no relanzar |
| Salida 2: falta la columna o el archivo no se lee | Cambió el formato | No relanzar ni editar el archivo; escalar |
| Salida 2: configuración inválida | Error en `config.toml` | Leer el mensaje, corregir, relanzar |
| Salida 1 con TIMEOUT o CONEXION | API o red caída | Esperar y relanzar (retoma) |
| Salida 1 con HTTP\_429 | Límite de peticiones | Relanzar más tarde o subir la espera |
| Salida 1 con HTTP\_4XX | URL o petición mal configurada | Corregir la configuración antes de relanzar |
| Salida 1 con RESPUESTA\_INVALIDA | Proxy o cambio en la API | Revisar una respuesta a mano y escalar |
| ERROR\_INESPERADO en el log | Bug | Guardar el traceback y escalar; el resto del Excel es válido |
| Excel no se genera | Archivo abierto, permisos o disco | Liberar el recurso y relanzar (se regenera desde la base) |
| Ejecución mucho más larga de lo normal | API lenta | Dejar terminar, o cortar y relanzar |

Reglas: relanzar siempre es seguro; no editar el CSV a mano (el hash cambia y se reconsulta todo); no borrar la base salvo último recurso (se reconsulta todo, sin corrupción); incluir consultas SQLite útiles (pendientes por archivo y conteo por estado y causa); sección de escalamiento con contacto por rellenar.

## 15. Bitácora y entrega

- `BITACORA.md`: el agente crea solo la plantilla con cuatro encabezados: 1) herramienta de IA y para qué partes; 2) dos o tres prompts útiles, tal cual; 3) algo que la IA entregó mal o incompleto y cómo se dio cuenta; 4) qué decidió el autor sin consultarle. Sin ese archivo no califican el reto.
- Repositorio: `README.md`, `BITACORA.md`, `cuentas.csv`, `config.toml`, `pyproject.toml`, `.gitignore` (`.venv`, estado, salidas, logs), `src/`, `tests/` y, opcional, `ejemplo_salida/`.
- `cuentas.csv` debe quedar byte a byte como el enunciado: la línea 4 empieza con un espacio (`  23 `) y hay una línea vacía entre `58` y `88`. Verificar con `cat -A cuentas.csv` y evitar que el editor recorte espacios.
- La entrega es el enlace al repositorio Git; comprobar que sea accesible.

## 16. Aceptación y resultado esperado

Con `cuentas.csv`: 20 líneas con datos, 1 línea en blanco, 17 ids únicos (16 válidos y `abc`), 3 repeticiones ignoradas (`7` ×3, `12` ×2). Se espera: 13 `OK`, 3 `NO_ENCONTRADO` (`0`, `101`, `150`; verificar en la primera ejecución real porque se asume que la API solo tiene posts del 1 al 100) y 1 `DATO_INVALIDO`.

Pruebas manuales:

- Correr dos veces seguidas: la segunda no hace llamadas a la API y el Excel mantiene el mismo número de filas.
- Interrumpir con Ctrl+C a mitad y relanzar: retoma sin repetir lo resuelto.
- Apuntar `url_base` a un host inexistente: todos quedan en `ERROR_TECNICO` (CONEXION), el proceso termina y sale con 1; al corregir y relanzar se resuelven.
- Dejar el Excel abierto en Windows durante una ejecución: sale con 2 y la base queda intacta.
- Reemplazar el CSV por otro contenido: se trata como archivo nuevo (otro hash y otro Excel).
