# Parcial de Robótica JetCobot

Repositorio del equipo 5 para el parcial: broker del RB2, interpretación de órdenes con LAYA, transcripción de voz con Google y herramientas de percepción y manipulación. Reúne el código desarrollado y los avances experimentales de las preguntas 1 y 3.

Repositorio: [AndreeJ-ue/Parcial-robotica-g5](https://github.com/AndreeJ-ue/Parcial-robotica-g5). La instalación y los comandos por equipo están en [GUIA_CONFIGURACION.md](GUIA_CONFIGURACION.md).

## Trabajo realizado

- Se integró la matriz DH estándar en la cinemática directa conservando la tabla DH del equipo.
- Se corrigieron la admisión concurrente, las cancelaciones y el manejo de errores del broker. Se incorporaron postura inicial explícita, estado medido separado de los comandos y registro de eventos por solicitud.
- Se observó movimiento real mediante la ruta cliente → broker → driver → brazo. Se ejecutó FIFO con cuatro clientes: atención secuencial según el orden de admisión, con esperas aproximadas de 0,055; 3,075; 5,126 y 8,149 segundos.
- Se desarrollaron el intérprete LAYA con respaldo local, las interfaces del parcial, la extensión del broker, percepción HSV, integración IK/MoveIt y voz. La petición de LAYA incluye `state: {"body": frase}`.
- Se incorporó una comprobación de contradicción entre el color explícito de la frase y la decisión antes de encolar.
- Se obtuvo una región roja, azul, verde y amarilla en la captura usada para ajustar la detección de colores.
- Se añadieron el adaptador `sync_plan_p2.py`, que comparte una conexión serial para comandos, mediciones y pinza, y un ensayo de giro que usa postura actual medida o declarada.

## Pregunta 1

En `avances/pregunta_1/` se conservan el código de interpretación, las 50 frases con etiquetas, los CSV originales de calma y carga, los documentos Word y sus fotografías. Los siguientes valores se recalcularon desde esos CSV:

| Indicador | Calma | Carga |
|---|---:|---:|
| Frases | 50 | 50 |
| Mediana del tiempo total | 103,00 ms | 100,85 ms |
| P95 del tiempo total | 122,47 ms | 119,84 ms |
| Coincidencia exacta LAYA | 17/50 · 34 % | 17/50 · 34 % |
| Coincidencia exacta clasificador | 40/50 · 80 % | 40/50 · 80 % |

La coincidencia exacta compara acción, objeto, color y permiso con las etiquetas del archivo recibido. Los campos de red y cómputo de estos registros son estimaciones del script. Los registros y los CSV corresponden a sus respectivas ejecuciones; el resumen anterior utiliza exclusivamente los CSV.

El registro de terminal incluye el servicio `/interpretar_orden` y una respuesta del clasificador forzado que rechaza una frase con tijeras. El contrato plano utilizado en estas mediciones se conserva en el workspace independiente `avances/codigo_p1_p3/`, adaptado a paquetes `jetcobot_p13` y `jetcobot_p13_interfaces` y al namespace `/p13`.

## Pregunta 3

`avances/pregunta_3/` contiene seis WAV —cinco órdenes y una conversión a 16 kHz—, el CSV original, el documento Word de evidencias y sus fotografías. El CSV registra cinco transcripciones con Google:

| Audio | Transcripción registrada | Transcripción | Decisión |
|---|---|---:|---:|
| `orden_01.wav` | Agarra el cubo rojo. | 2,993 s | 0,152 s |
| `orden_02.wav` | Recoge el cubo azul | 5,830 s | 0,133 s |
| `orden_03.wav` | Toma el cubo verde. | 3,935 s | 0,128 s |
| `orden_04.wav` | Agarra el cubo morado | 8,251 s | 0,180 s |
| `orden_05.wav` | Mueve el brazo fuera de la zona de trabajo | 7,301 s | 0,150 s |

Estos tiempos corresponden a transcripción y respuesta del intérprete. El CSV también conserva una fila de teclado cuyo texto es un comando pegado accidentalmente; se mantiene como registro original y se excluye de las cinco transcripciones anteriores. Los registros de sesión muestran el uso de `gemini-3.5-flash`; el modelo de las herramientas puede configurarse sin editar código.

## Organización

| Ruta | Contenido |
|---|---|
| `src/arm_broker/` | Broker RB2, estado, eventos, políticas, FK y cliente articular |
| `src/arm_broker_interfaces/` | Acciones, mensajes y servicios del proyecto principal |
| `src/parcial_jetcobot/` | Interpretación, voz, percepción y extensión del broker |
| `integraciones/` | Adaptación al driver y conexión serial |
| `scripts/` y `herramientas/` | Clientes, captura, calibración, mediciones y resúmenes |
| `config/` y `datos/` | Ejemplos compartidos y frases de desarrollo |
| `avances/pregunta_1/` y `avances/pregunta_3/` | Archivos originales de los ZIP y resúmenes derivados |
| `avances/codigo_p1_p3/` | Código de interpretación y voz para las preguntas 1 y 3 |
| `avances/pregunta_2/` | Poses enseñadas y captura de colores conservadas como referencias |
| `referencias/base_rb2_sha256.json` | Huellas de la base RB2 antes de ampliarla |

El proyecto principal usa `DecisionOrden` y `/manipular_objeto`. El avance P1/P3 usa una respuesta plana y publica la decisión en `/p13/orden_decidida`; se ejecuta por separado y no envía comandos al brazo. Su carpeta tiene `COLCON_IGNORE` para que la compilación de la raíz solo descubra los tres paquetes principales. Los archivos de resultados se conservan sin atribuirlos a versiones modificadas después de medir. Los documentos Word y las capturas se conservan en su formato original, incluidas las rutas visibles de las terminales.

## Incidencias resueltas

| Incidencia | Solución directa aplicada |
|---|---|
| Formato de petición LAYA | Enviar la frase dentro de `state.body` |
| Paquetes ROS no encontrados | Cargar ROS y el `install/setup.bash` del workspace utilizado |
| Archivos de compilación con rutas de otra máquina | Compilar desde las fuentes en cada equipo, con directorios propios del Jetson |
| Flecha verde detectada como otra región | Aumentar el área mínima del filtro en la captura de referencia |
| Descubrimiento incompleto del publicador en el ensayo | Esperar identidad y estabilidad de un único `arm_broker` |
| Postura fija antigua en el ensayo | Utilizar medida reciente o seis ángulos actuales declarados |
| Dominio 112 rechazado por el script | Ampliar la comprobación al rango Linux 0–232 y usar la asignación del laboratorio |

## Base del proyecto

El broker parte del [RB2 del equipo](https://github.com/Sergio-Jacobo-Jauregui/reto2), con las correcciones integradas durante el curso. Los datos de desarrollo en `datos/frases_50.csv` y las etiquetas experimentales en `avances/pregunta_1/` pertenecen a conjuntos distintos.
