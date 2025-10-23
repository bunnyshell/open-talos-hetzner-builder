#!/usr/bin/env python3
"""
Multi-purpose utility script demonstrating argparse functionality.
Performs various actions based on command-line arguments.
"""

import argparse
import sys
import os
import json
import hashlib
from datetime import datetime
from pathlib import Path
import shutil


import subprocess
from pathlib import Path
from jinja2 import Template, StrictUndefined
import yaml
import ipaddress

import requests
import json
import re
from dotenv import load_dotenv
import hashlib
import time

from hetzner_robot import HetznerRobotAPI

config_folders = {}
template_folders = {}


def initialize_config_file(source, destination):

    # print(f"? {source}    -> {destination}")

    if not destination.exists():
        # Create parent directories if they don't exist
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        print(f"✓ Copied {source}    -> {destination}")
    else:
        print(f"! SKIPPED {source} (exists)")

def initialize_config(args):
    print("initialize")

    # create config folders

    for k, v in config_folders.items():
        if k.endswith("_dir"):
            v.mkdir(parents=True, exist_ok=True)
            print(f"Created {v}")

    initialize_config_file(destination=config_folders['cluster_config_file'], source=template_folders['cluster_config_file'] )
    initialize_config_file(destination=config_folders['schematic_file'], source=template_folders['schematic_file'])
    initialize_config_file(destination=config_folders['cluster_nodes_index_file'], source=template_folders['cluster_nodes_index_file'] )
    # print(config_folders)
    
    initialize_talos_secrets()

    print("You should now edit the configs files:")
    print(config_folders['cluster_config_file'])
    print(config_folders['cluster_nodes_index_file'])
    print(config_folders['schematic_file'])
    return 0



def render_config(args):
    print("render")

    context=cluster_config
    
    # read and render all Jinja template files in patches dir
    rendered_patches_list = render_termplate_folder(template_folders['patches_dir'], config_folders['patches_dir'], context)
    rendered_patches_list_controlplane = render_termplate_folder(template_folders['patches_controlplane_dir'], config_folders['patches_controlplane_dir'], context)
    rendered_patches_list_worker = render_termplate_folder(template_folders['patches_worker_dir'], config_folders['patches_worker_dir'], context)

    print(rendered_patches_list)
    print(rendered_patches_list_controlplane)
    print(rendered_patches_list_worker)

    cluster_worker_nodes = render_node_template_files()


    generate_talos_config_controlplane(rendered_patches_list, rendered_patches_list_controlplane)
    generate_talos_config_talosconfig()
    generate_talos_config_workernodes(rendered_patches_list, rendered_patches_list_worker, cluster_worker_nodes)



    return 0


def generate_talos_config_controlplane(rendered_patches_list, rendered_patches_list_controlplane):

        # ------------ ControlPlane config-----------
    cp_command= ["talosctl", "gen", "config",
        "--with-examples=false", "--with-docs=false", 
        "--output", f"{config_folders['nodes_dir'] /'controlplane.yaml'}",
        "--output-types", "controlplane",
        "--kubernetes-version", "1.32.4",
        "--with-secrets", f"{config_folders['secrets_file']}"
        ]
    
    for patch_file in rendered_patches_list:
        cp_command.append("--config-patch")
        cp_command.append(f"@{config_folders['patches_dir']}/{patch_file}")
    
    for patch_file in rendered_patches_list_controlplane:
        cp_command.append("--config-patch")
        cp_command.append(f"@{config_folders['patches_controlplane_dir']}/{patch_file}")
       
    cp_command.append(cluster_config['cluster']['name']) 
    cp_command.append(cluster_config['cluster']['endpoint'])
    cp_command.append("--force")
        

    try:
        # print(' \\\n  '.join(cp_command))
        result_cp = subprocess.run(cp_command, capture_output=True, text=True)
        print(f"Command output for controlplane: {result_cp.stdout}")
        print(f"Command output for controlplane: {result_cp.stderr}")
        print("ok")
    except subprocess.SubprocessError as e:
        print(f"Error running command for controlplane: {e}")
    except Exception as e:
        print(f"{e}")


