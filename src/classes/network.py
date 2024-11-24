from lxml import etree
from src.utils.utils import init_log
import subprocess, os
import copy

class NET:
    def __init__(self, qcow_base, xml_base, devices, bridges, network_map, debug_mode):
        self.QCOW_BASE = qcow_base
        self.XML_BASE = xml_base
        self.DEVICES = devices
        self.BRIDGES = bridges
        self.NETWORK_MAP = network_map
        self.log = init_log("NET_Manager", debug_mode)

    def create_xml_files(self):
        """
        Creates XML files for each device in the network.
        """
        for device in self.DEVICES:
            try:
                subprocess.run(["cp", self.XML_BASE, f"{device}.xml"], capture_output=True, text=True)
                self.log.debug(f"{device}.xml successfully created.")
            except Exception as e:
                self.log.exception(f"Error while creating XML for {device}")

        self.log.info("All XML files successfully created")

    def create_qcow2_files(self):
        """
        Creates QCOW2 disk images for each device in the network.
        """
        for device in self.DEVICES:
            try:
                subprocess.run(
                    ["sudo", "-u", os.getenv('USER'), "qemu-img", "create", "-F", "qcow2", "-f", "qcow2", "-b", self.QCOW_BASE, f"{device}.qcow2"],
                    capture_output=True,
                    text=True
                )
                self.log.debug(f"{device}.qcow2 successfully created.")
            except Exception as e:
                self.log.exception(f"Error while creating QCOW2 for {device}")

        self.log.info("All QCOW2 files successfully created")

    def destroy_files(self):
        """
        Deletes all XML and QCOW2 files in the current directory that 
        do not match the base files specified in the configuration.
        """
        files = [f for f in os.listdir('.') if os.path.isfile(f) and (f.endswith('.xml') or f.endswith('.qcow2'))]
        for file in files:
            if file != self.XML_BASE and file != self.QCOW_BASE:
                try:
                    os.remove(file)
                    self.log.debug(f"Deleted {file}")
                except Exception as e:
                    self.log.exception(f"Error while deleting {file}")

        self.log.info("Clean-up completed: All XML and QCOW2 files except base files have been deleted.")


    def xml_modifier(self, xml_name, network_list):
        """
        Modifies the XML file for the device to include correct VM configuration
        like disk source, network interface, and other parameters.
        """
        try:
            tree = self.xml_finder(xml_name)
            root = tree.getroot()

            # Modify the name and source file
            new_name = xml_name.split(".")[0]
            qcow2_file = f"{new_name}.qcow2"
            source_path = os.path.abspath(qcow2_file)

            if not os.path.exists(qcow2_file):
                self.log.error(f"{qcow2_file} not found in the current directory")
                raise FileNotFoundError(f"{qcow2_file} does not exist")

            self.name_modifier(root, new_name)
            self.source_file_modifier(root, source_path)
            self.interface_lan_modifier(root, network_list[0])

            if len(network_list) > 1:
                for net in network_list[1:]:
                    self.duplicate_interface(root, net)

            tree.write(xml_name, pretty_print=True, xml_declaration=True, encoding="UTF-8")
            self.log.debug(f"{xml_name} successfully modified.")
        except Exception as e:
            self.log.exception(f"Error modifying {xml_name}")

    def configure_xml_env(self):
        """
        Configures the XML files for all devices based on the network topology.
        """
        for device, networks in self.NETWORK_MAP.items():
            self.xml_modifier(f"{device}.xml", networks)
        self.log.info("All XML files configured successfully")

    @staticmethod
    def xml_finder(xml_name):
        """
        Finds and parses the XML file.
        """
        try:
            return etree.parse(xml_name)
        except Exception as e:
            raise FileNotFoundError(f"{xml_name} not found") from e

    @staticmethod
    def name_modifier(root, new_name):
        """
        Modifies the name of the VM in the XML file.
        """
        root.find(".//name").text = new_name

    @staticmethod
    def source_file_modifier(root, new_source_path):
        """
        Modifies the source file path in the XML file for the VM's disk.
        """
        root.find(".//devices/disk/source").set("file", new_source_path)

    @staticmethod
    def interface_lan_modifier(root, new_bridge):
        """
        Modifies the network interface settings to connect to the specified bridge.
        """
        interface = root.find(".//devices/interface")
        interface.find("source").set("bridge", new_bridge)

        if interface.find("virtualport") is None:
            virtualport = etree.SubElement(interface, "virtualport")
            virtualport.set("type", "openvswitch")

    @staticmethod
    def duplicate_interface(root, bridge_name):
        """
        Duplicates the network interface and assigns it to the provided bridge name.
        """
        interface = root.find(".//devices/interface")
        if interface is not None:
            new_interface = copy.deepcopy(interface)
            new_interface.find("source").set("bridge", bridge_name)
            root.find(".//devices").append(new_interface)

    def create_bridges(self):
        """
        Creates the bridges defined in the 'bridges' attribute using ovs-vsctl.
        """
        for bridge in self.BRIDGES:
            try:
                subprocess.run(['sudo', 'ovs-vsctl', 'add-br', bridge], check=True)
                self.log.info(f"Bridge {bridge} created successfully.")
            except subprocess.CalledProcessError as e:
                self.log.error(f"Error creating bridge {bridge}: {e}")

    def delete_bridges(self):
        """
        Deletes the bridges defined in the 'bridges' attribute using ovs-vsctl.
        """
        for bridge in self.BRIDGES:
            try:
                subprocess.run(['sudo', 'ovs-vsctl', 'del-br', bridge], check=True)
                self.log.info(f"Bridge {bridge} deleted successfully.")
            except subprocess.CalledProcessError as e:
                self.log.error(f"Error deleting bridge {bridge}: {e}")

    def add_interface_to_host(self):
        """
        Adds interface LAN1 to the host with a fixed IP.
        """
        try:
            subprocess.run(['sudo', 'ifconfig', 'LAN1', 'up'], check=True)
            subprocess.run(['sudo', 'ifconfig', 'LAN1', '10.1.1.3/24'], check=True)
            subprocess.run(['sudo', 'ip', 'route', 'add', '10.1.0.0/16', 'via', '10.1.1.1'], check=True)
            self.log.info("LAN1 interface added to host")
        except subprocess.CalledProcessError as e:
                self.log.error(f"Error adding interface to host: {e}")


    def create_environment(self):
        """
        Creates the virtual environment by generating base files for each VM, 
        configuring their XML files according to the topology, and creating bridges
        on the system using openvswitch.
        """
        self.create_qcow2_files()
        self.create_xml_files()
        self.configure_xml_env()
        self.create_bridges()
        self.add_interface_to_host()

    def clean_environment(self):
        """
        Cleans up the environment by deleting all generated files and removing the 
        created bridges from the system.
        """
        self.log.debug("Starting environment clean-up...")
        self.destroy_files()
        self.delete_bridges()
        self.log.info("Environment clean-up completed.")
