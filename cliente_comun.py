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
    socket_tcp.sendall(f"REGISTER {clave}\n".encode("utf-8"))
    socket_tcp.settimeout(RECEIVE_TIMEOUT)

    try:
        respuesta = socket_tcp.recv(1024)
    except socket.timeout as exc:
        raise TimeoutError("No se recibió respuesta de registro del servidor")

    respuesta_str = respuesta.decode("utf-8").strip()
    if respuesta_str != "REG_RESP":
        raise RuntimeError(f"Respuesta de registro inesperada: {respuesta_str!r}")

    return True

def cerrar_registro(socket_tcp):
    """Elimina el registro del agente y cierra la conexión."""
    socket_tcp.sendall(b"END\n")
    socket_tcp.shutdown(socket.SHUT_RDWR)
    socket_tcp.close()
    return True

def enviar_metricas_periodicamente(socket_tcp, umbral_cpu, umbral_mem, detener):
    """Envía métricas al servidor cada 15 segundos."""

    while not detener.is_set():
        cpu_percent = psutil.cpu_percent(interval=None)
        memory_percent = psutil.virtual_memory().percent

        mensaje = f"METRIC CPU {cpu_percent}\n"
        socket_tcp.sendall(mensaje.encode("utf-8"))

        mensaje = f"METRIC MEM {memory_percent}\n"
        socket_tcp.sendall(mensaje.encode("utf-8"))

        if cpu_percent > umbral_cpu:
            mensaje = f"ALERT CPU {cpu_percent}\n"
            socket_tcp.sendall(mensaje.encode("utf-8"))

        if memory_percent > umbral_mem:
            mensaje = f"ALERT MEM {memory_percent}\n"
            socket_tcp.sendall(mensaje.encode("utf-8"))

        if cpu_percent > umbral_cpu: 
            print(f"Advertencia: Umbral superado CPU: {cpu_percent}%")

        if memory_percent > umbral_mem:
            print(f"Advertencia: Umbral superado Memoria: {memory_percent}%")

        detener.wait(15)  # Espera 15 segundos o hasta que se establezca el evento de detención

def get_proc(socket_tcp, detener):
    """Responde a GET_PROC con la lista de procesos del agente."""
    while not detener.is_set():
        try:
            solicitud_del_servidor = socket_tcp.recv(1024)
        except socket.timeout:
            continue
        except OSError:
            return

        if not solicitud_del_servidor:
            return

        if solicitud_del_servidor.decode("utf-8").strip() == "GET_PROC":
            procesos = []
            for proc in psutil.process_iter(["pid", "name"]):
                try:
                    procesos.append(f"{proc.info['pid']}:{proc.info['name']}")
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue

            respuesta = f"PROC {', '.join(procesos)}\n"
            socket_tcp.sendall(respuesta.encode("utf-8"))

def main():
    respuesta_servidor = descubrir_servidor()
    if respuesta_servidor is None:
        print("No se encontró ningún servidor")
        return -1

    ip_server, port_server, umbral_cpu, umbral_mem = respuesta_servidor
    print(f"Servidor encontrado en {ip_server}:{port_server} con umbral_cpu={umbral_cpu} y umbral_mem={umbral_mem}")

    socket_tcp = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    socket_tcp.connect((ip_server, port_server))

    try:
        registrar_agente(socket_tcp, CLAVE)
        print("Registro confirmado por el servidor")
        detener = threading.Event()
        proc_thread = threading.Thread(target=get_proc, args=(socket_tcp, detener))
        proc_thread.start()
        metricas_thread = threading.Thread(
            target=enviar_metricas_periodicamente,
            args=(socket_tcp, umbral_cpu, umbral_mem, detener),
        )
        metricas_thread.start()
        while True:
            comando = input("Comando (E para salir): ").strip().upper()
            if comando == "E":
                break
        detener.set()
        metricas_thread.join()
        cerrar_registro(socket_tcp)
        proc_thread.join()
        print("Registro eliminado y conexión cerrada")
    except (TimeoutError, RuntimeError) as exc:
        print(f"Error de registro: {exc}")
        socket_tcp.close()
        return -1

    return 0

main()
