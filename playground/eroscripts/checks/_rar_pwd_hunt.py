# 只读：在 topic JSON 正文里找 rar 密码线索（324125 / 312412）
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
TOPICS = os.path.join(ROOT, "data", "eroscripts", "topics")

# 密码样式的上下文词（eroscripts 惯例：password: xxx / pass: xxx / パス / 密码）
PAT = re.compile(
    r"(password|passwd|pass|pwd|パスワード|パス|解压密码|提取码|密码)\s*[:：=]?\s*`?\s*([^\s`<>)，。]+)",
    re.I)

for tid in (324125, 312412):
    p = os.path.join(TOPICS, f"{tid}.json")
    if not os.path.exists(p):
        print(f"{tid}: topic JSON 不存在")
        continue
    raw = json.load(open(p, encoding="utf-8"))
    # discourse topic JSON: post_stream.posts[].cooked
    posts = ((raw.get("post_stream") or {}).get("posts")) or []
    print(f"=== {tid}  posts {len(posts)} ===")
    hits = 0
    for i, post in enumerate(posts):
        cooked = post.get("cooked") or ""
        text = re.sub(r"<[^>]+>", " ", cooked)
        for m in PAT.finditer(text):
            ctx = text[max(0, m.start() - 60):m.end() + 40]
            print(f"  #{i} {m.group(1)}={m.group(2)!r}  ctx: …{ctx.strip()[:140]}")
            hits += 1
    if not hits:
        print("  （正文无密码样式匹配）")
