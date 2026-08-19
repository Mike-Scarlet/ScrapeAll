
import json
import os

# topic 页 JSON 落盘：fetch 阶段存 data/eroscripts/topics/{topic_id}.json，
# parse 阶段纯离线读（不碰浏览器），解析规则升级后可随时重跑 parse 重新分类。

_project_root = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))
TOPICS_DIR = os.path.join(_project_root, "data", "eroscripts", "topics")


def topic_json_path(topic_id: int) -> str:
  return os.path.join(TOPICS_DIR, f"{topic_id}.json")


def save_topic_json(topic_id: int, topic: dict):
  os.makedirs(TOPICS_DIR, exist_ok=True)
  with open(topic_json_path(topic_id), "w", encoding="utf-8") as f:
    json.dump(topic, f, ensure_ascii=False)


def load_topic_json(topic_id: int) -> dict:
  with open(topic_json_path(topic_id), "r", encoding="utf-8") as f:
    return json.load(f)
