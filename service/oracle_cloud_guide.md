# ☁️ Oracle Cloud Always Free 24/7 Hosting Guide for TradeAutoBot

Oracle Cloud provides an **Always Free Tier** that never expires, allowing you to run your MetaTrader 4 instance and the Telegram Bot **24 hours a day, 7 days a week for \/month**.

---

## 📋 Step 1: Sign Up for Oracle Cloud Always Free

1. Go to: **[https://signup.cloud.oracle.com/](https://signup.cloud.oracle.com/)**
2. Enter your Country, Name, and Email.
3. **Select your Home Region**:
   * Choose a region close to your broker's trade servers (e.g. **Germany Central (Frankfurt)** or **UK South (London)**) for ultra-low 1-2 ms execution latency.
4. **Payment Verification**:
   * Oracle requires a valid debit/credit card to prevent duplicate accounts.
   * They place a temporary ~$1 hold and immediately release it. **You will never be charged as long as you select "Always Free Eligible" resources.**
5. Complete account verification.

---

## 🖥️ Step 2: Create Your Free Cloud Instance

1. In the Oracle Cloud Console, navigate to **Compute > Instances**.
2. Click **Create Instance**.
3. Name your instance: `mt4-autotrade-vps`
4. **Placement**: Default AD is fine.
5. **Image and Shape**:
   * Click **Change Image**: Select **Canonical Ubuntu 24.04** or **Ubuntu 22.04 Minimal**.
   * Click **Change Shape**: Select **Ampere (ARM)**:
     * OCPUs: **2**
     * Memory (RAM): **12 GB** (Plenty of headroom for Wine + MT4 + Python Bot!)
6. **Networking**:
   * Choose standard Virtual Cloud Network (VCN).
   * Ensure **Assign a public IPv4 address** is selected.
7. **SSH Keys**:
   * Choose **Generate a key pair for me** and click **Save Private Key** to your computer.
8. Click **Create**. Your instance will be ready in 1-2 minutes!

---

## ⚡ Step 3: Run the 1-Click Automated Setup

1. Open your terminal (Linux/macOS) or PowerShell (Windows).
2. Connect to your instance:
   ```bash
   ssh -i /path/to/your/ssh-key.key ubuntu@<YOUR_INSTANCE_PUBLIC_IP>
   ```
3. Run the automated TradeAutoBot installer script:
   ```bash
   curl -fsSL https://raw.githubusercontent.com/Omerhalilli/TradeAutoBot/main/service/oracle_cloud_setup.sh | bash
   ```
   *This script automatically installs Wine-Staging, Python 3, MetaTrader dependencies, lightweight XFCE desktop, RDP server, and the TradeAutoBot daemon service!*

---

## 🖥️ Step 4: Connect via Remote Desktop (RDP)

1. On Windows, press `Win + R`, type `mstsc`, and press Enter.
   *(On macOS/Linux, use Microsoft Remote Desktop or Remmina)*
2. Computer: `<YOUR_INSTANCE_PUBLIC_IP>:3389`
3. Username: `ubuntu`
4. Password: The password you set during the setup script.
5. You will see an XFCE graphical desktop!

---

## 📈 Step 5: Launch MT4 & TradeAutoBot

Inside your Remote Desktop:
1. Open the browser or terminal and download your broker MT4 installer:
   ```bash
   wine /path/to/broker_mt4_setup.exe
   ```
2. Log into your broker trading account.
3. Open terminal and configure your .env:
   ` ash
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
