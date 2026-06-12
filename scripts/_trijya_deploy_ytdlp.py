"""Deploy the yt-dlp+cookies relay to Trijya (clean residential IP) and test it
end-to-end on that IP. Idempotent: re-run safely."""
import time

import paramiko

HOST, USER, PWD = "100.96.25.59", "sshuser", "1234"
REMOTE_DIR = "C:/Users/sshuser/yt-relay"
PY = r"C:\Users\sshuser\AppData\Local\Programs\Python\Python311\python.exe"
LOCAL_RELAY = "backend/collectors/youtube_v2/transcript_relay.py"
LOCAL_COOKIES = r"D:\cookies (5).txt"

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST, username=USER, password=PWD, timeout=30)


def run(cmd, t=300):
    _i, o, e = c.exec_command(cmd, timeout=t)
    return o.read().decode(errors="replace"), e.read().decode(errors="replace")


sftp = c.open_sftp()
try:
    sftp.mkdir(REMOTE_DIR)
except Exception:
    pass
sftp.put(LOCAL_RELAY, REMOTE_DIR + "/transcript_relay.py")
sftp.put(LOCAL_COOKIES, REMOTE_DIR + "/cookies.txt")
print("UPLOADED relay + cookies")

bat = (
    "@echo off\r\n"
    "cd /d C:\\Users\\sshuser\\yt-relay\r\n"
    "set YT_COOKIES=C:\\Users\\sshuser\\yt-relay\\cookies.txt\r\n"
    "set RELAY_PORT=8888\r\n"
    '"' + PY + '" transcript_relay.py\r\n'
)
with sftp.open(REMOTE_DIR + "/run_relay.bat", "w") as f:
    f.write(bat)

ht = (
    "import urllib.request, json\n"
    "def g(u):\n"
    "    return json.load(urllib.request.urlopen(u, timeout=70))\n"
    "h = g('http://127.0.0.1:8888/health')\n"
    "print('HEALTH engine=%s authed=%s circuit=%s' % (h.get('engine'), h.get('authenticated'), h.get('circuit')))\n"
    "try:\n"
    "    d = g('http://127.0.0.1:8888/fetch/dQw4w9WgXcQ')\n"
    "    print('FETCH ok=%s reason=%s segs=%s' % (d.get('ok'), d.get('reason'), len(d.get('segments', [])) if d.get('ok') else 0))\n"
    "except Exception as e:\n"
    "    print('FETCH err=%s %s' % (type(e).__name__, str(e)[:80]))\n"
)
with sftp.open(REMOTE_DIR + "/_ht.py", "w") as f:
    f.write(ht)
sftp.close()
print("WROTE run_relay.bat + _ht.py")

out, err = run(f'"{PY}" -m pip install -U yt-dlp flask -q')
print("PIP done", (out + err).strip()[-160:])

run("taskkill /F /IM python.exe")
time.sleep(2)
run(r'schtasks /create /tn YTRelay /tr "C:\Users\sshuser\yt-relay\run_relay.bat" /sc onlogon /rl highest /f')
out, err = run(r"schtasks /run /tn YTRelay")
print("TASK:", out.strip() or err.strip())
time.sleep(10)

out, err = run(f'"{PY}" {REMOTE_DIR}/_ht.py', t=120)
print(out.strip())
if err.strip():
    print("ERR:", err.strip()[-200:])
c.close()
