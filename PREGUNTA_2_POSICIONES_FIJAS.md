# Pregunta 2 con cuatro posiciones fijas

## Modo articular (recomendado mientras no haya MoveIt en el Jetson)

`manipulacion.ejecucion = "articular"` en `posiciones_fijas.articular.example.json`. El worker heredado del RB2 ejecuta, para cada pedido permitido: ir a búsqueda → captura nueva y mapa color→P1–P4 por ROI → abrir pinza → bajar a la pose enseñada de esa posición → cerrar → subir a búsqueda (despeja los demás cubos) → pose del depósito → abrir → volver a búsqueda. Cada tramo se interpola en espacio articular con pasos ≤ `paso_plan_rad` y cada punto se valida con los límites y el workspace de la FK del RB2. La pinza se acciona desde el mismo worker por `/arm/accionar_pinza`, así que ningún otro nodo envía comandos al brazo.

- **Cinemática inversa:** es la solución articular ya enseñada en el brazo para cada posición y depósito (IK resuelta por el firmware al enseñar). Se registra como etapa `cinematica_inversa` para el desglose de la pregunta 3.
- **Error de FK:** `error_fk_mm` compara la FK de la postura medida en el depósito con la FK de la postura solicitada; `error_fk_recogida_mm` (en `tareas.jsonl`) hace lo mismo en la recogida.
- **Datos:** postura de búsqueda `[20,-8,-21,-54,0,-22]` y anclas pos1–pos4 `(537,385) (114,380) (520,87) (122,90)` calibradas por el equipo; ROI de 140×140 px centradas en ellas. `tests/test_articular.py` comprueba que la captura del equipo (`tests/datos/cubos_busqueda_equipo.jpeg`) produce P1=rojo, P2=verde, P3=azul, P4=amarillo.
- **Habilitación:** todas las `confirmada` están en `false`. Copiar a `config/posiciones_fijas.local.json`, probar cada pose supervisada y marcarla. `scripts/preflight.py --real` lista lo pendiente; `BackendArticular` no arranca sin `adaptador_serial_confirmado` y `calibracion_confirmada`.

La ruta descrita a continuación (IK y planificación con MoveIt) sigue disponible con `"ejecucion": "moveit"`.

## Qué se implementó

El broker conserva el worker del RB2. Cada pedido permitido ejecuta: lectura articular → planificación y llegada a búsqueda → imagen nueva → identificación del color en P1–P4 → selección de la pose medida de esa posición → seis objetivos resueltos con IK y planificados con MoveIt → pinza y traslado → retorno planificado a búsqueda y comprobación de llegada.

Las posiciones pertenecen a P1–P4, no a un color. Si se intercambian rojo y verde, cambia la posición seleccionada para recoger rojo. Solo se admite este montaje de cuatro lugares; no se calculan coordenadas nuevas por homografía ni se asume que el cubo permanece donde estaba en el pedido anterior.

Una orden no permitida se rechaza antes de encolar. Una ausencia, duplicado o región ambigua se detecta después de atender la cola y alcanzar búsqueda, sin iniciar recogida ni accionar pinza. La llegada a búsqueda sí puede mover el brazo antes de descubrir la ausencia. Si ocurre un error después de agarrar, no se improvisa un retorno: se informa el fallo y debe comprobarse la postura/objeto antes de recuperar.

## Configuraciones

- `src/parcial_jetcobot/config/posiciones_fijas.simulacion.json`: geometría y colores ficticios para ensayar software. No acredita posiciones seguras del brazo.
- `src/parcial_jetcobot/config/posiciones_fijas.example.json`: plantilla real con coordenadas, orientación, ROI y búsqueda pendientes. Copiarla a `config/posiciones_fijas.local.json` y completar mediciones del montaje actual.
- `src/parcial_jetcobot/config/posiciones_fijas.mediciones.example.json`: sugerencia con las ocho posturas confirmadas por el grupo en la captura. Conserva los ángulos de referencia y semillas de IK; XYZ/orientación fueron derivados del DH del repositorio. Búsqueda, ROI y confirmaciones siguen pendientes. No es una calibración validada ni se carga por defecto.
- `src/parcial_jetcobot/config/posiciones_fijas.articular.example.json` y `.articular.simulacion.json`: modo articular real y su simulación (la simulación es ahora el lanzamiento predeterminado).
- La ruta de homografía fue retirada. `config/simulacion.json` se conserva solo para el clasificador y `scripts/evaluar_frases.py`, porque las etiquetas de `datos/frases_50.csv` usan `zona_a`/`zona_b`.

