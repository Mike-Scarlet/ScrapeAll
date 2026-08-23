"""一次性存量补标：把 8-18 已真跑转存过的帖子 stat 2->3 / 225111 死链 2->6。

证据链（不是写死 id，从日志解析）：
  data/bd_full_real_run.txt  全量 34 帖：汇总 63/63 op 成功、全成功 33 + 部分 0
                             + walk 失败 1（即 34 帖里除死链外全部成功）
  data/bd_smoke_run.txt      冒烟 4 帖：225540/216571/222356 已在全量集；
                             219782（ink+，全量时被剔）1/1 ok 单独标 3

标记前每帖断言当前 stat==2；先备份 cangku.db 到 db_backup/。
"""
import os
import re
import shutil
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scrape_all.sites.cangku.store import PostStore, Stat
from scrape_all.storage.models import PostItem

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(ROOT, "data", "cangku.db")
FULL_LOG = os.path.join(ROOT, "data", "bd_full_real_run.txt")
SMOKE_LOG = os.path.join(ROOT, "data", "bd_smoke_run.txt")


def parse_full_log():
  """全量日志 -> (全部 post_id, walk 失败 post_id, 汇总行的三档计数)"""
  text = open(FULL_LOG, encoding="utf-8").read()
  ids = re.findall(r"^=== \[\d+/\d+\] post (\d+)", text, re.M)
  m = re.search(r"全成功 (\d+) \+ 部分失败 (\d+) \+ walk 失败 (\d+)", text)
  assert m, "汇总行没找到"
  counts = tuple(int(x) for x in m.groups())
  dead = re.findall(r"walk 失败: (\d+)", text)
  return ids, dead, counts


def parse_smoke_ok():
  """冒烟日志 -> summary N/N ok 的 post id（summary 行归属其上方最近的 saving post）"""
  cur, ok = None, []
  for line in open(SMOKE_LOG, encoding="utf-8"):
    m = re.match(r"=== saving post (\d+)", line)
    if m:
      cur = m.group(1)
    m = re.match(r"summary: (\d+)/(\d+) ok", line)
    if m and cur and m.group(1) == m.group(2):
      ok.append(cur)
      cur = None
  return ok


def main():
  ids, dead, counts = parse_full_log()
  print(f"全量日志: {len(ids)} 帖，汇总 全成功{counts[0]} + 部分{counts[1]} + walk失败{counts[2]}")
  assert len(ids) == sum(counts) == 34, (len(ids), counts)
  assert counts[1] == 0, "存在部分失败帖，不能整集标 3，先人工看日志"
  assert len(dead) == counts[2] == 1, dead

  ok_set = set(ids) - set(dead)           # 33 帖全成功
  smoke_extra = set(parse_smoke_ok()) - set(ids)   # 冒烟里全成功但不在全量集的
  print(f"标 3（CONSUMED）: 全量成功 {len(ok_set)} + 冒烟补 {sorted(smoke_extra)}")
  print(f"标 6（SHARE_DEAD）: {dead}")

  with PostStore(DB) as store:
    # 前置断言：目标帖当前全部 stat=2
    rows = {p.url: p.stat for p in store.db.QueryRecords(PostItem, where="stat = 2")}
    by_id = {u.rstrip("/").split("/")[-1]: (u, s) for u, s in rows.items()}
    for pid in ok_set | smoke_extra | set(dead):
      assert pid in by_id and by_id[pid][1] == int(Stat.PARSED), f"{pid} 不在 stat=2 队列"

    bak = os.path.join(ROOT, "data", "db_backup", f"cangku.db.bak-{time.strftime('%Y%m%d_%H%M%S')}")
    shutil.copy2(DB, bak)
    print(f"已备份 -> {bak}")

    for pid in sorted(ok_set | smoke_extra):
      store.mark_consumed(by_id[pid][0])
    for pid in dead:
      store.mark_share_dead(by_id[pid][0])

    dist = {}
    for p in store.db.QueryRecords(PostItem):
      dist[p.stat] = dist.get(p.stat, 0) + 1
  print("标记后 stat 分布:", dict(sorted(dist.items())))


if __name__ == "__main__":
  main()
