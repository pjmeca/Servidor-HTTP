# coding=utf-8
#!/usr/bin/env python3

from ast import arg
from distutils.log import error
import socket
import selectors  # https://docs.python.org/3/library/selectors.html
import select
import string
import types        # Para definir el tipo de datos data
import argparse     # Leer parametros de ejecución
import os           # Obtener ruta y extension
from datetime import datetime, timedelta  # Fechas de los mensajes HTTP
import time         # Timeout conexión
import sys          # sys.exit
import re           # Analizador sintáctico
import logging      # Para imprimir logs

#from multiprocessing import Process  # Para ejecutarlo en Windows
import random

from tqdm import tqdm # Barra de progreso

from server_regex import *  # Expresiones regulares del servidor

BUFSIZE = 8192  # Tamaño máximo del buffer que se puede utilizar
TIMEOUT_CONNECTION = 200  # Timeout para la conexión persistente
MAX_ACCESOS = 10
MAX_AGE = 120 # Las cookies expiran a los 2 minutos
COOKIE_NAME = "cookie_counter"
SERVER_NAME = "www.serversstt73.com"

# Extensiones admitidas (extension, name in HTTP)
filetypes = {"gif": "image/gif", "jpg": "image/jpg", "jpeg": "image/jpeg", "png": "image/png", "htm": "text/htm",
             "html": "text/html; charset=UTF-8", "css": "text/css", "js": "text/js"}

# Archivos prohibidos
forbidden_files = {"./web_sstt.py", "./server_regex.py", "./error.html"}

# Configuración de logging
logging.basicConfig(level=logging.INFO,
                    format='[%(asctime)s.%(msecs)03d] [%(levelname)-7s] %(message)s',
                    datefmt='%Y-%m-%d %H:%M:%S')
logger = logging.getLogger()

"""
Cómo usar el logger
-------------------------------
logger.debug("HOLA")
logger.info("HOLA")
logger.warning("HOLA")
logger.error("HOLA")
"""

code_msg = {200: "OK", 400:"Bad request", 403:"Forbidden", 404:"Not found", 405:"Method Not Allowed",
505: "HTTP Version Not Supported"}


"""""""""""""""""""""CONEXIONES"""""""""""""""""""""""""""
def enviar_mensaje(cs, data):
    """ Esta función envía datos (data) a través del socket cs
        Devuelve el número de bytes enviados.
    """
    #logger.info("Sending:\n{}".format(data))

    # Nos aseguramos de que esté codificado en bytes
    if not isinstance(data, (bytes, bytearray)) :
        data = data.encode()

    # Y lo enviamos
    cs.sendall(data)


def enviar_fichero(cs, cabecera, root):
    """ Esta función envía el fichero en root a través del socket cs
        con la cabecera especificada.
    """
    if root:
        logger.info("Sending file...")
        # Leer y enviar el contenido del fichero a retornar en el cuerpo de la respuesta.
        # Se abre el fichero en modo lectura y modo binario
        f = open(root, "rb")
        bar = tqdm(total=os.path.getsize(root))
        # Se lee el fichero en bloques de BUFSIZE bytes (8KB)
        while True:
            bloque = f.read(BUFSIZE) 
            if not bloque :
                # Cuando ya no hay más información para leer, se corta el bucle
                break                        
            else :
                # Enviamos el contenido por el socket
                data = cabecera.encode() + bloque # Solo la primera vez habrá cabecera
                enviar_mensaje(cs, data)
                cabecera = "" 
                bar.update(len(bloque))
        bar.close()
        f.close()
    else :
        logger.info("Sending message...")
        enviar_mensaje(cs, cabecera)

def recibir_mensaje(cs):
    """ Esta función recibe datos a través del socket cs
        Leemos la información que nos llega. recv() devuelve un string con los datos.
    """
    data = cs.recv(BUFSIZE)
    if data :
        data = data.decode()
    # logger.info("Data received:\n{}".format(data))
    return data


def enviar_error(cs, codigo):
    logger.error("Sending error {}...".format(codigo))

    # Abrir archivo con el template de errores
    f = open("error.html", "r")
    html = f.read()
    f.close()

    # Mensaje de error
    msg = code_msg.get(codigo)
    if not msg : msg = "" # Puede ser que el código de error no tenga un mensaje asociado

    # Formar la web html de error
    final = error_html(html, codigo, msg)

    """ Para ver el mensaje que se envía:
    f = open("salida.html", "w+")
    f.write(final)
    f.close()
    """

    # Formar cabecera HTTP
    mensaje = construir_cabecera(codigo=codigo, connection="Keep-Alive", content_length=sys.getsizeof(final), content_type=filetypes.get("html"))
    mensaje = mensaje + final

    # Enviar mensaje con enviar_mensaje
    enviar_mensaje(cs, mensaje)


