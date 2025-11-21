import re
import httpx

from utils.logger import setup_logger
logger = setup_logger(__name__)

def get_emoji(lang_code):
    lang_code = lang_code.lower().strip()
    mapping = {
        "en": "🇬🇧", "eng": "🇬🇧", "english": "🇬🇧",
        "es": "🇪🇸", "spa": "🇪🇸", "spanish": "🇪🇸", "castellano": "🇪🇸",
        "lat": "🇲🇽", "mx": "🇲🇽", "latino": "🇲🇽",
        "jp": "🇯🇵", "jpn": "🇯🇵",
        "fr": "🇫🇷", "fra": "🇫🇷",
        "it": "🇮🇹", "ita": "🇮🇹",
        "de": "🇩🇪", "deu": "🇩🇪",
        "pt": "🇵🇹", "por": "🇵🇹",
        "ru": "🇷🇺", "rus": "🇷🇺",
        "multi": "🌎"
    }
    return mapping.get(lang_code, "")

async def parse_hls_to_stremio(client, url: str, content_title: str, duration: float = 0):
    try:
        r = await client.get(url)
        content = r.text
        lines = content.split('\n')
        max_height = 0
        max_bandwidth = 0

        for line in lines:
            if "#EXT-X-STREAM-INF" in line:
                res_match = re.search(r'RESOLUTION=\d+x(\d+)', line)
                bw_match = re.search(r'BANDWIDTH=(\d+)', line)
                
                if res_match:
                    height = int(res_match.group(1))
                    bandwidth = int(bw_match.group(1)) if bw_match else 0
                    
                    if height > max_height:
                        max_height = height
                        max_bandwidth = bandwidth

        max_quality = "Unknown"
        if max_height > 0:
            max_quality = f"{max_height}p"
        
        audio_langs = re.findall(r'TYPE=AUDIO.*LANGUAGE="?(\w+)"?', content)
        unique_langs = list(set(audio_langs))
        
        emojis_encontrados = []
        
        if unique_langs:
            for lang in unique_langs:
                emoji = get_emoji(lang)
                if emoji:
                    emojis_encontrados.append(emoji)
            
            if emojis_encontrados:
                flags_str = " / ".join(emojis_encontrados)
            else:
                flags_str = "🔊 Default"
        else:
            flags_str = "🔊 Default"

        size_info = ""
        if max_bandwidth > 0 and duration > 0:
            size_bits = max_bandwidth * (duration * 60)
            size_gb = size_bits / 8 / (1024 ** 3)
            size_info = f"💾 {size_gb:.2f}GB\n"

        spacer = "\u2800" * 2 
        name_formatted = f"NDKMAX{spacer} {max_quality}"
        
        description = f"{content_title}\n{size_info}{flags_str}"
        if "4k" in max_quality or "2160" in max_quality:
            description += " 🌟 4K"

        stream_entry = {
            "name": name_formatted,
            "title": description,
            "url": url,
            "behaviorHints": {
                "notWebReady": False,
                "bingeGroup": f"NDK-MAX-{max_quality}",
            }
        }

        return stream_entry

    except Exception as e:
        logger.error(f"Error parseando HLS: {e}")
        return {
            "name": "[NDKMAX] Error",
            "title": f"{content_title}\n⚠️ No metadata",
            "url": url
        }
