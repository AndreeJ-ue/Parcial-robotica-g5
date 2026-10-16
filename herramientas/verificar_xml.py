#!/usr/bin/env python3
"""Verifica perfil por defecto SUPER_CLIENT y servidores remotos del XML Fast DDS."""
import argparse
import ipaddress
import xml.etree.ElementTree as ET


def comprobar(ruta, direccion, puerto):
    ipaddress.IPv4Address(direccion)
    raiz = ET.parse(ruta).getroot()
    nombre = lambda e: e.tag.split('}')[-1]
    perfiles = [e for e in raiz.iter() if nombre(e) == 'participant'
                and e.attrib.get('is_default_profile', '').lower() in ('true', '1')]
    if len(perfiles) != 1:
        raise ValueError('se requiere exactamente un participant por defecto')
    perfil = perfiles[0]
    protocolos = [e.text.strip() for e in perfil.iter()
                  if nombre(e) == 'discoveryProtocol' and e.text]
    if protocolos != ['SUPER_CLIENT']:
        raise ValueError('el perfil por defecto debe usar discoveryProtocol SUPER_CLIENT')
    servidores = [e for e in perfil.iter() if nombre(e) == 'RemoteServer']
    if len(servidores) != 1:
        raise ValueError('esta configuración del equipo requiere un único RemoteServer')
    prefijo = servidores[0].attrib.get('prefix', '').upper()
    if prefijo != '44.53.00.5F.45.50.52.4F.53.49.4D.41':
        raise ValueError('prefix debe corresponder al servidor Fast DDS con id 0')
    locators = [e for e in servidores[0].iter() if nombre(e) == 'udpv4']
    if not locators:
        raise ValueError('RemoteServer no contiene un locator UDPv4')
    for locator in locators:
        valores = {nombre(e): (e.text or '').strip() for e in locator}
        if valores.get('address') != direccion or int(valores.get('port', '0')) != int(puerto):
            raise ValueError(f'XML remoto no coincide con {direccion}:{puerto}; revisar address/port')
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('xml')
    parser.add_argument('jetson')
    parser.add_argument('puerto', type=int)
    args = parser.parse_args()
    try:
        comprobar(args.xml, args.jetson, args.puerto)
    except (OSError, ValueError, ET.ParseError) as exc:
        parser.exit(1, f'ERROR XML: {exc}\n')
    print('XML Super Client coherente con el servidor configurado (id 0).')


if __name__ == '__main__':
    main()
