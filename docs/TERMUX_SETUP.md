# VECTOR Phone Node — Termux Setup Guide
### For someone who has never used Termux before

---

## What Is Termux?

Termux is a terminal app on Android. Think of it like Command Prompt or PowerShell, but on your phone. It lets you run Python scripts, install packages, and use your phone as a mini Linux computer.

You don't need to know Linux to follow this guide. Every command is written out exactly — just copy and paste.

---

## Part 1 — First Time in Termux

When you open Termux, you see a black screen with a `$` symbol. That's the prompt. You type commands after it and press Enter to run them.

```
~ $  ← you type here
```

**Useful Termux basics:**

| What you want | How to do it |
|--------------|-------------|
| Zoom in/out | Pinch the screen |
| Paste text | Long-press → Paste |
| Cancel a running command | Volume Down + C |
| See what folder you're in | Type `pwd` and press Enter |
| List files in current folder | Type `ls` and press Enter |
| Go to home folder | Type `cd ~` and press Enter |

The `~` symbol means your home folder. That's where we'll put everything.

---

## Part 2 — Before You Start (Do This on Legion First)

Open PowerShell on your Legion laptop and run:

```powershell
ipconfig | findstr "IPv4"
```

You'll see something like:
```
IPv4 Address. . . . . . . . : 192.168.1.5
```

**Write down that number.** This is your `LEGION_IP`. You'll need it later.

---

## Part 3 — Install Required Apps on Phone

You need two companion apps from **F-Droid** (not Play Store — Termux from Play Store is outdated):

1. **Termux:API** — lets the script read your battery and send notifications
2. **Termux:Boot** — lets the script auto-start when you restart your phone

**How to get F-Droid if you don't have it:**
- Go to `f-droid.org` in your phone's browser
- Download and install the F-Droid apk
- Open F-Droid → search "Termux API" → install
- Open F-Droid → search "Termux Boot" → install

---

## Part 4 — Set Up Termux (Run These Commands)

Open Termux on your phone. Type each command and press Enter. Wait for it to finish before typing the next one.

**Step 1 — Update package list:**
```bash
pkg update -y
```
This downloads the list of available software. May take a minute.

**Step 2 — Install required tools:**
```bash
pkg install -y python python-pip termux-api curl
```
This installs Python (the language VECTOR uses) and some tools.

**Step 3 — Install Python libraries:**
```bash
pip install httpx loguru
```
These are the libraries the VECTOR phone script needs.

**When all three commands finish, Termux is ready.**

---

## Part 5 — Get the Script onto Your Phone

You need to copy `ambient_server.py` from your Legion laptop to your phone.

**Method A — USB Cable (easiest)**

1. Connect your old phone to Legion with a USB cable
2. When the phone asks "Allow USB debugging?" → tap **Allow**
3. On Legion, open PowerShell in the VECTOR folder and run:

```powershell
adb devices
```

You should see your phone listed. If you do, run:

```powershell
adb push phone_node\ambient_server.py /sdcard/ambient_server.py
```

Then in Termux on the phone:
```bash
cp /sdcard/ambient_server.py ~/ambient_server.py
```

