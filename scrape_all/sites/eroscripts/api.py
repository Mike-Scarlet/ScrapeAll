
import asyncio
import json
import logging

from playwright.async_api import BrowserContext, Page

from scrape_all.sites.eroscripts.consts import ErosDef

# tag 列表取数：在 playwright 页面里同源 fetch 站内 .json（走浏览器登录态/指纹，
# 不解析主题化 DOM）。discourse 每 30 条一页。
#
# 分页取数规则（probe 实测，见 playground/_probe_eroscripts_p5/p6.py）：
#   第 1 页用无参 {tag_url}.json        —— 新鲜数据（含几分钟前的新帖）
#   第 2 页起用 {tag_url}.json?page=N   —— 服务端缓存快照，滞后数天
# 缓存位移会让相邻页少量重叠/漏排，靠 topic_id 去重吸收；全新帖最晚在下一次
# collect（缓存刷新后）必然出现，不丢。


_FETCH_JS = """async u => {
  const r = await fetch(u, {headers: {Accept: 'application/json'}});
  return {status: r.status, body: await r.text()};
}"""


class ErosApi:
  """tag 列表 JSON 拉取器：单页复用，429 按 wait_seconds 退避，5xx/挑战页重开页再试"""

  def __init__(self, context: BrowserContext):
    self.context = context
    self.page: Page = None

  async def _ready_page(self) -> Page:
    if self.page is None or self.page.is_closed():
      self.page = await self.context.new_page()
      await self.page.goto(ErosDef.root_url)
      await self.page.wait_for_load_state("domcontentloaded")
    return self.page

  async def get_tag_page(self, tag_url: str, page_no: int) -> dict:
    """取一页 tag 列表 JSON dict；重试耗尽抛 RuntimeError"""
    url = f"{tag_url}.json" if page_no <= 1 else f"{tag_url}.json?page={page_no}"
    last_err = ""
    for _ in range(ErosDef.request_retry):
      page = await self._ready_page()
      try:
        res = await page.evaluate(_FETCH_JS, url)
      except Exception as e:   # 页面被导航中断/关闭等
        last_err = f"evaluate: {e}"
        await self._reopen()
        continue

      status, body = res["status"], res["body"]
      if status == 200:
        try:
          j = json.loads(body)
        except ValueError:   # 缓存挑战页/HTML 错误页：重开走完整渲染再试
          last_err = f"non-json body: {body[:120]!r}"
          await self._reopen()
          await asyncio.sleep(5)
          continue
        await asyncio.sleep(ErosDef.page_delay_s)
        return j
      if status == 429:
        wait = ErosDef.page_delay_s
        try:
          wait = max(wait, float(json.loads(body).get("extras", {}).get("wait_seconds", 0)))
        except (ValueError, AttributeError, TypeError):
          pass
        logging.warning(f"eroscripts 429 限速，等 {wait:.0f}s 重试")
        await asyncio.sleep(wait)
        continue
      last_err = f"HTTP {status}: {body[:120]!r}"
      await self._reopen()
      await asyncio.sleep(5)

    raise RuntimeError(f"eroscripts 列表页取数失败 {url}: {last_err}")

  async def _reopen(self):
    if self.page and not self.page.is_closed():
      await self.page.close()
    self.page = None

  async def close(self):
    await self._reopen()