Cada posición contiene `roi_xywh: [x,y,ancho,alto]` en píxeles de la imagen de búsqueda; `xyz_m` en metros; `quaternion_xyzw` normalizado; `frame_id` de la base; altura de aproximación positiva y `confirmada`. No inferir orientación cartesiana convirtiendo seis ángulos articulares en quaternion. Obtenerla del modelo/TF validado. Los ángulos enseñados pueden servir como referencias/semillas, pero esta versión sigue resolviendo IK y solicitando MoveIt.

La captura reciente se conserva transcrita en `referencias/posturas_compartidas_p2.json`: P1 `[3,-19,-109,31,0,-45]`, P2 `[41,-13,-126,55,0,-4]`, P3 `[3,-51,-41,0,0,-45]`, P4 `[25,-54,-39,0,0,-25]`, todos en grados. Los cuatro destinos por color también están incluidos. El usuario confirmó los roles y unidades. G7=100 se conserva como referencia de pinza abierta, fuera de la FK de seis articulaciones. Las ocho posturas cumplen los límites numéricos del RB2; esto no confirma los del URDF ni ausencia de colisiones.

`python3 scripts/revisar_posturas_p2.py` muestra radianes y geometría derivada sin abrir ROS/serial. No genera ni envía movimientos. La configuración sugerida deriva la orientación de la matriz completa de FK, no interpreta los seis ángulos como ángulos cartesianos. Debe contrastarse con el enlace/herramienta de MoveIt y el frame real antes de usarla.

La búsqueda contiene seis `q_rad`, tolerancia articular, tiempo de asentamiento y plazo. La cámara es móvil (`camara_fija: false`): el servicio exige mediciones recientes compatibles con la búsqueda y captura un cuadro nuevo después de la petición. La resolución debe coincidir con `resolucion_calibracion_px`. Las ROI no pueden solaparse; se rechazan tamaños y rangos HSV inválidos.

Los destinos se configuran por separado de P1–P4. El ejemplo asigna rojo→`zona_rojo`, verde→`zona_verde`, azul→`zona_azul`, amarillo→`zona_amarillo`. Es una correspondencia editable, no una confirmación de la rúbrica ni de las coordenadas de depósito. El valor `por_color` resuelve esa tabla. Una zona explícita del intérprete tiene precedencia: «cubo rojo en zona azul» conserva rojo como color del objeto y utiliza `zona_azul`.

## Compilar en las máquinas ROS

Cambió la respuesta de `LocalizarObjeto` y el resultado de `ManipularObjeto`. Actualizar las mismas fuentes y recompilar en Jetson y Raspberry antes de mezclar nodos. No copiar build/install/log entre máquinas.

```bash
source /opt/ros/humble/setup.bash
colcon build --symlink-install --packages-select arm_broker_interfaces arm_broker parcial_jetcobot
source install/setup.bash
```

Si el Jetson usa `build_jetson`/`install_jetson`, conservar esos argumentos de la guía y cargar `install_jetson/setup.bash`. Cerrar los nodos que aún usen interfaces antiguas antes de reiniciarlos.

## Probar sin brazo

Con OpenCV/NumPy disponibles y desde la raíz:

```bash
python3 -B -m unittest discover -s tests -p 'test_posiciones_fijas.py' -v
python3 -B -m unittest discover -s tests -p 'test_driver_posiciones.py' -v
python3 -B scripts/demo_offline.py
```

Con ROS, en el entorno local de prueba o en el dominio asignado:

```bash
ros2 launch parcial_jetcobot parcial.launch.py
```

En otra terminal con el mismo entorno:

```bash
ros2 run parcial_jetcobot cliente_ordenes --ros-args -p client_id:=prueba_p2 -p frase:="Recoge el cubo rojo"
```

En el mapa simulado inicial rojo ocupa P2. El resultado debe incluir `simulado=true`, `posicion_id=P2`, destino y mapa de colores; el error FK real continúa sin medir (-1). Editar solo `mapa_simulado` en una copia local permite comprobar otra permutación. El mapa se consulta por pedido, no se fija rojo=P2 en el código.

`bash scripts/cuatro_clientes.sh` utiliza las cuatro órdenes de `datos/posiciones_fijas/`, una por color. La orden amarilla contiene urgencia; su prioridad procede del intérprete. El script acepta un directorio de órdenes alternativo como primer argumento. No ejecutar concurrencia física hasta completar un pedido supervisado.

## Ajustar visión sin mover el brazo

Con el brazo detenido en búsqueda y el montaje actual, obtener una imagen mediante la herramienta de captura existente. Definir cuatro ROI alrededor de los lugares de recogida; la primera versión usa rectángulos. Los elementos verdes de la impresión del tablero deben quedar fuera de las ROI o por debajo del umbral de área.