**Method B — Telegram (if you don't have a cable)**

1. On Legion, open Telegram and send yourself the file `phone_node\ambient_server.py`
2. On the phone, open Telegram, find the file, tap it → "Save to downloads"
3. In Termux:
```bash
cp /sdcard/Download/ambient_server.py ~/ambient_server.py
```

**Verify the file is there:**
```bash
ls ~
```
You should see `ambient_server.py` in the list.

---

## Part 6 — Create the Config File

This tells the script where your Legion laptop is.

In Termux, type this command **exactly** (replace `192.168.1.5` with YOUR Legion IP from Part 2):

```bash
mkdir -p ~/.vector
```

Then run this — it creates the config file:

```bash
cat > ~/.vector/phone_config.env << 'EOF'
VECTOR_BRAIN_URL=http://192.168.1.5:8000
VECTOR_API_KEY=
VECTOR_NODE_ID=phone-ambient
HEARTBEAT_INTERVAL_SEC=60
LOCAL_PORT=7700
EOF
```

> **Important:** Replace `192.168.1.5` with your actual Legion IP.
> Leave `VECTOR_API_KEY=` blank (empty) unless you set one in VECTOR's `.env` file.

**Verify the file was created:**
```bash
cat ~/.vector/phone_config.env
```
You should see the contents printed back.

---

## Part 7 — Run the Script

Make sure your phone and Legion are on the **same WiFi network**.

In Termux:
```bash
cd ~
python ambient_server.py
```

If everything is correct, you'll see:
```
[VECTOR][phone] Ambient server starting on 0.0.0.0:7700
[VECTOR][phone] Heartbeat loop started (interval=60s)
```

The script is now running. **Don't close Termux** — just leave it open in the background.

---

## Part 8 — Verify It Works (Test from Legion)

First, find your **phone's WiFi IP**:
- Phone → Settings → WiFi → tap the connected network name → look for "IP address"
- It looks like `192.168.1.x`

Then on Legion, open PowerShell and run:

```powershell
curl http://192.168.1.YOUR_PHONE_IP:7700/status
```

You should get a response like:
```json
{"node_id": "phone-ambient", "uptime_sec": 45.2, "battery_pct": 82, "hb_count": 1}
```

**Test that VECTOR can push a notification to your phone:**
```powershell
curl -X POST http://192.168.1.YOUR_PHONE_IP:7700/alert -H "Content-Type: application/json" -d "{\"title\":\"VECTOR\",\"content\":\"Phone node is online, sir.\"}"
```

A notification should appear on your phone.

---

## Part 9 — Connect It to VECTOR on Legion

With `run_vector.py` already running on Legion, open a **second** PowerShell window in the VECTOR folder and run:

```powershell
python phone_node/adb_bridge.py
```

This checks your phone's status every 60 seconds and stores the data in VECTOR's episodic memory. You'll see:
```
[VECTOR][adb_bridge] phone status: battery=82% uptime=120s
```

---

## Part 10 — Auto-Start (So It Restarts Automatically)

Right now if you close Termux or restart your phone, the script stops. These steps make it restart automatically.

**Step 1** — Create the auto-start script in Termux:
```bash
mkdir -p ~/.termux/boot
cat > ~/.termux/boot/vector_ambient.sh << 'EOF'
#!/data/data/com.termux/files/usr/bin/bash
cd ~
python ambient_server.py >> ~/.vector/ambient.log 2>&1 &
EOF
chmod +x ~/.termux/boot/vector_ambient.sh
```

**Step 2** — Open the **Termux:Boot** app on your phone once (just tap it). This activates it.

**Step 3** — Test it by restarting your phone. After it boots, wait 30 seconds, then check if the script is running by testing from Legion again (the `curl` from Part 8).

---

## Common Problems and Fixes

**"command not found: pkg"**
> Termux isn't properly installed. Uninstall it and re-download from F-Droid, not the Play Store.

**"No such file or directory: ambient_server.py"**
> The file didn't copy correctly. Go back to Part 5 and try again.

**curl from Legion returns "Connection refused"**
> - Make sure both devices are on the same WiFi
> - Make sure `python ambient_server.py` is still running in Termux (check the Termux window)
> - Check your phone's IP again — it may have changed

**"Battery status shows -1"**
> Termux:API app isn't installed or doesn't have permissions. Install it from F-Droid, then in Termux run: `termux-battery-status` — if it asks for permission, allow it.

**Notifications don't appear**
> Open the Termux:API app, grant notification permission. Also check your phone's notification settings for Termux.

**Script crashes immediately with an import error**
> Run `pip install httpx loguru` again in Termux.

---

## What Each File Does (For Reference)

| File | Where | What It Does |
|------|-------|-------------|
| `ambient_server.py` | Runs on phone | The main script. HTTP server on port 7700. Sends heartbeats to Legion, receives alerts. |
| `phone_config.env` | `~/.vector/` on phone | Your settings: Legion's IP, API key, timing |
| `adb_bridge.py` | Runs on Legion | Polls the phone every 60s, stores data in VECTOR's memory |
| `vector_ambient.sh` | `~/.termux/boot/` on phone | Auto-starts the script when Termux boots |

---

## Quick Reference — Commands You'll Use

| Task | Command (in Termux) |
|------|-------------------|
| Start the script | `python ~/ambient_server.py` |
| Check if it's running | `ps aux \| grep ambient` |
| View logs | `tail -f ~/.vector/ambient.log` |
| Stop the script | Press `Volume Down + C` in Termux |
| Edit the config | `nano ~/.vector/phone_config.env` (use arrow keys, Ctrl+X to save) |

---

## When You're Done

Your phone is now an ambient node for VECTOR:

- **Heartbeat every 60s** → VECTOR knows the phone is alive and sees battery level
- **VECTOR can push alerts** → notifications appear on your phone
- **Runs in background** → Termux stays open, phone stays connected over WiFi
- **Auto-restarts** → if your phone reboots, the script comes back automatically (after Termux:Boot is set up)

When the cloud brain is deployed later (`fly deploy`), just update `VECTOR_BRAIN_URL` in `~/.vector/phone_config.env` to the cloud URL and restart the script.
