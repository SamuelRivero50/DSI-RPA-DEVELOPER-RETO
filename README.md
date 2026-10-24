# Consolidación diaria de cuentas médicas

Proceso desatendido de madrugada que lee el CSV diario de cuentas médicas, consulta la API por cada identificador y deja un Excel consolidado para auditoría. No modifica el CSV de entrada y ningún identificador que falle detiene el proceso.

Flujo en una línea: **CSV → SHA-256 → normalización y deduplicación → estado en SQLite → consulta a la API con reintentos → Excel → resumen en consola y log**.

Una ejecución es cada vez que se lanza el programa. Las decisiones, los prompts usados y los errores detectados durante el desarrollo están en [BITACORA.md](BITACORA.md).

Con `cuentas.csv` el resultado esperado es: 20 líneas con datos, 1 línea en blanco, 17 ids únicos, 3 repeticiones ignoradas (`7` ×3 y `12` ×2), 13 `OK`, 3 `NO_ENCONTRADO` (`0`, `101` y `150`), 1 `DATO_INVALIDO` y salida `0`.

## Requisitos

- Python 3.11 o superior (probado con 3.12).
- `requests` y `openpyxl` como dependencias de ejecución; `pytest` y `ruff` para desarrollo.
- Acceso de red a la API configurada.
- SQLite viene incluido en la biblioteca estándar de Python.
- Permisos de escritura en la carpeta de salida, la base de datos y el log.

## Instalación

Linux / macOS:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
```

Windows PowerShell:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

Para una instalación solo de ejecución:

```bash
python -m pip install -e .
```

Comprobar que la CLI responde:

```bash
python -m cuentas_pipeline --help
```

## Configuración

La configuración vive en `config.toml` y se valida completa al arrancar. Las rutas relativas se resuelven desde el directorio de trabajo, así que conviene lanzar el proceso desde la raíz del proyecto o usar rutas absolutas. `--input` sustituye a `entrada.archivo` sin modificar el TOML.

| Sección | Clave | Significado | Por defecto |
| --- | --- | --- | --- |
| `entrada` | `archivo` | Ruta del CSV de entrada; `--input` la sobrescribe. | `cuentas.csv` |
| `entrada` | `columna` | Nombre de la columna que contiene el identificador. | `id_cuenta` |
| `entrada` | `codificacion` | Codificación usada para decodificar el CSV. | `utf-8-sig` |
| `api` | `url_base` | URL base de los posts; se consulta `{url_base}/{id}`. | `https://jsonplaceholder.typicode.com/posts` |
| `api` | `timeout_conexion_s` | Timeout de conexión en segundos. | `5` |
| `api` | `timeout_lectura_s` | Timeout de lectura en segundos. | `10` |
| `api` | `pausa_entre_consultas_s` | Espera entre ids pendientes durante la ejecución. | `0` |
| `reintentos` | `max_intentos` | Peticiones totales por id, incluida la inicial. | `4` |
| `reintentos` | `espera_base_s` | Base de la espera exponencial. | `1.0` |
| `reintentos` | `factor` | Factor de crecimiento de la espera. | `2.0` |
| `reintentos` | `espera_maxima_s` | Techo de la espera exponencial. | `30.0` |
| `reintentos` | `retry_after_maximo_s` | Techo aplicado a un `Retry-After` recibido. | `60.0` |
| `salida` | `carpeta` | Carpeta donde se genera el Excel. | `salida` |
| `salida` | `base_datos` | Ruta del archivo SQLite de estado. | `estado/estado.db` |
| `log` | `archivo` | Ruta del log rotativo. | `logs/proceso.log` |
| `log` | `nivel` | Nivel mínimo: `DEBUG`, `INFO`, `WARNING`, `ERROR` o `CRITICAL`. | `INFO` |
| `log` | `max_bytes` | Tamaño máximo de cada archivo de log. | `5242880` |
| `log` | `copias` | Número de archivos rotados que se conservan. | `5` |

La validación rechaza secciones o claves desconocidas, tipos incorrectos, timeouts no positivos, `max_intentos < 1`, `factor < 1`, niveles de log inválidos y codificaciones desconocidas. Un fallo de configuración termina con salida `2` y un mensaje claro.

