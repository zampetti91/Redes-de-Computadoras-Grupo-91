#!/usr/bin/env python3.8

import socket


DISCOVERY_PORT = 6091
MAX_ATTEMPTS = 5
RECEIVE_TIMEOUT = 10


def descubrir_servidor():
    """Busca un servidor mediante broadcast UDP.

    Devuelve (ip, puerto_tcp, umbral_cpu, umbral_mem) si encuentra un servidor o None si falla.
    """
    socket_udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    socket_udp.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    socket_udp.settimeout(RECEIVE_TIMEOUT)
    socket_udp.bind(("", 0))  # Asigna cualquier puerto libre disponible

    try:
        for _ in range(MAX_ATTEMPTS):
            socket_udp.sendto("DISCOVER\n".encode("utf-8"), ("255.255.255.255", DISCOVERY_PORT))

            try:
                data, server_address = socket_udp.recvfrom(1024)
            except socket.timeout:
                continue
    
            parts = data.decode("utf-8").strip().split()
            if len(parts) != 4 or parts[0] != "SERVER":
                continue

            umbral_cpu = int(parts[1])
            umbral_mem = int(parts[2])
            tcp_port = int(parts[3])

            return server_address[0], tcp_port, umbral_cpu, umbral_mem
    finally:
        socket_udp.close()

    return None


def main():
    respuesta_servidor = descubrir_servidor()
    if respuesta_servidor is None:
        print("No se encontró ningún servidor")
        return -1

    ip_server, port_server, umbral_cpu, umbral_mem = respuesta_servidor
    print(f"Servidor encontrado en {ip_server}:{port_server} con umbral_cpu={umbral_cpu} y umbral_mem={umbral_mem}")
    return 0


main()
