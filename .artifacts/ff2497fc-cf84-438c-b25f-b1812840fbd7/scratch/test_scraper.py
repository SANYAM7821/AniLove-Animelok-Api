import httpx
from selectolax.parser import HTMLParser

async def test():
    url = "https://watchanimeworlds.com/?s=Solo+Leveling"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    async with httpx.AsyncClient(follow_redirects=True) as client:
        resp = await client.get(url, headers=headers)
        print(f"Status: {resp.status_code}")
        tree = HTMLParser(resp.text)

        # WordPress themes usually use 'article' or specific classes like 'result-item'
        # Let's look for common patterns
        print("Possible links:")
        for node in tree.css("a[href*='/anime/'], a[href*='/series/'], a[href*='/movies/']"):
             print(f"- {node.attributes.get('href')} | Text: {node.text().strip()}")

        # Look for images
        print("\nImages:")
        for img in tree.css("img"):
            print(f"- {img.attributes.get('src')}")

if __name__ == "__main__":
    import asyncio
    asyncio.run(test())
