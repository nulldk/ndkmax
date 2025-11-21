import httpx
import re
from urllib.parse import urljoin, quote
from utils.logger import setup_logger

logger = setup_logger(__name__)

async def fetch_and_rewrite_manifest(client: httpx.AsyncClient, target_url: str, proxy_base_url: str):
    try:
        response = await client.get(target_url)
        
        if response.status_code != 200:
            logger.error(f"ORIGIN_ERROR: Status {response.status_code}")
            return None, response.status_code

        content = response.text
        base_url = str(response.url)
        lines = content.splitlines()
        rewritten_lines = []
        
        uri_pattern = re.compile(r'(URI=")([^"]+)(")')

        for line in lines:
            line = line.strip()
            if not line:
                rewritten_lines.append(line)
                continue

            # CASO 1: Líneas de metadatos (Empiezan por #)
            if line.startswith("#"):
                # Si la línea contiene una URI, hay que reescribirla también
                if "URI=" in line:
                    def replace_uri(match):
                        prefix, relative_url, suffix = match.groups()
                        absolute_url = urljoin(base_url, relative_url)
                        
                        # Si es un m3u8 (audio tracks), pasa por el proxy
                        if ".m3u8" in absolute_url:
                            encoded_target = quote(absolute_url)
                            new_url = f"{proxy_base_url}/proxy/manifest?url={encoded_target}"
                            logger.debug(f"TAG_REWRITE_PROXY: {relative_url} -> {new_url}")
                            return f"{prefix}{new_url}{suffix}"
                        else:
                            # Si es una imagen o key, bypass directo
                            logger.debug(f"TAG_REWRITE_BYPASS: {relative_url} -> {absolute_url}")
                            return f"{prefix}{absolute_url}{suffix}"

                    new_line = uri_pattern.sub(replace_uri, line)
                    rewritten_lines.append(new_line)
                else:
                    rewritten_lines.append(line)
                continue

            # CASO 2: URLs directas (Segmentos o Variantes)
            absolute_url = urljoin(base_url, line)

            if line.endswith(".m3u8"):
                encoded_target = quote(absolute_url)
                proxied_url = f"{proxy_base_url}/proxy/manifest?url={encoded_target}"
                rewritten_lines.append(proxied_url)
            else:
                rewritten_lines.append(absolute_url)

        return "\n".join(rewritten_lines), 200

    except Exception as e:
        logger.error(f"PROXY_EXCEPTION: {e}", exc_info=True)
        return None, 500
