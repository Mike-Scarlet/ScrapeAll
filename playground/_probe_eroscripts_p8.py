import asyncio, os, sys, json, sqlite3

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scrape_all.browser.session import BrowserSession

ROOT = "https://discuss.eroscripts.com"
TAG = f"{ROOT}/tag/loli/68"
CUTOFF = "2026-03-01"
PAGE_CAP = 150   # 防失控；真实深度 tags.json 先给出

async def fetch_json(page, url):
  return await page.evaluate(
      "async u => { const r = await fetch(u, {headers: {Accept: 'application/json'}});"
      " return {status: r.status, body: await r.text()}; }", url)

async def main():
  db = sqlite3.connect("data/eroscripts.db")
  known_ids = {r[0] for r in db.execute("select topic_id from EroTopicItem")}
  known_cat14 = {r[0] for r in db.execute(
      "select topic_id from EroTopicItem where category_id=14")}

  async with BrowserSession() as session:
    page = await session.new_page()
    await page.goto(ROOT, timeout=60000)

    r = await fetch_json(page, f"{ROOT}/tags.json")
    loli = [t for t in json.loads(r["body"]).get("tags", [])
            if t.get("slug") == "loli" or t.get("name") == "loli"]
    if loli:
      t = loli[0]
      print(f"tags.json: loli topic_count={t.get('topic_count')}")

    # 走到底：统计去重后总数 / cutoff 之前的 / 库里没有的
    seen = {}
    pages = 0
    for pno in range(1, PAGE_CAP + 1):
      url = f"{TAG}.json" if pno == 1 else f"{TAG}.json?page={pno}"
      r = await fetch_json(page, url)
      if r["status"] != 200:
        print(f"page {pno}: HTTP {r['status']}")
        break
      j = json.loads(r["body"])
      topics = (j.get("topic_list") or {}).get("topics")
      if not topics:
        print(f"page {pno}: 空（越界），到底了")
        break
      pages += 1
      for t in topics:
        seen[t["id"]] = t
      if pno % 10 == 0:
        print(f"  ...page {pno} 累计去重 {len(seen)}")
      await page.wait_for_timeout(700)

    missing = set(seen) - known_ids
    miss_cat14 = {i for i in missing if seen[i].get("category_id") == 14}
    older_missing = [i for i in missing if (seen[i].get("bumped_at") or "")[:10] < CUTOFF]
    print(f"\nwalked {pages} pages, 去重 topics={len(seen)}")
    print(f"库内已有 {len(known_ids)}（其中 cat14 {len(known_cat14)}）")
    print(f"库内没有的: {len(missing)}，其中 cat14（要抓的）: {len(miss_cat14)}")
    print(f"缺的里 bumped<{CUTOFF}（纯回填）: {len(older_missing)}")
    if seen:
      oldest = min(t.get("bumped_at", "")[:10] for t in seen.values())
      print(f"全 tag 最老 bumped_at: {oldest}")

    await page.close()

asyncio.run(main())
