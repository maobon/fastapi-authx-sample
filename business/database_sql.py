"""新闻业务相关的 SQL 语句。

该文件只维护 `business` 服务中新闻接口使用的 SQL，避免 SQL 散落在路由代码中。
"""

# 查询全部新闻，按主键升序返回，供 `GET /news` 不传分页参数时使用。
SELECT_NEWS = """
SELECT id, title, url, image, summary, date, img
FROM news
ORDER BY id ASC
"""

# 分页查询新闻，供 `GET /news?page=...&page_size=...` 使用。
SELECT_NEWS_PAGED = f"{SELECT_NEWS}LIMIT %s OFFSET %s"
