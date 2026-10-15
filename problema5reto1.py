///RETO 1 PROBLEMA 5

import ti
g_speed = 40me
import threading
import cv2 as cv
import ipywidgets as widgets
from IPython.display import display
from pymycobot.mycobot import MyCobot

mc = MyCobot("/dev/ttyUSB0", 1000000)

# ── Posturas fijas ──────────────────────────────────────────────────
POSE_HOME = [0, 0, 0, 0, 0, -45]
POSE_BUSQUEDA = [11.86, -5.8, -1.84, -69.87, 0.61, -44.29]
POSE_RECOGIDA = [216.4, -0.5, 114.9, 176.68, 6.58, -41.35]

DESTINOS = {
    "AMARILLO": [150.9, 214.8, 124.9, -175.75, 8.27, 14.93],
    "ROJO":     [95.4, 224.9, 122.4, -174.59, 15.01, 27.54],
    "VERDE":    [36.1, 224.6, 124.2, -174.09, 14.63, 42.43],
    "AZUL":     [-29.2, 230.6, 120.0, -171.48, 12.59, 59.13],
}

OFFSET_SEGURO = 60

LIMITES_ANGULOS = {1: (-168, 168), 2: (-135, 90), 3: (-150, 150),
                    4: (-145, 145), 5: (-165, 165), 6: (-180, 180)}
LIMITES_COORDS = {"x": (-280, 280), "y": (-280, 280), "z": (-70, 419),
                   "rx": (-180, 180), "ry": (-180, 180), "rz": (-180, 180)}

GRIPPER_ABIERTO, GRIPPER_CERRADO, GRIPPER_SPEED = 100, 0, 50

AREA_MINIMA = 300
FRAMES_ESTABILIDAD = 8      # para el boton manual
TIEMPO_ESTABLE_LOOP = 1.0   # segundos de deteccion continua antes de actuar en modo loop

COLORES = {
    "ROJO":     [((0, 120, 70), (10, 255, 255)), ((170, 120, 70), (180, 255, 255))],
    "AMARILLO": [((20, 100, 100), (35, 255, 255))],
    "VERDE":    [((40, 70, 70), (85, 255, 255))],
    "AZUL":     [((90, 100, 70), (130, 255, 255))],
}

_camara_activa = threading.Event()
_loop_activo = threading.Event()
camera_lock = threading.Lock()
ultimo_frame = None
ultima_deteccion = None


def angulo_valido(angulos):
    if len(angulos) != 6:
        print("Postura invalida")
        return False
    for i, a in enumerate(angulos, start=1):
        lo, hi = LIMITES_ANGULOS[i]
        if not (lo <= a <= hi):
            print(f"Angulo fuera de rango en J{i}: {a}")
            return False
    return True

def coord_valida(coords):
    for clave, valor in zip(["x", "y", "z", "rx", "ry", "rz"], coords):
        lo, hi = LIMITES_COORDS[clave]
        if not (lo <= valor <= hi):
            print(f"Fuera de rango en {clave}: {valor}")
            return False
    return True

def mover_angulos(postura, nombre="postura", pausa=2.5):
    if not angulo_valido(postura):
        print(f"Se omite el movimiento a {nombre}")
        return False
    print(f"Moviendo a {nombre}: {postura}")
    mc.send_angles(postura, g_speed)
    time.sleep(pausa)
    return True

def mover_coords(coords, nombre="punto", modo=0, pausa=2.5):
    if not coord_valida(coords):
        print(f"Se omite el movimiento a {nombre}")
        return False
    print(f"Moviendo a {nombre}: {coords}")
    mc.send_coords(coords, g_speed, modo)
    time.sleep(pausa)
    return True

def esperar_pinza(timeout=5):
    t0 = time.time()
    while mc.is_gripper_moving():
        if time.time() - t0 > timeout:
            print("Timeout de la pinza")
            break
        time.sleep(0.1)

def abrir_pinza():
    mc.set_gripper_value(GRIPPER_ABIERTO, GRIPPER_SPEED)
    time.sleep(0.2)
    esperar_pinza()

