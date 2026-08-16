
from scrape_all.sites.baidu_pan.tree import EntryInfo

# 假分享结构：
# /
#   Season 1/  01.mp4  02.mp4
#   Season 2/  extra/  21.mp4  empty/
#   readme.txt
FAKE_TREE = {
  "/": [
    ("Season 1", True),
    ("Season 2", True),
    ("readme.txt", False, "1K", "2025-10-01 00:00"),
  ],
  "/Season 1": [
    ("01.mp4", False, "326.1M", "2025-10-04 02:55"),
    ("02.mp4", False, "302.9M", "2025-10-10 02:07"),
  ],
  "/Season 2": [
    ("extra", True),
    ("21.mp4", False, "300M", "2025-11-01 00:00"),
    ("empty", True),
  ],
  "/Season 2/extra": [
    ("note.txt", False, "1K", "2025-11-02 00:00"),
  ],
  "/Season 2/empty": [],
}


def make_fake_lister(tree=None):
  """返回 (lister, calls)：calls 记录实际请求过的路径，用于断言省导航行为"""
  tree = FAKE_TREE if tree is None else tree
  calls = []

  async def lister(path):
    calls.append(path)
    return [EntryInfo(*item) for item in tree[path]]

  return lister, calls
