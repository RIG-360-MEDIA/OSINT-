"""Clean relaunch of the Trijya relay as a detached SYSTEM scheduled task so it
survives SSH disconnect. Confirms the NEW yt-dlp relay is the one running via
the /health engine field."""
import time

import paramiko

HOST, USER, PWD = "100.96.25.59", "sshuser", "1234"
PY = r"C:\Users\sshuser\AppData\Local\Programs\Python\Python311\python.exe"

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST, username=USER, password=PWD, timeout=30)


def run(cmd, t=120):
    _i, o, e = c.exec_command(cmd, timeout=t)
    return o.read().decode(errors="replace"), e.read().decode(errors="replace")


def safe(s):
    return s.encode("ascii", "replace").decode()


# 1. hard stop everything
run("taskkill /F /IM python.exe")
time.sleep(2)

# 2. recreate the task to run as SYSTEM (detaches from this SSH session) at boot
run(r'schtasks /delete /tn YTRelay /f')
out, err = run(
    r'schtasks /create /tn YTRelay /tr "C:\Users\sshuser\yt-relay\run_relay.bat" '
    r'/sc onstart /ru SYSTEM /rl highest /f'
)
print("CREATE:", safe((out + err).strip()))

out, err = run(r"schtasks /run /tn YTRelay")
print("RUN:", safe((out + err).strip()))
time.sleep(10)

# 3. listening?
out, _ = run('netstat -ano | findstr :8888')
print("LISTEN:", safe(out.strip()) or "(nothing)")

# 4. which relay is it? /health engine field proves new vs old
hc = (
    "import urllib.request,json\n"
    "try:\n"
    "    d=json.load(urllib.request.urlopen('http://127.0.0.1:8888/health',timeout=8))\n"
    "    print('HEALTH engine=%s authed=%s circuit=%s cb=%s' % (d.get('engine'),d.get('authenticated'),d.get('circuit'),d.get('cb_failures')))\n"
    "except Exception as e:\n"
    "    print('HEALTH err=%s' % (type(e).__name__,))\n"
)
sftp = c.open_sftp()
with sftp.open("C:/Users/sshuser/yt-relay/_hc.py", "w") as f:
    f.write(hc)
sftp.close()
out, _ = run(f'"{PY}" C:/Users/sshuser/yt-relay/_hc.py')
print(safe(out.strip()))
c.close()
