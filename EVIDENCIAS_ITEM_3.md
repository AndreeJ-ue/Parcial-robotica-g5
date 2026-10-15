# Evidencias — ÍTEM 3

> En esta entrega, lo propio del ítem 3 es la **transcripción de voz a texto**. Las columnas de
> "qué hizo el brazo" dependen del **ítem 2** (ver `PARA_COMPLETAR_EL_ITEM_2_Y_CERRAR_EL_ITEM_3.md`).

## Tabla de entregables (y con qué se generan)

| Evidencia | Cómo se genera |
|---|---|
| `transcripciones.csv` | Lo escribe el nodo `transcriptor_voz` (una fila por audio). Cabecera en `anchy/evidencias/transcripciones_cabecera.csv`. |
| Audios `orden_01.wav … orden_05.wav` | `arecord -D plughw:1,0 -f S16_LE -r 16000 -c 1 -d 8 orden_0X.wav` |
| `ordenes_demo.csv` (tabla de 5 órdenes) | Llenar `anchy/evidencias/plantilla_ordenes.csv` con la demo real. |
| `etapas.csv` | Calcular la mediana por etapa sobre las 5 órdenes (ver abajo). |
| `desglose_tiempos.png` | `python3 herramientas/graficar_tiempos.py etapas.csv --salida desglose_tiempos.png` |
| Video del **modo texto sin internet** | Grabar la demo del Paso G de `README_ITEM_3.md`. |
| `evidencia/publicadores.txt` | `python3 analisis/verificar_publicadores.py --salida evidencia/publicadores.txt` |
| Respuestas a las 2 preguntas | Con tus números (ver abajo). |

## Formato de `etapas.csv`

```csv
etapa,mediana_s
Captura de audio,0.05
Transcripcion en la nube,0.90
Decision del modelo,0.42
Espera en la cola,1.10
Percepcion,0.08
Cinematica inversa,0.12
Planificacion,0.20
```

Cómo sale cada etapa: Captura = `t1 − t0`; Transcripción = `t2 − t1`; Decisión = `t3 − t2`;
Cola = `wait_time_s`; Total voz→movimiento = `t5 − t0`. Las etapas de percepción, IK y
planificación solo tienen sentido cuando está el ítem 2 completo.

## Tabla de las 5 órdenes (`ordenes_demo.csv`)

| n | se dijo (audio) | transcribió | acción/objeto/color/prioridad/permitido | rechazo/encolado | qué hizo el brazo | ¿correcto? |
|---|---|---|---|---|---|---|
| 1 | `orden_01.wav` | … | … | … | … | sí/no |
| 2 | `orden_02.wav` | … | … | … | … | … |
| 3 | `orden_03.wav` | … | … | … | … | … |
| 4 | `orden_04.wav` | … | … | … | … | … |
| 5 | `orden_05.wav` | … | … | … | … | … |

Debe incluir **una con objeto que no está en la mesa** y **una no permitida**. Criterio de
acierto: resultado **final** esperado, **incluido el rechazo** cuando corresponde.

## Las 2 preguntas numéricas (respóndelas con TUS números)

1. **¿Cuál es la etapa dominante?** — la de mayor mediana (suele ser la transcripción en la
   nube o la espera en la cola, según carga).
2. **Si hay que reducir a la mitad el tiempo voz→movimiento, ¿sobre qué etapa trabajas y qué
   dejas de obtener?** — atacar la transcripción (modelo de voz local) mejora el total pero
   pierdes calidad ASR multilingüe y sumas mantenimiento; atacar la cola (menor `tau`,
   prioridades agresivas) mejora lo urgente pero **empeora la equidad/inanición** de las
   prioridades bajas. La respuesta correcta es la que salga de **tus números**.

## Checklist de entrega (ítem 3)

- [ ] `probar_transcripcion.py orden_01.wav gemini-2.5-flash` devuelve la frase.
- [ ] `transcriptor_voz` funciona por archivo y por teclado.
- [ ] Fallback a teclado verificado (sin clave / sin internet).
- [ ] `transcripciones.csv` con una fila por audio.
- [ ] `ordenes_demo.csv` (5 órdenes, incluida no permitida y objeto inexistente).
- [ ] `etapas.csv` + `desglose_tiempos.png` + respuestas a las 2 preguntas.
- [ ] Demo **sin internet** en modo texto, grabada en video.
- [ ] `verificar_publicadores.py` = exactamente 1 publicador `arm_broker`.