def generate_talos_config_talosconfig():
     # ---- generate talosconfig file ---------
    command_talosconfig= ["talosctl", "gen", "config",
        "--output", f"{config_folders['talosconfig_file']}",
        "--output-types", "talosconfig",
        "--with-secrets", f"{config_folders['secrets_file']}",
        cluster_config['cluster']['name'],
        cluster_config['cluster']['endpoint']
    ]
    
    try:
        # print(' \\\n  '.join(command_talosconfig))
        result_talosconfig = subprocess.run(command_talosconfig, capture_output=True, text=True)
        print(f"Command output for controlplane: {result_talosconfig.stdout}")
        print(f"Command output for controlplane: {result_talosconfig.stderr}")
        print("ok")
    except subprocess.SubprocessError as e:
        print(f"Error running command for {filename}: {e}")
    except Error as e:
        print(("{e}"))

def generate_talos_config_workernodes(rendered_patches_list, rendered_patches_list_worker, cluster_worker_nodes):

    for node in cluster_worker_nodes:

        command_workernodes= ["talosctl", "gen", "config",
            # "--with-examples=false", "--with-docs=false", 
            "--output", f"{config_folders['nodes_dir']}/{node['config_file']}",
            "--output-types", "worker",
            "--kubernetes-version", "1.32.4",
            "--with-secrets", f"{config_folders['secrets_file']}"
            ]
        
        for patch_file in rendered_patches_list:
            command_workernodes.append("--config-patch")
            command_workernodes.append(f"@{config_folders['patches_dir']}/{patch_file}")
        
        for patch_file in rendered_patches_list_worker:
            command_workernodes.append("--config-patch")
            command_workernodes.append(f"@{config_folders['patches_worker_dir']}/{patch_file}")                          
        
        command_workernodes.append("--config-patch")
        command_workernodes.append(f"@{config_folders['nodes_dir']}/{node['config_file']}") 
        command_workernodes.append(cluster_config['cluster']['name']) 
        command_workernodes.append(cluster_config['cluster']['endpoint'])
        command_workernodes.append("--force")
        

        try:
            # print(' \\\n  '.join(command_workernodes))
            result_cp = subprocess.run(command_workernodes, capture_output=True, text=True)
            print(f"Command output for controlplane {node['name']}: {result_cp.stdout}")
            # print(result_cp)
            
            if (result_cp.returncode):
                print(f"Command output for controlplane {node['name']}: {result_cp.stderr}")
                exit(1)

        except subprocess.SubprocessError as e:
            print(f"Error running command for {node}: {e}")
        except Exception as e:
            print(("{e}"))


    for node in cluster_worker_nodes:
        print("talosctl validate --config config/talos/nodes/w2.yaml --mode metal")
        print(f"talosctl apply-config  --talosconfig {config_folders['talosconfig_file']} --nodes {node['public_ip']} -e {node['public_ip']}  --file {config_folders['nodes_dir']}/{node['config_file']} --insecure")




def get_node_index(ip):
    """returns the index of ip in cluster_node_index.yaml"""

    nodes_index= load_yaml_file(config_folders['cluster_nodes_index_file'])['index']
    # print(nodes_index)
    nodes = {v: k for k, v in nodes_index.items()}
    # print(nodes)
    return nodes[ip]

