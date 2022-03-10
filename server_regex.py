"""
Expresiones regulares utilizadas en el servidor.
"""

import re

# Procesar línea de solicitud
solicitud_pattern = r"([^\s]+) ([^\s]+) HTTP/([^\s]+)"
solicitud_er = re.compile(solicitud_pattern)

# Línea de cabecera
cabecera_pattern = r"([a-zA-Z-_]+): (.*)\r\n"
cabecera_er = re.compile(cabecera_pattern)

# Cookie
cookie_pattern = r"[^\s]+=[^\s]+" # Supondremos que las cookies llegan bien formateadas
cookie_er = re.compile(cookie_pattern)