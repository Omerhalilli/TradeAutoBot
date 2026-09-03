# ☁️ Oracle Cloud Always Free 24/7 Hosting Guide for TradeAutoBot

Oracle Cloud provides an **Always Free Tier** that never expires, allowing you to run your MetaTrader 4 instance and the Telegram Bot **24 hours a day, 7 days a week for \/month**.

---

## 📋 Step 1: Sign Up for Oracle Cloud Always Free

1. Go to: **[https://signup.cloud.oracle.com/](https://signup.cloud.oracle.com/)**
2. Enter your Country, Name, and Email.
3. **Select your Home Region**:
   * Choose a European region close to Invest-AZ's servers (e.g. **Germany Central (Frankfurt)** or **UK South (London)**) for ultra-low 1-2 ms execution latency.
4. **Payment Verification**:
   * Oracle requires a valid debit/credit card to prevent duplicate accounts.
   * They place a temporary ~\ hold and immediately release it. **You will never be charged as long as you select \"Always Free Eligible\" resources.**
5. Complete account verification.

---

## 🖥️ Step 2: Create Your Free Cloud Instance

1. In the Oracle Cloud Console, click **Create a VM instance**.
2. **Name**: TradeAutoBot-VPS
3. **Image and Shape**:
   * **OS**: Click *Change Image* ➜ Select **Ubuntu 22.04 Minimal** or **Ubuntu 22.04**.
   * **Shape**: Select **VM.Standard.E2.1.Micro** (AMD x86_64, 1 core, 1 GB RAM — *Always Free Eligible*).
     *(Or VM.Standard.A1.Flex if you prefer ARM 4-core, 24GB RAM)*.
4. **Networking**: Keep defaults (Create new Virtual Cloud Network).
5. **Add SSH Keys**:
   * Click **Save private key** and download ssh-key-....key to your computer.
6. **Firewall / Ingress Rules**:
   * In your Subnet's Security List, add an Ingress Rule for Port 3389 (TCP) to allow Remote Desktop (RDP).
7. Click **Create** (takes ~60 seconds to provision).

---

## ⚡ Step 3: Run the 1-Click Installer

Connect via SSH from your computer (using Windows Terminal or PowerShell):
`cmd
ssh -i "path\to\your-key.key" ubuntu@<YOUR_VM_PUBLIC_IP>
`

Run the automated installer script:
`ash
curl -sSL https://raw.githubusercontent.com/Omerhalilli/TradeAutoBot/main/service/oracle_cloud_setup.sh | bash
`

Set a password for Remote Desktop:
`ash
sudo passwd ubuntu
`
*(Enter a secure password for your desktop login)*.

---

## 💻 Step 4: Connect via Windows Remote Desktop

1. On your Windows laptop, press Win + R, type **mstsc**, and press Enter.
2. In **Computer**, enter your Oracle VM's **Public IP address**.
3. Click **Connect**.
4. Log in with:
   * **Username**: ubuntu
   * **Password**: *(The password you created in Step 3)*.
5. You will see an XFCE graphical desktop!

---

## 📈 Step 5: Launch MT4 & TradeAutoBot

Inside your Remote Desktop:
1. Open the browser or terminal and download your Invest-AZ MT4 installer:
   `ash
   wine /path/to/investaz_mt4_setup.exe
   `
2. Log into your Invest-AZ demo account.
3. Open terminal and configure your .env:
   `ash
   cd /opt/TradeAutoBot
   sudo nano .env
   `
   Paste your TELEGRAM_BOT_TOKEN and ALLOWED_CHAT_IDS.
4. Start the 24/7 background system service:
   `ash
   sudo systemctl start mt4-telegram-bot
   sudo systemctl enable mt4-telegram-bot
   `

Now you can close Remote Desktop, turn off your home laptop, and your MT4 bot will trade and send Telegram notifications 24/7 in the cloud!