def render_node_template_files():
### renders all node files
### for each node file reads context from it's corresponding discovery file

    # ------------- render worker node config ----------------
    # read and render node template file
    node_template_file = template_folders["nodes_dir"] / "node_template.yaml.j2"
    print(f"reading {node_template_file}")
    with open(node_template_file, "r") as f:
        node_template_content = f.read()
    node_template = Template(node_template_content, undefined=StrictUndefined)

     # ------ prepare some variables needed for rendering node ----------------
    cluster_private_cidr=ipaddress.ip_network(cluster_config['cluster']['networking']['private-node-cidr'])
    
    cluster_private_cidr_workers=ipaddress.ip_network(cluster_config['cluster']['networking']['subnet-metal'])
    cluster_private_cidr_controlplane=ipaddress.ip_network(cluster_config['cluster']['networking']['subnet-virtual'])
    ip_list_workers = list(cluster_private_cidr_workers.hosts())  # Only usable hosts (excludes network/broadcast)
    # ip_list_controlplane = list(cluster_private_cidr_controlplane.hosts())  # Only usable hosts (excludes network/broadcast)
    gateway_workers = ip_list_workers[0]



    # Find and read all files in discovery directory
    cluster_worker_nodes = []
    discovery_files = {}
    if config_folders['discovery_dir'].exists():
        for file_path in sorted(config_folders['discovery_dir'].iterdir()):
            if file_path.is_file():
                # extract the filename without extension 
                ip = file_path.stem

                # read node index from config
                node_index = get_node_index(ip)
                print(f"index of {ip} -> {node_index} --------------")
                content = load_yaml_file(file_path)

                discovery_files[ip] = content
                content['node_private_ip']= str(ip_list_workers[99+node_index])
                content['node_public_ip']= file_path.stem
                content['node_public_network'] = str(ipaddress.ip_network(content['node_public_ip'] + "/29", strict=False))
                content['node_name'] = f"{cluster_config['cluster']['name']}-{node_index}"
                content['gateway_workers']=gateway_workers

                node_config = cluster_config | content 
                print(node_config)
                rendered_node_content = node_template.render(node_config)
                # print(rendered_node_content)
                local_config_file_name = f"w{node_index}.yaml"
                output_path = config_folders['nodes_dir'] / local_config_file_name
                with open(output_path, "w") as out_f:
                    out_f.write(rendered_node_content)
                print(f"Rendered node {node_index} -> {output_path}")
                cluster_worker_nodes.append({
                    "name": content['node_name'],
                    "public_ip": content['node_public_ip'],
                    "private_ip": content['node_private_ip'],
                    "config_file": local_config_file_name}
                    )
    return cluster_worker_nodes

# renders each file in folder
# returns a list of rendered files
def render_termplate_folder(template_folder, output_folder, context):

    rendered_files_list=[]
    for template_file in template_folder.glob("*.j2"):
        print(f"Rendering {template_file.name}")
        output_path = output_folder / template_file.stem
        render_template_file(template_file, output_path, context)
        rendered_files_list.append( f"{template_file.stem}")
        print(f"Rendered {template_file.name} -> {output_path}")
    return rendered_files_list

def render_template_file(template_file, output_path, context):
        with open(template_file, "r") as f:
            template_content = f.read()
        template = Template(template_content, undefined=StrictUndefined)
        rendered = template.render(context)
        # output_path = rendered_patches_dir / f"{template_file.stem}"
        with open(output_path, "w") as out_f:
            out_f.write(rendered)



def get_folder_names(config_dir):
    
    # Compose relative directories
    paths = {}
    paths['config_dir'] = config_dir
    paths['discovery_dir'] = config_dir / "discovery"
    paths['secrets_dir'] = config_dir / "secrets"
    paths['talos_dir'] = config_dir / 'talos'

    paths['nodes_dir'] = config_dir / 'talos' / 'nodes'
    paths['patches_dir'] = config_dir / 'talos' / 'patches'
    paths['patches_controlplane_dir'] = config_dir / 'talos' / 'patches' / 'controlplane'
    paths['patches_worker_dir'] = config_dir / 'talos' / 'patches' / 'worker'

    # file paths
    paths['cluster_config_file'] = config_dir / 'cluster_config.yaml'
    paths['cluster_nodes_index_file'] = config_dir / 'cluster_nodes_index.yaml'
    paths['schematic_file'] = config_dir / 'talos' / 'schematic.yaml'

    paths['secrets_file'] = paths['secrets_dir'] / 'secrets.yaml'
    paths['talosconfig_file'] = paths['secrets_dir'] /'talosconfig.yaml'
    return paths


