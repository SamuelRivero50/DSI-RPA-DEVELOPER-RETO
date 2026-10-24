# Consolidación diaria de cuentas médicas

Proceso desatendido de madrugada que lee el CSV diario de cuentas médicas, consulta la API por cada identificador y deja un Excel consolidado para auditoría. No modifica el CSV de entrada y ningún identificador que falle detiene el proceso.

Flujo en una línea: **CSV → SHA-256 → normalización y deduplicación → estado en SQLite → consulta a la API con reintentos → Excel → resumen en consola y log**.

Las decisiones, los prompts usados y los errores detectados durante el desarrollo están en [BITACORA.md](BITACORA.md).

Con `cuentas.csv` el resultado esperado es: 20 líneas con datos, 1 línea en blanco, 17 ids únicos, 3 repeticiones ignoradas (`7` ×3 y `12` ×2), 13 `OK`, 3 `NO_ENCONTRADO` (`0`, `101` y `150`), 1 `DATO_INVALIDO` y salida `0`.

## Requisitos

- Python 3.11 o superior (probado con 3.12).
- `requests` y `openpyxl` como dependencias de ejecución; `pytest` y `ruff` para desarrollo.
- Acceso de red a la API configurada.
- SQLite viene incluido en la biblioteca estándar de Python.
- Permisos de escritura en la carpeta de salida, la base de datos y el log.

## Instalación

```bash
python -m venv .venv

# Linux / macOS
source .venv/bin/activate

# Windows PowerShell
.venv\Scripts\Activate.ps1

pip install -e ".[dev]"
```

Para una instalación solo de ejecución:

