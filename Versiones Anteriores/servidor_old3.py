#!/usr/bin/env python3.8

import socket
import threading

TCP_PORT = 5001
UDP_PORT = 6091
SECRET_KEY = "clave1234"
REGISTERED_AGENTS = set()


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


def handle_client(client_socket, client_address):
    """Maneja la comunicación con un cliente TCP."""
    print(f"Cliente conectado desde {client_address}")
    registered = False
    buffer = b""
    try:
        while True:
            data = client_socket.recv(1024)
            if not data:
                break

            buffer += data
            while b"\n" in buffer:
                raw_message, buffer = buffer.split(b"\n", 1)
                message = raw_message.decode("utf-8").strip()
                if not message:
                    continue

                print(f"Recibido de {client_address}: {message}")

                if message.startswith("METRIC "):
                    if registered:
                        parts = message.split(" ", 2)
                        if len(parts) == 3:
                            print(f"Métrica recibida de {client_address}: {parts[1]} {parts[2]}")
                    continue

                if message == "END":
                    if registered:
                        REGISTERED_AGENTS.discard(client_address)
                        print(f"Agente eliminado del registro: {client_address}")
                    return

                if message.startswith("REGISTER "):
                    partes = message.split(" ", 1)
                    if len(partes) != 2 or not partes[1]:
                        client_socket.sendall(b"ERROR\n")
                        print(f"Registro inválido para {client_address}: formato incorrecto")
                        return

                    clave = partes[1]
                    if clave == SECRET_KEY:
                        REGISTERED_AGENTS.add(client_address)
                        registered = True
                        client_socket.sendall(b"REG_RESP\n")
                        print(f"Agente registrado correctamente desde {client_address}")
                        continue

                    client_socket.sendall(b"ERROR\n")
                    print(f"Registro rechazado para {client_address}: clave incorrecta")
                    return

                client_socket.sendall(b"ERROR\n")
                print(f"Mensaje inválido recibido desde {client_address}: {message}")
                return
    except ConnectionResetError:
        print(f"Conexión con {client_address} cerrada inesperadamente.")
    finally:
        if registered:
            REGISTERED_AGENTS.discard(client_address)
        client_socket.close()
        print(f"Cliente desconectado desde {client_address}")


def main():
    socket_udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    socket_udp.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    socket_udp.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    socket_udp.bind(("0.0.0.0", UDP_PORT))

    discovery_thread = threading.Thread(
        target=handle_discover,
        args=(socket_udp, TCP_PORT, 80, 90),
        daemon=False,
    )
    discovery_thread.start()
    print("Servidor de descubrimiento escuchando en UDP 0.0.0.0:6091")

    socket_tcp = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    socket_tcp.bind(("0.0.0.0", TCP_PORT))
    socket_tcp.listen(5)

    while True:
        client_socket, client_address = socket_tcp.accept()
        client_thread = threading.Thread(
            target=handle_client,
            args=(client_socket, client_address),
            daemon=False,
        )
        client_thread.start()

main()