def cerrar_pinza():
    mc.set_gripper_value(GRIPPER_CERRADO, GRIPPER_SPEED)
    time.sleep(0.2)
    esperar_pinza()

def mascara_color(hsv, rangos):
    total = None
    for bajo, alto in rangos:
        m = cv.inRange(hsv, bajo, alto)
        total = m if total is None else cv.bitwise_or(total, m)
    return total

def detectar_color(frame):
    hsv = cv.cvtColor(frame, cv.COLOR_BGR2HSV)
    kernel = cv.getStructuringElement(cv.MORPH_ELLIPSE, (5, 5))

    mejor_color, mejor_area, mejor_punto = None, 0, None
    for nombre, rangos in COLORES.items():
        mascara = mascara_color(hsv, rangos)
        mascara = cv.morphologyEx(mascara, cv.MORPH_OPEN, kernel)
        mascara = cv.morphologyEx(mascara, cv.MORPH_CLOSE, kernel)

        contornos, _ = cv.findContours(mascara, cv.RETR_EXTERNAL, cv.CHAIN_APPROX_SIMPLE)
        if not contornos:
            continue
        contorno = max(contornos, key=cv.contourArea)
        area = cv.contourArea(contorno)
        if area < AREA_MINIMA or area <= mejor_area:
            continue
        m = cv.moments(contorno)
        if m["m00"] == 0:
            continue
        cx, cy = int(m["m10"] / m["m00"]), int(m["m01"] / m["m00"])
        mejor_color, mejor_area, mejor_punto = nombre, area, (cx, cy)

    return None if mejor_punto is None else (mejor_color, *mejor_punto)

def abrir_camara():
    for indice in [0, 1, 2, 3]:
        cap = cv.VideoCapture(indice)
        if cap.isOpened():
            ok, _ = cap.read()
            if ok:
                print(f"Camara encontrada en indice {indice}")
                return cap
            cap.release()
    print("No se encontro una camara disponible")
    return None


# ── Camara en vivo, en su propio hilo, siempre corriendo cuando esta activa ──
def hilo_camara():
    global ultimo_frame, ultima_deteccion
    cap = abrir_camara()
    if cap is None:
        _camara_activa.clear()
        return

    try:
        while _camara_activa.is_set():
            ok, frame = cap.read()
            if not ok:
                continue

            resultado = detectar_color(frame)
            if resultado is not None:
                color, cx, cy = resultado
                cv.circle(frame, (cx, cy), 10, (255, 255, 255), 2)
                cv.putText(frame, color, (cx + 10, cy), cv.FONT_HERSHEY_SIMPLEX,
                           0.7, (255, 255, 255), 2)

            with camera_lock:
                ultimo_frame = frame
                ultima_deteccion = resultado

            ok_jpg, buffer = cv.imencode(".jpg", frame)
            if ok_jpg:
                img_widget.value = buffer.tobytes()
    finally:
        cap.release()
        print("Camara detenida")


def pick_and_place(color):
    if color not in DESTINOS:
        print(f"Color '{color}' sin destino definido")
        return

    pose_destino = DESTINOS[color]
    rx_r, ry_r, rz_r = POSE_RECOGIDA[3:]
    rx_d, ry_d, rz_d = pose_destino[3:]

    recogida_arriba = [POSE_RECOGIDA[0], POSE_RECOGIDA[1], POSE_RECOGIDA[2] + OFFSET_SEGURO, rx_r, ry_r, rz_r]
    destino_arriba = [pose_destino[0], pose_destino[1], pose_destino[2] + OFFSET_SEGURO, rx_d, ry_d, rz_d]

    print(f"Pick and place: recogiendo para destino {color}")
    abrir_pinza()

    if not mover_coords(recogida_arriba, "sobre recogida", modo=0):
        return
    if not mover_coords(POSE_RECOGIDA, "bajando a recoger", modo=1):
        return

    cerrar_pinza()

    if not mover_coords(recogida_arriba, "subiendo con el cubo", modo=1):
        return
    if not mover_coords(destino_arriba, "sobre destino", modo=0):
        return
    if not mover_coords(pose_destino, "bajando a soltar", modo=1):
        return

    abrir_pinza()

    if not mover_coords(destino_arriba, "subiendo sin el cubo", modo=1):
        return

    mover_angulos(POSE_HOME, "POSE_HOME")
    print("Pick and place terminado")


