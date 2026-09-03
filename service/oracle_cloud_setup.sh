#!/bin/bash
# ==============================================================================
# Oracle Cloud Always Free: MT4 + TradeAutoBot 1-Click Installer
# OS: Ubuntu 22.04 LTS (AMD x86_64 or ARM with box86)
# ==============================================================================
set -e

echo "=== [1/5] Updating System Packages ==="
sudo apt update && sudo apt upgrade -y

echo "=== [2/5] Installing Wine & Remote Desktop (XRDP + XFCE) ==="
sudo dpkg --add-architecture i386
sudo apt update
sudo apt install -y wine wine32 wine64 winetricks xfce4 xfce4-goodies xrdp git python3 python3-pip python3-venv

# Configure XRDP
echo "xfce4-session" > ~/.xsession
sudo systemctl enable xrdp
sudo systemctl restart xrdp

echo "=== [3/5] Cloning TradeAutoBot Repository ==="
cd /opt
if [ ! -d "/opt/TradeAutoBot" ]; then
    sudo git clone https://github.com/Omerhalilli/TradeAutoBot.git
fi
cd /opt/TradeAutoBot

echo "=== [4/5] Installing Python Dependencies ==="
sudo pip3 install -r requirements.txt

echo "=== [5/5] Setup Systemd Service ==="
sudo cp service/mt4-telegram-bot.service /etc/systemd/system/
sudo systemctl daemon-reload

echo "=================================================================="
echo "✅ Installation Complete!"
echo "Next Steps:"
echo "1. Set a password for your user: sudo passwd \"
echo "2. Open Windows Remote Desktop (mstsc.exe) and connect to this VM's Public IP"
echo "3. Download your MT4 installer inside the desktop (wine mt4setup.exe)"
echo "4. Configure /opt/TradeAutoBot/.env with your Bot Token and Chat ID"
echo "5. Start bot: sudo systemctl start mt4-telegram-bot"
echo "=================================================================="
