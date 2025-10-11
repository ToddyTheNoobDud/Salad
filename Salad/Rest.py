"""DO WHAT THE FUCK YOU WANT TO PUBLIC LICENSE
                    Version 2, December 2004

 Copyright (C) 2004 Sam Hocevar <sam@hocevar.net>

 Everyone is permitted to copy and distribute verbatim or modified
 copies of this license document, and changing it is allowed as long
 as the name is changed.

            DO WHAT THE FUCK YOU WANT TO PUBLIC LICENSE
   TERMS AND CONDITIONS FOR COPYING, DISTRIBUTION AND MODIFICATION

  0. You just DO WHAT THE FUCK YOU WANT TO.

URL: https://www.wtfpl.net/txt/copying/
"""
import aiohttp
import logging
from typing import Optional, Dict
try:
    import orjson as json
    dumps = lambda x: json.dumps(x).decode('utf-8')
    loads = json.loads
except ImportError:
    try:
        import ujson as json
        dumps = json.dumps
        loads = json.loads
    except ImportError:
        import json
        dumps = json.dumps
        loads = json.loads

logger = logging.getLogger(__name__)


class Rest:
    """Optimized REST client with connection pooling."""

    __slots__ = ('salad', 'node', 'headers', 'session')

    def __init__(self, salad, node):
        self.salad = salad
        self.node = node
        self.headers = {
            'Authorization': node.auth,
            'User-Id': '',
            'Client-Name': node.clientName
        }
        self.session = None

    async def makeRequest(self, method: str, endpoint: str, data: Optional[Dict] = None):
        """Make HTTP request with connection pooling."""
        if not self.session or self.session.closed:
            timeout = aiohttp.ClientTimeout(total=30, connect=10)
            conn = aiohttp.TCPConnector(
                limit=100,
                limit_per_host=30,
                ttl_dns_cache=300
            )
            self.session = aiohttp.ClientSession(
                connector=conn,
                timeout=timeout,
                json_serialize=dumps
            )

        scheme = 'https' if self.node.ssl else 'http'
        url = f"{scheme}://{self.node.host}:{self.node.port}/{endpoint.lstrip('/')}"

        try:
            if method == 'GET':
                async with self.session.get(url, headers=self.headers) as resp:
                    if resp.status == 200:
                        body = await resp.read()
                        return loads(body) if body else None
                    return None

            elif method == 'POST':
                json_data = dumps(data).encode('utf-8') if data else b'{}'
                headers = {**self.headers, 'Content-Type': 'application/json'}
                async with self.session.post(url, data=json_data, headers=headers) as resp:
                    if resp.status in (200, 201):
                        body = await resp.read()
                        return loads(body) if body else None
                    return None

            elif method == 'PATCH':
                json_data = dumps(data).encode('utf-8') if data else b'{}'
                headers = {**self.headers, 'Content-Type': 'application/json'}
                async with self.session.patch(url, data=json_data, headers=headers) as resp:
                    if resp.status in (200, 201):
                        body = await resp.read()
                        return loads(body) if body else None
                    if resp.status == 204:
                        return None
                    return None

            elif method == 'DELETE':
                async with self.session.delete(url, headers=self.headers) as resp:
                    return resp.status in (200, 204)

        except Exception as e:
            logger.debug(f"Request failed: {e}")
            return None

    async def close(self) -> None:
        """Close session."""
        if self.session and not self.session.closed:
            await self.session.close()
