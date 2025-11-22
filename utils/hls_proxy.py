import httpx
import re
import time
import asyncio
from urllib.parse import urljoin, quote
from utils.logger import setup_logger

logger = setup_logger(__name__)

# --- CONFIGURACIÓN ---
manifest_cache = {}
CACHE_TTL = 0
MAX_CACHE_SIZE = 1000

# --- REGEX ---
RE_BANDWIDTH = re.compile(r'BANDWIDTH=(\d+)')
RE_ATTRIBUTES = re.compile(r'([A-Z0-9-]+)=(?:"([^"]*)"|([^,]+))')
RE_URI_QUOTED = re.compile(r'(URI=")([^"]+)(")')

def parse_bandwidth(line):
    match = RE_BANDWIDTH.search(line)
    return int(match.group(1)) if match else 0

def extract_attributes(line):
    attrs = {}
    for match in RE_ATTRIBUTES.finditer(line):
        key = match.group(1)
        val = match.group(2) if match.group(2) is not None else match.group(3)
        attrs[key] = val
    return attrs

def get_readable_lang_and_code(code_raw, name_raw):
    code = code_raw.lower().strip()
    name = name_raw.lower().strip()
    
    if code in ["et", "est", "es-419", "es-mx", "mx", "lat"] or "eesti" in name or "latino" in name or "latin" in name:
        return "Latino", "es-MX"
    elif code in ["es-es", "esp", "spa", "es"] or "castellano" in name or "spain" in name or "español" in name:
        return "Castellano", "es-ES"
    elif code in ["eng", "en", "ing", "en-us", "en-gb"] or "english" in name:
        return "English", "en"
    elif code in ["jpn", "ja"] or "japanese" in name:
        return "Japanese", "ja"
    elif code in ["ita", "it"] or "italian" in name:
        return "Italiano", "it"
    elif code in ["fra", "fr"] or "french" in name:
        return "Français", "fr"
    elif code in ["deu", "de", "ger"] or "german" in name:
        return "Deutsch", "de"
    return None, code_raw

def process_media_tag(line, base_url, proxy_base_url):
    """
    Modifica la línea original usando sustitución de texto para NO romper 
    la estructura de GROUP-ID ni los flags de sincronización.
    """
    if not line.startswith("#EXT-X-MEDIA:TYPE=AUDIO"):
        return line

    try:
        attrs = extract_attributes(line)
        raw_lang = attrs.get("LANGUAGE", "und")
        original_name = attrs.get("NAME", "Unknown")
        clean_name = original_name.replace('"', '')
        original_uri = attrs.get("URI", None)
        
        if clean_name.isdigit():
            clean_name = f"Track {clean_name}"

        readable_lang, clean_code = get_readable_lang_and_code(raw_lang, clean_name)
        
        base_name = readable_lang if readable_lang else clean_name
        details = []
        channels = attrs.get("CHANNELS", "").replace('"', '')
        
        if channels:
            if channels == "6" or "5.1" in channels:
                details.append("5.1")
            elif channels == "2":
                details.append("2.0")
            else:
                details.append(f"{channels}ch")

        haystack = (clean_name + " " + (original_uri if original_uri else "")).lower()
        if "ac3" in haystack or "dd" in haystack:
            details.append("HQ")

        if details:
            final_name_str = f"{base_name} ({' '.join(details)})"
        else:
            final_name_str = base_name

        line = re.sub(
            r'NAME=(?:"[^"]*"|[^,]+)',
            f'NAME="{final_name_str}"',
            line,
            count=1
        )

        if clean_code:
            line = re.sub(
                r'LANGUAGE=(?:"[^"]*"|[^,]+)',
                f'LANGUAGE="{clean_code}"',
                line,
                count=1
            )

        if original_uri:
            clean_uri = original_uri.replace('"', '')
            absolute_url = urljoin(base_url, clean_uri)
            
            if ".m3u8" in absolute_url:
                encoded_target = quote(absolute_url, safe=':/?&=')
                new_uri = f"{proxy_base_url}/proxy/manifest?url={encoded_target}"
                
                line = re.sub(
                    r'URI=(?:"[^"]*"|[^,]+)',
                    f'URI="{new_uri}"',
                    line,
                    count=1
                )
            else:
                line = re.sub(
                    r'URI=(?:"[^"]*"|[^,]+)',
                    f'URI="{absolute_url}"',
                    line,
                    count=1
                )

        return line

    except Exception as e:
        logger.error(f"Error processing media tag safely: {e}")
        return line

