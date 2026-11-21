import os

import httpx


async def serper_news(query: str, num: int = 5) -> list:
    key = os.getenv("SERPER_API_KEY")
    if not key:
        return []
    async with httpx.AsyncClient(timeout=20) as http:
        r = await http.post("https://google.serper.dev/news", headers={"X-API-KEY": key},
                            json={"q": query, "num": num, "hl": "fr"})
    if r.status_code != 200:
        return []
    return r.json().get("news", []) or []