Puede comprobarse el mapa aunque todavía falten coordenadas de movimiento:

```bash
python3 scripts/ver_posiciones_fijas.py --config config/posiciones_fijas.local.json --imagen FOTO_BUSQUEDA.png --salida evidencias/roi_corrida_01
```

La carpeta de salida debe ser nueva. Genera `mapa.json` y `regiones.png`. `--color rojo` comprueba además selección y pose si ya está medida. Repetir tras permutar cubos. Este script no abre serial, no mueve el brazo y no certifica el modelo mecánico.

## Antes de habilitar operación real

Completar y verificar los cuatro lugares y depósitos, búsqueda, resolución/ROI, orientación, alturas, modelo y límites. La plantilla conserva las confirmaciones en falso. Las poses de rojo guardadas en `avances/pregunta_2/` no se importan automáticamente: su discrepancia de J2 con el URDF sigue pendiente de resolver. No ampliar límites para ocultarla.

```bash
python3 scripts/preflight.py --config config/posiciones_fijas.local.json --real
```

Solo después de completar esa verificación, usar un único driver compatible en el Jetson y arrancar MoveIt con la escena del montaje. `integraciones/sync_plan_p2.py` conserva un único puerto serial. Su grupo de mediciones puede ejecutarse mientras espera la pinza; cada acceso serial usa el mismo mutex. Las lecturas se intercalan entre consultas de pinza. Las operaciones seriales individuales siguen dependiendo de los tiempos de respuesta del firmware. Los comandos permanecen deshabilitados al iniciar.

El lanzamiento del parcial sustituye al broker articular de prueba; no ejecutar ambos publicadores a la vez:

```bash
ros2 launch parcial_jetcobot parcial.launch.py config_file:="$PWD/config/posiciones_fijas.local.json"
```

La cámara debe estar físicamente accesible al nodo `percepcion` (normalmente en el Jetson). Si el intérprete/clientes están en Raspberry, conservar un solo conjunto de servicios/acción en el grafo y ejecutar los componentes en sus máquinas correspondientes. El lanzamiento completo se ejecuta en el Jetson para la cámara USB local; los clientes pueden ejecutarse desde Raspberry.

Probar primero un solo pedido supervisado y contrastar posiciones medidas. Al terminar debe confirmarse búsqueda antes de marcar la tarea como completada. Probar los cuatro lugares, permutaciones, ausencia/prohibición y después concurrencia. Completar diez intentos con éxito físico definido como objeto y depósito correctos, no solo `success=true`.

## Resultados y tiempos

Se conservan mapa de colores, posición, destino, FK, búsqueda, estabilización, percepción, seis IK, planes, pinza, recogida/traslado y retorno en los resultados y `tareas.jsonl`. El retorno se registra por separado. El inicio real del movimiento puede corresponder a búsqueda si el brazo no estaba allí. Para pregunta 3 no sumar percepción y planes de recogida como si necesariamente fueran anteriores a ese primer movimiento. Registrar la búsqueda por separado o comenzar la demostración desde búsqueda ya verificada.

La detección de comienzo usa cambios articulares recibidos; no sustituye sincronización de relojes ni conocimiento de la frecuencia del driver. `inicio_movimiento_wall_ns=0` significa que no hay medición de movimiento real; nunca interpretarlo como latencia cero.

## Comprobación local

La suite de esta implementación usa imágenes sintéticas y un backend simulado: comprueba las 24 permutaciones, selección por posición, regiones ambiguas/duplicadas/ausentes, cancelación, planificación antes de pinza y retorno. No ejecuta ROS, MoveIt ni hardware desde Windows. La compilación y las mediciones físicas deben verificarse en laboratorio.

## Postura de búsqueda

El modo articular usa la postura `[20,-8,-21,-54,0,-22]`, la misma con la que el equipo calibró las anclas de cámara. Las plantillas MoveIt (`posiciones_fijas.example.json` y `.mediciones.example.json`) conservan la postura `observacion` previamente medida (J1=9.22°, J2=-5.71°, J3=0.26°, J4=-71.19°, J5=0.52°, J6=-44.38°); si se usa esa ruta, sus ROI deben definirse desde esa postura. Las dos plantillas incluyen sus radianes y procedencia. Cumple los límites numéricos del RB2; la validación del modelo y del montaje de cámara actual permanece pendiente. Las regiones P1–P4 deben definirse desde esta postura. La simulación conserva su postura ficticia de pruebas.
