
from typing import Mapping

from scrape_all.sites.eroscripts.consts import ErosDef
from scrape_all.sites.eroscripts.history import TopicRef

# 纯逻辑模块：tag 列表 JSON（{tag_url}.json 的响应 dict）-> TopicRef 列表，不依赖 playwright


def _op_author(topic: dict, users: Mapping[int, str]) -> str:
  """posters 里找 Original Poster（改过标题/沉帖后 description 可能缺），兜底取第一个"""
  posters = topic.get("posters") or []
  uid = None
  for p in posters:
    if "Original Poster" in (p.get("description") or ""):
      uid = p.get("user_id")
      break
  if uid is None and posters:
    uid = posters[0].get("user_id")
  return users.get(uid, "") if uid is not None else ""


def _tag_names(raw) -> tuple:
  """新版 discourse tags 是 dict 列表，旧版是字符串列表，两种都收"""
  if not raw:
    return ()
  return tuple(t["name"] if isinstance(t, dict) else str(t) for t in raw)


def parse_topic_list(page_json: dict) -> list[TopicRef]:
  """一页 tag 列表 JSON -> refs。

  空页 / 越界页（无 topic_list 或 topics 为空）返回 []（walk 停页条件）。
  url 用站内规范形式 /t/<slug>/<id>；slug 随标题改名会变，落库以 topic_id 为主键。
  """
  if not isinstance(page_json, dict):
    return []
  users = {u.get("id"): u.get("username", "") for u in page_json.get("users") or []}
  refs = []
  for t in (page_json.get("topic_list") or {}).get("topics") or []:
    tid = t.get("id")
    if tid is None:
      continue
    refs.append(TopicRef(
        topic_id=int(tid),
        url=f"{ErosDef.root_url}/t/{t.get('slug') or 'topic'}/{tid}",
        title=(t.get("title") or "").strip(),
        author=_op_author(t, users),
        created_at=t.get("created_at") or "",
        bumped_at=t.get("bumped_at") or "",
        tags=_tag_names(t.get("tags")),
        category_id=int(t.get("category_id") or 0),
        posts_count=int(t.get("posts_count") or 0),
        views=int(t.get("views") or 0),
        pinned=bool(t.get("pinned")),
    ))
  return refs
