#!/usr/bin/env python3.8

import socket
import threading

import time
import psutil

BROADCAST_ADDRESS = "255.255.255.255"
DISCOVERY_PORT = 6091
MAX_ATTEMPTS = 5
RECEIVE_TIMEOUT = 10
CLAVE = "clave1234" 


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
            socket_udp.sendto("DISCOVER\n".encode("utf-8"), (BROADCAST_ADDRESS, DISCOVERY_PORT))

            try:
                data, server_address = socket_udp.recvfrom(1024)
            except socket.timeout:
                continue

            parts = data.decode("utf-8").strip().split()
            if len(parts) != 4 or parts[0] != "SERVER":
                continue

            umbral_cpu = float(parts[1])
            umbral_mem = float(parts[2])
            tcp_port = int(parts[3])

            return server_address[0], tcp_port, umbral_cpu, umbral_mem
    finally:
        socket_udp.close()

    return None


def registrar_agente(socket_tcp, clave):
    """Realiza el registro del agente común en el servidor."""
    socket_tcp.sendall(f"ADMIN {clave}\n".encode("utf-8"))
    socket_tcp.settimeout(RECEIVE_TIMEOUT)

    try:
        respuesta = socket_tcp.recv(1024)
    except socket.timeout as exc:
        raise TimeoutError("No se recibió respuesta de registro del servidor")

    respuesta_str = respuesta.decode("utf-8").strip()
    if respuesta_str != "ADMIN_RESP":
        raise RuntimeError(f"Respuesta de registro inesperada: {respuesta_str!r}")

    return True


def cerrar_registro(socket_tcp):
    """Elimina el registro del agente y cierra la conexión."""
    socket_tcp.sendall(b"END\n")
    socket_tcp.shutdown(socket.SHUT_RDWR)
    socket_tcp.close()
    return True


def recibir_linea(socket_tcp):
    """Recibe una respuesta TCP completa, terminada en salto de línea."""
    respuesta = bytearray()
    while b"\n" not in respuesta:
        datos = socket_tcp.recv(4096)
        if not datos:
            raise ConnectionError("El servidor cerró la conexión")
        respuesta.extend(datos)
    return bytes(respuesta).split(b"\n", 1)[0].decode("utf-8").strip()


def main():
    respuesta_servidor = descubrir_servidor()
    if respuesta_servidor is None:
        print("No se encontró ningún servidor")
        return -1

    ip_server, port_server, umbral_cpu, umbral_mem = respuesta_servidor
    print(f"Servidor encontrado en {ip_server}:{port_server}")

    socket_tcp = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    socket_tcp.connect((ip_server, port_server))

    try:
        registrar_agente(socket_tcp, CLAVE)
        print("Registro confirmado por el servidor")
        lista = ""
        while True:
            comando = input("Comando (L, P <idAgente>, M <idAgente> <metric> o E): ").strip().upper()
            if comando == "L":
                socket_tcp.sendall(b"LIST_AGENTS\n")
                lista = recibir_linea(socket_tcp)
                print(lista)
            elif comando.startswith("P "):
                try:
                    partes_comando = comando.split()
                    if len(partes_comando) != 2:
                        raise ValueError
                    agent_id = int(partes_comando[1])
                except (ValueError, IndexError):
                    print("Debe indicar un idAgente válido")
                    continue

                socket_tcp.sendall(f"GET_PROC {agent_id}\n".encode("utf-8"))
                try:
                    print(recibir_linea(socket_tcp))
                except socket.timeout:
                    print("El agente no respondió a la solicitud de procesos")
            elif comando.startswith("M "):
                try:
                    partes_comando = comando.split()
                    if len(partes_comando) != 3:
                        raise ValueError
                    agent_id = int(partes_comando[1])
                    metric = partes_comando[2]
                    if metric not in ("CPU", "MEM"):
                        raise ValueError
                except (ValueError, IndexError):
                    print("Debe indicar un idAgente y una métrica válidos (CPU o MEM)")
                    continue

                socket_tcp.sendall(
                    f"GET_METRIC {agent_id} {metric}\n".encode("utf-8")
                )
                try:
                    print(recibir_linea(socket_tcp))
                except socket.timeout:
                    print("El servidor no respondió a la solicitud de métricas")
            elif comando == "E":
                break
            else:
                print("Comando inválido")

        cerrar_registro(socket_tcp)
        print("Registro eliminado y conexión cerrada")
    except (TimeoutError, RuntimeError) as exc:
        print(f"Error de registro: {exc}")
        socket_tcp.close()
        return -1

    return 0

main()
