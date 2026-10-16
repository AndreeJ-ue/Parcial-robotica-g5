#!/usr/bin/env bash
# Usar: source ~/parcial-jetcobot/conectar_reto.sh
# No modifica .bashrc, el XML, otros nodos ni el Discovery Server.
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  echo 'ERROR: usa source conectar_reto.sh para conservar el entorno.' >&2
  exit 1
fi

_configurar_reto() {
  local raiz archivo dominio puerto jetson perfil
  raiz="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)" || return 1
  archivo="$raiz/config/equipo.env"
  [[ -f "$archivo" ]] || { echo "ERROR: copia config/equipo.env.example a config/equipo.env y revisa sus valores." >&2; return 1; }
  # Impedir que una configuración incompleta herede IP o dominio de otra reserva.
  unset JETSON ROS_DOMAIN_ID DISCOVERY_PORT FASTRTPS_DEFAULT_PROFILES_FILE ROS_DISCOVERY_SERVER
  source "$archivo" || return 1
  jetson="${JETSON:-}"; dominio="${ROS_DOMAIN_ID:-}"; puerto="${DISCOVERY_PORT:-11811}"
  [[ -n "$jetson" ]] || { echo 'ERROR: falta JETSON (JETSON_IP no es la variable de este script).' >&2; return 1; }
  [[ "$dominio" =~ ^[0-9]+$ && ${#dominio} -le 3 ]] || { echo 'ERROR: dominio inválido.' >&2; return 1; }
  [[ "$puerto" =~ ^[0-9]+$ && ${#puerto} -le 5 ]] || { echo 'ERROR: puerto inválido.' >&2; return 1; }
  (( 10#$dominio <= 232 && 10#$puerto >= 1 && 10#$puerto <= 65535 )) || { echo 'ERROR: dominio fuera de 0..232 o puerto fuera de 1..65535.' >&2; return 1; }
  [[ "${ROS_LOCALHOST_ONLY:-0}" == 0 ]] || { echo 'ERROR: ROS_LOCALHOST_ONLY debe ser 0 para la red del laboratorio.' >&2; return 1; }
  [[ "${RMW_IMPLEMENTATION:-rmw_fastrtps_cpp}" == rmw_fastrtps_cpp ]] || { echo 'ERROR: esta configuración requiere rmw_fastrtps_cpp.' >&2; return 1; }
  perfil="${FASTRTPS_DEFAULT_PROFILES_FILE:-$HOME/super_client_configuration_file.xml}"
  [[ -f /opt/ros/humble/setup.bash ]] || { echo 'ERROR: falta ROS 2 Humble.' >&2; return 1; }
  [[ -f "$raiz/install/setup.bash" ]] || { echo "ERROR: compila primero: source /opt/ros/humble/setup.bash; cd $raiz; colcon build" >&2; return 1; }
  [[ -f "$perfil" ]] || { echo "ERROR: falta XML de Super Client: $perfil" >&2; return 1; }
  python3 "$raiz/herramientas/verificar_xml.py" "$perfil" "$jetson" "$puerto" || return 1
  source /opt/ros/humble/setup.bash || return 1
  source "$raiz/install/setup.bash" || return 1
  export JETSON="$jetson" ROS_DOMAIN_ID="$((10#$dominio))" ROS_LOCALHOST_ONLY=0
  export DISCOVERY_PORT="$((10#$puerto))" RMW_IMPLEMENTATION=rmw_fastrtps_cpp
  export ROS_DISCOVERY_SERVER="$jetson:$DISCOVERY_PORT" FASTRTPS_DEFAULT_PROFILES_FILE="$perfil"
  ros2 daemon stop || return 1
  ros2 daemon start || return 1
  echo "Entorno cargado: equipo 5 · dominio=$ROS_DOMAIN_ID · jetson=$JETSON · discovery=$ROS_DISCOVERY_SERVER"
  echo 'Entorno ROS del equipo configurado.'
}
_configurar_reto
_reto_resultado=$?
unset -f _configurar_reto
return "$_reto_resultado"
