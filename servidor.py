#!/usr/bin/env python3.8

import socket
import threading


def handle_discover(discovery_socket, tcp_port, umbral_cpu, umbral_mem):
    """Responde a los clientes que buscan el servidor por UDP."""
    while True:
        try:
            data, client_address = discovery_socket.recvfrom(1024)
        except OSError:
            break

        if data.decode("utf-8").strip() == "DISCOVER":
            response = f"SERVER {umbral_cpu} {umbral_mem} {tcp_port}\n".encode("utf-8")
            try:
                discovery_socket.sendto(response, client_address)
            except OSError:
                break


def main():

    socket_udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    socket_udp.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    socket_udp.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    socket_udp.bind(("0.0.0.0", 6091))

    discovery_thread = threading.Thread(
        target=handle_discover,
        args=(socket_udp, 5001, 80, 90),
        daemon=False,
    )
    discovery_thread.start()
    print("Servidor de descubrimiento escuchando en UDP 0.0.0.0:6091")


main()
