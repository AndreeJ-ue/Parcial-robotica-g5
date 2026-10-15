# Cómo funciona la cadena (los 3 ítems en contexto)

## Los 3 ítems, en una frase cada uno

- **Ítem 1 (6 pts) — Interpretar la orden.** Un nodo ROS 2 (`interprete_ordenes`) recibe una
  **frase** ("agarra el cubo rojo") y devuelve una **decisión tipada** (acción, objeto, color,
  prioridad, permitido). Consulta a **LAYA** por HTTP y, si no responde a tiempo, cae a un
  **clasificador por palabras clave** (`degradada=True`). Mide latencia y exactitud.
- **Ítem 2 (8 pts) — Mover el brazo.** Un **orquestador** (`orquestador`) toma la decisión,
  la mete en la **cola de prioridad del broker** y mueve el **brazo** (cámara + poses + pinza).
  Implementado completo; ver `README_ITEM_2.md` y `COMANDOS_ITEM_2.md`.
- **Ítem 3 (6 pts) — De la voz al texto.** Un nodo (`transcriptor_voz`) convierte **audio →
  texto** con **Google AI Studio** y entrega el texto al ítem 1. Si no hay internet o se agota el
  tiempo, **cae a modo texto por teclado**. Mide dónde se va el tiempo. *(En esta carpeta, lo
  propio del ítem 3 es la transcripción; el movimiento es el ítem 2.)*

## La cadena completa

```
audio (.wav)                 frase (texto)
     │                            │
     ▼                            │        PC Windows
transcriptor_voz ──texto──────────┤        ┌───────────────┐
  (ítem 3)                        │◄──HTTP─│  LAYA local   │
                                  │        │ (laya-serve)  │
                                  ▼        └───────────────┘
                        /interpretar_orden (servicio ROS 2, ítem 1)
                                  │
                          decisión tipada
                                  ▼
                          /orden_decidida
                                  │
                    ┌─────────────┴──────────────┐
                    │  orquestador                │
                    │  · rechaza permitido=False  │
                    │    antes de encolar         │
                    │  · cámara + poses + pinza    │
                    │    (ítem 2, completo)        │
                    └─────────────┬──────────────┘
                                  │ goals move_arm
                                  ▼
                          broker (arm_broker)
                         · única cola de prioridad
                         · ÚNICO publicador de /joint_states
                                  │
                                  ▼
                       /joint_states ──► driver ──► brazo + pinza
```

En esta carpeta la cadena está **completa**: el ítem 1 produce la decisión, el ítem 3 antepone la
voz y el ítem 2 (`orquestador`) mueve el brazo de verdad (cámara + poses + pinza) enviando
goals al broker. Detalles del ítem 2 en `README_ITEM_2.md` y `COMANDOS_ITEM_2.md`.

## Qué corre en cada máquina

```
┌──────────────────────────┐   HTTP /v1/systemone   ┌──────────────────────────────┐
│  PC Windows del equipo   │ ◄───────────────────── │  JETSON (grafo ROS 2)        │
│  laya-serve (GPU/CPU)    │                        │  interprete_ordenes (ítem 1) │
│  NO necesita internet    │                        │  transcriptor_voz   (ítem 3) │
└──────────────────────────┘                        │  orquestador (ítem 2)        │
                                                    │  broker (RB-2)               │
┌──────────────────────────┐   HTTPS (internet)     │  sync_plan_nx (driver)       │
│  Google AI Studio        │ ◄───────────────────── └──────────────┬───────────────┘
│  (transcripción, ítem 3) │      x-goog-api-key                   │ /joint_states
└──────────────────────────┘                                       ▼
                                                            JetCobot (brazo + pinza)
```

Dato del enunciado que guía el diseño: *"la transcripción depende de internet; la decisión y el
movimiento, no"*. Por eso **LAYA corre local** (en tu PC) y **solo la transcripción** sale a la
nube.

## Glosario rápido

- **LAYA** — motor de decisiones **tipadas** (`choice` / `score` / sí-no) servido por HTTP
  (`laya-serve`). No es un nodo ROS 2. Nunca redacta texto libre.
- **Decisión tipada** — la respuesta viene como opciones cerradas (elige una acción de una lista),
  no como una frase. Así parsear "sí/no" no es ambiguo y el brazo no se mueve mal.
- **`degradada`** — bandera: `False` = contestó LAYA; `True` = contestó el clasificador local.
- **`/interpretar_orden`** — el **servicio** ROS 2 del ítem 1 (pides una frase, esperas la respuesta).
- **`/orden_decidida`** — el **tópico** donde el ítem 1/3 publica la decisión ya en JSON para que
  la tome el orquestador.
- **Broker (`arm_broker`)** — nodo único que serializa el acceso al brazo y es el **único
  publicador de `/joint_states`**.
- **Publicador único** — regla dura: solo `arm_broker` publica `/joint_states`. Más de uno anula
  el puntaje.

## Puntajes del parcial

| Pregunta | Puntos | En esta carpeta |
|---|---|---|
| P1 (ítem 1) | 6 | Sí, completo |
| P2 (ítem 2) | 8 | Sí: `orquestador` (cámara + poses + pinza + cola) |
| P3 (ítem 3) | 6 | Sí: la transcripción (audio → texto) |
