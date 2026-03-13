import aiohttp
from config import TELEMT_API_URL


async def add_secret(username: str, secret: str) -> bool:
    url = f"{TELEMT_API_URL}/v1/users"
    payload = {"username": username, "secret": secret}
    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=payload) as resp:
            return resp.status in (200, 201)


async def remove_secret(username: str) -> bool:
    url = f"{TELEMT_API_URL}/v1/users/{username}"
    async with aiohttp.ClientSession() as session:
        async with session.delete(url) as resp:
            return resp.status in (200, 204)
