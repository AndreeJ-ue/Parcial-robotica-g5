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
    description='Broker de acceso exclusivo al JetCobot',
    license='Apache-2.0',
    entry_points={
        'console_scripts': [
            'broker = arm_broker.broker:main',
            'cliente = arm_broker.cliente:main',
            'interprete_ordenes = arm_broker.interprete_ordenes:main',
            'transcriptor_voz = arm_broker.transcriptor_voz:main',
            'percepcion_camara = arm_broker.percepcion_camara:main',   
            'orquestador_item2 = arm_broker.orquestador_item2:main',  
            'cliente_texto = arm_broker.cliente_texto:main',
            'pinza_pymycobot = arm_broker.pinza_pymycobot:main',
        ],
    },
)
