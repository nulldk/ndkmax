import httpx
import asyncio
from urllib.parse import urljoin 
from utils.logger import setup_logger

logger = setup_logger(__name__)

def _is_url(line):
    return line and not line.startswith("#") and len(line.strip()) > 0

def _cpu_bound_rewrite(content, base_url):
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
                    
                    new_uri = absolute_url
                    
                    line = line[:start_idx] + new_uri + line[end_idx:]
                    rewrite_count += 1
            except Exception:
                pass
            rewritten_lines.append(line)

        elif _is_url(line):
            absolute_url = urljoin(base_url, line)
            rewritten_lines.append(absolute_url)
            rewrite_count += 1
        
        else:
            rewritten_lines.append(line)
    
    return "\n".join(rewritten_lines), rewrite_count

async def fetch_and_rewrite_manifest(client: httpx.AsyncClient, target_url: str):
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept-Encoding": "gzip, deflate"
        }
        
        logger.info(f"[FETCH] Downloading Master: {target_url[:60]}...")
        response = await client.get(target_url, headers=headers)
        
        if response.status_code != 200:
            return None, response.status_code, None

        content_type = response.headers.get("content-type", "application/vnd.apple.mpegurl")
        base_url = str(response.url)
        
        final_content, count = await asyncio.to_thread(_cpu_bound_rewrite, response.text, base_url)
        return final_content, 200, content_type

    except Exception as e:
        logger.error(f"[CRITICAL] Proxy error: {e}")
        return None, 500, None

def filter_manifest_by_quality(content: str, target_bandwidth: int):
    lines = content.splitlines()
    filtered_lines = []
    
    if lines and lines[0].startswith("#EXTM3U"):
        filtered_lines.append(lines[0])
        
    for i, line in enumerate(lines):
        line = line.strip()
        
        if line.startswith("#EXT-X-MEDIA") or line.startswith("#EXT-X-VERSION") or line.startswith("#EXT-X-INDEPENDENT"):
            filtered_lines.append(line)
            continue
            
        if line.startswith("#EXT-X-STREAM-INF"):
            if f"BANDWIDTH={target_bandwidth}" in line:
                filtered_lines.append(line)
                if i + 1 < len(lines):
                    filtered_lines.append(lines[i+1])
    
    return "\n".join(filtered_lines)