## Ejecución

Ejecución manual:

```bash
python -m cuentas_pipeline --input cuentas.csv --config config.toml
```

Si se omite `--input`, se usa `entrada.archivo` del TOML. Si se omite `--config`, se usa `config.toml`.

Ejemplo de cron para las 3:00, ejecutando desde la raíz del proyecto:

```cron
0 3 * * * cd /opt/cuentas-pipeline && .venv/bin/python -m cuentas_pipeline --input /datos/cuentas.csv --config config.toml >> logs/cron.log 2>&1
```

En el Programador de tareas de Windows, crear una tarea diaria a las 3:00 con:

- **Programa o script:** `C:\cuentas-pipeline\.venv\Scripts\python.exe`
- **Argumentos:** `-m cuentas_pipeline --input C:\datos\cuentas.csv --config config.toml`
- **Iniciar en:** `C:\cuentas-pipeline`

El proceso es secuencial. La pausa configurada se aplica entre ids pendientes, no entre reintentos.

## Salidas

### Excel

Se escribe siempre al final de la ejecución, aunque queden pendientes, en `salida/consolidado_<YYYY-MM-DD>_<hash8>.xlsx`. La fecha es la de la primera carga del archivo (`MIN(creado_en)`) y `hash8` son los primeros ocho caracteres del SHA-256 del contenido. El archivo se escribe en un temporal de la misma carpeta y se reemplaza con `os.replace`, de modo que nunca queda un Excel a medias.

En Windows el Excel de destino debe estar cerrado al ejecutar. Si está abierto, `os.replace` no puede reemplazarlo: la ejecución termina con código `2` y el estado ya confirmado en SQLite no se pierde; al cerrarlo y relanzar se regenera el Excel (comportamiento esperado en Windows; no verificado en el entorno Linux de desarrollo).

Hoja `Resultados`, una fila por id único y ordenada por línea de origen. El orden real de columnas y encabezados visibles es:

| Orden | Encabezado visible | Contenido |
| --- | --- | --- |
| 1 | `Línea origen` | Línea del CSV (la cabecera es la 1). |
| 2 | `Valor original` | Campo tal como lo entrega el parser, sin normalizar; las comillas de `"42"` ya las quitó el parser. |
| 3 | `ID cuenta` | Entero si el id es válido; vacío si es inválido. |
| 4 | `Estado` | `PENDIENTE`, `OK`, `NO_ENCONTRADO`, `DATO_INVALIDO` o `ERROR_TECNICO`. |
| 5 | `Causa` | Causa del estado, cuando aplica; vacía en `OK` y `PENDIENTE`. |
| 6 | `Apariciones` | Veces que aparece el id en el CSV. |
| 7 | `Intentos` | Peticiones HTTP realizadas para ese id; `0` si no se consultó. |
| 8 | `Detalle del error` | Detalle técnico, cuando aplica. |
| 9 | `Consultado en` | Última actualización (`actualizado_en`), mostrada como `AAAA-MM-DD HH:MM:SS` en hora local, sin `T` ni zona; en SQLite se guarda en ISO-8601 con zona. |
| 10 | `ID usuario` | `userId` de la API. |
| 11 | `Título` | `title` de la API. |
| 12 | `Cuerpo` | `body` de la API, sin ajuste de línea. |

Formato de `Resultados`: encabezado de altura 28 con banda oscura (`404040`), texto blanco en negrita, centrado y con ajuste de línea; autofiltro; anchos fijos 12, 16, 11, 18, 22, 13, 10, 24, 20, 12, 40 y 70; filas de datos de altura 20, alineación vertical centrada y sin ajuste de línea en `Título` ni `Cuerpo`. Las columnas `Línea origen`, `ID cuenta`, `Apariciones`, `Intentos` e `ID usuario` se centran y el resto queda a la izquierda. La celda `Estado` lleva el color de estado: verde claro para `OK`, amarillo para `NO_ENCONTRADO`, naranja para `DATO_INVALIDO`, rojo claro para `ERROR_TECNICO` y gris para `PENDIENTE`; las filas con estado distinto de `OK` llevan además un relleno suave de la misma familia, y las `OK` no llevan relleno de fila. Panel congelado en `D2`; impresión horizontal ajustada a una página de ancho con la fila 1 repetida; al abrir el archivo queda activa `Resultados`.

