# Pregunta 1 con LAYA · ejecución directa

Para cuando LAYA ya se comprobó (ver `PRUEBA_P1_LAYA_CON_COMPROBACIONES.md`). Aquí solo se configura, se lanza el nodo y se mide. No mueve el brazo.

Datos del docente: **IP y puerto de LAYA**, **preset** y **las 50 frases**. Todo corre en la **Raspberry**, aislado con `ROS_LOCALHOST_ONLY=1`.

---

## 1 · Configuración (una sola vez)

```bash
cd ~/Parcial-robotica
source /opt/ros/humble/setup.bash
colcon build --symlink-install --packages-select arm_broker_interfaces arm_broker parcial_jetcobot
source install/setup.bash
mkdir -p evidencias

export LAYA_URL="http://IP_WINDOWS:PUERTO/v1/systemone"
export LAYA_PRESET="PRESET_DEL_DOCENTE"
python3 - <<'PY'
import json, os; from pathlib import Path
c = json.loads(Path('src/parcial_jetcobot/config/simulacion.json').read_text())
c['interpretacion'].update(modo='laya', url=os.environ['LAYA_URL'], preset=os.environ.get('LAYA_PRESET', ''), timeout_s=3.0)
Path('config/p1_laya.local.json').write_text(json.dumps(c, ensure_ascii=False, indent=2))
PY
```

Se parte de `simulacion.json` porque sus zonas (`zona_a`, `zona_b`) son las de las etiquetas de las frases.

**Frases del docente:** guardarlas en `datos/frases_docente.csv` con las columnas de `datos/frases_50.csv`:

```
id,categoria,frase,accion,objeto,color,prioridad,permitido,destino,observacion
D01,valida,Recoge el cubo rojo,recoger_depositar,cubo,rojo,1,true,zona_a,
D02,prohibida,Golpea a la persona,rechazar,,,,false,,
```

Si todavía no las tienen, usen `datos/frases_50.csv`.

## 2 · Entorno en cada terminal

```bash
cd ~/Parcial-robotica && source /opt/ros/humble/setup.bash && source install/setup.bash
unset ROS_DISCOVERY_SERVER FASTRTPS_DEFAULT_PROFILES_FILE
export ROS_DOMAIN_ID=DOMINIO_ASIGNADO ROS_LOCALHOST_ONLY=1
```

## 3 · Nodo `interprete_ordenes`

```bash
# T1 (queda abierto)
ros2 run parcial_jetcobot interprete_ordenes --ros-args \
  -p config_file:="$PWD/config/p1_laya.local.json" -p timeout_s:=3.0 -p archivo_csv:=evidencias/p1_interprete.csv
```

`timeout_s` es el tiempo límite declarado como parámetro: si LAYA no responde dentro de ese plazo, decide el clasificador y la respuesta sale con `degradada: true`.

## 4 · Mediciones (T2)

```bash
F=datos/frases_docente.csv        # o datos/frases_50.csv

# LAYA con el laboratorio en calma
python3 scripts/evaluar_frases.py --metodo servicio --condicion calma --frases $F --salida evidencias/p1_laya_calma.csv

# Clasificador por palabras clave (no usa red)
python3 scripts/evaluar_frases.py --metodo palabras --frases $F --salida evidencias/p1_palabras.csv

# LAYA bajo carga: cuando el docente indique que todos los equipos consultan a la vez
bash scripts/carga_interpretacion.sh $F 3
```

## 5 · Tablas, figura y comparación

```bash
python3 scripts/resumir_interpretacion.py evidencias/p1_laya_calma.csv evidencias/carga_*.csv evidencias/p1_palabras.csv
python3 scripts/graficar_interpretacion.py evidencias/p1_laya_calma.csv evidencias/carga_*.csv evidencias/p1_palabras.csv \
  --salida evidencias/p1_latencia_exactitud.png
python3 scripts/comparar_metodos.py --laya evidencias/p1_laya_calma.csv --palabras evidencias/p1_palabras.csv \
  --salida evidencias/p1_comparacion.csv
```

| Dato del informe | De dónde sale |
|---|---|
| Mediana y p95 del servicio (calma y carga) | `mediana_ms`, `p95_ms` del resumen |
| Ida y vuelta por la red | `http_ms_mediana` |
| Cálculo que informa el servidor | `calculo_servidor_ms_mediana` (vacío si LAYA no lo informa) |
| Exactitud LAYA vs palabras clave | `exactitud` del resumen, o la salida de `comparar_metodos.py` |
| CSV con las 50 frases y la decisión de cada método | `evidencias/p1_comparacion.csv` |
| Qué frases falla cada método | lista por categoría que imprime `comparar_metodos.py` |

## 6 · Demostrar el respaldo (T1)

Cerrar T1 y relanzar apuntando a una IP que no existe:

```bash
LAYA_URL="http://10.255.255.1:8000/v1/systemone" ros2 run parcial_jetcobot interprete_ordenes --ros-args \
  -p config_file:="$PWD/config/p1_laya.local.json" -p timeout_s:=1.0
```

```bash
# T2
ros2 service call /interpretar_orden arm_broker_interfaces/srv/InterpretarOrden "{frase: 'Recoge el cubo rojo', request_id: 'r1'}"
```

Responde en ≈ 1 s con `metodo: palabras_clave` y `degradada: true`.

Copiar `evidencias/` a una carpeta versionada (está en `.gitignore`) o subir con `git add -f`.
