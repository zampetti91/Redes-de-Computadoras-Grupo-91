#!/usr/bin/env python3.8

import logging
import socket
import threading

TCP_PORT = 5001
UDP_PORT = 6091
SECRET_KEY = "clave1234"
LOG_FILE = "servidor.log"
REGISTERED_AGENTS = set()
NEXT_AGENT_ID = 1
AGENTS_LOCK = threading.Lock()
REGISTERED_ADMINS = set()
AGENT_SOCKETS = {}
PROC_REQUESTS = {}
AGENT_METRICS = {}

logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

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
    admin_registered = False
    agent_id = None
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

                # print(f"Recibido de {client_address}: {message}")

                if message.startswith("METRIC "):
                    if registered:
                        parts = message.split(" ", 2)
                        if len(parts) == 3 and agent_id is not None:
                            with AGENTS_LOCK:
                                metricas = AGENT_METRICS.setdefault(agent_id, [])
                                metricas.append((parts[1], parts[2]))
                                if len(metricas) > 20:
                                    metricas.pop(0)
                            print(f"Métrica recibida de {client_address}: {parts[1]} {parts[2]}")
                    continue

                if message.startswith("ALERT "):
                    if registered:
                        parts = message.split(" ", 2)
                        if len(parts) == 3 and agent_id is not None:
                            logger.info(
                                "Alerta del agente %s (%s): %s %s",
                                agent_id,
                                client_address,
                                parts[1],
                                parts[2],
                            )
                            print(f"Alerta recibida de {client_address}: {parts[1]} {parts[2]}")
                    continue                    

                if message.startswith("PROC "):
                    if agent_id is not None:
                        with AGENTS_LOCK:
                            admin_socket = PROC_REQUESTS.pop(agent_id, None)
                        if admin_socket is not None:
                            admin_socket.sendall(f"{message}\n".encode("utf-8"))
                    continue

                if message == "END":
                    if registered:
                        if agent_id is not None:
                            with AGENTS_LOCK:
                                REGISTERED_AGENTS.discard((client_address, agent_id))
                            print(f"Agente {agent_id} eliminado del registro: {client_address}")
                        elif admin_registered:
                            REGISTERED_ADMINS.discard(client_address)
                            print(f"Agente administrador eliminado del registro: {client_address}")
                    return

                if message == "LIST_AGENTS":
                    if admin_registered:
                        with AGENTS_LOCK:
                            agentes = sorted(REGISTERED_AGENTS, key=lambda agente: agente[1])
                        listado = " ".join(
                            f"{agent_id} {address[0]}:{address[1]}"
                            for address, agent_id in agentes
                        )
                        client_socket.sendall(
                            f"AGENTS {len(agentes)} {listado}\n".encode("utf-8")
                        )
                    else:
                        client_socket.sendall(b"ERROR\n")
                    continue

                if message.startswith("GET_METRIC "):
                    partes = message.split()
                    try:
                        if len(partes) != 3:
                            raise ValueError
                        requested_agent_id = int(partes[1])
                        metric_name = partes[2]
                    except (IndexError, ValueError):
                        client_socket.sendall(b"ERROR\n")
                        continue

                    if not admin_registered:
                        client_socket.sendall(b"ERROR\n")
                        continue

                    with AGENTS_LOCK:
                        valores = [
                            value
                            for name, value in AGENT_METRICS.get(requested_agent_id, [])
                            if name == metric_name
                        ]
                    respuesta = " ".join(
                        ["MEASUREMENTS", str(requested_agent_id), metric_name, str(len(valores))]
                        + valores
                    )
                    client_socket.sendall(f"{respuesta}\n".encode("utf-8"))
                    continue

                if message.startswith("GET_PROC "):
                    partes = message.split(" ", 1)
                    try:
                        requested_agent_id = int(partes[1])
                    except (IndexError, ValueError):
                        client_socket.sendall(b"ERROR\n")
                        continue

                    if not admin_registered:
                        client_socket.sendall(b"ERROR\n")
                        continue

                    with AGENTS_LOCK:
                        agent_socket = AGENT_SOCKETS.get(requested_agent_id)
                        if agent_socket is not None:
                            PROC_REQUESTS[requested_agent_id] = client_socket

                    if agent_socket is None:
                        client_socket.sendall(b"ERROR\n")
                    else:
                        agent_socket.sendall(b"GET_PROC\n")
                    continue

                if message.startswith("REGISTER "):
                    partes = message.split(" ", 1)
                    if len(partes) != 2 or not partes[1]:
                        client_socket.sendall(b"ERROR\n")
                        print(f"Registro inválido para {client_address}: formato incorrecto")
                        return

                    clave = partes[1]
                    if clave == SECRET_KEY:
                        global NEXT_AGENT_ID
                        with AGENTS_LOCK:
                            agent_id = NEXT_AGENT_ID
                            NEXT_AGENT_ID += 1
                            REGISTERED_AGENTS.add((client_address, agent_id))
                            AGENT_SOCKETS[agent_id] = client_socket
                            AGENT_METRICS[agent_id] = []
                        registered = True
                        client_socket.sendall(b"REG_RESP\n")
                        print(f"Agente {agent_id} registrado correctamente desde {client_address}")
                        continue

                    client_socket.sendall(b"ERROR\n")
                    print(f"Registro rechazado para {client_address}: clave incorrecta")
                    return

                if message.startswith("ADMIN "):
                    partes = message.split(" ", 1)
                    if len(partes) != 2 or not partes[1]:
                        client_socket.sendall(b"ERROR\n")
                        print(f"Registro inválido para {client_address}: formato incorrecto")
                        return

                    clave = partes[1]
                    if clave == SECRET_KEY:
                        REGISTERED_ADMINS.add(client_address)
                        registered = True
                        admin_registered = True
                        client_socket.sendall(b"ADMIN_RESP\n")
                        print(f"Agente administrador registrado correctamente desde {client_address}")
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
            if agent_id is not None:
                with AGENTS_LOCK:
                    REGISTERED_AGENTS.discard((client_address, agent_id))
                    AGENT_SOCKETS.pop(agent_id, None)
                    PROC_REQUESTS.pop(agent_id, None)
            elif admin_registered:
                REGISTERED_ADMINS.discard(client_address)
        client_socket.close()
        print(f"Cliente desconectado desde {client_address}")


def main():
    socket_udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    socket_udp.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    socket_udp.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    socket_udp.bind(("0.0.0.0", UDP_PORT))

    discovery_thread = threading.Thread(
        target=handle_discover,
        args=(socket_udp, TCP_PORT, 2.9, 30.1),
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
