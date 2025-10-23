#!/usr/bin/env python3

import os
import sys
import argparse
import paramiko
from pathlib import Path
import yaml
import time

class SSHConnection:
    def __init__(self, hostname, username, key_file):
        self.hostname = hostname
        self.username = username
        self.key_file = key_file
        self.client = None
        
    def connect(self):
        """Establish SSH connection"""
        try:
            self.client = paramiko.SSHClient()
            self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            self.client.connect(
                hostname=self.hostname,
                username=self.username,
                key_filename=self.key_file
            )
            print(f"✓ Connected to {self.hostname}")
        except Exception as e:
            print(f"✗ Error: Failed to connect to {self.hostname}: {e}")
            sys.exit(1)
    
    def disconnect(self):
        """Close SSH connection"""
        if self.client:
            self.client.close()
    
    def run_tolerant(self, cmd):
        """Run command with error tolerance"""
        print(f"Running: {cmd}")
        try:
            stdin, stdout, stderr = self.client.exec_command(cmd)
            exit_code = stdout.channel.recv_exit_status()
            if exit_code == 0:
                print(f"✓ Success: {cmd}")
            else:
                print(f"⚠ Warning: {cmd} failed (continuing anyway)")
        except Exception as e:
            print(f"⚠ Warning: {cmd} failed with exception: {e} (continuing anyway)")

    def run_critical(self, cmd):
        """Run critical command that must succeed"""
        print(f"Running critical command: {cmd}")
        try:
            stdin, stdout, stderr = self.client.exec_command(cmd)
            exit_code = stdout.channel.recv_exit_status()
            output = stdout.read().decode().strip()
            error = stderr.read().decode().strip()
            
            if exit_code != 0:
                print(f"✗ Error: Critical command failed: {cmd}")
                print(f"stderr: {error}")
                sys.exit(1)
            print(f"✓ Success: {cmd}")
            return output
        except Exception as e:
            print(f"✗ Error: Critical command failed with exception: {cmd}: {e}")
            sys.exit(1)

    def get_command_output(self, cmd):
        """Get command output without error handling"""
        try:
            stdin, stdout, stderr = self.client.exec_command(cmd)
            return stdout.read().decode().strip()
        except Exception:
            return ""

def reboot(ssh):
    ssh.run_tolerant("reboot")

    
def install_talos(ssh, talos_version, talos_schematic):
    """Install Talos on the remote server"""
    
    print("=== Stopping RAID arrays (tolerating failures) ===")
    ssh.run_tolerant("mdadm --stop /dev/md0")
    ssh.run_tolerant("mdadm --stop /dev/md1")
    ssh.run_tolerant("mdadm --stop /dev/md2")

    print("=== Deactivating LVM (tolerating failures) ===")
    ssh.run_tolerant("vgchange -an vg0")

    print("=== Cleaning partition tables and disk signatures ===")
    ssh.run_critical("sgdisk --zap-all /dev/nvme0n1")
    ssh.run_critical("sgdisk --zap-all /dev/nvme1n1")
    ssh.run_critical("wipefs -a /dev/nvme0n1")
    ssh.run_critical("wipefs -a /dev/nvme1n1")

    # Show disk layout
    disk_layout = ssh.get_command_output("lsblk -o SERIAL,NAME,PATH,UUID,WWN,MODEL,SIZE")
    print(disk_layout)

    print("=== Determining primary disk ===")
    # Get primary disk info
    lsblk_output = ssh.get_command_output("lsblk -dn -o SERIAL,NAME,SIZE,TYPE -e 1,7,11,14,15")
    if not lsblk_output:
        print("✗ Error: Could not get disk information")
        sys.exit(1)
    
    lines = lsblk_output.strip().split('\n')
    sorted_lines = sorted(lines)
    if not sorted_lines:
        print("✗ Error: Could not determine primary disk")
        sys.exit(1)
    
    primary_disk_line = sorted_lines[0].split()
    if len(primary_disk_line) < 2:
        print("✗ Error: Could not parse primary disk information")
        sys.exit(1)
    
    primary_disk = primary_disk_line[1]
    primary_disk_id = primary_disk_line[0]

    print(f"PRIMARY_DISK={primary_disk}")
    print(f"PRIMARY disk ID: {primary_disk_id}")

    print("=== Updated disk layout ===")
    disk_layout = ssh.get_command_output("lsblk -o SERIAL,NAME,PATH,UUID,WWN,MODEL,SIZE")
    print(disk_layout)

    print(f"=== Downloading Talos image {talos_version} for schematic {talos_schematic} ===")

    # Change to /tmp directory and download
    download_url = f"https://factory.talos.dev/image/{talos_schematic}/{talos_version}/metal-amd64.iso"
    ssh.run_critical("cd /tmp && rm -f metal-amd64.iso")
    
    download_cmd = f'cd /tmp && wget -q "{download_url}"'
    try:
        ssh.run_critical(download_cmd)
    except:
        print("✗ Error: Failed to download Talos image")
        sys.exit(1)

    # Verify download
    check_file = ssh.get_command_output("cd /tmp && ls -la metal-amd64.iso 2>/dev/null")
    if not check_file or "metal-amd64.iso" not in check_file:
        print("✗ Error: Talos image file not found after download")
        # Debug: show what's in /tmp
        tmp_contents = ssh.get_command_output("cd /tmp && ls -la")
        print(f"Debug - /tmp contents: {tmp_contents}")
        sys.exit(1)

    print("✓ Downloaded Talos image successfully")

    print(f"=== Writing Talos image to PRIMARY_DISK {primary_disk} ===")
    ssh.run_critical(f"cd /tmp && dd of=/dev/{primary_disk} bs=4M oflag=sync if=metal-amd64.iso")

    print("Done")

    # Get secondary disk EUI
    lsblk_wwn_output = ssh.get_command_output("lsblk -dn -o SERIAL,NAME,SIZE,TYPE,WWN -e 1,7,11,14,15")
    secondary_disk_eui = ""
    for line in lsblk_wwn_output.split('\n'):
        parts = line.split()
        if len(parts) >= 5 and primary_disk_id not in line:
            secondary_disk_eui = parts[4]
            break

    print("=== Installation Complete ===")
    print(f"✓ Installed Talos on {primary_disk}")

    print("USE")
    print(f"  diskSelector={primary_disk_id}")
    print(f"  second disk ID /dev/disk/by-id/nvme-{secondary_disk_eui}")

    return primary_disk_id, secondary_disk_eui