```bash
pip install -e .
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
| `api` | `pausa_entre_consultas_s` | Espera entre ids pendientes durante la corrida. | `0` |
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

Se escribe siempre al final de la corrida, aunque queden pendientes, en `salida/consolidado_<YYYY-MM-DD>_<hash8>.xlsx`. La fecha es la de la primera carga del archivo (`MIN(creado_en)`) y `hash8` son los primeros ocho caracteres del SHA-256 del contenido. El archivo se escribe en un temporal de la misma carpeta y se reemplaza con `os.replace`, de modo que nunca queda un Excel a medias.

Hoja `Resultados`, una fila por id único y ordenada por línea de origen:

| Columna | Contenido |
| --- | --- |
| `linea_origen` | Línea del CSV (la cabecera es la 1). |
| `valor_original` | Texto tal como lo entrega el parser. |
| `id_cuenta` | Entero si el id es válido; vacío si es inválido. |
| `estado` | `PENDIENTE`, `OK`, `NO_ENCONTRADO`, `DATO_INVALIDO` o `ERROR_TECNICO`. |
| `causa` | Causa del estado, cuando aplica. |
| `apariciones` | Veces que aparece el id en el CSV. |
| `user_id` | `userId` de la API. |
| `titulo` | `title` de la API. |
| `cuerpo` | `body` de la API, con ajuste de línea. |
| `intentos` | Peticiones HTTP realizadas para ese id. |
| `detalle_error` | Detalle técnico, cuando aplica. |
| `consultado_en` | Última actualización del registro, en ISO-8601 con zona horaria. |

La hoja tiene encabezado en negrita, fila congelada, autofiltro, anchos razonables y relleno por estado: verde claro para `OK`, amarillo para `NO_ENCONTRADO`, naranja para `DATO_INVALIDO`, rojo claro para `ERROR_TECNICO` y gris para `PENDIENTE`. Todo texto de origen externo se escribe como texto; si empieza por `=`, `+`, `-` o `@` se fuerza `cell.data_type = 's'` para evitar inyección de fórmulas.

Hoja `Resumen`, derivada de la base de datos:

- Archivo: nombre, hash, primera carga y fecha de generación.
- Entrada: líneas con datos, líneas en blanco ignoradas, repeticiones ignoradas e ids únicos.
- Resultado por estado.
- Errores técnicos por causa.
- Lista de ids repetidos y sus apariciones.

### Base de datos

`estado/estado.db` es SQLite con una sola tabla, `resultados`, cuya clave primaria es `(archivo_hash, id)`. Usa `journal_mode=WAL` y `synchronous=FULL`; cada id resuelto se confirma en su propia transacción. Toda consulta filtra por `archivo_hash`, de modo que un CSV distinto se trata como un archivo nuevo.

### Log

`logs/proceso.log` es rotativo (`max_bytes` × `copias`) y también se escribe en consola. Registra el inicio, el resultado de cada id, los reintentos y el resumen final. Los cuerpos de las respuestas no se escriben nunca en el log.

Ejemplo de resumen:

```text
archivo=cuentas.csv hash=5d797c34...
entrada: lineas_con_datos=20 lineas_en_blanco=1 repeticiones_ignoradas=3 ids_unicos=17
repetidos: 7 x3, 12 x2
resultado: PENDIENTE=0 OK=13 NO_ENCONTRADO=3 DATO_INVALIDO=1 ERROR_TECNICO=0
errores_tecnicos: ninguno
corrida: consultados=16 reutilizados=0 reintentos=0 duracion_s=0.05
excel=salida/consolidado_2026-10-23_5d797c34.xlsx
```

`reutilizados` cuenta los ids que ya estaban resueltos por la API (`OK` o `NO_ENCONTRADO`) antes de esta corrida. Los `DATO_INVALIDO` no se reconsultan ni se cuentan como reutilizados, y los `ERROR_TECNICO` se vuelven a consultar.

### Códigos de salida

| Código | Significado |
| --- | --- |
| `0` | Terminó y no queda nada pendiente. `NO_ENCONTRADO` y `DATO_INVALIDO` son resultados de negocio. |
| `1` | Terminó, pero quedan `ERROR_TECNICO` o `PENDIENTE`; conviene relanzar. El Excel se genera igualmente. |
| `2` | Fallo fatal: configuración inválida, CSV ausente o ilegible, columna ausente, error de base de datos o del Excel. |

## Decisiones de diseño

### Repetidos

Se consulta y se escribe **una sola fila por id único**, con la columna `apariciones`. El id es la clave de negocio y la API es determinista, así que reconsultar no aporta; una fila por id mantiene la clave única y hace trivial la idempotencia. El conteo se conserva para auditoría, pero no se interpreta: un repetido no implica por sí mismo un doble cobro, puede ser un error de origen o una re-radicación. Se descartaron consultar y escribir cada ocurrencia (duplica trabajo y filas) y deduplicar en silencio (pierde trazabilidad).

### Qué se reintenta y qué no

Se reintenta lo que puede cambiar al volver a preguntar: timeouts, errores de conexión, HTTP 5xx, HTTP 429 y respuestas corruptas o sin el id esperado. No se reintenta dentro de la corrida lo determinista: un 404, un dato inválido o un 4xx por una petición mal formada. Todo `ERROR_TECNICO` se vuelve a intentar en la siguiente ejecución. La espera es exponencial con jitter parcial, con techo, y respeta `Retry-After` cuando es válido.

### Idempotencia y reanudación

La identidad del archivo es su SHA-256. La primera carga inserta los ids con `INSERT OR IGNORE`; las siguientes corridas solo procesan `PENDIENTE` y `ERROR_TECNICO`, y el Excel se regenera siempre desde la base. Relanzar es seguro: no se duplican filas ni se reconsulta lo ya resuelto. Cada id se confirma al terminar, así que un Ctrl+C o un corte dejan el estado consistente y la corrida siguiente retoma donde quedó.

### 404 definitivo

Un 404 se trata como resultado definitivo (`NO_ENCONTRADO`) y no se reconsulta. La API de ejemplo es estática y el requisito de reanudación pide no volver a preguntar lo resuelto. En un sistema con replicación o altas posteriores un 404 podría ser transitorio; si eso cambiara, habría que revisar esta decisión y la política de reutilización.

### Sin cortacircuitos

No hay cortacircuitos ni límite global de fallos: cada id agota su propio ciclo de reintentos y el proceso continúa con el siguiente. Es la lectura literal de «ningún identificador que falle detiene el proceso». La contrapartida es que una API completamente caída tarda lo que tarden todos los ids en agotar sus reintentos.

### Log sin datos clínicos

El log registra id, estado, causa e intentos, pero nunca los cuerpos de las respuestas. El Excel y la base sí contienen esos datos y deben tratarse como información sensible: permisos restringidos y una política de retención definida.

### Otras decisiones

- Los datos inválidos se auditan: aparecen en el Excel como `DATO_INVALIDO` y no se envían a la API.
- Configuración fuera del código, en TOML, validada antes de tocar el CSV.
- El Excel se regenera completo desde SQLite y se reemplaza de forma atómica.

## Runbook de las 3:00

Primeros cinco minutos:

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
| `ERROR_INESPERADO` en el log | Bug | Guardar el traceback y escalar; el resto del Excel es válido |
| Excel no se genera | Archivo abierto, permisos o disco | Liberar el recurso y relanzar (se regenera desde la base) |
| Corrida mucho más larga de lo normal | API lenta | Dejar terminar, o cortar y relanzar |

Reglas:

- Relanzar siempre es seguro.
- No editar el CSV a mano: cambia el hash y se reconsulta todo.
- No borrar la base salvo último recurso: se reconsulta todo, sin corrupción.
- Si el Excel está abierto en Windows, `os.replace` falla y la corrida sale con `2`; la base ya está confirmada y se puede regenerar al liberar el archivo.

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

-- Pendientes y errores que se reintentarán en la próxima corrida
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

Escalamiento: completar con el contacto de guardia o el dueño del proceso (nombre, teléfono y correo). Mientras no exista, escalar al responsable técnico del repositorio.

## Pendiente y por qué

Fuera de alcance en esta entrega:

- Otros formatos de CSV. Solo se contempla una columna de identificadores localizada por el encabezado configurado; si la columna no aparece, el proceso falla con salida `2`. No se adivinan codificaciones ni delimitadores.
- Concurrencia, cortacircuitos, bloqueo de instancia única y puertos/adaptadores formales. El volumen diario no lo exige y añadirlos complicaría la explicación sin mejorar el resultado.
- 404 transitorios. Se asume la API estática; ver la decisión sobre el 404 definitivo.
- Purga automática de datos viejos.

Retención: los logs rotan, pero el Excel y la base de datos se acumulan. No hay limpieza automática; hay que definir una política de retención y archivado según las necesidades de auditoría y privacidad. Mientras no exista, revisar el espacio en disco y no borrar la base sin confirmar que se puede reconsultar todo.

Límites conocidos:

- Solo se aceptan ids con dígitos ASCII; `-5`, `3.5` o `abc` se auditan como `DATO_INVALIDO` y no se consultan. Los ceros a la izquierda se normalizan (`007` → `7`).
- La ausencia de un id en la API se interpreta como 404 definitivo.
- El proceso es secuencial y no bloquea una segunda instancia; dos ejecuciones simultáneas pueden competir por la base y el Excel.
- Si el CSV cambia, se trata como un archivo nuevo y se consulta de nuevo todo.
- El log no contiene cuerpos, pero el Excel y SQLite sí; su acceso debe restringirse.

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