def _cpu_bound_rewrite(content, base_url, proxy_base_url):
    lines = content.splitlines()
    
    if "#EXT-X-STREAM-INF" in content:
        header_lines = []
        streams = []
        audio_lines = []
        current_stream = None

        for line in lines:
            line = line.strip()
            if not line:
                continue

            if line.startswith("#EXT-X-MEDIA:TYPE=AUDIO"):
                processed_line = process_media_tag(line, base_url, proxy_base_url)
                audio_lines.append(processed_line)
            elif line.startswith("#EXTM3U") or line.startswith("#EXT-X-VERSION") or line.startswith("#EXT-X-INDEPENDENT"):
                header_lines.append(line)
            elif line.startswith("#EXT-X-STREAM-INF"):
                current_stream = {"meta": line, "url": None}
            elif current_stream and not line.startswith("#"):
                current_stream["url"] = line
                current_stream["bandwidth"] = parse_bandwidth(current_stream["meta"])
                streams.append(current_stream)
                current_stream = None
            else:
                if not current_stream and not line.startswith("#EXT-X-MEDIA"):
                    header_lines.append(line)

        streams.sort(key=lambda x: x["bandwidth"], reverse=True)
        
        final_lines = header_lines[:]
        final_lines.extend(audio_lines)

        for s in streams:
            absolute_url = urljoin(base_url, s["url"])
            encoded_target = quote(absolute_url, safe=':/?&=')
            proxied_url = f"{proxy_base_url}/proxy/manifest?url={encoded_target}"
            final_lines.append(s["meta"])
            final_lines.append(proxied_url)
        
        return "\n".join(final_lines)

    else:
        rewritten_lines = []
        for line in lines:
            line = line.strip()
            if not line:
                rewritten_lines.append(line)
                continue

            if line.startswith("#"):
                if line.startswith("#EXT-X-MEDIA:TYPE=AUDIO"):
                    line = process_media_tag(line, base_url, proxy_base_url)
                elif "URI=" in line:
                    def replace_uri(match):
                        prefix, r_url, suffix = match.groups()
                        abs_url = urljoin(base_url, r_url)
                        if ".m3u8" in abs_url:
                            enc = quote(abs_url, safe=':/?&=')
                            return f"{prefix}{proxy_base_url}/proxy/manifest?url={enc}{suffix}"
                        return f"{prefix}{abs_url}{suffix}"
                    line = RE_URI_QUOTED.sub(replace_uri, line)
                rewritten_lines.append(line)
                continue

            absolute_url = urljoin(base_url, line)
            if line.endswith(".m3u8"):
                encoded_target = quote(absolute_url, safe=':/?&=')
                proxied_url = f"{proxy_base_url}/proxy/manifest?url={encoded_target}"
                rewritten_lines.append(proxied_url)
            else:
                rewritten_lines.append(absolute_url)

        return "\n".join(rewritten_lines)

async def fetch_and_rewrite_manifest(client: httpx.AsyncClient, target_url: str, proxy_base_url: str):
    now = time.time()
    if target_url in manifest_cache:
        cached_data = manifest_cache[target_url]
        if now - cached_data['timestamp'] < CACHE_TTL:
            return cached_data['content'], 200, cached_data.get('content_type')
        else:
            del manifest_cache[target_url]
    if len(manifest_cache) > MAX_CACHE_SIZE:
        keys_to_del = list(manifest_cache.keys())[:int(MAX_CACHE_SIZE * 0.3)]
        for k in keys_to_del:
            del manifest_cache[k]
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Accept-Encoding": "gzip, deflate"
        }
        response = await client.get(target_url, headers=headers)
        if response.status_code != 200:
            return None, response.status_code, None
        content_type = response.headers.get("content-type", "")
        is_m3u8 = ".m3u8" in str(response.url.path) or "application/vnd.apple.mpegurl" in content_type or "application/x-mpegURL" in content_type
        if not is_m3u8:
            body = response.content
            manifest_cache[target_url] = {
                'content': body,
                'timestamp': now,
                'content_type': content_type
            }
            return body, 200, content_type
        content = response.text
        base_url = str(response.url)
        final_content = await asyncio.to_thread(_cpu_bound_rewrite, content, base_url, proxy_base_url)
        manifest_cache[target_url] = {
            'content': final_content,
            'timestamp': now,
            'content_type': "application/vnd.apple.mpegurl"
        }
        return final_content, 200, "application/vnd.apple.mpegurl"
    except Exception as e:
        logger.error(f"PROXY_ERROR: {e}")
        return None, 500, None
