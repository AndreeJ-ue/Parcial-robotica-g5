from setuptools import find_packages, setup

package_name = 'arm_broker'

setup(
    name=package_name,
    version='0.1.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='equipo',
    maintainer_email='equipo@esan.edu.pe',
    description='Broker del JetCobot y nodos de los Ítems 1 y 3',
    license='Apache-2.0',
    entry_points={
        'console_scripts': [
            # Broker (no se modifica): el único nodo que publica /joint_states
            'broker = arm_broker.broker:main',
            # Ítem 1: intérprete de frases en español
            'interprete_ordenes = arm_broker.interprete_ordenes:main',
            # Ítem 3: transcriptor de voz
            'transcriptor_voz = arm_broker.transcriptor_voz:main',
            # Ítem 2: orquestador (poses + pinza + cola; la cámara es un nodo aparte)
            'orquestador = arm_broker.orquestador:main',
            # Ítem 2: nodo de percepción por color (cámara montada en el brazo)
            'percepcion_camara = arm_broker.percepcion_camara:main',
            # Ítem 2: cliente de frases por teclado para pruebas
            'cliente_texto = arm_broker.cliente_texto:main',
        ],
    },
)