def save_server_info(hostname, primary_disk_id, secondary_disk_eui, config_dir):
    """Save server information to servers/<ip>.yaml"""
    discovery_dir = Path(config_dir) / "discovery"
    discovery_dir.mkdir(exist_ok=True)
    
    server_file = discovery_dir / f"{hostname}.yaml"
    
    server_info = {
        'PRIMARY_DISK_ID': primary_disk_id,
        'SECONDARY_DISK': f"/dev/disk/by-id/nvme-{secondary_disk_eui}"
    }
    
    with open(server_file, 'w') as f:
        yaml.dump(server_info, f, default_flow_style=False)
    
    print(f"✓ Server information saved to {server_file}")

def read_nodes_index(config_dir):
    config_file = config_dir / 'cluster_nodes_index.yaml'
    with open( config_file, 'r') as f:
        nodes_index = yaml.safe_load(f)
    return nodes_index['index']

def read_talos_config(config_dir):
    config_file = config_dir / 'cluster_config.yaml'
    with open( config_file, 'r') as f:
        talos_config = yaml.safe_load(f)
    return talos_config

def main():
    parser = argparse.ArgumentParser(description='Install Talos on remote server via SSH')
    # parser.add_argument('hostname', help='Target server hostname/IP')
    parser.add_argument('-i', '--index', help='Index number (starting from 1) of server of target server. Index is read from cluster_nodex_index.yaml ')
    parser.add_argument('--ip', help='ip address of target server')
    parser.add_argument('-u', '--username', default='root', help='SSH username (default: root)')
    parser.add_argument('-k', '--key-file', required=True, help='SSH private key file path')
    parser.add_argument('-c', '--config-dir', default='config/', help='Path to config dir (where talos/cluster_nodes_index.yaml should be)')
    parser.add_argument('--talos-version', help='Talos version (can also use TALOS_VERSION env var)')
    parser.add_argument('--talos-schematic', help='Talos schematic ID (can also use TALOS_SCHEMATIC env var)')
    parser.add_argument('-r', '--reboot', action='store_true', help='Reboot server after install')
    

    args = parser.parse_args()
    config_dir =  Path(args.config_dir).resolve()
    
    talos_config = read_talos_config(config_dir)
    print(talos_config)
    # exit()
    # Get Talos version and schematic from args or environment
    talos_version = args.talos_version or os.environ.get('TALOS_VERSION') or talos_config['talos']['version']
    talos_schematic = args.talos_schematic or os.environ.get('TALOS_SCHEMATIC') or talos_config['talos']['schematicId']
    nodes_index= read_nodes_index(config_dir)
    hostname = nodes_index[int(args.index)]
    print(hostname)
    # exit()
    
    if not talos_version or not talos_schematic:
        print("✗ Error: TALOS_VERSION and TALOS_SCHEMATIC must be provided via args or environment variables")
        print("Example: --talos-version=v1.5.0 --talos-schematic=your-schematic-id")
        print("Or: export TALOS_VERSION=v1.5.0 && export TALOS_SCHEMATIC=your-schematic-id")
        sys.exit(1)
    
    # exit()
    # Establish SSH connection
    ssh = SSHConnection(hostname, args.username, args.key_file)
    ssh.connect()
    
    try:
        # Install Talos and collect disk information
        primary_disk_id, secondary_disk_eui = install_talos(ssh, talos_version, talos_schematic)
        
        # Save server information
        save_server_info(hostname, primary_disk_id, secondary_disk_eui, config_dir)
        
        if args.reboot:
            print('Rebooting in 5 seconds')
            time.sleep(5)

            reboot(ssh)

    finally:
        ssh.disconnect()

if __name__ == "__main__":
    main()