def load_yaml_file(file_path):

    result = {}
    if file_path.is_file():
        with open( file_path, 'r') as f:
            result = yaml.safe_load(f)
    return result

def save_schematic_id(args):

    # print(f"called with params {args}")
    global cluster_config

    if not config_folders['schematic_file'].is_file():
        print('Missing schemetic file')
        return False

    with open(config_folders['schematic_file'], 'rb') as f:
        schematic_data = f.read()

    response = requests.post('https://factory.talos.dev/schematics', data=schematic_data )        


    response.raise_for_status()  # Raise an error if the request failed
    schematic_id = response.json()['id']

    print (f"schamatic id: {schematic_id}")

    cluster_config['talos']['schematicId']=schematic_id
    # print(format_yaml(cluster_config))


    # update cluster_config file with new schematic id
    with open(config_folders['cluster_config_file'], "r") as f:
        content = f.read()
    content = re.sub(r'schematicId:\s*.*', f'schematicId: {schematic_id}', content)


    with open(config_folders['cluster_config_file'], "w") as f:
        f.write(content)

    cluster_config=load_yaml_file(config_folders['cluster_config_file'])        
    print('Updated cluster config:')
    print(format_yaml(cluster_config))


def format_yaml(arg):
    return yaml.dump(arg, default_flow_style=False)

def format_json(arg):
    return json.dumps(arg, indent=2, sort_keys=True)

def initialize_talos_secrets():

    # -------------Initialize Secrets if needed------------------
    secrets_path = config_folders['secrets_file']

    if Path(secrets_path).is_file():
        print("Talos secrets already exists")
    else:
        secrets_command = ["talosctl", "gen", "secrets", "-o",  f"{secrets_path}"]
        try:
            print(f"Initializing Talos secrets...")
            print(secrets_command)
            result = subprocess.run(secrets_command, capture_output=True, text=True)
            print(result)
            print(result.stdout.strip())
            if (result.returncode):
                print(f"ERROR: {result.stderr}")
                
                return False
            print(f"Done. Talos secrets files initialized in {secrets_path}")
        except subprocess.SubprocessError as e:
            print(f"Error running command for {filename}: {e}")

