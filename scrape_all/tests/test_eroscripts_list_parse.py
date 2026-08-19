
from scrape_all.sites.eroscripts.list_parse import parse_topic_list


def _topic(**kw):
  base = {
      "id": 332232, "slug": "some-topic", "title": "【Multi-axis】标题",
      "created_at": "2026-08-19T13:29:23.611Z", "bumped_at": "2026-08-19T13:48:00.000Z",
      "posts_count": 1, "views": 10, "category_id": 14, "pinned": False,
      "tags": [{"id": 68, "name": "loli"}, {"id": 922, "name": "straight"}],
      "posters": [
          {"user_id": 7, "description": "Original Poster, Most Posts"},
          {"user_id": 9, "description": "Frequent Poster"}],
  }
  base.update(kw)
  return base


def test_parse_basic_fields():
  page = {
      "users": [{"id": 7, "username": "alice"}, {"id": 9, "username": "bob"}],
      "topic_list": {"topics": [_topic()]},
  }
  refs = parse_topic_list(page)
  assert len(refs) == 1
  r = refs[0]
  assert r.topic_id == 332232
  assert r.url == "https://discuss.eroscripts.com/t/some-topic/332232"
  assert r.title == "【Multi-axis】标题"
  assert r.author == "alice"          # Original Poster，不是第一个 poster 恰好也是
  assert r.tags == ("loli", "straight")
  assert r.category_id == 14
  assert r.posts_count == 1
  assert r.views == 10
  assert r.bumped_at == "2026-08-19T13:48:00.000Z"
  assert not r.pinned


def test_parse_op_fallback_first_poster():
  # description 缺失/不含 Original Poster 时兜底第一个 poster
  page = {
      "users": [{"id": 9, "username": "bob"}],
      "topic_list": {"topics": [_topic(
          posters=[{"user_id": 9, "description": ""}])]},
  }
  assert parse_topic_list(page)[0].author == "bob"


def test_parse_tags_str_form():
  # 旧版 discourse tags 为字符串列表
  page = {"users": [], "topic_list": {"topics": [_topic(tags=["loli"])]}}
  assert parse_topic_list(page)[0].tags == ("loli",)


def test_parse_empty_or_missing_topic_list():
  # 空页（topics=[]）与越界页（无 topic_list）都归一为 []，walk 据此停页
  assert parse_topic_list({}) == []
  assert parse_topic_list({"topic_list": {"topics": []}}) == []
  assert parse_topic_list(None) == []


def test_parse_skips_topic_without_id():
  page = {"users": [], "topic_list": {"topics": [_topic(), {"title": "no id"}]}}
  assert len(parse_topic_list(page)) == 1


def test_parse_pinned_flag_and_missing_optional():
  page = {"users": [], "topic_list": {"topics": [_topic(
      pinned=True, tags=None, posters=None, views=None)]}}
  r = parse_topic_list(page)[0]
  assert r.pinned
  assert r.tags == ()
  assert r.author == ""
  assert r.views == 0
