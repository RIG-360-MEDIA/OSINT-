import requests
p = {'http':'socks5h://host.docker.internal:40000','https':'socks5h://host.docker.internal:40000'}
r = requests.get('https://www.youtube.com/watch?v=fsI0NkuZnCM', proxies=p, timeout=20)
print('status:', r.status_code, 'len:', len(r.text))