Todo texto de origen externo se escribe como texto; si empieza por `=`, `+`, `-` o `@` se fuerza `cell.data_type = 's'` para evitar inyección de fórmulas.

Hoja `Resumen`, derivada de la base de datos:

- Título «Resumen del archivo».
- Bloque Archivo: `Nombre`, `Hash`, `Primera carga` y `Generado en`.
- Bloque Entrada: `Líneas con datos`, `Líneas en blanco ignoradas`, `Repeticiones ignoradas` e `Identificadores únicos`.
- Bloque Resultado por estado: tabla `Estado`/`Total` con los cinco estados y una fila `Total`.
- Bloque Errores técnicos por causa: tabla `Causa`/`Total`, o «Sin errores técnicos» si no hay ninguno.
- Bloque Repetidos: tabla `Id`/`Apariciones`, o «Sin repetidos» si no hay ninguno.

### Base de datos

`estado/estado.db` es SQLite con una sola tabla, `resultados`, cuya clave primaria es `(archivo_hash, id)`. Usa `journal_mode=WAL` y `synchronous=FULL`; cada id resuelto se confirma en su propia transacción. Toda consulta filtra por `archivo_hash`, de modo que un CSV distinto se trata como un archivo nuevo.

### Log

`logs/proceso.log` es rotativo: cada archivo puede llegar a `max_bytes` y se conservan hasta `copias` archivos rotados, además del actual. También se escribe en consola. Registra el inicio, el resultado de cada id, cada intento fallido y el resumen final. Los cuerpos de las respuestas son datos médicos y no se escriben nunca en el log.

Salida real de una ejecución con el estado ya resuelto:

```text
==============================================================
 RESUMEN DE LA EJECUCIÓN
==============================================================
 Archivo : cuentas.csv  (hash 5d797c34)
 Excel   : salida/consolidado_2026-10-24_5d797c34.xlsx

 ENTRADA
   Líneas con datos .............  20
   Líneas en blanco ignoradas ...   1
   Repeticiones ignoradas .......   3   (7 x3, 12 x2)
   Identificadores únicos .......  17

 RESULTADO POR ESTADO
   OK ...........................  13
   NO_ENCONTRADO ................   3
   DATO_INVALIDO ................   1
   ERROR_TECNICO ................   0
   PENDIENTE ....................   0
   Total ........................  17

 ERRORES TÉCNICOS POR CAUSA
   (ninguno)

 ESTA EJECUCIÓN
   Consultados ..................   0
   Reutilizados .................  16
   Reintentos ...................   0
   Duración .....................  0.09 s
==============================================================
```

`consultados` cuenta los ids únicos que esta ejecución intentó resolver, incluidos los que terminaron en `ERROR_TECNICO`. `reutilizados` cuenta solo las consultas evitadas: ids que ya estaban `OK` o `NO_ENCONTRADO` en ejecuciones anteriores. Los `DATO_INVALIDO` no se consultan ni se cuentan como reutilizados, y los `ERROR_TECNICO` se vuelven a consultar. `reintentos` suma los intentos adicionales al primero y `duración` mide el pipeline: normalización, consultas, pausas y generación del Excel.

### Códigos de salida

| Código | Significado |
| --- | --- |
| `0` | Terminó y no queda nada pendiente. `NO_ENCONTRADO` y `DATO_INVALIDO` son resultados de negocio. |
| `1` | Terminó, pero quedan `ERROR_TECNICO` o `PENDIENTE`; conviene relanzar. El Excel se genera igualmente. |
| `2` | Fallo fatal: configuración inválida, CSV ausente o ilegible, columna ausente, error de base de datos o del Excel, o cualquier excepción no controlada. |

## Decisiones de diseño

### Repetidos

