# Bitácora

## 1. Herramienta de IA y para qué partes

Usé **Claude** (modelo Sonnet 5.5, en el chat) y **Opencode** (con el modelo
DeepSeek V4.1 Flash Free).

- **Claude: razonamiento y diseño.** Yo tenía en mente un flujo de
  preprocesamiento de datos como los que vemos en la carrera. A partir de ahí le
  pedí a Claude que me diera opciones para cada decisión técnica (repetidos,
  estado, reintentos, estructura, Excel, logging, README y runbook), y yo
  validaba cada una antes de pasar a la siguiente. El resultado fue una
  especificación (`docs/SPEC.md`) que le pasé al agente de código. También lo
  usé para revisar los informes que me daba el agente en cada parada, para
  redactar los prompts de ajustes, para dudas de Git y para preparar un borrador
  de esta bitácora, que luego reescribí con mis palabras.
- **Opencode: implementación.** Le pasé la especificación y fui avanzando por
  etapas, con paradas de revisión. No tengo créditos de Opencode y los modelos
  gratuitos no razonan tan bien, así que aproveché su capacidad agéntica (su
  harness me parece muy bueno) y delegué el razonamiento a Claude.

## 2. Prompts útiles, tal cual

**Para fijar el método de trabajo:**

> Ese es el reto completo, yo voy a tomar las decisiones técnicas de la
> solución, pero me gustaría que me des opciones para tomar la mejor decisión
> posible siempre, yo evaluaré si lo que me dices es factible y es correcto, y
> si te doy el visto bueno entonces seguimos con la siguiente decisión. Al final
> vamos a tener un documento refinado para pasarle a otro agente y empezar a
> codificar la solución, me gusta seguir un enfoque de spec-driven development
> y seguir las mejores prácticas de Python.

**Para cuestionar una premisa de Claude (los repetidos):**

> pero no sé si el hecho de que aparezca varias veces ya nos indique que puede
> haber un doble cobro, al final del día al consultar la api esta nos va a
> devolver la información de un mismo id de cuenta, si se cobra de nuevo a un
> paciente, la cuenta no sería otra diferente?

**Para mejorar el diseño del estado:**

> si vamos a usar el hash para el estado, no sería poco eficiente tener una base
> de datos diferente por estado? no se puede manejar como una base de datos
> estado y tener una clave primaria compuesta? o qué opinas de eso?

## 3. Algo que la IA entregó mal o incompleto y cómo me di cuenta

- **Doble cobro.** Claude justificó la columna `apariciones` diciendo que un id
  repetido podía indicar un doble cobro. Me di cuenta razonando sobre qué es un
  número de cuenta: un nuevo cobro sería otra cuenta con otro número, así que la
  inferencia no tenía base. Se lo planteé y lo reconoció. La columna se mantuvo,
  pero solo por trazabilidad, sin interpretar la causa de la repetición.
- **Supuesto presentado como hecho.** Claude escribió que «el CSV de cada día
  es distinto», cuando el enunciado solo dice que llega un archivo cada día.
- **Alcance mal calibrado, en las dos direcciones.** Claude propuso cinco
  subpaquetes con interfaces (`Protocol`) para un reto de 4 horas, y después
  recortó los colores del Excel y la hoja Resumen para ahorrar tiempo. Me di
  cuenta por el límite de horas y porque, con IA, los colores y el Resumen casi
  no cuestan. Simplifiqué a tres carpetas (`core`, `steps`, `adapters`), dejé
  las interfaces como mejora futura y recuperé los colores y el Resumen.
- **Especificación incompleta.** La spec no cubría los códigos HTTP 1xx y 3xx y
  definía «reutilizados» contando también los datos inválidos, que nunca se
  consultan. El agente lo detectó y me preguntó antes de decidir. Elegí que
  «reutilizados» cuente solo las consultas evitadas, y que lo no previsto se
  clasifique como `ERROR_INESPERADO` sin reintento.
- **Un comando que podía borrar un archivo.** Claude me dio un `echo ... >
  .gitattributes`, que sobrescribe el archivo si ya existe. Sospeché que ya
  estaba en el repositorio y lo comprobé con `git status` y `git diff`: no
  existía, así que no se perdió nada.

## 4. Qué decidí sin consultarle

- Plantear el problema como un pipeline de preprocesamiento de datos (la idea de
  partida era mía).
- Que el estado fuera por archivo de entrada: como el flujo corre una vez al día
  con un archivo nuevo, supuse que su contenido cambiaría y que cada archivo
  debía tener su propio estado y su Excel.
- Una sola base de datos con clave primaria compuesta, en vez de una por archivo.
- Quitar las tablas `archivos` y `ejecuciones`: la base de datos es para
  reconstruir el estado, y el log y el Excel cubren la auditoría.
- La estructura de carpetas `core`, `steps` y `adapters`, y dejar ports y
  adapters como mejora futura por el límite de tiempo.
- Pedir una mejora de presentación de la hoja Resumen, de la hoja Resultados y
  de la consola, que no estaba en la spec.
- Unificar el término «ejecución» en todo el proyecto y cuestionar la redacción
  del README sobre qué se reintenta y cuándo.
