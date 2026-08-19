import asyncio, os, sys, time, json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scrape_all.browser.session import BrowserSession

ROOT = "https://discuss.eroscripts.com"
TAG_URL = f"{ROOT}/tag/loli/68"

async def settle(page, timeout_s: float = 20):
  sel = "table.topic-list tbody tr"
  deadline = time.monotonic() + timeout_s
  last, stable_since = -1, None
  while time.monotonic() < deadline:
    n = await page.locator(sel).count()
    now = time.monotonic()
    if n != last:
      last, stable_since = n, now
    if n > 0 and now - stable_since >= 1.5:
      return n
    await page.wait_for_timeout(250)
  return last

async def dom_ids(page, url):
  await page.goto(url, timeout=60000)
  await settle(page)
  return await page.evaluate(
      "() => [...document.querySelectorAll('tr.topic-list-item')]"
      ".map(tr => tr.dataset.topicId)")

async def fetch_json(page, url):
  r = await page.evaluate(
      "async u => { const r = await fetch(u, {headers: {Accept: 'application/json'}});"
      " return {status: r.status, body: await r.text()}; }", url)
  return r["status"], json.loads(r["body"]) if r["status"] == 200 else r["body"][:200]

async def main():
  async with BrowserSession() as session:
    page = await session.new_page()

    # 同一时刻取三份：DOM 无 page 参数 / DOM page=1 / JSON page=1
    dom_noparam = await dom_ids(page, TAG_URL)
    dom_page1 = await dom_ids(page, f"{TAG_URL}?page=1")
    status, j = await fetch_json(page, f"{TAG_URL}.json?page=1")
    topics = j["topic_list"]["topics"]
    json_ids = [str(t["id"]) for t in topics]
    json_tag_ok = all(any(tg.get("name") == "loli" for tg in t.get("tags", [])) for t in topics)

    print(f"DOM(no param): {len(dom_noparam)} rows, first5={dom_noparam[:5]}")
    print(f"DOM(page=1):   {len(dom_page1)} rows, first5={dom_page1[:5]}")
    print(f"JSON(page=1):  {len(json_ids)} topics, first5={json_ids[:5]}  status={status}")
    print(f"JSON 页内全部 topic 都带 loli tag: {json_tag_ok}")
    print(f"DOM(no param) == DOM(page=1): {dom_noparam == dom_page1}")
    print(f"DOM(page=1)  == JSON(page=1): {dom_page1 == json_ids}")
    if dom_page1 != json_ids:
      only_dom = [i for i in dom_page1 if i not in json_ids]
      only_json = [i for i in json_ids if i not in dom_page1]
      print(f"  仅在 DOM: {only_dom[:10]}\n  仅在 JSON: {only_json[:10]}")
      tid_map = {str(t["id"]): t for t in topics}
      for i in only_dom[:3]:
        t = tid_map.get(i)
        if t:
          print(f"  DOM-only {i}: title={t['title'][:40]!r} bumped={t['bumped_at']} tags={[tg['name'] for tg in t.get('tags', [])][:6]}")
        else:
          print(f"  DOM-only {i}: 不在本页 JSON 里")
    # 332232 现在还在不在（p1 首跑的首行）
    print("332232 in dom:", "332232" in dom_noparam + dom_page1, "in json:", "332232" in json_ids)
    await page.close()

asyncio.run(main())
