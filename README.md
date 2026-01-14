# Network Device Manager

A web-based application for managing and monitoring Cisco IOS network devices. This tool provides a centralized interface for device inventory management, remote command execution, file management, and live terminal access.

![Python](https://img.shields.io/badge/python-3.10+-blue.svg)
![Flask](https://img.shields.io/badge/flask-3.0.0-green.svg)
![License](https://img.shields.io/badge/license-MIT-blue.svg)

## Features

- **Device Inventory Management**: Store and manage multiple Cisco IOS devices with encrypted credentials
- **Real-time Monitoring**: Background ping worker tracks device online/offline status
- **Remote Command Execution**: Run individual commands or multi-line scripts on devices
- **File Management**: Upload and delete files via TFTP integration
- **Live Terminal**: Interactive SSH sessions with xterm.js terminal emulator
- **Quick Actions**: Create reusable command shortcuts for frequently used operations
- **Drag & Drop Ordering**: Organize device list with drag-and-drop reordering
- **Secure Credential Storage**: Fernet encryption for passwords and enable secrets

## Prerequisites

- Python 3.10 or higher
- Network access to Cisco IOS devices (SSH port 22)
- TFTP server (for file upload functionality)
- Administrator privileges on target devices

## Installation

### 1. Clone or Download the Repository

```bash
cd "Final Project - Dustin Marchak"
```

### 2. Create Virtual Environment (Recommended)

```bash
python -m venv venv

# Windows
venv\Scripts\activate

# Linux/Mac
source venv/bin/activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure TFTP Server (Optional - for file uploads)

The application requires a TFTP server for file upload functionality:

- Install a TFTP server (e.g., Tftpd64 for Windows, tftpd-hpa for Linux)
- Configure TFTP root directory: `C:\TFTP-Root` (Windows) or update [app.py:443](app.py#L443)
- Update TFTP server IP in [app.py:450](app.py#L450) to match your server's IP
- Ensure the device can reach the TFTP server

## Usage

### Starting the Application

```bash
python app.py
```

The application will:
- Start the Flask web server on `http://127.0.0.1:5000`
- Automatically open your default web browser
- Begin monitoring device status in the background

### Adding Devices

1. Navigate to the home page
2. Fill in the "Add New Device" form:
   - **IP Address**: Device management IP
   - **Username**: SSH username
   - **Password**: SSH password
   - **Enable Secret**: Privileged EXEC mode password
3. Click "Add Device"

The application will verify connectivity and store the device with encrypted credentials.

### Managing Devices

Click the "Manage" button next to any online device to access:

#### Utilities Tab
- **Quick Actions**: Execute pre-configured commands with one click
- **Custom Commands**: Run any IOS command
- **Save Quick Actions**: Store frequently used commands

#### File Management Tab
- **Upload Files**: Transfer files via TFTP
- **Delete Files**: Remove files from device filesystem
- **Browse Filesystems**: View and manage files across all device filesystems

#### Scripts Tab
- **Multi-line Scripts**: Execute multiple commands sequentially
- **Execution Modes**:
  - **Enable Mode**: Run commands in privileged EXEC
  - **Configure Terminal**: Run commands in configuration mode

#### Terminal Tab
- **Live SSH Session**: Interactive terminal with command history
- **Real-time Output**: Instant feedback from device
- **Auto-reconnect**: Automatic session restoration

## Project Structure

```
Final Project - Dustin Marchak/
├── app.py                      # Main Flask application
├── requirements.txt            # Python dependencies
├── README.md                   # This file
├── setup.iss                   # Inno Setup installer script
├── modules/                    # Application modules
│   ├── config.py              # Configuration settings
│   ├── connection.py          # SSH connection management
│   ├── device.py              # Device operations & persistence
│   ├── terminal.py            # Live terminal session handling
│   ├── quick_actions.py       # Quick action persistence
│   └── utils.py               # Utility functions
├── templates/                  # HTML templates
│   ├── base.html              # Base template with navigation
│   ├── index.html             # Device list page
│   └── device.html            # Device management page
├── static/                     # Static assets
│   ├── css/                   # Bootstrap CSS
│   └── js/                    # Bootstrap JavaScript
└── data/                       # Runtime data (auto-created)
    ├── Devices.csv            # Device inventory
    ├── quick_actions.json     # Quick action definitions
    └── key.key                # Encryption key (auto-generated)
```

## Configuration

### Application Settings

Edit [modules/config.py](modules/config.py) to customize:

- `PING_INTERVAL`: Device status check interval (default: 5 seconds)
- `FAST_CLI`: Netmiko performance mode (default: True)
- `DATA_DIR`: Location for data files

### TFTP Settings

Currently hardcoded in [app.py](app.py):

- TFTP Root: Line 443
- TFTP Server IP: Line 450

**Note**: A future update will move these to the config module.

## Security Considerations

- **Credential Encryption**: All passwords are encrypted using Fernet symmetric encryption
- **Local Storage**: Credentials stored in CSV file in `data/` directory
- **Network Security**: Ensure the application runs on a trusted network
- **Access Control**: No built-in authentication; secure the host system
- **HTTPS**: Consider running behind a reverse proxy with SSL/TLS for production

## Troubleshooting

### Device Shows Offline

- Verify network connectivity: `ping <device-ip>`
- Check SSH is enabled on device: `show ip ssh`
- Verify credentials are correct
- Check firewall rules allow SSH (port 22)

### TFTP Upload Fails

- Verify TFTP server is running
- Check TFTP server IP matches configuration
- Ensure device can reach TFTP server
- Verify file permissions in TFTP root directory

### Terminal Connection Issues

- Check device SSH settings
- Verify enable secret is correct
- Review browser console for WebSocket errors
- Try refreshing the page

### Application Won't Start

```bash
# Check Python version
python --version  # Should be 3.10+

# Verify all dependencies installed
pip list

# Check for port conflicts
netstat -an | findstr 5000  # Windows
lsof -i :5000               # Linux/Mac
```

## Development

### Running in Debug Mode

Edit [app.py:733](app.py#L733):

```python
socketio.run(app, host="127.0.0.1", port=5000, debug=True, use_reloader=True)
```

### Adding New Routes

1. Define route handler in [app.py](app.py)
2. Keep business logic in `modules/` directory
3. Create/update templates in `templates/`
4. Test with actual devices or mocks

### Building Installer

The project includes an Inno Setup script ([setup.iss](setup.iss)) for creating Windows installers:

1. Install Inno Setup
2. Update paths in setup.iss
3. Compile the script
4. Distribute the generated installer

## Known Limitations

- Single-user application (no authentication system)
- TFTP required for file uploads (SCP support planned)
- Designed for Cisco IOS devices (other vendors untested)
- CSV-based storage (database migration planned)
- No command history persistence

## Future Enhancements

- Multi-device command execution
- Scheduled configuration backups
- Configuration change tracking
- User authentication and RBAC
- Database backend (SQLite/PostgreSQL)
- REST API
- Device grouping and tagging
- Search and filtering
- Export/import functionality

## Contributing

This is a course final project. If you'd like to enhance it:

1. Test thoroughly with your network devices
2. Add error handling for edge cases
3. Document any new features
4. Consider security implications

## License

This project is created as a final project for CSCI 5020.

## Author

Dustin Marchak

## Acknowledgments

- Flask and Flask-SocketIO for the web framework
- Netmiko for Cisco device automation
- xterm.js for terminal emulation
- Bootstrap 5 for UI components
