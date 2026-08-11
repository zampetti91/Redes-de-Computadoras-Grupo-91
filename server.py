#!/usr/bin/env python3.8

from socket import *
import xml.etree.ElementTree as ET
from inspect import signature
import threading


class Server:
    def __init__(self, server, port):
        self.procedures = []  # Inicializar la lista vacía           
        self.server = server
        self.port = port
        self.socket = socket(AF_INET, SOCK_STREAM)          
        self.socket.bind((self.server, self.port))
        self.socket.listen(5)
     
    def add_method(self, procedure_name):
        self.procedures.append(procedure_name)

    def crear_response_falta(self, fault_code, fault_string):
        """Crea una respuesta de falta XML-RPC"""
        xml_content = f"""<?xml version="1.0"?>
<methodResponse>
    <fault>
        <value>
            <struct>
                <member>
                    <name>faultCode</name>
                    <value><int>{fault_code}</int></value>
                </member>
                <member>
                    <name>faultString</name>
                    <value><string>{fault_string}</string></value>
                </member>
            </struct>
        </value>
    </fault>
</methodResponse>"""
        return xml_content

    def serve(self):
        print(f"Servidor XML-RPC iniciado en {self.server}:{self.port}")

        while True:
            connectionSocket = self.recibir_conexion_cliente()
            # Procesar la conexión en un hilo separado para no bloquear el loop principal
            threading.Thread(target=self.handle_client, args=(connectionSocket,), daemon=True).start()

    def handle_client(self, connectionSocket):
        try:
            try:
                recibido = connectionSocket.recv(1024).decode()
            except Exception:
                xml_content = self.crear_response_falta(5, "Otros errores")
                self.enviar_response(xml_content, connectionSocket)
                return
            try:
                # Separar headers y body del HTTP request
                headers, body = recibido.split("\n\n", 1)
            except ValueError:
                xml_content = self.crear_response_falta(5, "Otros errores")
                self.enviar_response(xml_content, connectionSocket)
                return

            try:
                # Parsear el XML del body
                root = ET.fromstring(body)
            except ET.ParseError:
                xml_content = self.crear_response_falta(1, "Error parseo de XML")
                self.enviar_response(xml_content, connectionSocket)
                return

            try:
                # Obtener el nombre del método
                method_name = root.find('methodName').text
            except AttributeError:
                xml_content = self.crear_response_falta(1, "Error parseo de XML")
                self.enviar_response(xml_content, connectionSocket)
                return

            # Obtener los valores de los parámetros (int, string o nil)
            params = root.findall('.//param/value')
            param_values = []
            for p in params:
                int_val = p.find('int')
                string_val = p.find('string')
                nil_val = p.find('nil')
                
                if int_val is not None:
                    param_values.append(int(int_val.text))
                elif string_val is not None:
                    param_values.append(string_val.text)
                elif nil_val is not None:
                    param_values.append(None)
                else:
                    param_values.append(None)

            # Buscar el método registrado
            procedure_found = None
            for procedure in self.getProcedures():
                if method_name == procedure.__name__:
                    procedure_found = procedure
                    break

            if procedure_found is None:
                xml_content = self.crear_response_falta(2, "No existe el método invocado")
                self.enviar_response(xml_content, connectionSocket)
                return

            # Verificar cantidad de parámetros
            sig = signature(procedure_found)
            expected_params = len(sig.parameters)
            
            if len(param_values) != expected_params:
                xml_content = self.crear_response_falta(3, "Error en parámetros del método invocado")
                self.enviar_response(xml_content, connectionSocket)
                return

            try:
                # Ejecutar el método
                result = procedure_found(*param_values)
                
                # Determinar el tipo de respuesta basado en el resultado
                if isinstance(result, str):
                    value_xml = f"<string>{result}</string>"
                elif isinstance(result, int):
                    value_xml = f"<int>{result}</int>"
                elif result is None:
                    value_xml = "<nil/>"
                else:
                    value_xml = f"<string>{str(result)}</string>"
                
                xml_content = f"""<?xml version="1.0"?>
<methodResponse>
    <params>
        <param>
            <value>{value_xml}</value>
        </param>
    </params>
</methodResponse>"""
            except Exception:
                xml_content = self.crear_response_falta(4, "Error interno en la ejecución del método")
                self.enviar_response(xml_content, connectionSocket)
                return

            self.enviar_response(xml_content, connectionSocket)
        finally:
            try:
                connectionSocket.close()
            except Exception:
                pass

    def recibir_conexion_cliente(self):
        self.connectionSocket, addr = self.socket.accept()
        return self.connectionSocket

    def getProcedures(self):
        return self.procedures

    def enviar_response(self, xml_content, connectionSocket):
        """Envía la respuesta HTTP con el contenido XML"""
        response = f"""HTTP/1.1 200 OK
Connection: close
Content-Length: {len(xml_content)}
Content-Type: text/xml

{xml_content}"""
        connectionSocket.sendall(response.encode())
        connectionSocket.close()

    def sendResponse(self, response, connectionSocket):
        self.connectionSocket.sendall(response.encode())
        self.connectionSocket.close()