def upload_hcloud_image(args):

    global cluster_config

    hcloud_token = os.getenv("HCLOUD_TOKEN")

    if not hcloud_token:
        print("Error: HCLOUD_TOKEN environment variable is not set", file=sys.stderr)
        print("Please set it with: export HCLOUD_TOKEN=your_token_here", file=sys.stderr)
        sys.exit(1)

    talos_image_arch = "amd64"
    hcloud_server_arch = "x86"

    # Read Talos version from config file
    talos_version = cluster_config["talos"]["version"]
    talos_schematic_id = cluster_config['talos']['schematicId']

    print(f"Preparing Talos image hcloud-{talos_image_arch} {talos_version} for schematic ID {talos_schematic_id}")

    # Create storage directory
    os.makedirs("storage", exist_ok=True)

    OUTPUT_FILE = f"storage/hcloud-{talos_image_arch}-{talos_version}.raw.xz"
    SCHEMATIC_ID= "376567988ad370138ad8b2698212367b8edcb69b5fd68c80be1f2ec7d603b4ba"
    DOWNLOAD_URL = f"https://factory.talos.dev/image/{SCHEMATIC_ID}/{talos_version}/hcloud-{talos_image_arch}.raw.xz"
    SCHEMATIC_HASH = hashlib.md5(SCHEMATIC_ID.encode()).hexdigest()
    LABEL = f"open-talos-builer/v={SCHEMATIC_HASH}-{talos_version}"
    print(LABEL)

    # check if the image exists already
    # 
    # Retrieve the snapshot id
    result = subprocess.run(
        ["hcloud", "image", "list", "--type", "snapshot", "-l", LABEL, "-o", "json"],
        capture_output=True,
        text=True,
        check=True
    )
    images = json.loads(result.stdout)
    print(images)
    if len(images)>0:
        HCLOUD_TALOS_IMAGE_ID = images[0]["id"] 
        print(f"found image already in HCloud, id={HCLOUD_TALOS_IMAGE_ID}")

    else:

        # Download image if it doesn't exist
        if not os.path.isfile(OUTPUT_FILE):
            print(f"wget {DOWNLOAD_URL} -O {OUTPUT_FILE}")
            subprocess.run(["wget", DOWNLOAD_URL, "-O", OUTPUT_FILE], check=True)
        else:
            print(f"found {OUTPUT_FILE}, will not re-download")

        print("Running Docker hcloud-upload-image:latest")

        # Run Docker container
        subprocess.run([
            "docker", "run", "--rm",
            "-e", f"HCLOUD_TOKEN={hcloud_token}",
            "-v", f"{os.getcwd()}/{OUTPUT_FILE}:/image.xz",
            "ghcr.io/apricote/hcloud-upload-image:latest", "upload",
            "--image-path", "/image.xz",
            "--architecture", hcloud_server_arch,
            "--compression", "xz",
            "--labels", LABEL
        ], check=True)

        # Retrieve the snapshot id
        result = subprocess.run(
            ["hcloud", "image", "list", "--type", "snapshot", "-l", LABEL, "-o", "json"],
            capture_output=True,
            text=True,
            check=True
        )
        images = json.loads(result.stdout)
        HCLOUD_TALOS_IMAGE_ID = images[0]["id"]

    # update cluster_config file with new image id
    with open(config_folders['cluster_config_file'], "r") as f:
        content = f.read()
    # content = re.sub(r'hcloud-image-id:\s*.* ', f'hcloud-image-id: {HCLOUD_TALOS_IMAGE_ID}', content)
    content = re.sub(r'(hcloud-image-id:)\s+\S+(\s+#.*)$', rf'\1       {HCLOUD_TALOS_IMAGE_ID}\2  ', content, flags=re.MULTILINE)


    with open(config_folders['cluster_config_file'], "w") as f:
        f.write(content)

    cluster_config=load_yaml_file(config_folders['cluster_config_file'])        
    print('Updated cluster config:')
    print(format_yaml(cluster_config))

    print(f"Use snapshot {HCLOUD_TALOS_IMAGE_ID}")
    print('Updated cluster config with image id')


def create_cp_lb(args):

    global cluster_config

    lb_name = f"{cluster_config['cluster']['name']}-controlplane"
    lb_label = 'type=controlplane'
    lb_zone = cluster_config['hetzner']['hcloud-zone']

    # check LB exists
    command = ["hcloud", "load-balancer", "list", "-l", lb_label, "-o", "json"]
    result = subprocess.run( command, capture_output=True, text=True, check=True)
    lbs = json.loads(result.stdout)
    if len(lbs) > 0:
        print(f"load balancer {lb_name} already exists")
    else:
        print(f"creating LB {lb_name}")
        command = ['hcloud', 'load-balancer', 'create', '--name', lb_name, '--network-zone', lb_zone, '--type', 'lb11', '--label', lb_label]
        print(" ".join(command))
        result = subprocess.run(command, capture_output=True, text=True, check=True )
        print(result.stdout)
    
        time.sleep(2)
        print('adding 6443 sevice to LB')
        command = ['hcloud', 'load-balancer', 'add-service', lb_name, '--listen-port', '6443', '--destination-port', '6443', '--protocol', 'tcp']
        print(" ".join(command))
        result = subprocess.run(command, capture_output=True, text=True, check=False )
        print('--------')
        if (result.returncode):
            print(f"ERROR: {result.stderr}")
        else:
            print(result.stdout)
    
        print('adding targets to LB')
        print(" ".join(command))
        command = ['hcloud', 'load-balancer', 'add-target', '--label-selector', lb_label, lb_name ]
        result = subprocess.run(command, capture_output=True, text=True, check=False )
        if (result.returncode):
                print(f"ERROR: {result.stderr}")
        else:
            print(result.stdout)
    

    # check
    command = ["hcloud", "load-balancer", "list", "-l", lb_label, "-o", "json"]
    result = subprocess.run( command, capture_output=True, text=True, check=True)
    lbs = json.loads(result.stdout)
    lb = lbs[0]
    lb_ip = lb['public_net']['ipv4']['ip']
    print(format_json(lb_ip))
    
    # update cluster_config file with new image id
    with open(config_folders['cluster_config_file'], "r") as f:
        content = f.read()
    content = re.sub(r'(cp-lb-ip:)\s+\S+(\s+#.*)$', rf'\1 {lb_ip}\2', content, flags=re.MULTILINE)

    with open(config_folders['cluster_config_file'], "w") as f:
        f.write(content)

    cluster_config=load_yaml_file(config_folders['cluster_config_file'])        
    print('Updated cluster config:')
    print(format_yaml(cluster_config))

    print(f"Control plane LB IP is {lb_ip}")
    print('Saved to cluster config')


