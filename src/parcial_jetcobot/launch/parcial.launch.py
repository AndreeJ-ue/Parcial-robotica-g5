from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration,PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    config=LaunchConfiguration('config_file')
    default=PathJoinSubstitution([FindPackageShare('parcial_jetcobot'),'config','posiciones_fijas.articular.simulacion.json'])
    return LaunchDescription([
        DeclareLaunchArgument('config_file',default_value=default),
        DeclareLaunchArgument('eventos',default_value='evidencias/broker_eventos.csv'),
        Node(package='parcial_jetcobot',executable='interprete_ordenes',output='screen',parameters=[{'config_file':config}]),
        Node(package='parcial_jetcobot',executable='percepcion',output='screen',parameters=[{'config_file':config}]),
        Node(package='parcial_jetcobot',executable='broker_parcial',output='screen',parameters=[
            {'config_file':config,'politica':'prioridad','archivo_eventos':LaunchConfiguration('eventos')}])
    ])
