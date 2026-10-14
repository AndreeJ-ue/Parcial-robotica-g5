from setuptools import setup, find_packages
setup(name='jetcobot_p13',version='0.1.0',packages=find_packages(),
 data_files=[('share/ament_index/resource_index/packages',['resource/jetcobot_p13']),('share/jetcobot_p13',['package.xml'])],
 install_requires=['setuptools','requests'],zip_safe=True,maintainer='Equipo 5',maintainer_email='equipo@esan.edu.pe',license='Apache-2.0',
 entry_points={'console_scripts':['interprete_ordenes = jetcobot_p13.interprete_ordenes:main','transcriptor_voz = jetcobot_p13.transcriptor_voz:main']})
