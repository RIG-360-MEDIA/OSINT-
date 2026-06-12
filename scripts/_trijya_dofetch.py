"""Call the relay's _do_fetch directly on Trijya to capture the real exception."""
import paramiko

HOST, USER, PWD = "100.96.25.59", "sshuser", "1234"
PY = r"C:\Users\sshuser\AppData\Local\Programs\Python\Python311\python.exe"

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST, username=USER, password=PWD, timeout=30)

test = r'''
import os, sys, traceback
os.environ["YT_COOKIES"] = r"C:\Users\sshuser\yt-relay\cookies.txt"
sys.path.insert(0, r"C:\Users\sshuser\yt-relay")
import transcript_relay as r
print("COOKIE_FILE", r.COOKIE_FILE, "exists", os.path.exists(r.COOKIE_FILE))
try:
    res = r._do_fetch("dQw4w9WgXcQ")
    print("RESULT ok=%s reason=%s segs=%s" % (res.get("ok"), res.get("reason"), len(res.get("segments", [])) if res.get("ok") else 0))
except Exception:
    traceback.print_exc()
'''
sftp = c.open_sftp()
with sftp.open("C:/Users/sshuser/yt-relay/_df.py", "w") as f:
    f.write(test)
sftp.close()
_i, o, e = c.exec_command(f'"{PY}" C:/Users/sshuser/yt-relay/_df.py', timeout=120)
print(o.read().decode(errors="replace").strip())
err = e.read().decode(errors="replace").strip()
if err:
    print("STDERR:", err[-400:])
c.close()
