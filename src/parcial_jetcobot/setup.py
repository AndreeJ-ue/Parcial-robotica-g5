from glob import glob
from setuptools import setup, find_packages

setup(name='parcial_jetcobot', version='0.1.0', packages=find_packages(),
      data_files=[('share/ament_index/resource_index/packages',['resource/parcial_jetcobot']),
                  ('share/parcial_jetcobot',['package.xml']),
                  ('share/parcial_jetcobot/config',glob('config/*.json')),
                  ('share/parcial_jetcobot/launch',glob('launch/*.launch.py'))],
      install_requires=['setuptools'], zip_safe=True,
      maintainer='Equipo 5', maintainer_email='equipo@esan.edu.pe', license='Apache-2.0',
      description='Gran Reto JetCobot sobre el broker del RB2',
      entry_points={'console_scripts':[
          'interprete_ordenes = parcial_jetcobot.nodos:main_interprete',
          'broker_parcial = parcial_jetcobot.broker_parcial:main',
          'percepcion = parcial_jetcobot.nodos:main_percepcion',
          'cliente_ordenes = parcial_jetcobot.cliente:main',
          'transcriptor_voz = parcial_jetcobot.voz:main']})
