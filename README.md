# Bunnyshell Open Talos-Hetzner Cluster Builder

This is a collection of scripts and templates to help create Kubernetes cluster on metal (and virtul) servers in Hetzner.

## Architecture

- Hibrid Cluster
  - HA control plane running on 3 VMs (Talos)
  - N worker nodes running on Metal servers (Talos)
- Load Balancer for Control Plane
- Load Balancer for Ingress
- vSwitch (connecting VMs and Metal servers)

## Repo structure

```text
.
├── config
│   ├── cluster_config.yaml
│   ├── cluster_nodes_index.yaml
│   ├── discovery
│   ├── secrets
│   └── talos
├── config_templates
│   ├── cluster_config.yaml
│   ├── cluster_nodes_index.yaml
│   └── talos
├── README.md
├── requirements.txt
├── scripts
│   ├── config.py
│   ├── hetzner_robot.py
│   └── install-talos-metal.py
└── storage
```

- `config` folder stores all config files relates to a cluster. You might want to handle it as a distinct git repo. - `config/secrets` is where all the Talos secrets for the cluster are stored. DO NOT ADD to git!!!
- `config_templates` - template files used by the scripts to bootstrap `./config` content
- `scripts/config.py` - main python script
- `scripts/install-talos-metal.py` - script that handles intallation of Talos on metal servers over SSH

## Usage

### Clone the repo

```sh
git clone git@github.com:bunnyshell/open-talos-hetzner-builder 
cd open-talos-hetzner-builder--taloscon
```

### Install Python requirements (using mise)

```sh
mise trust
mise i
```

```sh
uv venv
uv pip install -r requirements.txt
# source .venv/bin/activate
```

### Set Hetzner credentials in .env

The script can manage the needed vSwitch if provided with Hetzner Robot Webservice credentials.
Alternatively, you can create and manage the vSwitch manually from the Robot UI.
To create a Webservice/app user in Hetzner Robot navigate to `robot.hetzner.com` -> `Settings` -> `Webservice and app settings`.

```env
HCLOUD_TOKEN="__________________________________"
HETZNER_ROBOT_USER="__________________________________"
HETZNER_ROBOT_PASSWORD="__________________________________"
```

### Initialize Cluster Config

This script will create config folder, subfolder and draft config files.
Also, it will create Talos secrets.

```sh
uv run scripts/config.py init
```

### Edit the config

Set cluster name, endpoint, hostname and talos version.
Optionally, edit Hetzner zone, datacenter and `cp-server-type`, `robot-vlan-tag`.

### Edit the Talos Schematic and get the schematic ID.

The Talos schematic is used to build the Talos server image for each cluster node. We have 2 types of nodes: worker (metal) and controlplane (VMs).

Edit `config/talos/schematic.yaml` and make sure you include your required Talos extentions.

Next, run:

```sh
uv run scripts/config.py schematic
```

This will calculate the Talos schematic ID and save it to `scripts/cluste_config.yaml`


### Render the Talos config files

In order to install Talos on all servers, we need:

- a Talos config file for all control plane nodes. (All control plane nodes share the same Talos config)
- a Talos config file for each worker node. (Each worker node has it's own Taloc config file because of disk IDs)

Run this command to render Talos config files:

```sh
uv run scripts/config.py render
```

The Talos config files are stored in `config/secrets/nodes/`

### Create a vSwitch in "Robot/Server" (for metal servers)

The cluster needs a vSwitch to connect all metal servers in a private network.
You have 2 choiches to create the vSwitch:

#### Option A: Manually

1. Use the Robot Web UI to create a vSwitch.  (or run `uv run scripts/config.py vswitch`)
2. Connect the metal servers to this vSwitch. 
3. Make sure edit `config/talos_config/cluster_config.yaml` and fill in:
   - the VLAN TAG
   - vSwitch ID (automatic if `uv run scripts/config.py vswitch`)

#### Option B: Using the script

The script will create the vSwitch (with the tag specified in the `config/cluster_config.yaml` file) and save the vSwitch ID (in the same file).

```sh
ur run scripts/config.py vswitch
```

### Create HCloud Network, subnets and connect subnets to vswitch

The cluster needs Virtual Network (similar to a VPC) and dedicated subnets for metal and virtual servers. The metal subnet need to be exposed to the vSwitch (so that metal and virtual servers can communicate over the private network). This command handles all these requirements:

`uv run scripts/config.py net`

### Create LoadBalancer for Control Plane

The cluster needs one load balancer dedicated to the control plane. All control plane nodes will be added to this LB. Run:

`uv run scripts/config.py cp-lb`

### Create DNS record(s) for the cluster Kube API

Create DNS records pointing the cluster hostname (defined as `cluster.hostname` in `scripts/cluster_config.yaml`) to the IP address or hostname of the control plane LB (created at the previous step).

Run  `dig` or `nslookup` to make sure the hostname of the cluster is properly resolved by the DNS system.

### Upload Talos image (snapshot) to HCloud

Hetzner does not support Talos out of the box, we need to create snapshot of Talos to be used for creating VMs.

```sh
uv run scripts/config.py hcloud-image
```

If you want to upload the image manually, skip this step and set `hetzner.hcloud-image-id` in `config/cluster_config.yaml` value to match the desired image ID.

### Create control plane nodes

The cluster uses 3 control plane nodes. These are VMs in HCloud. Run this command:

```sh
uv run scripts/config.py cp-nodes
```

### Bootstrap Kubernetes on one control plane node

```sh

export CP1=___IP_OF_CONTROL_PLANE_SERVER_1___
export TALOSCONFIG=$(realpath config/secrets/talosconfig.yaml)

talosctl dashboard -n $CP1 -e $CP1
# wait for the CP1 server to boot

# bootstrap Kubernetes on CP1
talosctl bootstrap -n $CP1 -e $CP1

```

Get the `kubeconfig.yaml` file

```sh
export KUBECONFIG=$(pwd)/config/secrets/kubeconfig.yaml
talosctl kubeconfig -n $CP1 -e $CP1
```

Wait for the other nodes to join the cluster:

```sh
kubectl get nodes
```

At this point the cluster should have 3 control plane nodes, but NO CNI, so the nodes will be `NOT READY'.

### Add metal servers as worker nodes to the cluster

#### Edit Worker nodes list

We need to have a consistent naming/numbering scheme for the worker nodes. To do this, we write the `config/cluster_nodes_index.yaml` file.

```sh
index:
  1: __ip_of_workernopde_1__
  2: __ip_of_workernopde_2__
  3: __ip_of_workernopde_3__
```

#### Install Talos on metal worker nodes

Reboot each metal node in restore mode (using the Robot interface). Make sure you configure an SSH key for access to the server during restore.

Next, run similar commands for each node (provide `-i` with `__server_number__` value):

```sh

# Example for worker node 1
uv run scripts/install-talos-metal.py -k ~/ssh-key -u root -i 1


# Example for worker node 2
uv run scripts/install-talos-metal.py -k ~/ssh-key -u root -i 2

```

## Next Steps

- Install CNI
- Install CSI

