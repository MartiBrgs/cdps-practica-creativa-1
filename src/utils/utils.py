import logging, sys

def init_log(log_name, show_debug=True):
    """
    Inicializa un logger con un único handler para evitar duplicados.
    """
    log = logging.getLogger(log_name)
    if not log.hasHandlers():  # Evitar duplicar handlers
        log.setLevel(logging.DEBUG if show_debug else logging.INFO)
        ch = logging.StreamHandler(sys.stdout)
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s', "%Y-%m-%d %H:%M:%S")
        ch.setFormatter(formatter)
        log.addHandler(ch)
    log.propagate = False  # No propagar a otros loggers padres
    return log

def generate_devices_ifaces(number_of_servers: int):
    """
    Genera dinámicamente un diccionario de interfaces de red basado en el número de servidores especificado.

    Args:
        number_of_servers (int): Número de servidores que comienzan con "s".

    Returns:
        dict: Diccionario con la estructura de `DEVICES_IFACES`.
    """
    devices_ifaces = {
        'lb': {
            "eth0": {
                "ipv4": "10.1.1.1",
                "mask": "255.255.255.0",
                "gateway": "10.1.1.1"
            },
            "eth1": {
                "ipv4": "10.1.2.1",
                "mask": "255.255.255.0",
                "gateway": "10.1.2.1"
            },
        },
        'c1': {
            "eth0": {
                "ipv4": "10.1.1.2",
                "mask": "255.255.255.0",
                "gateway": "10.1.1.1"
            }
        },
    }

    # Base IP para los servidores "sX"
    base_ip = 11

    # Agregar servidores dinámicamente
    for i in range(1, number_of_servers + 1):
        server_name = f"s{i}"
        devices_ifaces[server_name] = {
            "eth0": {
                "ipv4": f"10.1.2.{base_ip}",
                "mask": "255.255.255.0",
                "gateway": "10.1.2.1"
            }
        }
        base_ip += 1

    return devices_ifaces