#!/bin/bash

# Check if script is run as root
if [ "$EUID" -ne 0 ]; then
  echo "Please run as root"
  exit
fi

# Create a systemd service file with the necessary content
cat > /etc/systemd/system/espresso_shot.service <<EOL
[Unit]
Description=Espresso Shot Script Service
DefaultDependencies=false

[Service]
ExecStart=/usr/bin/python3 /home/christian/ascaso/main.py
Restart=always
User=root
Group=root

[Install]
WantedBy=sysinit.target
EOL

# Reload systemd daemon to recognize the new service file
systemctl daemon-reload

# Enable the service so it starts on boot
systemctl enable espresso_shot.service

# Start the service
systemctl start espresso_shot.service

# Print the status of the service to confirm it is running correctly
systemctl status espresso_shot.service