def cerrar_conexion(cs):
    """ Esta función cierra una conexión activa.
    """
    cs.close()
    logger.info("Connection closed")
    pass


""""""""""""""""""""""""""""""""""""""""""""""""

"""""""""""""""""""""PROCESAMIENTO"""""""""""""""""""""""""""
def construir_cabecera(codigo, connection, cookies=None, content_length=0, content_type="text/html", last_modified=None) :

    # Línea de estado. P.ej: HTTP/1.1 200 OK\r\n
    respuesta = "HTTP/1.1 {} {}\r\n".format(codigo, code_msg.get(codigo))

    # Fecha. P.ej: Date: Sun, 26 Sep 2010 20:09:20 GMT\r\n
    respuesta = respuesta + "Date: {}\r\n".format(datetime.utcnow().strftime('%a, %d %b %Y %H:%M:%S GMT'))

    # Servidor. P.ej: Server: Apache/2.0.52 (CentOS)\r\n
    respuesta = respuesta + "Server: {}\r\n".format(SERVER_NAME)

    # Conexión. P.ej: Connection: Keep-Alive\r\n
    respuesta = respuesta + "Connection: {}\r\n".format(connection)

    # Set-cookie. 
    if cookies :
        cookie_list = ""
        # Pasamos la lista de cookies a string
        for cookie in cookies :
            cookie_list = cookie_list + "{}={};".format(cookie[0],cookie[1])
        cookie_list = cookie_list[:-1] # Eliminamos el último ";"
        respuesta = respuesta + "Set-Cookie: {}; Max-Age={}\r\n".format(cookie_list, MAX_AGE)

    # Content-Length. P.ej: Content-Length: 2652\r\n
    respuesta = respuesta + "Content-Length: {}\r\n".format(content_length)

    # Content-Type. P.ej: Content-Type: text/html; charset=ISO-8859-1\r\n
    respuesta = respuesta + "Content-Type: {}\r\n".format(content_type)

    # (EXTRA) Last-Modified: Tue, 30 Oct 2007 17:00:02 GMT\r\n
    format(datetime.utcnow().strftime('%a, %d %b %Y %H:%M:%S GMT'))
    if last_modified :
        respuesta = respuesta + "Last-Modified: {}\r\n".format(datetime.fromtimestamp(last_modified).strftime('%a, %d %b %Y %H:%M:%S GMT'))
    
    # (EXTRA) Keep-Alive: timeout=10, max=100\r\n
    respuesta = respuesta + "Keep-Alive: timeout={}, max={}\r\n".format(TIMEOUT_CONNECTION, MAX_ACCESOS)

    # \r\n
    respuesta = respuesta + "\r\n"

    return respuesta
	        
            

def process_cookies(headers, isHtml):
    """ Esta función procesa la cookie cookie_counter
        1. Se analizan las cabeceras en headers para buscar la cabecera Cookie
        2. Una vez encontrada una cabecera Cookie se comprueba si el valor es cookie_counter
        3. Si no se encuentra cookie_counter , se devuelve 1
        4. Si se encuentra y tiene el valor MAX_ACCESSOS se devuelve MAX_ACCESOS
        5. Si se encuentra y tiene un valor 1 <= x < MAX_ACCESOS se incrementa en 1 y se devuelve el valor
    """
    value = 0

    for cabecera in headers:
        if cabecera[0].lower() == "cookie" :
            # Separar cada cookie
            cookies = cookie_er.findall(cabecera[1])
            # Buscar la cookie cookie_counter
            for cookie in cookies :
                cookie = cookie.replace(";","") # Eliminamos el ; (si está)
                aux = cookie.partition("=")
                if aux[0].lower() == COOKIE_NAME :
                    value = int(aux[2])
                    break
            break
    if not isHtml :
        logger.info("Not html, delivering same cookie value.")
        return value    # Si no es un html, no lo contamos como un acceso
    elif value >= MAX_ACCESOS :
        return -1       # CAMBIO ---> Devuelvo -1 para diferenciar el caso en que ya estaba en MAX_ACCESOS del que 
                        #    acaba de llegar al incrementar 1
    elif value < 1 :
        return 1        # No la ha encontrado
    else :
        return value+1  # Sí la ha encontrado