Se consulta y se escribe **una sola fila por id único**, con la columna `apariciones`. El id es la clave de negocio y la API es determinista, así que reconsultar no aporta; una fila por id mantiene la clave única y hace trivial la idempotencia. El conteo se conserva para auditoría, pero no se interpreta: un repetido no implica por sí mismo un doble cobro, puede ser un error de origen o una re-radicación. Se descartaron consultar y escribir cada ocurrencia (duplica trabajo y filas) y deduplicar en silencio (pierde trazabilidad).

### Qué se reintenta y qué no

**Dentro de la ejecución** (hasta `max_intentos` intentos por id, con espera exponencial con jitter parcial, con techo, y respetando `Retry-After`): se reintenta lo que puede cambiar al volver a preguntar, es decir, timeouts, errores de conexión, 5xx, 429 y respuestas corruptas o sin el id esperado. No se reintenta lo determinista: un 404, un dato inválido, cualquier otro 4xx (por ejemplo, una petición mal formada), un error inesperado ni un código HTTP fuera de la tabla (1xx, 3xx, 2xx distintos de 200), que se clasifica como `ERROR_INESPERADO` con el código en `detalle_error`.

**Entre ejecuciones**: todo `ERROR_TECNICO` se vuelve a intentar en la siguiente ejecución, incluidos los que no se reintentaron dentro de la ejecución. Solo `OK`, `NO_ENCONTRADO` y `DATO_INVALIDO` son finales.

Dos matices que conviene tener presentes:

- Un timeout de conexión se clasifica como `TIMEOUT`: la comprobación de `requests.exceptions.Timeout` va antes que la de `ConnectionError`, así que `ConnectTimeout` no cae en `CONEXION`.
- `Retry-After` se respeta en cualquier respuesta reintentable, no solo en 429. Si es inválido o negativo, se ignora y se usa la espera exponencial normal; si es válido, se limita a `retry_after_maximo_s`.

| Situación | ¿Reintenta dentro de la ejecución? | Estado | Causa |
| --- | --- | --- | --- |
| 200 con JSON válido y el `id` esperado | No aplica | `OK` | — |
| 404 | No | `NO_ENCONTRADO` | `HTTP_404` |
| `Timeout` (incluido `ConnectTimeout`) | Sí | `ERROR_TECNICO` | `TIMEOUT` |
| `ConnectionError` | Sí | `ERROR_TECNICO` | `CONEXION` |
| Cualquier 5xx | Sí | `ERROR_TECNICO` | `HTTP_5XX` |
| 429 | Sí | `ERROR_TECNICO` | `HTTP_429` |
| 200 sin JSON válido, JSON que no es objeto o `id` distinto | Sí | `ERROR_TECNICO` | `RESPUESTA_INVALIDA` |
| Cualquier otro 4xx | No | `ERROR_TECNICO` | `HTTP_4XX` |
| Otra excepción de `requests` | No | `ERROR_TECNICO` | `ERROR_INESPERADO` |
| HTTP 1xx, 3xx o 2xx distinto de 200 | No | `ERROR_TECNICO` | `ERROR_INESPERADO` |
| Excepción no relacionada con `requests` durante la resolución | No | `ERROR_TECNICO` | `ERROR_INESPERADO` |
| Valor no válido en el CSV | No se consulta | `DATO_INVALIDO` | `FORMATO_INVALIDO` |

### Idempotencia y reanudación

La identidad del archivo es su SHA-256. La primera carga inserta los ids con `INSERT OR IGNORE`; las siguientes ejecuciones solo procesan `PENDIENTE` y `ERROR_TECNICO`, y el Excel se regenera siempre desde la base. Relanzar es seguro: no se duplican filas ni se reconsulta lo ya resuelto. Cada id se confirma al terminar, así que un Ctrl+C o un corte dejan el estado consistente y la ejecución siguiente retoma donde quedó.

**Supuesto:** se asume que el archivo de cada día tiene contenido distinto. Si llegara uno idéntico a otro ya procesado, tendría el mismo hash: no se reconsultaría nada y el Excel conservaría el nombre de la primera carga. Una mejora futura sería incluir la fecha de recepción en la identidad del archivo.

### 404 definitivo (supuesto)

**Supuesto:** un 404 se trata como resultado definitivo (`NO_ENCONTRADO`) y no se reconsulta. La API de ejemplo es estática y el requisito de reanudación pide no volver a preguntar lo resuelto. En un sistema con replicación o altas posteriores un 404 podría ser transitorio; si eso cambiara, habría que revisar esta decisión y la política de reutilización.

