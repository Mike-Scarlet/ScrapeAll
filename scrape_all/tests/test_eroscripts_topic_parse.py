
from scrape_all.sites.eroscripts.topic_parse import (
    extract_post_links, link_kind, parse_topic_links,
)

ROOT = "https://discuss.eroscripts.com"


def test_link_kind_attachment_default_script():
  # 站点上传附件无视频扩展名：按脚本论（本站惯例挂 .funscript/.zip 脚本包）
  assert link_kind(f"{ROOT}/uploads/short-url/aBc123", is_attachment=True) == "script"
  assert link_kind(f"{ROOT}/uploads/original/3X/a/b/video.mp4", is_attachment=True) == "media"


def test_link_kind_by_extension():
  assert link_kind("https://random.host/files/my.funscript", is_attachment=False) == "script"
  assert link_kind("https://random.host/files/clip.mkv", is_attachment=False) == "media"


def test_link_kind_funscript_named_archive():
  # 文件名带 funscript 的 zip 直链（流媒体站 CDN 挂的脚本包）判 script，
  # 不被 source 域名表抢走；锚文本带字样同理
  assert link_kind("https://hmvmania.com/wp-content/uploads/2021/01/x_funscript.zip", False) == "script"
  assert link_kind("https://mega.nz/folder/abc", False, name="My Funscript Pack") == "script"


def test_link_kind_by_host():
  assert link_kind("https://mega.nz/folder/c9AWxKwb#8J7OMrzogZWBVo90BMH0Kg", False) == "media"
  assert link_kind("https://www.pixeldrain.com/l/sYxd45NS", False) == "media"   # www. 剥除
  assert link_kind("https://www.iwara.tv/video/abc", False) == "source"
  assert link_kind("https://hanime1.me/watch?v=405984", False) == "source"      # hanime 镜像
  assert link_kind("https://www.patreon.com/someuser", False) == "other"
  assert link_kind("https://disk.yandex.com/i/XkSgLZItzZ2Eog", False) == "media"


def test_extract_tracks_section_and_skips_noise():
  cooked = (
      '<h2><a class="anchor" href="#p-1-framed-picture-preview-1"></a>🖼 Preview</h2>'
      '<p><a class="lightbox" href="https://cdn.example/img.png">image</a></p>'
      '<h2><a class="anchor" href="#p-1-movie-camera-video-link-2"></a>🎬 Video Link</h2>'
      '<p><a href="https://www.iwara.tv/video/abc">iwara.tv</a></p>'
      '<p><a href="https://mega.nz/folder/c9AWxKwb#8J7OMrzogZWBVo90BMH0Kg">mega.nz</a></p>'
      '<h2>📂 Script</h2>'
      '<p><a class="attachment" href="/uploads/short-url/SzFaJX.funscript">'
      "[HMV] Prophet.funscript</a></p>"
  )
  links = extract_post_links(cooked, 1, "alice")
  by_host = {l.url.split("/")[2].removeprefix("www.").split(".")[0]: l for l in links}
  assert len(links) == 3   # lightbox/anchor 不算
  assert by_host["mega"].kind == "media"
  assert by_host["mega"].section == "🎬 Video Link"
  att = by_host["discuss"]
  assert att.kind == "script"
  assert att.name == "[HMV] Prophet.funscript"   # 附件锚文本=文件名
  assert att.section == "📂 Script"
  assert by_host["iwara"].kind == "source"
  assert all(l.post_number == 1 and l.username == "alice" for l in links)


def test_extract_site_internal_links_skipped():
  # 引用/导航等站内链接跳过；/uploads/ 附件保留
  cooked = (
      '<aside class="quote"><a href="/t/another-topic/123">引用原帖</a></aside>'
      '<a class="attachment" href="/uploads/short-url/x.funscript">x.funscript</a>'
  )
  links = extract_post_links(cooked, 2, "bob")
  assert len(links) == 1
  assert links[0].url == f"{ROOT}/uploads/short-url/x.funscript"


def test_extract_empty_name_fallback():
  # 图标/图片链接无锚文本：回退文件名或域名
  links = extract_post_links('<a href="https://mega.nz/folder/abc"><img src="x.png"></a>', 1, "a")
  assert links[0].name == "mega.nz"
  links = extract_post_links('<a href="https://host.test/files/clip.mp4"><img src="x.png"></a>', 1, "a")
  assert links[0].name == "clip.mp4"


def test_extract_bare_url_in_code_block():
  # discourse 不给 code 块里的 URL 自动转链，正则补收
  cooked = "<pre><code>https://pixeldrain.com/l/sYxd45NS</code></pre>"
  links = extract_post_links(cooked, 1, "alice")
  assert [l.kind for l in links if l.url == "https://pixeldrain.com/l/sYxd45NS"] == ["media"]


def test_parse_topic_dedup_order_deleted():
  topic = {
      "post_stream": {"posts": [
          {"post_number": 1, "username": "op", "cooked":
              '<a href="https://mega.nz/folder/x">mega</a>'
              '<a class="attachment" href="/uploads/short-url/a.funscript">a.funscript</a>'},
          {"post_number": 3, "username": "fan", "deleted_at": "2026-08-01T00:00:00Z",
           "cooked": '<a href="https://pixeldrain.com/l/zzz">zzz</a>'},
          {"post_number": 2, "username": "op", "cooked":
              # 同 URL 重复出现（OP 顶楼重发）去重；回帖新链接保留并记楼层
              '<a href="https://mega.nz/folder/x">mega again</a>'
              '<a class="attachment" href="/uploads/short-url/b.funscript">b.funscript</a>'},
      ]},
  }
  links = parse_topic_links(topic)
  urls = [l.url for l in links]
  assert urls == [
      "https://mega.nz/folder/x",
      f"{ROOT}/uploads/short-url/a.funscript",
      f"{ROOT}/uploads/short-url/b.funscript",
  ]
  assert urls.count("https://mega.nz/folder/x") == 1
  assert links[-1].post_number == 2 and links[-1].username == "op"
  assert all(l.url != "https://pixeldrain.com/l/zzz" for l in links)   # 删帖跳过


def test_parse_topic_empty_or_missing():
  assert parse_topic_links({}) == []
  assert parse_topic_links({"post_stream": {}}) == []
  assert parse_topic_links({"post_stream": {"posts": None}}) == []
