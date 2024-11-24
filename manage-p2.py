import argparse
from src.classes.vm import VM
from src.classes.network import NET
import json

from src.utils.utils import init_log, generate_devices_ifaces


# GLOBAL PARAMS
MIN_SERVERS = 2
MAX_SERVERS = 5

if __name__ == "__main__":

    json_path = "config/manage-p2.json"

    try:
        with open(json_path, "r") as json_file:
            config = json.load(json_file)

        # Declaring variables from the JSON file
        debug_mode = config.get("debug", False)  # Access the "debug" value with a default
        qcow_base_file_name = config.get("qcow_base", " ")
        xml_base_file_name = config.get("xml_base", " ")
        number_of_servers = config.get("number_of_servers", 2)
        if number_of_servers < MIN_SERVERS:
            raise ValueError("The number of servers must be at least 2")
        if number_of_servers > MAX_SERVERS:
            raise ValueError("The maximum number of servers to create is 5")

    except FileNotFoundError:
        print(f"Error: The file {json_path} does not exist.")
        raise FileNotFoundError
    except json.JSONDecodeError:
        print(f"Error: The file {json_path} does not contain a valid JSON.")
        raise json.JSONDecodeError

    
    DEVICES_IFACES = generate_devices_ifaces(number_of_servers)

    BRIDGES = ["LAN1", "LAN2"]

    NETWORK_MAP = {
        device: (
            ['LAN1', 'LAN2'] if device == 'lb' else  # Special rule for "lb" (load balancer)
            ['LAN1'] if device.startswith('c') else  # "c" devices (hosts) on LAN1
            ['LAN2'] if device.startswith('s') else  # "s" devices (servers) on LAN2
            []
        )
        for device in DEVICES_IFACES.keys()
    }

    # create log for main
    log = init_log("manage-p2", debug_mode)
    log.info("manage-p2 launched")

    # instantiate NET object
    net = NET(
            qcow_base=qcow_base_file_name,
            xml_base=xml_base_file_name,
            devices=DEVICES_IFACES.keys(),
            bridges=BRIDGES,
            network_map=NETWORK_MAP,
            debug_mode=debug_mode
    )

    # dict associates device name with device VM object / instantiate the VM object
    device_to_vm = {
        device_name: VM(device_name, interfaces, debug_mode) 
        for device_name, interfaces in DEVICES_IFACES.items()
    }

    # main parser
    parser = argparse.ArgumentParser(
        description="This script creates a default corporate network virtual environment."
    )
    subparsers = parser.add_subparsers(dest="orden", help="Available subcommands")

    # 'create' subcommand
    subparsers.add_parser("create", help="Create the virtual environment")

    # 'start' subcommand
    start_parser = subparsers.add_parser("start", help="Start the virtual environment or a specific VM")
    start_parser.add_argument(
        "vm_name", nargs="?", default=None, help="The name of the VM to start (optional)"
    )

    # 'stop' subcommand
    stop_parser = subparsers.add_parser("stop", help="Stop the virtual environment or a specific VM")
    stop_parser.add_argument(
        "vm_name", nargs="?", default=None, help="The name of the VM to stop (optional)"
    )

    # 'destroy' subcommand
    subparsers.add_parser("destroy", help="Destroy the virtual environment")

    # Parse arguments
    args = parser.parse_args()

    if args.orden == "create":
        log.info("Creating environment")
        # copying and creating files
        net.create_environment()

        # defining every device vm
        for vm in device_to_vm.values():
            vm.define_vm()
            vm.configure_vm(DEVICES_IFACES)
            log.info(f"VM '{vm.name}' configured correctly")

    elif args.orden == "start":
        if args.vm_name:
            if args.vm_name in DEVICES_IFACES.keys():
                log.info(f"Starting '{args.vm_name}'")
                vm_to_start = device_to_vm[args.vm_name]
                vm_to_start.close_vm_console() # to prevent re-opening to the same vm / this might be better
                vm_to_start.start_vm()
                vm_to_start.show_console_vm()
        else:
            for vm in device_to_vm.values():
                vm.close_vm_console() # to prevent re-opening to the same vm / this might be better
                vm.start_vm()
                vm.show_console_vm()

    elif args.orden == "stop":
        # if a vm name is passed as an argument, stop only that vm
        if args.vm_name:
            if args.vm_name in DEVICES_IFACES.keys():
                log.info(f"Stopping '{args.vm_name}'")
                vm_to_stop = device_to_vm[args.vm_name]
                vm_to_stop.stop_vm()
                vm_to_stop.close_vm_console()
            else:
                log.error(f"VM '{args.vm_name}' not found or running")
        else:
            log.info("Stopping all the VMs")
            for vm in device_to_vm.values():
                vm.stop_vm()
                vm.close_vm_console()
        

    elif args.orden == "destroy":
        log.info("Destroying environment")

        # virsh destroy and virsh undefine each vm
        for vm in device_to_vm.values():
            vm.destroy_vm()
            vm.undefine_vm()
            vm.close_vm_console()

        # deleting qcow2 and xml files (except for base files) and removing the created bridges
        net.clean_environment()

    else:
        log.info("unrecognized parameter")
