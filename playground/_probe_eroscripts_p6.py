import asyncio, os, sys, json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scrape_all.browser.session import BrowserSession

ROOT = "https://discuss.eroscripts.com"
TAG_URL = f"{ROOT}/tag/loli/68"

async def fetch_json(page, url):
  r = await page.evaluate(
      "async u => { const r = await fetch(u, {headers: {Accept: 'application/json'}});"
      " return {status: r.status, body: await r.text()}; }", url)
  return r["status"], (json.loads(r["body"]) if r["status"] == 200 else r["body"][:200])

async def main():
  async with BrowserSession() as session:
    page = await session.new_page()
    await page.goto(TAG_URL, timeout=60000)

    for label, u in (
        ("no param", f"{TAG_URL}.json"),
        ("page=1", f"{TAG_URL}.json?page=1"),
        ("page=1&no_definitions", f"{TAG_URL}.json?page=1&no_definitions=true"),
    ):
      status, j = await fetch_json(page, u)
      if status != 200:
        print(f"{label}: HTTP {status}")
        continue
      topics = j["topic_list"]["topics"]
      ids = [str(t["id"]) for t in topics]
      bumps = [t["bumped_at"][:16] for t in topics]
      print(f"{label}: {len(topics)} topics first3={ids[:3]} bumped[0]={bumps[0]} bumped[-1]={bumps[-1]} "
            f"has_332232={'332232' in ids}")

    await page.close()

asyncio.run(main())
