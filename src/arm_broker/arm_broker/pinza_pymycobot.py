""" Envoltorio del puerto serie de la pinza del kit por pymycobot — Ítem 2 """

""" Esta clase es la que habla con la garra por serie (set_gripper_value). La usan DOS vías:
  - el nodo `servidor_pinza`, que la expone como la acción `gripper_command` (vía primaria), y
  - el respaldo de `gripper.py`, si esa acción no está disponible (ver gripper.py).

Si el driver del brazo ya tiene tomado el puerto (`/dev/ttyUSB0`), se reintenta abrirlo en MODO
COMPARTIDO NO EXCLUSIVO (exclusive=False), porque la pinza y el brazo comparten el mismo M5. Si
aun así falla, la pinza queda deshabilitada sin tumbar al llamador. """

import time

try:
    from pymycobot.mycobot import MyCobot
    PYMYCOBOT_DISPONIBLE = True
except ImportError:
    PYMYCOBOT_DISPONIBLE = False


class PinzaPymycobot:

    def __init__(self, puerto='/dev/ttyUSB0', baudios=1000000, velocidad=50,
                 abierta=100, cerrada=0, timeout_s=5.0, exclusivo=False):
        self.velocidad = int(velocidad)
        self.abierta = int(abierta)
        self.cerrada = int(cerrada)
        self.timeout_s = float(timeout_s)
        self.exclusivo = bool(exclusivo)
        self.disponible = False
        self.mc = None

        if not PYMYCOBOT_DISPONIBLE:
            print('[PINZA] pymycobot no está instalado: sin vía serie')
            return

        try:
            self.mc = MyCobot(puerto, baudios)
            self.disponible = True
            print(f'[PINZA] vía pymycobot lista en {puerto}')
            return
        except Exception as e:
            primer_error = e

        # Reintento en MODO COMPARTIDO NO EXCLUSIVO: el driver del brazo y la pinza comparten
        # /dev/ttyUSB0 (los dos viven en el mismo M5). Si pymycobot abre con exclusive=True, el
        # driver ya lo tiene y la apertura falla. Se fuerza exclusive=False para compartirlo.
        if not self.exclusivo:
            try:
                self.mc = self._abrir_compartido(puerto, baudios)
                self.disponible = True
                print(f'[PINZA] vía pymycobot lista en {puerto} (compartido no exclusivo)')
                return
            except Exception as e:
                print(f'[PINZA] no pude abrir {puerto} con pymycobot: {primer_error!r} · '
                      f'compartido no exclusivo: {e!r}')
        else:
            print(f'[PINZA] no pude abrir {puerto} con pymycobot: {primer_error!r}')

    @staticmethod
    def _abrir_compartido(puerto, baudios):
        """Abre el puerto sin bloqueo exclusivo parcheando, SOLO durante la construcción, el
        __init__ de serial.Serial (afecta a cualquier módulo que haya importado la clase, use
        serial.Serial o un 'from serial import Serial')."""
        import serial

        init_real = serial.Serial.__init__

        def init_compartido(self, *args, **kwargs):
            kwargs['exclusive'] = False          # sin TIOCEXCL: se comparte con el driver
            kwargs.setdefault('timeout', 0.1)
            return init_real(self, *args, **kwargs)

        serial.Serial.__init__ = init_compartido
        try:
            return MyCobot(puerto, baudios)
        finally:
            serial.Serial.__init__ = init_real

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

    def ir_a(self, valor):
        """Lleva la garra a una posición arbitraria de la escala del kit (0..100).

        Es la primitiva que expone el nodo servidor_pinza a la acción gripper_command; abrir() y
        cerrar() son solo atajos a las dos posiciones fijas."""
        try:
            valor = int(round(float(valor)))
        except (TypeError, ValueError):
            print(f'[PINZA] posición inválida: {valor!r}')
            return False
        if not 0 <= valor <= 100:
            print(f'[PINZA] posición fuera de la escala 0..100: {valor}')
            return False
        return self._mover(valor)

    def abrir(self):
        return self._mover(self.abierta)

    def cerrar(self):
        return self._mover(self.cerrada)
