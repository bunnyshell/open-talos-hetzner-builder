"""
Hetzner Robot API Client for vSwitch Management

This script provides functions to:
- Create a new vSwitch
- List existing vSwitches
- Add servers to a vSwitch
- Remove servers from a vSwitch
- Delete a vSwitch

Requirements:
    pip install requests

Setup:
    1. Create a web service user in Hetzner Robot:
       - Login to https://robot.hetzner.com
       - Go to Settings -> Web service and app settings
       - Create a new user with your preferred credentials
    
    2. Set environment variables or provide credentials directly:
       export HETZNER_ROBOT_USER="your_username"
       export HETZNER_ROBOT_PASSWORD="your_password"
"""

import os
import requests
from typing import Dict, List, Optional, Any
from requests.auth import HTTPBasicAuth
import json

def format_json(arg):
    return json.dumps(arg, indent=2, sort_keys=True)

class HetznerRobotAPI:
    """Client for Hetzner Robot API operations"""
    
    BASE_URL = "https://robot-ws.your-server.de"
    
    def __init__(self, username: str, password: str):
        """
        Initialize the Hetzner Robot API client
        
        Args:
            username: Hetzner Robot web service user
            password: Hetzner Robot web service password
        """
        self.username = username
        self.password = password
        self.auth = HTTPBasicAuth(username, password)
    
    def _make_request(
        self, 
        method: str, 
        endpoint: str, 
        data: Optional[Dict] = None,
        json_format: bool = True
    ) -> Dict[str, Any]:
        """
        Make an HTTP request to the Robot API
        
        Args:
            method: HTTP method (GET, POST, DELETE, etc.)
            endpoint: API endpoint (e.g., "/vswitch")
            data: POST/PUT data
            json_format: If True, request JSON format
            
        Returns:
            Parsed API response
            
        Raises:
            requests.HTTPError: If request fails
        """
        url = self.BASE_URL + endpoint
        if json_format:
            url += ".json"
        
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded"
        }
        
        try:
            response = requests.request(
                method=method,
                url=url,
                auth=self.auth,
                data=data,
                headers=headers,
                timeout=30
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            print(f"HTTP Error: {e.response.status_code}")
            print(f"Response: {e.response.text}")
            raise
        except Exception as e:
            print(f"Request failed: {e}")
            raise
    
    def create_vswitch(self, name: str, vlan: int) -> Dict[str, Any]:
        """
        Create a new vSwitch
        
        Args:
            name: Name for the vSwitch
            vlan: VLAN ID (must be between 4000 and 4091)
            
        Returns:
            API response with created vSwitch details
        """
        if not (4000 <= vlan <= 4091):
            raise ValueError("VLAN ID must be between 4000 and 4091")
        
        data = {
            "name": name,
            "vlan": vlan
        }
        
        # print(f"Creating vSwitch '{name}' with VLAN {vlan}...")
        response = self._make_request("POST", "/vswitch", data=data)
        # print(f"✓ vSwitch created successfully")
        return response
    

    def list_vswitches(self) -> Dict[str, Any]:
        """
        List all vSwitches
        
        Returns:
            API response with list of vSwitches
        """
        print("Fetching vSwitches...")
        response = self._make_request("GET", "/vswitch")
        # print(f"✓ Found {len('vswitches')} vSwitch(es)")
        return response
    
    def get_vswitch(self, vswitch_id: int) -> Dict[str, Any]:
        """
        Get details of a specific vSwitch
        
        Args:
            vswitch_id: ID of the vSwitch
            
        Returns:
            API response with vSwitch details
        """
        print(f"Fetching vSwitch {vswitch_id}...")
        response = self._make_request("GET", f"/vswitch/{vswitch_id}")
        return response
    
    def add_server_to_vswitch(self, vswitch_id: int, server_id: int) -> Dict[str, Any]:
        """
        Add a server to a vSwitch
        
        Args:
            vswitch_id: ID of the vSwitch
            server_id: ID of the server to add
            
        Returns:
            API response
        """
        data = {
            "server": server_id
        }
        
        print(f"Adding server {server_id} to vSwitch {vswitch_id}...")
        response = self._make_request(
            "POST", 
            f"/vswitch/{vswitch_id}/server", 
            data=data
        )
        print(f"✓ Server {server_id} added to vSwitch successfully")
        return response
    
    def remove_server_from_vswitch(self, vswitch_id: int, server_id: int) -> Dict[str, Any]:
        """
        Remove a server from a vSwitch
        
        Args:
            vswitch_id: ID of the vSwitch
            server_id: ID of the server to remove
            
        Returns:
            API response
        """
        data = {
            "server": server_id
        }
        
        print(f"Removing server {server_id} from vSwitch {vswitch_id}...")
        response = self._make_request(
            "DELETE", 
            f"/vswitch/{vswitch_id}/server", 
            data=data
        )
        print(f"✓ Server {server_id} removed from vSwitch successfully")
        return response
    
    def delete_vswitch(self, vswitch_id: int) -> Dict[str, Any]:
        """
        Delete a vSwitch
        
        Args:
            vswitch_id: ID of the vSwitch to delete
            
        Returns:
            API response
        """
        print(f"Deleting vSwitch {vswitch_id}...")
        response = self._make_request("DELETE", f"/vswitch/{vswitch_id}")
        print(f"✓ vSwitch {vswitch_id} deleted successfully")
        return response

