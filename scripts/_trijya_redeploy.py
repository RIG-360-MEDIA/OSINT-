"""Push updated relay to Trijya, restart, and live-test a real fetch."""
import time

import paramiko

HOST, USER, PWD = "100.96.25.59", "sshuser", "1234"
PY = r"C:\Users\sshuser\AppData\Local\Programs\Python\Python311\python.exe"

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST, username=USER, password=PWD, timeout=30)


def run(cmd, t=180):
    _i, o, e = c.exec_command(cmd, timeout=t)
    return o.read().decode(errors="replace"), e.read().decode(errors="replace")


sftp = c.open_sftp()
sftp.put("backend/collectors/youtube_v2/transcript_relay.py",
         "C:/Users/sshuser/yt-relay/transcript_relay.py")
sftp.close()
print("uploaded new relay")

run("taskkill /F /IM python.exe")
time.sleep(2)
run(r"schtasks /run /tn YTRelay")
time.sleep(9)

# live fetch of a video known to have captions, THROUGH the relay (Trijya's IP)
hc = (
    "import urllib.request, json\n"
    "try:\n"
    "    d = json.load(urllib.request.urlopen('http://127.0.0.1:8888/fetch/dQw4w9WgXcQ', timeout=90))\n"
    "    print('FETCH ok=%s reason=%s lang=%s segs=%s' % (d.get('ok'), d.get('reason'), d.get('language'), len(d.get('segments', [])) if d.get('ok') else 0))\n"
    "except Exception as e:\n"
    "    print('FETCH err=%s %s' % (type(e).__name__, str(e)[:80]))\n"
)
sftp = c.open_sftp()
with sftp.open("C:/Users/sshuser/yt-relay/_fc.py", "w") as f:
    f.write(hc)
sftp.close()
out, _ = run(f'"{PY}" C:/Users/sshuser/yt-relay/_fc.py', t=120)
print(out.strip())
c.close()
