import asyncio

try:
    from ddgs import DDGS
except ImportError:  # ancien nom du paquet
    from duckduckgo_search import DDGS


def _news_sync(query: str, num: int) -> list:
    with DDGS(timeout=20) as ddgs:
        rows = ddgs.news(query, region="fr-fr", safesearch="moderate", max_results=num) or []
    # Même format que Serper : title, link, snippet, date, source, imageUrl
    return [
        {
            "title": r.get("title", ""),
            "link": r.get("url", ""),
            "snippet": r.get("body", ""),
            "date": r.get("date", ""),
            "source": r.get("source", ""),
            "imageUrl": r.get("image", ""),
        }
        for r in rows
    ]


async def serper_news(query: str, num: int = 5) -> list:
    for essai in range(3):
        try:
            return await asyncio.to_thread(_news_sync, query, num)
        except Exception:
            if essai < 2:
                await asyncio.sleep(1.5 * (essai + 1))
    return []