def process_web_request(cs):
    """ Procesamiento principal de los mensajes recibidos.
    Típicamente se seguirá un procedimiento similar al siguiente (aunque el alumno puede modificarlo si lo desea)
    """
    # Bucle para esperar hasta que lleguen datos en la red a través del socket cs con select()
    rlist = [cs]
    while not cs.fileno() == -1:
        rsublist, [], [] = select.select(rlist, [], [], TIMEOUT_CONNECTION)

        # Se comprueba si hay que cerrar la conexión por exceder TIMEOUT_CONNECTION segundos
        #  sin recibir ningún mensaje o hay datos. Se utiliza select.select
        if rsublist :
            # Si no es por timeout y hay datos en el socket cs.
            # Leer los datos con recv.
            logger.info("New data in socket. Reading...")
            data = recibir_mensaje(cs)

            if not data :
                logger.error("Data was empty, closing...")
                cerrar_conexion(cs)
                return

            # Analizar que la línea de solicitud y comprobar está bien formateada según HTTP 1.1
            aux = data.partition("\r\n")
            solicitud = aux[0]
            data = aux[2]
            m = solicitud_er.fullmatch(solicitud)
            if m:
                # Extraer valores de la solicitud
                method = m.group(1)
                url = m.group(2)
                http_version = m.group(3)
                logger.info("Request Method: {}; Request Location: {}; Request HTTP version: {}".format(
                    method, url, http_version))

                # Comprobar si la versión de HTTP es 1.1
                if not http_version == "1.1":
                    enviar_error(cs, 505)
                    continue
                # Comprobar si es un método GET. Si no devolver un error Error 405 "Method Not Allowed".
                if not method == "GET":
                    enviar_error(cs, 405)
                    continue

                logger.info("Request is valid.")

                # Devuelve una lista con los atributos de las cabeceras.
                headers = cabecera_er.findall(data)
                # Verificar que la petición contenga la cabecera Host
                contieneHost = False
                for h in headers:
                    if h[0] == "Host" :
                        contieneHost = True
                if not contieneHost:
                    logger.error("Illegal request: no Host header!")
                    enviar_error(cs, 400)
                    continue

                # Leer URL y eliminar parámetros si los hubiera (los parámetros están detrás del ?)
                aux = url.partition("?")
                url = aux[0]
                # Comprobar si el recurso solicitado es /, En ese caso el recurso es index.html
                if url == "/":
                    recurso = "index.html"
                # Si no, si empieza por /, quitarla
                elif url[0] == "/":
                    recurso = url[1:]
                else:
                    recurso = url

                # Construir la ruta absoluta del recurso (webroot + recurso solicitado).
                # Hacerlo con os.path.join(), no con el "+".
                # root = os.path.join(webroot, recurso)
                # Con os.path.abspath podemos saber la ruta absoluta.
                root = os.path.abspath(recurso)
                logger.info("Client looking for {}".format(root))
                # Comprobar que la ruta esté dentro de webroot para que no haya fallo de seguridad --> 403
                relpath = os.path.relpath(root)
                if relpath.startswith(".."):
                    logger.error("Client tried to access outside of webroot!")
                    enviar_error(cs, 403)
                    continue
                # Comprobar que el recurso (fichero) existe, si no devolver Error 404 "Not found"
                if not os.path.exists(root):
                    logger.error("Client tried to access unexisting file!")
                    enviar_error(cs, 404)
                    continue
                # Comprobar que el recurso no pertenece a los recursos privados
                accedido = False
                for forb_file in forbidden_files :
                    if os.path.samefile(root, os.path.abspath(forb_file)) :
                        logger.error("Client tried to access forbidden file!")
                        enviar_error(cs, 403)
                        accedido = True
                if accedido :
                    continue

                # Analizar las cabeceras. Imprimir cada cabecera y su valor.
                logger.info("Request Headers:")
                for cabecera in headers:
                    print(
                        "\t\t\t\t    |-{}: {}".format(cabecera[0], cabecera[1]))

                # Extraer extensión para obtener el tipo de archivo. Necesario para la cabecera Content-Type
                file_name, file_extension = os.path.splitext(root)
                file_extension = file_extension[1:] # Eliminamos el punto de la extensión
                content_type = filetypes.get(file_extension)

                #  Si la cabecera es Cookie comprobar
                #  el valor de cookie_counter para ver si ha llegado a MAX_ACCESOS. (process_cookies())
                #  Si se ha llegado a MAX_ACCESOS devolver un Error "403 Forbidden"
                cookie_val = process_cookies(headers=headers, isHtml=(content_type==filetypes.get("html")))
                logger.info("Next cookie value: {}".format(cookie_val))
                if cookie_val == -1 :
                    logger.info("Max cookie reached!")
                    enviar_error(cs, 403)
                    continue

                # Obtener el tamaño del recurso en bytes.
                file_size = os.path.getsize(root)
                logger.info("Requested resource size: {}B".format(file_size))

                # Preparar respuesta con código 200. Construir una respuesta que incluya: la línea de respuesta y
                #  las cabeceras Date, Server, Connection, Set-Cookie (para la cookie cookie_counter),
                #  Content-Length y Content-Type.
                logger.debug("Cambiar el valor de connection al mismo que envía el cliente en process_web_request.")
                cabecera = construir_cabecera(codigo=200, connection="Keep-Alive", cookies=[(COOKIE_NAME, cookie_val)], content_length=file_size, content_type=content_type, last_modified=os.path.getmtime(root))

                enviar_fichero(cs, cabecera, root)
                    	
            else:
                # Enviar mensaje de que el formato de la solicitud no es correcto
                enviar_error(cs, 400)

        # Si es por timeout, se cierra el socket tras el período de persistencia.
        else:
            logger.error("Timeout reached!")
            cerrar_conexion(cs)
            return

        # NOTA: Si hay algún error, enviar una respuesta de error con una pequeña página HTML que informe del error.


