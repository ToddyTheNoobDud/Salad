import aiohttp

try:
  import orjson
  HAS_ORJSON = True
except ImportError:
  import json
  HAS_ORJSON = False

class Rest:
  def __init__(self, salad, node):
    self.salad = salad
    self.node = node
    self.headers = {
      'Authorization': node.auth,
      'User-Id': '',
      'Client-Name': node.clientName
    }
    self.session = None

  async def makeRequest(self, method, endpoint, data=None):
    if not self.session:
      self.session = aiohttp.ClientSession()

    scheme = 'https' if self.node.ssl else 'http'
    url = f"{scheme}://{self.node.host}:{self.node.port}{endpoint}"

    try:
      if method == 'GET':
        async with self.session.get(url, headers=self.headers) as resp:
          if resp.status == 200:
            if HAS_ORJSON:
              body = await resp.read()
              return orjson.loads(body) if body else None
            else:
              return await resp.json()
          return None

      elif method == 'POST':
        if HAS_ORJSON and data:
          json_data = orjson.dumps(data)
          headers = {**self.headers, 'Content-Type': 'application/json'}
          async with self.session.post(url, data=json_data, headers=headers) as resp:
            if resp.status in (200, 201):
              body = await resp.read()
              return orjson.loads(body) if body else None
            return None
        else:
          async with self.session.post(url, json=data, headers=self.headers) as resp:
            if resp.status in (200, 201):
              return await resp.json()
            return None

      elif method == 'PATCH':
        if HAS_ORJSON and data:
          json_data = orjson.dumps(data)
          headers = {**self.headers, 'Content-Type': 'application/json'}
          async with self.session.patch(url, data=json_data, headers=headers) as resp:
            if resp.status in (200, 201):
              body = await resp.read()
              return orjson.loads(body) if body else None
            if resp.status == 204:
              return None
            return None
        else:
          async with self.session.patch(url, json=data, headers=self.headers) as resp:
            if resp.status in (200, 201):
              return await resp.json()
            if resp.status == 204:
              return None
            return None

      elif method == 'DELETE':
        async with self.session.delete(url, headers=self.headers) as resp:
          if resp.status in (200, 204):
            return True
          return None

    except Exception:
      return None

  async def close(self):
    if self.session and not self.session.closed:
      await self.session.close()