def create_network(args):
    """
    mise set NETWORK_NAME=$CLUSTER_NAME
    hcloud network create --ip-range 10.12.0.0/16 --name $NETWORK_NAME
    hcloud network add-subnet --type server --network-zone eu-central --ip-range 10.12.2.0/24 $NETWORK_NAME
    hcloud network add-subnet --type vswitch --network-zone eu-central --ip-range 10.12.3.0/24 --vswitch-id $VSWITCH_ID  $NETWORK_NAME
    hcloud network  $NETWORK_NAME
    """

    global cluster_config

    net_name = f"{cluster_config['cluster']['name']}"
    net_cidr = cluster_config['cluster']['networking']['private-node-cidr']
    net_zone = cluster_config['hetzner']['hcloud-zone']
    net_subnet_virtual = cluster_config['cluster']['networking']['subnet-virtual']
    net_subnet_metal = cluster_config['cluster']['networking']['subnet-metal']
    vswitch_id = cluster_config['hetzner']['robot-vswitch-id']


    # check Net exists
    command = ["hcloud", "network", "list", "-o", "json"]
    result = subprocess.run( command, capture_output=True, text=True, check=True)
    nets = json.loads(result.stdout)
    if len(nets) > 0:
        print(f"Network {net_name} already exists")
        network = nets[0]
        # print(format_json(network))

    else:
        exit()
        print(f"creating net {net_name}")
        command = ['hcloud', 'network', 'create', '--name', net_name, '--ip-range', net_cidr]
        print(" ".join(command))
        result = subprocess.run(command, capture_output=True, text=True, check=True )
        if (result.returncode):
            print(f"ERROR: {result.stderr}")
        else:
            print(result.stdout)
    
        print('adding VM subnet')
        command = ['hcloud', 'network', 'add-subnet', '--type', 'server', '--network-zone', net_zone, '--ip-range', net_subnet_virtual, net_name]
        print(" ".join(command))
        result = subprocess.run(command, capture_output=True, text=True, check=False )
        print('--------')
        if (result.returncode):
            print(f"ERROR: {result.stderr}")
        else:
            print(result.stdout)

        print('adding Metal subnet')
        command = ['hcloud', 'network', 'add-subnet', '--type', 'vswitch', '--network-zone', 
            net_zone, '--ip-range', f"{net_subnet_metal}", '--vswitch-id', f"{vswitch_id}", net_name]
        print(" ".join(command))
        result = subprocess.run(command, capture_output=True, text=True, check=False )
        print('--------')
        if (result.returncode):
            print(f"ERROR: {result.stderr}")
        else:
            print(result.stdout)

        print('exposing routes to vswitch')
        command = ['hcloud', 'network', 'expose-routes-to-vswitch', net_name]
        print(" ".join(command))
        result = subprocess.run(command, capture_output=True, text=True, check=False )
        print('--------')
        if (result.returncode):
            print(f"ERROR: {result.stderr}")
        else:
            print(result.stdout)


        # check Net exists
        command = ["hcloud", "network", "list", "-o", "json"]
        result = subprocess.run( command, capture_output=True, text=True, check=True)
        nets = json.loads(result.stdout)
        network = nets[0]

    if network:
        print(f"Network is:")
        print(format_json(network))

        # update cluster_config file with new image id
        with open(config_folders['cluster_config_file'], "r") as f:
            content = f.read()
        content = re.sub(r'(hcloud-network-id:)\s+\S+(\s+#.*)$', rf'\1     {network['id']}\2', content, flags=re.MULTILINE)

        with open(config_folders['cluster_config_file'], "w") as f:
            f.write(content)

        cluster_config=load_yaml_file(config_folders['cluster_config_file'])        
        print('Updated cluster config:')
        print(format_yaml(cluster_config))

        print(f"HCloud Network ID is {network['id']}")
        print('Saved to cluster config')
                
        return True
    
    return False