### Sin cortacircuitos

No hay cortacircuitos ni límite global de fallos: cada id agota su propio ciclo de reintentos y el proceso continúa con el siguiente.

- Cada id se procesa de forma independiente. Por eso, con la API completamente caída, la ejecución dura lo que tarden todos los ids en agotar sus reintentos. Con la configuración por defecto, el orden de magnitud esperado es de unos 5 segundos por id si la conexión se rechaza al instante, y de unos 45 segundos si la API no responde (timeouts); no se ha medido contra una API caída en esta entrega. Crece linealmente con el número de ids.
- Se acepta porque es la lectura literal de «ningún identificador que falle detiene el proceso» y no se pierde ningún dato: todo lo que se consulta queda como `ERROR_TECNICO`, la ejecución termina con código `1` y al relanzar retoma.
- Se puede reducir sin tocar código con `max_intentos`, `timeout_lectura_s` y `espera_maxima_s`, además del resto de parámetros de `[reintentos]`.
- Mejora futura: un cortacircuitos que deje de reintentar tras N fallos seguidos pero siga procesando el resto.

### Log sin datos clínicos

El log registra id, estado, causa e intentos, pero nunca los cuerpos de las respuestas: son datos médicos. El Excel y la base sí contienen esos datos y deben tratarse como información sensible: permisos restringidos y una política de retención definida.

### Otras decisiones

- Los datos inválidos se auditan: aparecen en el Excel como `DATO_INVALIDO` y no se envían a la API.
- Configuración fuera del código, en TOML, validada antes de tocar el CSV.
- El Excel se regenera completo desde SQLite y se reemplaza de forma atómica.
- Protección contra inyección de fórmulas: todo texto externo que empieza por `=`, `+`, `-` o `@` se escribe con `cell.data_type = 's'`.

## Runbook de las 3:00

Primeros cinco minutos:

