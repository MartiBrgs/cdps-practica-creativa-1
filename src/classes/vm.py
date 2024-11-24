from src.utils.utils import init_log
import subprocess, os
import tempfile
import textwrap


class VM:
    def __init__(self, name, ifaces, debug_mode):
        self.name = name
        self.ifaces = ifaces
        self.log = init_log("VM_Manager", debug_mode)


    def define_vm(self):
        """
        Defines a virtual machine (VM) using the provided XML configuration file.
        """
        command = f"virsh define {self.name}.xml"
        try:
            subprocess.run(command.split(" "), check=True)
            self.log.debug(f"vm '{self.name}' defined")
        except subprocess.CalledProcessError as e:
            self.log.error(f"error while running virsh define with {self.name}.xml")

    def copy_hostname(self):
        """
        Copies the VM's hostname to the /etc/hostname file inside the VM.
        """
        # write/copy hostname into /etc/hostname file
        self.copy_to_vm(file_content=f"{self.name}\n", file_name="hostname", target_path="/etc/")

    def copy_index_html(self):
        """
        Copies the index page content to the /var/www/html/ directory inside the VM.
        """
        # write/copy hostname into /etc/hostname file
        self.copy_to_vm(file_content=f"'{self.name}' index page\n", file_name="index.html", target_path="/var/www/html/")

    def copy_interfaces(self):
        """
        Copies network interface configurations to the /etc/network/interfaces file inside the VM.
        """
        # write/copy interfaces into /etc/network/interfaces
        content = textwrap.dedent(f"""
        auto lo
        iface lo inet loopback
        """)
        for iface, config in self.ifaces.items(): 
            content += textwrap.dedent(f"""
            auto {iface}
            iface {iface} inet static
                address {config["ipv4"]}
                netmask {config["mask"]}
                gateway {config["gateway"]}
            """)

        self.copy_to_vm(file_content=f"{content}\n", file_name="interfaces", target_path="/etc/network/")

    def edit_hosts(self):
        """
        Edits the /etc/hosts file in the VM to associate its IP with its hostname.
        """
        command = [
            "sudo", "virt-edit", "-d", self.name, "/etc/hosts",
            "-e", f"s/127.0.1.1.*/127.0.1.1 {self.name}/"
        ]
        try:
            subprocess.run(command, check=True)
            self.log.debug(f"VM '{self.name}':/etc/hosts file edited succesfully.")
        except subprocess.CalledProcessError as e:
            self.log.error(f"error while editing /etc/hosts in '{self.name}'")
        except Exception as ex:
            self.log.error(f"Unexpected error: {ex}")

    def edit_load_balancer(self):
        """
        Enables IP forwarding in the VM by editing /etc/sysctl.conf to allow load balancing.
        """
        command = [
            "sudo", "virt-edit", "-d", self.name, "/etc/sysctl.conf", 
            "-e", "s/#net.ipv4.ip_forward=1/net.ipv4.ip_forward=1/"
        ]
        try:
            subprocess.run(command, check=True)
            self.log.debug(f"VM '{self.name}':/etc/sysctl.conf file edited succesfully.")
        except subprocess.CalledProcessError as e:
            self.log.error(f"error while editing /etc/sysctl.conf in '{self.name}'")
        except Exception as ex:
            self.log.error(f"Unexpected error: {ex}")

    def configure_rc_local(self, service_name):
        """
        Configures the service to start on boot by editing /etc/rc.local in the VM.
        """
        try:
            # Command to edit the /etc/rc.local file in the VM
            command = [
            "sudo", "virt-edit", "-d", self.name, "/etc/rc.local",
            "-e", f"s|^exit 0|systemctl start {service_name}\nexit 0|"
            ]

            # Run the command
            subprocess.run(command, check=True)
            self.log.debug(f"Service '{service_name}' configured  succesfully on {self.name}:/etc/rc.local")
        except subprocess.CalledProcessError as e:
            self.log.error(f"Error while configuring /etc/rc.local on '{self.name}': {e}")
        except Exception as ex:
            self.log.error(f"Unexpected error: {ex}")

    def restart_haproxy(self):
        """
        Restarts the HAProxy service inside the VM by editing /etc/rc.local to include the restart command.
        """
        try:
            # Command to edit the /etc/rc.local file in the VM
            command = [
            "sudo", "virt-edit", "-d", self.name, "/etc/rc.local",
            "-e", "s|^exit 0|service haproxy restart\nexit 0|"
            ]

            # Run the command
            subprocess.run(command, check=True)
            self.log.debug(f"Service haproxy restarted succesfully on {self.name}:/etc/rc.local")
        except subprocess.CalledProcessError as e:
            self.log.error(f"Error while configuring /etc/rc.local on '{self.name}': {e}")
        except Exception as ex:
            self.log.error(f"Unexpected error: {ex}")

    @staticmethod
    def generate_haproxy_config(devices_ifaces):
        """
        Generates an HAProxy configuration string based on device interface information.
        """
        # Filter servers that start with "s" (this is assumed as the format)
        servers = {
            name: data["eth0"]["ipv4"]
            for name, data in devices_ifaces.items()
            if name.startswith("s") and "eth0" in data and "ipv4" in data["eth0"]
        }

        # Build the configuration
        haproxy_config = textwrap.dedent("""
        listen stats
            bind :8001
            stats enable
            stats uri /
            stats hide-version
            stats auth admin:cdps

        frontend lb
            bind *:80
            mode http
            default_backend webservers

        backend webservers
            mode http
            balance roundrobin
        """)
        for name, ip in servers.items():
            haproxy_config += f"    server {name} {ip}:80 check\n"

        return haproxy_config.strip()
    
    def update_haproxy_config(self, config_to_append):
        """
        Updates the HAProxy configuration file by appending the given configuration string.
        """
        try:
            # Reads the current content of the cfg file using virt-cat
            result = subprocess.run(
                ['sudo', 'virt-cat', '-d', self.name, '/etc/haproxy/haproxy.cfg'],
                capture_output=True,
                text=True,
                check=True
            )
            
            current_content = result.stdout
            
            file_content = "\n" + current_content + config_to_append + "\n"

            return file_content
        
        except subprocess.CalledProcessError as e:
            self.log.error(f"Error while reading original config file from vm: {e.stderr}")
            return False

    def edit_haproxy_conf(self, devices_ifaces):
        """
        Edits the HAProxy configuration file in the VM with new server IPs from the devices' interfaces.
        """
        # generates string to append with correct server ips from devices_ifaces dict
        config_to_append = self.generate_haproxy_config(devices_ifaces)
        self.log.debug("generated new config to append")

        # retrieve the current content from the haproxy.cfg file on the vm, 
        # then appends the new config and returns a new string with the entire new content
        file_content = self.update_haproxy_config(config_to_append)
        self.log.debug("New content to write in haproxy.cfg generated")

        # copy the whole content into the vm again, overwriting it by using virt-copy-in
        self.copy_to_vm(
            file_content=file_content,
            file_name="haproxy.cfg",
            target_path="/etc/haproxy/"
        )

    def configure_vm (self, devices_ifaces):
        """
        Configures the VM by copying necessary files and settings (hostname, interfaces, etc.).
        If it's a load balancer, it configures HAProxy; if it's a server, it configures Apache2.
        """
        self.copy_hostname()
        self.copy_interfaces()
        self.edit_hosts()
        # Enables load balancing on lb
        if self.name == "lb": 
            self.edit_load_balancer()
            self.edit_haproxy_conf(devices_ifaces)
            self.restart_haproxy()

        # Enables apache2 on servers (devices with name starting with an 's')
        if self.name.startswith("s"): 
            self.configure_rc_local("apache2")
            self.copy_index_html()

    def copy_to_vm(self, file_content, file_name, target_path):
        """
        Copies the specified content into a file on the VM using a temporary file.
        """
        # Creates a temp directory
        with tempfile.TemporaryDirectory() as temp_dir:
            # Absolute path to temp file
            temp_file_path = os.path.join(temp_dir, file_name)

            # Write the content into the temp file
            with open(temp_file_path, "w") as temp_file:
                temp_file.write(file_content)

            # Run virt-copy-in to pass the file
            try:
                subprocess.run(
                    ["sudo", "virt-copy-in", "-d", self.name, temp_file_path, target_path],
                    check=True
                )
                self.log.debug(f"File '{file_name}' copied succesfully to {self.name}:{target_path}")
            except subprocess.CalledProcessError as e:
                self.log.error(f"Error while copying the file '{file_name}': {e}")
        
    
    def start_vm(self):
        """
        Starts the VM using the virsh command.
        """
        try:
            # Start the VM
            subprocess.run(["sudo", "virsh", "start", self.name], check=True)
            self.log.info(f"VM '{self.name}' started succesfully.")
        except subprocess.CalledProcessError as e:
            self.log.error(f"error while starting VM '{self.name}'")
        except Exception as ex:
            self.log.error(f"Unexpected error: {ex}")
   
    def show_console_vm(self):
        """
        Opens a console window for the VM (xterm).
        """
        try:    
            # Opens a new windows with xterm terminal containing the terminal of the VM
            subprocess.Popen(["xterm", "-hold", "-e", f"sudo virsh console {self.name}"]) # bug al usar sudo aqui
            self.log.debug(f"VM '{self.name}' console opened in a new window.")
        except subprocess.CalledProcessError as e:
            self.log.error(f"error while opening console: {e}")
        except Exception as ex:
            self.log.error(f"Unexpected error: {ex}")
    
    def stop_vm (self):
        """
        Stops/shutdowns a VM using virsh shutdown.
        """
        if self.is_vm_running():
            try:
                # Stop/shutdown the VM
                subprocess.run(["sudo", "virsh", "shutdown", self.name], check=True)
                self.log.info(f"VM '{self.name}' stopped succesfully.")
            except subprocess.CalledProcessError as e:
                self.log.error(f"error while stopping VM '{self.name}'")
            except Exception as ex:
                self.log.error(f"Unexpected error: {ex}")
        else:
            self.log.info(f"VM '{self.name}' is not running.")
        

    def is_vm_running(self):
        """
        Checks if the VM is running (boolean)
        """
        try:
            # Run virsh list --all to obtain the state of all the VMs
            result = subprocess.run(
                ["sudo", "virsh", "list", "--all"],
                capture_output=True,
                text=True,
                check=True
            )
            # Search for the VM name in the output
            for line in result.stdout.splitlines():
                if self.name in line:
                    # Check if the state of the VM is "running"
                    return "running" in line
            return False  # Whether the VM is not running or does not exists
        except subprocess.CalledProcessError as e:
            self.log.error(f"Error while verifying the state of the VM '{self.name}': {e}")
            return False
        except Exception as ex:
            self.log.error(f"Unexpected error while verifying the state of the VM '{self.name}': {ex}")
            return False
    
    def destroy_vm (self):
        """
        Destroys a VM using virsh destroy.
        """
        if self.is_vm_running():
            try:
                # destroy vm
                subprocess.run(["sudo", "virsh", "destroy", self.name], check=True)
                self.log.debug(f"vm '{self.name}' destroyed")
            except subprocess.CalledProcessError as e:
                self.log.error(f"error while running virsh destroy {self.name}")
            except Exception as ex:
                self.log.error(f"Unexpected error: {ex}")
        else:
            self.log.info(f"VM '{self.name}' is not running.")

    def undefine_vm (self):
        """
        Undefine a VM from the local system using virsh undefine.
        """
        try:
            # undefine vm
            subprocess.run(["sudo", "virsh", "undefine", self.name], check=True)
            self.log.debug(f"vm '{self.name}' undefined")
        except subprocess.CalledProcessError as e:
            self.log.error(f"error while running virsh undefine {self.name}")
        except Exception as ex:
            self.log.error(f"Unexpected error: {ex}")

    def close_vm_console(self):
        """
        Close the xterm console window for the VM.
        """
        try:
            # Find xterm processes related to the VM
            result = subprocess.run(
                ["ps", "aux"],
                capture_output=True,
                text=True,
                check=True
            )
            
            # Filter xterm processes run with virsh console for this VM
            for line in result.stdout.splitlines():
                if "xterm" in line and f"virsh console {self.name}" in line:
                    # Extract the PID of the process
                    pid = int(line.split()[1])  # PID is in the second column
                    # Kill the process
                    subprocess.run(["kill", "-9", str(pid)], check=True)
                    self.log.debug(f"Closed xterm window for VM console '{self.name}'.")
        except subprocess.CalledProcessError as e:
            self.log.error(f"Error closing xterm window for VM '{self.name}': {e}")
        except Exception as ex:
            self.log.error(f"Unexpected error closing xterm window for VM '{self.name}': {ex}")