def create_cp_nodes(args):

    global cluster_config

    """
    mise set HCLOUD_NETWORK_ID=$(hcloud network list -o json | jq '.[0].id')
    mise set HCLOUD_TALOS_IMAGE_ID=$(hcloud image list | grep snapshot | awk '{print $1;}')

    hcloud server create --name $CLUSTER_NAME-cp-1 \
            --without-ipv6 \
            --network $HCLOUD_NETWORK_ID \
            --image $HCLOUD_TALOS_IMAGE_ID \
            --type ccx13 \
            --datacenter fsn1-dc14 \
        --label 'type=controlplane' \
        --user-data-from-file ../config/rendered/controlplane.yaml
    """


    
    server_label = 'type=controlplane'
    server_zone = cluster_config['hetzner']['hcloud-zone']
    server_type = cluster_config['hetzner']['cp-server-type']
    datacenter = cluster_config['hetzner']['cp-datacenter']
    network_id = cluster_config['hetzner']['hcloud-network-id']
    server_image = cluster_config['hetzner']['hcloud-image-id']
    userdata_file = config_folders['nodes_dir'] / 'controlplane.yaml'
    desired_cp_node_count = 3

    # check servers exist
    command = ["hcloud", "server", "list", "-l", server_label, "-o", "json"]
    result = subprocess.run( command, capture_output=True, text=True, check=True)
    servers = json.loads(result.stdout)
    # exit()
    if len(servers) == desired_cp_node_count:
        print(f"Controlplane: {len(servers)} servers already exist")
        return True
    else:
        print(f"creating control plane nodes:")

        for i in range(len(servers)+1, desired_cp_node_count+1):
            print(f"creating control plane node {i}:")
            # continue

            server_name = f"{cluster_config['cluster']['name']}-cp-{i}"
            command = ['hcloud', 'server', 'create', '--name', f"{server_name}", '--without-ipv6', 
                '--network', f"{network_id}", '--image', f"{server_image}",  '--type', f"{server_type}", 
                '--datacenter', f"{datacenter}",
                '--label', f"{server_label}",
                '--user-data-from-file', f"{userdata_file}"]
            print(" ".join(command))
            result = subprocess.run(command, capture_output=True, text=True, check=False )
            if result.returncode:
                print(result.stderr)
            else:
                print(result.stdout)
            exit()
    
        


