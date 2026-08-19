
class ErosDef:
  root_url = "https://discuss.eroscripts.com"   # do not end with /

  # tag 列表走站内 JSON（{tag_url}.json?page=N），比扒主题化 DOM 稳；
  # fetch 在 playwright 页面里发（同浏览器登录态/指纹）。discourse 每 30 条一页。
  page_delay_s = 1.2       # 两次列表请求间隔（限速友好）
  request_retry = 3        # 单页请求重试次数（429/5xx/非 JSON）
