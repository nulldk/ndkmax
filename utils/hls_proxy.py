import httpx
import time
import asyncio
from urllib.parse import urljoin, quote
from utils.logger import setup_logger

logger = setup_logger(__name__)

manifest_cache = {}
CACHE_TTL = 120
MAX_CACHE_SIZE = 1000

def _is_url(line):
    return line and not line.startswith("#") and len(line.strip()) > 0

def _is_playlist(url):
    return ".m3u8" in url or "mpegurl" in url

def _cpu_bound_rewrite(content, base_url, proxy_base_url):
    lines = content.splitlines()
    rewritten_lines = []
    rewrite_count = 0

    for line in lines:
        line = line.strip()
        if not line:
            rewritten_lines.append(line)
            continue

        if line.startswith("#") and 'URI="' in line:
            try:
                start_idx = line.find('URI="') + 5
                end_idx = line.find('"', start_idx)
                if start_idx > 4 and end_idx > start_idx:
                    relative_uri = line[start_idx:end_idx]
                    absolute_url = urljoin(base_url, relative_uri)
                    
                    if _is_playlist(absolute_url):
                        encoded = quote(absolute_url, safe='')
                        new_uri = f"{proxy_base_url}/proxy/manifest?url={encoded}"
                    else:
                        new_uri = absolute_url
                    
                    line = line[:start_idx] + new_uri + line[end_idx:]
                    rewrite_count += 1
            except Exception:
                pass
            rewritten_lines.append(line)

        elif _is_url(line):
            absolute_url = urljoin(base_url, line)
            
            if _is_playlist(absolute_url):
                encoded = quote(absolute_url, safe='')
                proxied_url = f"{proxy_base_url}/proxy/manifest?url={encoded}"
                rewritten_lines.append(proxied_url)
            else:
                rewritten_lines.append(absolute_url)
            rewrite_count += 1
        
        else:
            rewritten_lines.append(line)

    return "\n".join(rewritten_lines), rewrite_count

async def fetch_and_rewrite_manifest(client: httpx.AsyncClient, target_url: str, proxy_base_url: str):
    now = time.time()
    
    if target_url in manifest_cache:
        cached = manifest_cache[target_url]
        if now - cached['timestamp'] < CACHE_TTL:
            logger.info(f"[CACHE HIT] {target_url[:60]}...")
            return cached['content'], 200, cached['content_type']
        else:
            del manifest_cache[target_url]
    
    if len(manifest_cache) > MAX_CACHE_SIZE:
        keys = list(manifest_cache.keys())[:int(MAX_CACHE_SIZE * 0.2)]
        for k in keys: del manifest_cache[k]

    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Accept-Encoding": "gzip, deflate"
        }
        
        logger.info(f"[FETCH] Downloading: {target_url[:60]}...")
        response = await client.get(target_url, headers=headers)
        
        if response.status_code != 200:
            logger.error(f"[ERROR] Status {response.status_code} for {target_url}")
            return None, response.status_code, None

        content_type = response.headers.get("content-type", "application/vnd.apple.mpegurl")
        
        if "#EXTM3U" not in response.text[:20]:
             logger.warning("[WARN] Not a valid M3U8, passing through raw content.")
             return response.content, 200, content_type

        base_url = str(response.url)
        final_content, count = await asyncio.to_thread(_cpu_bound_rewrite, response.text, base_url, proxy_base_url)
        
        logger.info(f"[REWRITE] Processed {count} URLs. Base: {base_url[:40]}...")

        manifest_cache[target_url] = {
            'content': final_content,
            'timestamp': now,
            'content_type': content_type
        }

        return final_content, 200, content_type

    except Exception as e:
        logger.error(f"[CRITICAL] Proxy error: {e}")
        return None, 500, None
