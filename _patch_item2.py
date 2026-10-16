# coding: utf-8
from pathlib import Path

p = Path('ITEM_2_BRAZO.md')
s = p.read_text(encoding='utf-8', errors='replace')
old = '''### T3 — Intérprete de órdenes (ítem 1)
`ash
ros2 run arm_broker interprete_ordenes --ros-args -p laya_url:=http://<IP_DE_TU_PC>:8000 -p timeout_laya_s:=2.0
`
Si LAYA no responde, cae al clasificador (degradada=True) y la cadena sigue.'''
new = '''### T3 — Intérprete de órdenes (ítem 1)
`ash
ros2 run arm_broker interprete_ordenes --ros-args -p laya_url:=http://<IP_DE_TU_PC>:8000 -p timeout_laya_s:=2.0
`
**Parámetro útil para demo:** -p forzar_clasificador:=true fuerza el uso exclusivo del clasificador local (evita que LAYA confunda colores, p. ej. "verde"?"rojo").
Si LAYA no responde o se fuerza, cae/va al clasificador (degradada=True) y la cadena sigue.'''
if old not in s:
    print('notfound')
else:
    s=s.replace(old,new)
    p.write_text(s,encoding='utf-8')
    print('ok')
