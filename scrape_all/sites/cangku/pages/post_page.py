
import os

from scrape_all.sites.cangku import locators

# 帖子页抓取（fetch 阶段）与本地落盘位置。
# HTML 落 data/cangku/posts/{id}.html，二维码图落 data/cangku/qr/，
# parse 阶段纯离线读这些文件（只有取二维码图要走浏览器）。

_project_root = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
DATA_DIR = os.path.join(_project_root, "data", "cangku")
POSTS_DIR = os.path.join(DATA_DIR, "posts")
QR_DIR = os.path.join(DATA_DIR, "qr")


def post_id(url: str) -> str:
  """/archives/219673 -> 219673"""
  return url.rstrip("/").rsplit("/", 1)[-1]


def post_html_path(pid: str) -> str:
  return os.path.join(POSTS_DIR, f"{pid}.html")


def save_post_html(pid: str, html: str):
  os.makedirs(POSTS_DIR, exist_ok=True)
  with open(post_html_path(pid), "w", encoding="utf-8") as f:
    f.write(html)


def load_post_html(pid: str) -> str:
  with open(post_html_path(pid), "r", encoding="utf-8") as f:
    return f.read()


def save_qr_image(name: str, data: bytes):
  os.makedirs(QR_DIR, exist_ok=True)
  with open(os.path.join(QR_DIR, name), "wb") as f:
    f.write(data)


class PostPage:
  """帖子页浏览器封装：打开并等帖子主体渲染，返回整页 HTML"""

  def __init__(self, page):
    self.page = page

  async def fetch_html(self, url: str) -> str:
    await self.page.goto(url)
    # 就绪检查等 article 而不是分类 meta-label：个别帖没挂任何分类
    # （225885/226386，分类链为空但帖子/下载区正常），等 label 会永远超时
    await self.page.wait_for_selector(locators.ARTICLE, timeout=15000)
    return await self.page.content()
