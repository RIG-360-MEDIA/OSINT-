"""ASCII-safe read of Trijya relay.log + listen state + health."""
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


out, _ = run("type C:\\Users\\sshuser\\yt-relay\\relay.log")
print("=== relay.log (tail) ===")
print(safe(out.strip()[-900:]))

out, _ = run('netstat -ano | findstr :8888')
print("=== listening :8888 ===")
print(safe(out.strip()) or "(nothing)")
c.close()
