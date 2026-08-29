import asyncio, os, sys, json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from scrape_all.browser.session import BrowserSession

ROOT = "https://discuss.eroscripts.com"

async def fetch_json(page, url):
  return await page.evaluate(
      "async u => { const r = await fetch(u, {headers: {Accept: 'application/json'}});"
      " return {status: r.status, body: await r.text()}; }", url)

async def peek(page, pno):
  r = await fetch_json(page, f"{ROOT}/tag/loli/68.json?page={pno}")
  if r["status"] != 200:
    return pno, f"HTTP {r['status']}", None
  j = json.loads(r["body"])
  tl = j["topic_list"]
  topics = tl["topics"]
  if not topics:
    return pno, "EMPTY", None
  bumps = [t["bumped_at"][:10] for t in topics]
  return pno, f"{len(topics)} topics bumped {bumps[0]}..{bumps[-1]} more={bool(tl.get('more_topics_url'))}", bumps

async def main():
  async with BrowserSession() as session:
    page = await session.new_page()
    await page.goto(ROOT, timeout=60000)

    # 粗探深度：大步长跳页，找到空页边界
    for pno in (50, 100, 150, 200, 300, 400, 500):
      pno, info, _ = await peek(page, pno)
      print(f"page {pno}: {info}")
      if info == "EMPTY":
        break
      await page.wait_for_timeout(700)

    # 空页 JSON 具体形状（拿 topics/more_topics_url 字段做停止条件依据）
    r = await fetch_json(page, f"{ROOT}/tag/loli/68.json?page=5000")
    j = json.loads(r["body"])
    tl = j["topic_list"]
    print("empty page keys:", sorted(tl.keys()))
    print("empty page topics:", tl.get("topics"), "more:", tl.get("more_topics_url"))

    await page.close()

asyncio.run(main())
