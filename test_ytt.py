from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api.proxies import GenericProxyConfig
pc = GenericProxyConfig(
    http_url='socks5h://host.docker.internal:40000',
    https_url='socks5h://host.docker.internal:40000',
)
api = YouTubeTranscriptApi(proxy_config=pc)
r = api.fetch('fsI0NkuZnCM', languages=['en','te'])
print('Segs:', len(r.snippets))
print('Lang:', r.language_code)
print('First:', r.snippets[0].text[:80], '@', r.snippets[0].start)
