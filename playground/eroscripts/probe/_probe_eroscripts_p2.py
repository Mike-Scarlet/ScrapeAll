import asyncio, os, sys, time, json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from scrape_all.browser.session import BrowserSession

ROOT = "https://discuss.eroscripts.com"

async def settle(page, timeout_s: float = 20, sel="table.topic-list tbody tr"):
  deadline = time.monotonic() + timeout_s
  last, stable_since = -1, None
  while time.monotonic() < deadline:
    n = await page.locator(sel).count()
    now = time.monotonic()
    if n != last:
      last, stable_since = n, now
    if n > 0 and now - stable_since >= 1.2:
      break
    await page.wait_for_timeout(250)
  return last

async def topic_ids(page):
  return await page.evaluate(
      "() => [...document.querySelectorAll('tr.topic-list-item')]"
      ".map(tr => tr.dataset.topicId)")

async def main():
  async with BrowserSession() as session:
    page = await session.new_page()

    # 1) URL page 参数翻页是否可行
    ids1 = []
    for pno in (1, 2, 3):
      await page.goto(f"{ROOT}/tag/loli/68?page={pno}", timeout=60000)
      n = await settle(page)
      ids = await topic_ids(page)
      print(f"page {pno}: rows={n} first={ids[0] if ids else None} last={ids[-1] if ids else None}")
      if pno == 1:
        ids1 = ids
      else:
        overlap = set(ids) & set(ids1)
        print(f"  overlap with page1: {len(overlap)}")
        if not overlap:
          print(f"  page2 sample: {ids[:5]}")

    # 2) 空页/翻过界长什么样（page=999）
    await page.goto(f"{ROOT}/tag/loli/68?page=999", timeout=60000)
    n = await settle(page)
    ids = await topic_ids(page)
    print(f"page 999: rows={n} ids={ids[:5]}")
    body_text = (await page.locator("#list-area").inner_text()
                 if await page.locator("#list-area").count() else "")
    print("list-area text tail:", body_text[-200:].replace("\n", " | "))

    # 3) 站内 JSON API 拿总量（走浏览器登录态）
    for u in (f"{ROOT}/tag/loli/68.json?page=1", f"{ROOT}/tag/loli.json?page=1",
              f"{ROOT}/tags/loli/latest.json"):
      try:
        data = await page.evaluate(
            "async u => { const r = await fetch(u, {headers: {Accept: 'application/json'}});"
            " return {status: r.status, body: await r.text()}; }", u)
        body = data["body"]
        print(f"\nJSON {u} -> {data['status']} len={len(body)}")
        if data["status"] == 200 and body.lstrip().startswith("{"):
          j = json.loads(body)
          tl = j.get("topic_list", {})
          topics = tl.get("topics", [])
          print(f"  topics={len(topics)} more_topics_url={tl.get('more_topics_url')}")
          if topics:
            t0 = topics[0]
            keys = ["id", "title", "slug", "created_at", "bumped_at", "last_posted_at",
                    "posts_count", "views", "tags", "category_id", "pinned"]
            print("  t0:", {k: t0.get(k) for k in keys})
        break
      except Exception as e:
        print(f"JSON {u} -> error {e}")

    await page.close()

asyncio.run(main())
