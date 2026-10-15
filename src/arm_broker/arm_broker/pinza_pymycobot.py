""" Control directo de la pinza del kit por pymycobot — vía de RESPALDO del Ítem 2 """

""" La vía primaria es la acción `gripper_command` (ver gripper.py). Cuando esa acción no
responde, se intenta este canal: set_gripper_value() por el puerto serie del kit. Si el driver
ya tiene tomado el puerto, la apertura falla y la pinza queda deshabilitada sin tumbar el nodo. """

import time

try:
    from pymycobot.mycobot import MyCobot
    PYMYCOBOT_DISPONIBLE = True
except ImportError:
    PYMYCOBOT_DISPONIBLE = False


class PinzaPymycobot:

    def __init__(self, puerto='/dev/ttyUSB0', baudios=1000000, velocidad=50,
                 abierta=100, cerrada=0, timeout_s=5.0):
        self.velocidad = int(velocidad)
        self.abierta = int(abierta)
        self.cerrada = int(cerrada)
        self.timeout_s = float(timeout_s)
        self.disponible = False
        self.mc = None

        if not PYMYCOBOT_DISPONIBLE:
            print('[PINZA] pymycobot no está instalado: sin vía serie')
            return
        try:
            self.mc = MyCobot(puerto, baudios)
            self.disponible = True
            print(f'[PINZA] vía pymycobot lista en {puerto}')
        except Exception as e:
            print(f'[PINZA] no pude abrir {puerto} con pymycobot: {e!r}')

    def _esperar(self):
        t0 = time.time()
        try:
            while self.mc.is_gripper_moving():
                if time.time() - t0 > self.timeout_s:
                    break
                time.sleep(0.1)
        except Exception:
            pass

    def _mover(self, valor):
        if not self.disponible:
            return False
        try:
            self.mc.set_gripper_value(int(valor), self.velocidad)
            time.sleep(0.2)
            self._esperar()
            return True
        except Exception as e:
            print(f'[PINZA] error al mover la pinza: {e!r}')
            return False

    def abrir(self):
        return self._mover(self.abierta)

    def cerrar(self):
        return self._mover(self.cerrada)
