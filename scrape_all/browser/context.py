
import os, sys
from playwright.async_api import BrowserContext, ProxySettings
from playwright.async_api._generated import Playwright as AsyncPlaywright

_file_dir = os.path.dirname(os.path.dirname(__file__))

def GetBrowserCreateParam():
  session_save_path = os.path.join(_file_dir, 'browser_session')
  extra_param = {
    "channel": "chrome",
    "headless": False,
    "user_data_dir": session_save_path,
  }
  return extra_param

async def GetWrapPlaywrightBrowserContext(p: AsyncPlaywright, proxy_settings: ProxySettings=None) -> BrowserContext:
  return await p.chromium.launch_persistent_context(**GetBrowserCreateParam(), proxy=proxy_settings)

# def GetDefaultSyncPlaywrightBrowser(p: "PlaywrightContextManager"):
#   return p.chromium.launch(**GetBrowserCreateParam())

# async def GetDefaultAsyncPlaywrightBrowser(p: "PlaywrightContextManager"):
#   return await p.chromium.launch(**GetBrowserCreateParam())