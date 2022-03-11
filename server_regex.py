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

# error.html
#                          Primer dig                  Segundo dig                Último dig           Mensaje
error_pattern = r"([\s\S]*)ERR_CODE_0([\s\S]*)ZERO_BEGIN([\s\S]*)ZERO_END([\s\S]*)ERR_CODE_2([\s\S]*)ERR_CODE_MSG([\s\S]*)"
error_er = re.compile(error_pattern)
def error_html(html, num, msg) :
    html = error_er.match(html)

    if not html :
        raise Exception("Error file does not match!")

    # Separar digitos del número
    d1 = ("{}".format(num))[0]
    d2 = ("{}".format(num))[1]
    d3 = ("{}".format(num))[2]

    # Primer dígito
    result = html.group(1)+d1+html.group(2)

    # Si el número tiene un 0 en el segundo dígito, podemos incluir la animación
    if d2 == "0" :
        result = result + html.group(3)
    # Si no, ponemos el número como html
    else :
        result = result + '<div class="errz">'+d2+'</div>'

    # Tercer dígito
    result = result + html.group(4) + d3

    # Mensaje
    result = result + html.group(5) + msg + html.group(6)

    return result