""""""""""""""""""""""""""""""""""""""""""""""""


def main():
    """ Función principal del servidor
    """

    try:

        # Argument parser para obtener la ip y puerto de los parámetros de ejecución del programa. IP por defecto 0.0.0.0
        parser = argparse.ArgumentParser()
        parser.add_argument(
            "-p", "--port", help="Puerto del servidor", type=int, required=True)
        parser.add_argument(
            "-ip", "--host", help="Dirección IP del servidor o localhost", required=True)
        parser.add_argument(
            "-wb", "--webroot", help="Directorio base desde donde se sirven los ficheros (p.ej. /home/user/mi_web)")
        parser.add_argument('--verbose', '-v', action='store_true',
                            help='Incluir mensajes de depuración en la salida')
        args = parser.parse_args()

        if args.verbose:
            logger.setLevel(logging.DEBUG)

        logger.info('Enabling server in address {} and port {}.'.format(
            args.host, args.port))

        # Webroot
        if args.webroot:
            webroot = args.webroot
        else:
            webroot = os.path.dirname(os.path.realpath(__file__))
        logger.info("Serving files from {}".format(webroot))
        os.chdir(webroot)

        # NOTA: Linux tiene la librería os path para gestionar los paths. Mirar esto.
        # NOTA 2: Para pasar de cadena binaria a string hacer cadena.decode()
        # NOTA 3: Para pasar de string a cadena binaria hacer cadena.encode() P.ej: "Hola".encode()

        # Creamos el socket TCP
        logger.info("Creating TCP socket...")
        my_socket = socket.socket(
            family=socket.AF_INET, type=socket.SOCK_STREAM, proto=0)
        # Permitimos que se pueda reusar la dirección
        my_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        # Vinculamos el socket a (IP, puerto)
        my_socket.bind((args.host, args.port))
        # Comenzamos a escuchar las conexiones entrantes
        my_socket.listen(MAX_ACCESOS)

        logger.info("Listening at {}:{}...".format(args.host, args.port))

        while True:
            # Aceptar la conexión
            conn, addr = my_socket.accept()
            logger.info(
                "New conection from: {} will be listened at socket: {}".format(addr, conn))

            # Si estamos en Windows
            if os.name == "nt":
                # Creamos un proceso con multitasking
                """
                p = Process(target=process_web_request,
                            args=(conn, webroot))
                p.start()
                """
                logger.error(
                    "This server cannot run on Windows due to socket.select() limitations.")
                sys.exit(1)

            # Si estamos en Unix
            else:
                # Crear proceso hijo
                if os.fork() == 0:
                    # Cerrar el socket del padre
                    my_socket.close()
                    # Procesar la petición
                    process_web_request(conn)
                    # Matamos al hijo
                    sys.exit()
                else:
                    # Cerrar el socket del hijo
                    conn.close()

    except KeyboardInterrupt:
        True


if __name__ == "__main__":
    main()