def vswitch(args):

    global cluster_config
    load_dotenv()
    username = os.getenv("HETZNER_ROBOT_USER")
    password = os.getenv("HETZNER_ROBOT_PASSWORD")
    print(f"usernmame is {password}:{username}")

    # Initialize API client
    print("\nInitializing API client...")
    robot = HetznerRobotAPI(username, password)
    print("✓ API client initialized\n")

    switches=robot.list_vswitches()
    # print(format_json(switches))

    vswitch_name=cluster_config['cluster']['name']
    vswitch_tag = cluster_config['hetzner']['robot-vlan-tag']

    matching_vswitches = [vs for vs in switches if vs['name'] == vswitch_name and vs['vlan'] == vswitch_tag and vs['cancelled']==False]
    if len(matching_vswitches):
        vswitch=matching_vswitches[0]
        print(f"vSwitch exits: {vswitch}")

    else:
        print(f"creating vswitch {vswitch_name} with tag {vswitch_tag}")
        vswitch=robot.create_vswitch(name=vswitch_name, vlan=vswitch_tag)
        print(vswitch)
    

    # update cluster_config file with new vSwitch ID
    with open(config_folders['cluster_config_file'], "r") as f:
        content = f.read()
    content = re.sub(r'(robot-vswitch-id:)\s+\S+(\s+#.*)$', rf'\1 {vswitch['id']}\2', content, flags=re.MULTILINE)

    with open(config_folders['cluster_config_file'], "w") as f:
        f.write(content)

    cluster_config=load_yaml_file(config_folders['cluster_config_file'])        
    print('Updated cluster config:')
    print(format_yaml(cluster_config))

    print(f"vSwitch ID: {vswitch['id']}")
    print('Saved to cluster config')        

def test(args):
    return True

def main():
    parser = argparse.ArgumentParser(
        description='Multi-purpose utility script with various actions',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
  %(prog)s fileinfo /path/to/file --hash
  %(prog)s calc add 10 20 --verbose
  %(prog)s text "Hello World" --uppercase --stats
  %(prog)s list /path/to/directory --long --sort size
        '''
    )

    # Load variables from .env file
    load_dotenv()
    
    # Global arguments
    parser.add_argument('--version', action='version', version='%(prog)s 1.0.0')
    parser.add_argument('--debug', action='store_true', help='Enable debug output')
    
    # Subcommands
    subparsers = parser.add_subparsers(dest='action', help='Action to perform', required=True)
    
    # File info subcommand
    parser_init = subparsers.add_parser('init', help='Initialize configuration')
    parser_init.set_defaults(func=initialize_config)
    
    parser_render = subparsers.add_parser('render', help='Render configuration')
    parser_render.set_defaults(func=render_config)

    parser_schematic = subparsers.add_parser('schematic', help='Calculate Talos schematic id and save in config file')
    parser_schematic.set_defaults(func=save_schematic_id)
    
    parser_hcloud_image = subparsers.add_parser('hcloud-image', help="Upload Talos image to HCloud, update config file")
    parser_hcloud_image.set_defaults(func=upload_hcloud_image)
    
    parser_cp_lb = subparsers.add_parser('cp-lb', help="create control plain LB")
    parser_cp_lb.set_defaults(func=create_cp_lb)

    parser_cp_nodes = subparsers.add_parser('cp-nodes', help="create control plain nodes")
    parser_cp_nodes.set_defaults(func=create_cp_nodes)

    parser_network = subparsers.add_parser('net', help="create network and subnets")
    parser_network.set_defaults(func=create_network)

    parser_vswitch = subparsers.add_parser('vswitch', help="create vSwitch and save ID to cluster config")
    parser_vswitch.set_defaults(func=vswitch)


    parser_test = subparsers.add_parser('test', help="run some tests")
    parser_test.set_defaults(func=test)


    # Parse arguments
    args = parser.parse_args()

    if args.debug:
        print(f"Debug: Arguments parsed: {args}")
    


    global config_folders, template_folders
    config_folders = get_folder_names(Path("config"))
    template_folders = get_folder_names(Path("config_templates"))


    global cluster_config , nodes_index

    cluster_config = load_yaml_file(config_folders['cluster_config_file'])

    # Execute the appropriate function
    try:
        return args.func(args)
    except KeyboardInterrupt:
        print("\nOperation cancelled by user.")
        return 130
    except Exception as e:
        print(f"Error: {e}")
        if args.debug:
            import traceback
            traceback.print_exc()
        return 1


if __name__ == '__main__':
    sys.exit(main())
