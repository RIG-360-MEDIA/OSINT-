"""Replace the personal cookies on Trijya with the burner cookies and restart."""
import time

import paramiko

HOST, USER, PWD = "100.96.25.59", "sshuser", "1234"
PY = r"C:\Users\sshuser\AppData\Local\Programs\Python\Python311\python.exe"
BURNER = r"D:\www.youtube.com_cookies (2).txt"

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST, username=USER, password=PWD, timeout=30)


def run(cmd, t=60):
    _i, o, e = c.exec_command(cmd, timeout=t)
    return o.read().decode(errors="replace"), e.read().decode(errors="replace")


# overwrite the cookies file with the burner (same path the relay already uses)
sftp = c.open_sftp()
sftp.put(BURNER, "C:/Users/sshuser/yt-relay/cookies.txt")
sftp.close()
print("burner cookies uploaded (personal overwritten)")

run("taskkill /F /IM python.exe")
time.sleep(2)
run(r"schtasks /run /tn YTRelay")
time.sleep(9)

hc = (
    "import urllib.request,json\n"
    "try:\n"
    "    d=json.load(urllib.request.urlopen('http://127.0.0.1:8888/health',timeout=8))\n"
    "    print('HEALTH engine=%s authed=%s circuit=%s' % (d.get('engine'),d.get('authenticated'),d.get('circuit')))\n"
    "except Exception as e:\n"
    "    print('HEALTH err=%s' % type(e).__name__)\n"
)
sftp = c.open_sftp()
with sftp.open("C:/Users/sshuser/yt-relay/_hc.py", "w") as f:
    f.write(hc)
sftp.close()
out, _ = run(f'"{PY}" C:/Users/sshuser/yt-relay/_hc.py')
print(out.strip())
c.close()
