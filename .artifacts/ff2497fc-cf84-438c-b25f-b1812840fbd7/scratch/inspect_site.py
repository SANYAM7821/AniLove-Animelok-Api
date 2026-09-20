import asyncio
import httpx
from bs4 import BeautifulSoup

async def inspect():
    url = "https://animeworld-india.me/"
    async with httpx.AsyncClient(follow_redirects=True) as client:
        resp = await client.get(url, headers={"User-Agent": "Mozilla/5.0"})
        print(f"Status: {resp.status_code}")
        soup = BeautifulSoup(resp.text, 'html.parser')
        # Print some structural info
        print("Titles found:")
        for h2 in soup.find_all('h2')[:5]:
            print(f"- {h2.text.strip()}")

        # Check for card patterns
        print("\nPossible card links:")
        for a in soup.find_all('a', href=True):
            if '/series/' in a['href'] or '/movies/' in a['href']:
                print(f"- {a['href']}")
                if len(a.text.strip()) > 5:
                     print(f"  Text: {a.text.strip()}")
                break

if __name__ == "__main__":
    asyncio.run(inspect())
