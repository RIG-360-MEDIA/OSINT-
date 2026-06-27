"""Diagnose why the Trijya relay didn't bind :8888 — capture startup output."""
import time

import paramiko

HOST, USER, PWD = "100.96.25.59", "sshuser", "1234"
REMOTE_DIR = "C:/Users/sshuser/yt-relay"
PY = r"C:\Users\sshuser\AppData\Local\Programs\Python\Python311\python.exe"

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST, username=USER, password=PWD, timeout=30)


def run(cmd, t=120):
    _i, o, e = c.exec_command(cmd, timeout=t)
    return o.read().decode(errors="replace"), e.read().decode(errors="replace")


# 1. deps present?
out, err = run(f'"{PY}" -c "import flask, yt_dlp; print(\'IMPORTS OK yt_dlp\', yt_dlp.version.__version__)"')
print("DEPS:", (out + err).strip()[-200:])

# 2. rewrite bat to log startup output
sftp = c.open_sftp()
bat = (
    "@echo off\r\n"
    "cd /d C:\\Users\\sshuser\\yt-relay\r\n"
    "set YT_COOKIES=C:\\Users\\sshuser\\yt-relay\\cookies.txt\r\n"
    "set RELAY_PORT=8888\r\n"
    '"' + PY + '" transcript_relay.py > C:\\Users\\sshuser\\yt-relay\\relay.log 2>&1\r\n'
)
with sftp.open(REMOTE_DIR + "/run_relay.bat", "w") as f:
    f.write(bat)
sftp.close()

# 3. restart via task, give it time, read the log
run("taskkill /F /IM python.exe")
time.sleep(2)
run(r"schtasks /run /tn YTRelay")
time.sleep(9)

out, _ = run("type C:\\Users\\sshuser\\yt-relay\\relay.log")
print("=== relay.log ===")
print(out.strip()[-800:])

# 4. is anything listening now?
out, _ = run('netstat -ano | findstr :8888')
print("=== netstat :8888 ===")
print(out.strip() or "(nothing listening)")
c.close()
