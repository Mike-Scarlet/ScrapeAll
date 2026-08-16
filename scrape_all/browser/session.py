
import os

from playwright.async_api import async_playwright, BrowserContext, Page, Playwright, ProxySettings

# scrape_all/browser/session.py -> scrape_all/browser -> scrape_all -> project root
_project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_session_save_path = os.path.join(_project_root, 'browser_session')

_channel = "chrome"
_headless = False

class BrowserSession:
  """
  the only owner of playwright lifecycle: launch persistent context on enter,
  close everything on exit. reuse browser_session/ profile to keep login state.
  """
  def __init__(self, proxy_server: str = None):
    self.proxy_server = proxy_server
    self._playwright: Playwright = None
    self.context: BrowserContext = None

  async def __aenter__(self) -> "BrowserSession":
    proxy_settings = ProxySettings(server=self.proxy_server) if self.proxy_server else None

    self._playwright = await async_playwright().start()
    self.context = await self._playwright.chromium.launch_persistent_context(
      channel=_channel,
      headless=_headless,
      user_data_dir=_session_save_path,
      proxy=proxy_settings,
    )
    return self

  async def __aexit__(self, exc_type, exc, tb):
    if self.context:
      await self.context.close()
    if self._playwright:
      await self._playwright.stop()

  async def new_page(self) -> Page:
    return await self.context.new_page()
