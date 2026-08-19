import asyncio, os, sys, time, json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scrape_all.browser.session import BrowserSession

ROOT = "https://discuss.eroscripts.com"

async def fetch_json(page, url):
  return await page.evaluate(
      "async u => { const r = await fetch(u, {headers: {Accept: 'application/json'}});"
      " return {status: r.status, body: await r.text()}; }", url)

async def main():
  async with BrowserSession() as session:
    page = await session.new_page()
    await page.goto(ROOT, timeout=60000)

    # 1) 全站 tags 清单里 loli 的 topic_count
    r = await fetch_json(page, f"{ROOT}/tags.json")
    tags = json.loads(r["body"]).get("tags", [])
    loli = [t for t in tags if t.get("slug") == "loli" or t.get("name") == "loli"]
    print("loli tag:", loli)

    # 2) 跟着 more_topics_url 走到尾，统计页数/主题数/尾页行为（上限 12 页防失控）
    url = f"{ROOT}/tag/loli/68.json?page=1"
    pages = 0
    total = 0
    pinned_ids = []
    while url and pages < 12:
      r = await fetch_json(page, url)
      if r["status"] != 200:
        print(f"status {r['status']} at {url}")
        break
      j = json.loads(r["body"])
      tl = j["topic_list"]
      topics = tl["topics"]
      pages += 1
      total += len(topics)
      pins = [t["id"] for t in topics if t.get("pinned")]
      if pins:
        pinned_ids += [(pages, p) for p in pins]
      mtu = tl.get("more_topics_url")
      if pages <= 3 or not mtu:
        bumps = [t["bumped_at"][:10] for t in topics]
        print(f"page {pages}: topics={len(topics)} bumped range {bumps[0]}..{bumps[-1]} more={bool(mtu)}")
      url = ROOT + mtu if mtu else None
      await page.wait_for_timeout(800)
    print(f"walked {pages} pages, {total} topics, pinned={pinned_ids}")
    print("(more pages likely remain)" if pages >= 12 else "(reached end)")

    await page.close()

asyncio.run(main())
