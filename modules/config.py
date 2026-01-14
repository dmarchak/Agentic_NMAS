import os

# Data directory
DATA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data"))

# Ensure the data directory exists
os.makedirs(DATA_DIR, exist_ok=True)

# Runtime file paths
DEVICES_FILE = os.path.join(DATA_DIR, "Devices.csv")
QUICK_ACTIONS_FILE = os.path.join(DATA_DIR, "quick_actions.json")
KEY_FILE = os.path.join(DATA_DIR, "key.key")
SECRET_KEY_FILE = os.path.join(DATA_DIR, "secret.key")

# Application settings
PING_INTERVAL = 5
FAST_CLI = True

# Flask web server settings
FLASK_HOST = "127.0.0.1"
FLASK_PORT = 5000
FLASK_DEBUG = False

# File transfer settings
# TFTP settings for file upload functionality
# Update these values to match your TFTP server configuration
TFTP_ROOT = "C:/TFTP-Root"  # Local TFTP root directory
TFTP_SERVER_IP = "192.168.47.1"  # TFTP server IP address (must be reachable by devices)

# Ensure TFTP root exists
os.makedirs(TFTP_ROOT, exist_ok=True)

# File transfer method: 'tftp' or 'scp'
# SCP is more reliable and secure but requires SCP to be enabled on the device
# NOTE: SCP requires 'ip scp server enable' on Cisco devices
FILE_TRANSFER_METHOD = "tftp"  # Options: 'tftp', 'scp'

# Connection timeouts
SSH_TIMEOUT = 60  # Seconds for SSH command execution
SSH_PORT = 22  # Default SSH port