# ── Modo manual: espera FRAMES_ESTABILIDAD lecturas seguidas del mismo color ──
def detectar_color_estable_manual(intentos_maximos=60):
    conteo_color, repeticiones = None, 0
    for _ in range(intentos_maximos):
        with camera_lock:
            resultado = ultima_deteccion
        if resultado is None:
            conteo_color, repeticiones = None, 0
        else:
            color = resultado[0]
            if color == conteo_color:
                repeticiones += 1
            else:
                conteo_color, repeticiones = color, 1
            if repeticiones >= FRAMES_ESTABILIDAD:
                return color
        time.sleep(0.05)
    print("No se logro una deteccion estable")
    return None

def ejecutar_manual(b):
    boton_manual.disabled = True
    boton_loop.disabled = True
    with salida:
        try:
            mover_angulos(POSE_BUSQUEDA, "postura de busqueda")
            color = detectar_color_estable_manual()
            if color is None:
                print("No se detecto ningun color valido")
                return
            print(f"Color detectado: {color}")
            pick_and_place(color)
        finally:
            boton_manual.disabled = False
            boton_loop.disabled = False


# ── Modo loop: exige deteccion continua del mismo color por 1s antes de actuar ──
def hilo_loop():
    with salida:
        print("Iniciando modo loop...")

    mover_angulos(POSE_BUSQUEDA, "postura de busqueda")

    color_desde, t_inicio_estable = None, None

    while _loop_activo.is_set():
        with camera_lock:
            resultado = ultima_deteccion

        if resultado is not None:
            color = resultado[0]
            if color == color_desde:
                if time.time() - t_inicio_estable >= TIEMPO_ESTABLE_LOOP:
                    with salida:
                        print(f"{color} detectado de forma estable por {TIEMPO_ESTABLE_LOOP}s, recogiendo")
                    pick_and_place(color)
                    color_desde, t_inicio_estable = None, None
                    if _loop_activo.is_set():
                        mover_angulos(POSE_BUSQUEDA, "postura de busqueda")
            else:
                color_desde, t_inicio_estable = color, time.time()
        else:
            color_desde, t_inicio_estable = None, None

        time.sleep(0.05)

    with salida:
        print("Modo loop detenido")


hilo_camara_obj = None
hilo_loop_obj = None

img_widget = widgets.Image(format="jpeg", width=480)
boton_camara = widgets.Button(description="Iniciar camara", button_style="info")
boton_manual = widgets.Button(description="Detectar y recoger", button_style="success")
boton_loop = widgets.Button(description="Iniciar loop", button_style="warning")
boton_detener_loop = widgets.Button(description="Detener loop", button_style="danger")
salida = widgets.Output()

def iniciar_camara(b):
    global hilo_camara_obj
    if _camara_activa.is_set():
        with salida:
            print("La camara ya esta activa")
        return
    _camara_activa.set()
    hilo_camara_obj = threading.Thread(target=hilo_camara, daemon=True)
    hilo_camara_obj.start()

def iniciar_loop(b):
    global hilo_loop_obj
    if not _camara_activa.is_set():
        with salida:
            print("Primero inicia la camara")
        return
    if _loop_activo.is_set():
        with salida:
            print("El loop ya esta corriendo")
        return
    boton_manual.disabled = True
    _loop_activo.set()
    hilo_loop_obj = threading.Thread(target=hilo_loop, daemon=True)
    hilo_loop_obj.start()

def detener_loop(b):
    _loop_activo.clear()
    boton_manual.disabled = False

boton_camara.on_click(iniciar_camara)
boton_manual.on_click(ejecutar_manual)
boton_loop.on_click(iniciar_loop)
boton_detener_loop.on_click(detener_loop)

display(
    widgets.HBox([boton_camara, boton_manual, boton_loop, boton_detener_loop]),
    img_widget,
    salida
)

