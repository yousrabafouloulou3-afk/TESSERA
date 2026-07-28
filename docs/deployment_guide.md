# Streamlit TimeTable App Server Deployment Guide (Option 1)

This guide explains how to host the **TESSERA Smart Timetabling App** on a central server in your local network (LAN) or a private cloud. This allows the testing department to access and test the app securely via their web browsers without having access to the source code.

---

## 📋 Table of Contents
1. [Preparation: Create the Deployment Package](#1-preparation-create-the-deployment-package)
2. [Server Setup](#2-server-setup)
   - [A. Deploying on a Linux Server (Ubuntu/Debian) - Recommended](#a-deploying-on-a-linux-server-ubuntudebian---recommended)
   - [B. Deploying on a Windows Server](#b-deploying-on-a-windows-server)
3. [Firewall Configuration](#3-firewall-configuration)
4. [Accessing the Application](#4-accessing-the-application)
5. [Database Considerations](#5-database-considerations)

---

## 1. Preparation: Create the Deployment Package

Before deploying, run the packaging script to generate a clean zip file containing only the app runtime files, assets, and database (excluding local git files, developer scratchpads, and backups).

1. Execute the packaging script:
   ```bash
   python package_app.py
   ```
2. This creates `TimeTable_App_Deliverable.zip` in the parent directory of your project. This ZIP contains:
   * Main entrypoint (`app.py`), views, engines, and database.
   * Image assets (logos).
   * App configurations (`requirements.txt`, `.streamlit/config.toml`).

---

## 2. Server Setup

Choose the guide matching your server operating system.

### A. Deploying on a Linux Server (Ubuntu/Debian) - Recommended

#### 1. Transfer and Extract Code
Copy `TimeTable_App_Deliverable.zip` to the server and extract it:
```bash
sudo apt update
sudo apt install unzip python3-pip python3-venv -y

# Move the zip file to a deployment folder (e.g. /var/www/timetable-app)
sudo mkdir -p /var/www/timetable-app
sudo unzip TimeTable_App_Deliverable.zip -d /var/www/timetable-app
cd /var/www/timetable-app
```

#### 2. Configure Virtual Environment & Install Dependencies
Setting up a Python virtual environment ensures clean, isolated dependency management:
```bash
# Create and activate virtual environment
python3 -m venv venv
source venv/bin/activate

# Install requirements
pip install --upgrade pip
pip install -r requirements.txt
```

#### 3. Configure Streamlit for Network Sharing
Create or update `.streamlit/config.toml` to tell Streamlit to run headlessly and listen to external network interfaces:
```toml
[server]
headless = true
address = "0.0.0.0"
port = 8501
enableCORS = false
enableXsrfProtection = true

[client]
toolbarMode = "viewer"
```

#### 4. Run as a Background Service (systemd)
To ensure the app starts automatically when the server boots and runs reliably in the background, set up a `systemd` service.

Create the service file:
```bash
sudo nano /etc/systemd/system/timetable.service
```

Paste the following configuration:
```ini
[Unit]
Description=TESSERA Streamlit Timetabling Application
After=network.target

[Service]
User=www-data
WorkingDirectory=/var/www/timetable-app
ExecStart=/var/www/timetable-app/venv/bin/streamlit run app.py
Restart=always

[Install]
WantedBy=multi-user.target
```
*(Note: Ensure that the database file `timetabling.db` is writable by the specified `User` e.g. `chown -R www-data:www-data /var/www/timetable-app` if running as `www-data`)*

Enable and start the service:
```bash
sudo systemctl daemon-reload
sudo systemctl enable timetable.service
sudo systemctl start timetable.service

# Verify the status
sudo systemctl status timetable.service
```

---

### B. Deploying on a Windows Server

#### 1. Copy Files
Extract `TimeTable_App_Deliverable.zip` into a directory on the server (e.g., `C:\TimeTable_App`).

#### 2. Install Python & Dependencies
1. Download and install **Python 3.10+** (ensure "Add Python to PATH" is checked during installation).
2. Open PowerShell as Administrator, navigate to the folder, and install the libraries:
   ```powershell
   cd C:\TimeTable_App
   pip install -r requirements.txt
   ```

#### 3. Configure Streamlit
Create or verify that `C:\TimeTable_App\.streamlit\config.toml` looks like this:
```toml
[server]
headless = true
address = "0.0.0.0"
port = 8501

[client]
toolbarMode = "viewer"
```

#### 4. Run in the Background as a Windows Service
To run Streamlit in the background without needing a user to stay logged in with a visible console window, you can use **NSSM (Non-Sucking Service Manager)**:

1. Download NSSM from [nssm.cc](https://nssm.cc/) and copy the executable to your server.
2. In PowerShell (as Administrator), run:
   ```powershell
   nssm install TimeTableApp
   ```
3. A GUI window will pop up. Configure the fields as follows:
   * **Path**: Select the path to Python (`C:\Users\<User>\AppData\Local\Programs\Python\Python310\python.exe` or wherever Python is installed).
   * **Startup directory**: `C:\TimeTable_App`
   * **Arguments**: `-m streamlit run app.py`
4. Click **Install service**.
5. Start the service:
   ```powershell
   Start-Service TimeTableApp
   ```

Alternatively, you can set up a basic startup script using **Windows Task Scheduler** to run `Run_TimeTable_App.bat` at system boot.

---

## 3. Firewall Configuration

For other computers in the department to access the app, the server's firewall must allow incoming connections on port `8501`.

### On Linux (UFW):
```bash
sudo ufw allow 8501/tcp
sudo ufw reload
```

### On Windows Server (PowerShell as Administrator):
```powershell
New-NetFirewallRule -DisplayName "Allow Streamlit 8501" -Direction Inbound -LocalPort 8501 -Protocol TCP -Action Allow
```

---

## 4. Accessing the Application

Once the service is running and the firewall is open, testers can open any web browser (Chrome, Edge, Firefox) and navigate to:
```
http://<server-ip-or-hostname>:8501
```
*(e.g., `http://192.168.1.50:8501`)*

Since the app has built-in user authentication, the testers will see the TESSERA login/signup portal and can register their accounts directly.

---

## 5. Database Considerations

* **Database File:** SQLite stores data in a local file (`timetabling.db`).
* **Preserving Tester Data:** Since sqlite writes changes directly to this file on the server, ensure you do not overwrite the server's `timetabling.db` file when deploying software updates in the future, as this will erase testing accounts and inputs.
* **Permissions:** Make sure the system user running the process (e.g. `www-data` on Linux, or the executing Windows service user) has write permissions to both the `timetabling.db` file and the root application directory (SQLite needs to write temp journals in the directory containing the `.db` file).