Códigos de salida: `0` no queda nada pendiente; `1` quedan `ERROR_TECNICO` o `PENDIENTE`; `2` fallo fatal. El detalle está en [Códigos de salida](#códigos-de-salida).

1. Mirar el código de salida del proceso.
2. Leer las últimas líneas de `logs/proceso.log`; el resumen final resume entrada, estados, causas, consultas y ruta del Excel.
3. Si la salida es `2`, localizar el error fatal en el log y no relanzar hasta corregir la causa.
4. Si la salida es `1`, identificar las causas técnicas y decidir si conviene relanzar.
5. No editar el CSV ni borrar la base como primera medida.

| Síntoma | Causa probable | Acción |
| --- | --- | --- |
| Salida 2: archivo no encontrado | No llegó el CSV | Avisar al responsable de la clínica; no relanzar |
| Salida 2: falta la columna o el archivo no se lee | Cambió el formato | No relanzar ni editar el archivo; escalar |
| Salida 2: configuración inválida | Error en `config.toml` | Leer el mensaje, corregir, relanzar |
| Salida 1 con `TIMEOUT` o `CONEXION` | API o red caída | Esperar y relanzar (retoma) |
| Salida 1 con `HTTP_429` | Límite de peticiones | Relanzar más tarde o subir la espera |
| Salida 1 con `HTTP_4XX` | URL o petición mal configurada | Corregir la configuración antes de relanzar |
| Salida 1 con `RESPUESTA_INVALIDA` | Proxy o cambio en la API | Revisar una respuesta a mano y escalar |
| Salida 1 con `ERROR_INESPERADO` (o en el log) | Bug o respuesta HTTP fuera de la tabla | Guardar el traceback y escalar; el resto del Excel es válido |
| Salida 2: el Excel no se genera | Archivo abierto, permisos o disco | Liberar el recurso y relanzar (se regenera desde la base) |
| Ejecución mucho más larga de lo normal | API lenta | Dejar terminar, o cortar y relanzar |

Reglas:

- Relanzar siempre es seguro.
- No editar el CSV a mano: cambia el hash y se reconsulta todo.
- No borrar la base salvo último recurso: se reconsulta todo, sin corrupción.
- Si el Excel está abierto en Windows, `os.replace` falla y la ejecución sale con `2`; la base ya está confirmada y se puede regenerar al liberar el archivo.

Consultas SQLite útiles (sustituir `<hash>` por el valor del resumen):

```sql
-- Archivos conocidos y su primera carga
SELECT archivo_nombre, archivo_hash, MIN(creado_en) AS primera_carga, COUNT(*) AS ids
FROM resultados
GROUP BY archivo_hash, archivo_nombre
ORDER BY primera_carga;

-- Conteo por estado
SELECT estado, COUNT(*)
FROM resultados
WHERE archivo_hash = '<hash>'
GROUP BY estado;

-- Errores técnicos por causa
SELECT causa, COUNT(*)
FROM resultados
WHERE archivo_hash = '<hash>' AND estado = 'ERROR_TECNICO'
GROUP BY causa;

-- Pendientes y errores que se reintentarán en la próxima ejecución
SELECT id, linea_origen, causa, intentos, detalle_error
FROM resultados
WHERE archivo_hash = '<hash>' AND estado IN ('PENDIENTE', 'ERROR_TECNICO')
ORDER BY linea_origen;

-- Repetidos del archivo
SELECT id, apariciones
FROM resultados
WHERE archivo_hash = '<hash>' AND apariciones > 1
ORDER BY apariciones DESC, id;
```

Escalamiento: [CONTACTO]. Completar con el nombre, teléfono y correo del contacto de guardia o del dueño del proceso.

## Tests

La suite usa clientes falsos, SQLite temporal y no llama a la API real:

```bash
.venv/bin/pytest -q
.venv/bin/ruff check .
```

En Windows:

```powershell
.venv\Scripts\pytest -q
.venv\Scripts\ruff check .
```

Los tests cubren lectura y normalización del CSV, clasificación y reintentos, repositorio, pipeline (idempotencia, reanudación, Excel y hoja Resumen), configuración, CLI, logging y modelos.

## Pendiente y por qué

Fuera de alcance en esta entrega:

- Otros formatos de CSV. Solo se contempla una columna de identificadores localizada por el encabezado configurado; si la columna no aparece, el proceso falla con salida `2`. No se adivinan codificaciones ni delimitadores.
- Concurrencia. El proceso es secuencial y no bloquea una segunda instancia; dos ejecuciones simultáneas pueden competir por la base y el Excel.
- Cortacircuitos. Hoy cada id agota su propio ciclo; una mejora futura sería dejar de reintentar tras N fallos seguidos sin detener el resto de ids.
- Bloqueo de instancia única. Evitaría que dos procesos compitan por la misma base y el mismo Excel.
- Interfaces formales (ports y adapters). Las dependencias se inyectan como parámetros; no se usan `Protocol` ni clases abstractas.
- 404 transitorios. Se asume la API estática; ver la decisión sobre el 404 definitivo.
- Purga automática de datos viejos.
- Identidad por contenido. La identidad actual es el SHA-256 del contenido: un archivo idéntico a otro ya procesado conservaría el hash, no reconsultaría nada y reutilizaría el nombre de la primera carga. Una mejora futura sería incluir la fecha de recepción en la identidad del archivo.

Retención: los logs rotan, pero el Excel y la base de datos se acumulan. No hay limpieza automática; hay que definir una política de retención y archivado según las necesidades de auditoría y privacidad. Mientras no exista, revisar el espacio en disco y no borrar la base sin confirmar que se puede reconsultar todo.

Límites conocidos:

- Solo se aceptan ids con dígitos ASCII; `-5`, `3.5` o `abc` se auditan como `DATO_INVALIDO` y no se consultan. Los ceros a la izquierda se normalizan (`007` → `7`).
- La ausencia de un id en la API se interpreta como 404 definitivo.
- El proceso es secuencial y no bloquea una segunda instancia; dos ejecuciones simultáneas pueden competir por la base y el Excel.
- Si el CSV cambia, se trata como un archivo nuevo y se consulta de nuevo todo.
- El log no contiene cuerpos, pero el Excel y SQLite sí; su acceso debe restringirse.
