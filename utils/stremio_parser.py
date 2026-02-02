import re
from urllib.parse import quote
from utils.logger import setup_logger
from config import ADDON_URL

logger = setup_logger(__name__)

def get_emoji(lang_code):
    lang_code = lang_code.lower().strip()
    mapping = {
        "en": "🇬🇧", "eng": "🇬🇧", "english": "🇬🇧",
        "es": "🇪🇸", "spa": "🇪🇸", "spanish": "🇪🇸", "castellano": "🇪🇸",
        "lat": "🇲🇽", "mx": "🇲🇽", "latino": "🇲🇽", "et": "🇲🇽",
        "jp": "🇯🇵", "jpn": "🇯🇵",
        "fr": "🇫🇷", "fra": "🇫🇷",
        "it": "🇮🇹", "ita": "🇮🇹",
        "de": "🇩🇪", "deu": "🇩🇪",
        "pt": "🇵🇹", "por": "🇵🇹",
        "ru": "🇷🇺", "rus": "🇷🇺",
        "multi": "🌎"
    }
    return mapping.get(lang_code, "")

def parse_manifest_to_qualities(master_url: str, content_title: str, duration: float, content: str):
    try:
        lines = content.split('\n')
        streams_found = []
        
        audio_langs = re.findall(r'TYPE=AUDIO.*LANGUAGE="?(\w+)"?', content)
        unique_langs = list(set(audio_langs))
        emojis = [get_emoji(l) for l in unique_langs if get_emoji(l)]
        flags_str = " / ".join(emojis) if emojis else "🇪🇸"

        base_addon_url = str(ADDON_URL).rstrip('/')

        for i, line in enumerate(lines):
            line = line.strip()
            
            if line.startswith("#EXT-X-STREAM-INF"):
                res_match = re.search(r'RESOLUTION=\d+x(\d+)', line)
                bw_match = re.search(r'BANDWIDTH=(\d+)', line)
                
                height = int(res_match.group(1)) if res_match else 0
                bandwidth = int(bw_match.group(1)) if bw_match else 0
                
                if bandwidth > 0:
                    quality_label = f"{height}p" if height > 0 else "Auto"
                    
                    size_info = ""
                    if duration > 0:
                        size_bits = bandwidth * (duration * 60)
                        size_gb = size_bits / 8 / (1024 ** 3)
                        size_info = f"💾 {size_gb:.2f}GB "

                    spacer = "\u2800" * 2
                    name_formatted = f"NDKMAX{spacer} {quality_label}"
                    title_formatted = f"{content_title} - {quality_label}\n{size_info}\n{flags_str}"
                    
                    generated_url = f"{base_addon_url}/proxy/filter?url={quote(master_url)}&bw={bandwidth}"

                    stream_entry = {
                        "name": name_formatted,
                        "title": title_formatted,
                        "url": generated_url,
                        "behaviorHints": {
                            "notWebReady": False,
                            "bingeGroup": f"NDK-MAX-{quality_label}",
                        }
                    }
                    streams_found.append(stream_entry)

        if not streams_found:
             return [{
                "name": "NDKMAX Default",
                "title": f"{content_title}\nUnknown Quality {flags_str}",
                "url": master_url
            }]

        def get_quality_key(x):
            try:
                if 'p' in x['name']:
                    quality_str = x['name'].split()[-1].replace('p', '')
                    return int(quality_str) if quality_str.isdigit() else 0
                return 0
            except (ValueError, IndexError):
                return 0
        
        streams_found.sort(key=get_quality_key, reverse=True)
        return streams_found

    except Exception as e:
        logger.error(f"Error parseando HLS streams: {e}")
        return []
