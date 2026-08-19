import asyncio, os, sys, json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scrape_all.browser.session import BrowserSession

ROOT = "https://discuss.eroscripts.com"

# topic 页 JSON 结构探针：
# 1) 顶层有哪些键、post_stream.posts[0]（OP）有哪些键
# 2) OP cooked 里的 <a> 链接形态（锚文本/class/href），看媒体/脚本链接怎么区分

_SAMPLES = (
    332232,   # 今日新帖，1 post
    268961,   # 13 posts 的热帖
    332067,   # 1 post
)


async def fetch_json(page, url):
  r = await page.evaluate(
      "async u => { const r = await fetch(u, {headers: {Accept: 'application/json'}});"
      " return {status: r.status, body: await r.text()}; }", url)
  return r["status"], (json.loads(r["body"]) if r["status"] == 200 else r["body"][:200])


async def main():
  async with BrowserSession() as session:
    page = await session.new_page()
    await page.goto(ROOT, timeout=60000)

    for tid in _SAMPLES:
      status, j = await fetch_json(page, f"{ROOT}/t/{tid}.json")
      if status != 200:
        print(f"=== {tid}: HTTP {status}")
        continue
      print(f"\n=== {tid} top keys:", sorted(j.keys()))
      posts = j.get("post_stream", {}).get("posts", [])
      print(f"posts_in_payload={len(posts)} stream_len={len(j.get('post_stream', {}).get('stream', []))}"
            f" category_id={j.get('category_id')} posts_count={j.get('posts_count')}")
      op = posts[0]
      print("OP keys:", sorted(op.keys()))
      cooked = op.get("cooked", "")
      print(f"cooked len={len(cooked)}")
      # 粗提 <a> 看形态
      import re
      for m in re.finditer(r'<a ([^>]*)>(.*?)</a>', cooked, re.S):
        attrs, text = m.group(1), re.sub(r"<[^>]+>", "", m.group(2))[:40]
        href = re.search(r'href="([^"]+)"', attrs)
        cls = re.search(r'class="([^"]*)"', attrs)
        print(f"  <a class={cls.group(1) if cls else '-'!r:30} href={href.group(1) if href else '-'!r:75} text={text!r}")
      await asyncio.sleep(1.5)

    await page.close()

asyncio.run(main())
