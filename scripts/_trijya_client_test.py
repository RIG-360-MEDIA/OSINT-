"""Find which yt-dlp player_client yields captions on Trijya's newer yt-dlp."""
import paramiko

HOST, USER, PWD = "100.96.25.59", "sshuser", "1234"
PY = r"C:\Users\sshuser\AppData\Local\Programs\Python\Python311\python.exe"

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST, username=USER, password=PWD, timeout=30)

test = r'''
import os, yt_dlp
from yt_dlp import YoutubeDL
ck = r"C:\Users\sshuser\yt-relay\cookies.txt"
print("ytdlp", yt_dlp.version.__version__, "cookie_bytes", os.path.getsize(ck) if os.path.exists(ck) else "MISSING")
for client in (["web"], ["tv"], ["mweb"], ["android"], ["web_safari"]):
    opts = {"skip_download": True, "quiet": True, "no_warnings": True,
            "ignore_no_formats_error": True, "cookiefile": ck,
            "extractor_args": {"youtube": {"player_client": client}}}
    try:
        with YoutubeDL(opts) as y:
            info = y.extract_info("https://www.youtube.com/watch?v=dQw4w9WgXcQ", download=False, process=False)
        print(client[0], "auto", len(info.get("automatic_captions") or {}), "manual", len(info.get("subtitles") or {}))
    except Exception as e:
        print(client[0], "ERR", type(e).__name__, str(e)[:60])
'''
sftp = c.open_sftp()
with sftp.open("C:/Users/sshuser/yt-relay/_ct.py", "w") as f:
    f.write(test)
sftp.close()
_i, o, e = c.exec_command(f'"{PY}" C:/Users/sshuser/yt-relay/_ct.py', timeout=180)
print(o.read().decode(errors="replace").strip())
err = e.read().decode(errors="replace").strip()
if err:
    print("ERR:", err[-200:])
c.close()
