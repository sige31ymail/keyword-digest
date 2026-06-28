"""StaticSitePublisher: レポート HTML / feed.xml / index.html を site/ に書き出す。

PocketDigest の SimpleArticleTextExtractor が抽出できるよう、本文は
<article> 配下の <h1> + <p> 段落で構成する（広告・スクリプトは入れない）。
各レポート HTML の <head> にメタ情報を埋め込み、再実行時のフィード再構築に使う。
"""
from __future__ import annotations

import html
import os
import re
from datetime import datetime, timezone
from email.utils import format_datetime

from ..domain.feed import Feed, FeedItem
from ..domain.report import Report
from ..ports.site_publisher import SitePublisher

_REPORT_TEMPLATE = """<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="kd:title" content="{meta_title}">
<meta name="kd:slug" content="{slug}">
<meta name="kd:published" content="{published_iso}">
<meta name="kd:keyword" content="{meta_keyword}">
<meta name="kd:generated_by" content="{generated_by}">
<title>{title}</title>
</head>
<body>
<article>
<h1>{title}</h1>
{paragraphs}
<footer><p>キーワード「{keyword}」について {generated_by} が生成。{published_human}</p></footer>
</article>
</body>
</html>
"""


class StaticSitePublisher(SitePublisher):
    def __init__(self, site_dir: str, base_url: str):
        self._site_dir = site_dir
        self._reports_dir = os.path.join(site_dir, "reports")
        self._base_url = base_url.rstrip("/")
        os.makedirs(self._reports_dir, exist_ok=True)

    def _report_link(self, slug: str) -> str:
        return f"{self._base_url}/reports/{slug}.html"

    def write_report_page(self, report: Report) -> FeedItem:
        slug = report.slug
        published = report.generated_at.astimezone(timezone.utc)
        paragraphs_html = "\n".join(
            f"<p>{html.escape(p)}</p>" for p in report.paragraphs
        )
        content = _REPORT_TEMPLATE.format(
            meta_title=html.escape(report.title, quote=True),
            slug=html.escape(slug, quote=True),
            published_iso=published.isoformat(),
            meta_keyword=html.escape(report.keyword.title, quote=True),
            generated_by=html.escape(report.generated_by, quote=True),
            title=html.escape(report.title),
            paragraphs=paragraphs_html,
            keyword=html.escape(report.keyword.title),
            published_human=published.strftime("%Y-%m-%d %H:%M UTC"),
        )
        path = os.path.join(self._reports_dir, f"{slug}.html")
        with open(path, "w", encoding="utf-8") as fp:
            fp.write(content)
        return FeedItem(
            title=report.title,
            link=self._report_link(slug),
            guid=self._report_link(slug),
            published_at=published,
        )

    _META_RE = {
        key: re.compile(
            rf'<meta name="kd:{key}" content="([^"]*)"', re.IGNORECASE
        )
        for key in ("title", "slug", "published")
    }

    def list_existing_items(self) -> list[FeedItem]:
        items: list[FeedItem] = []
        if not os.path.isdir(self._reports_dir):
            return items
        for name in os.listdir(self._reports_dir):
            if not name.endswith(".html"):
                continue
            path = os.path.join(self._reports_dir, name)
            try:
                with open(path, "r", encoding="utf-8") as fp:
                    head = fp.read(4096)
            except OSError:
                continue
            meta = {}
            for key, pattern in self._META_RE.items():
                m = pattern.search(head)
                if m:
                    meta[key] = html.unescape(m.group(1))
            slug = meta.get("slug") or name[:-5]
            title = meta.get("title") or slug
            try:
                published = datetime.fromisoformat(meta["published"])
            except (KeyError, ValueError):
                published = datetime.fromtimestamp(
                    os.path.getmtime(path), tz=timezone.utc
                )
            link = self._report_link(slug)
            items.append(
                FeedItem(title=title, link=link, guid=link, published_at=published)
            )
        return items

    def write_feed(self, feed: Feed) -> None:
        # RSS 2.0
        parts = [
            '<?xml version="1.0" encoding="UTF-8"?>',
            '<rss version="2.0">',
            "<channel>",
            f"<title>{html.escape(feed.title)}</title>",
            f"<link>{html.escape(feed.link)}</link>",
            f"<description>{html.escape(feed.description)}</description>",
            "<language>ja</language>",
            f"<lastBuildDate>{format_datetime(datetime.now(timezone.utc))}</lastBuildDate>",
        ]
        for item in feed.items:
            parts.extend(
                [
                    "<item>",
                    f"<title>{html.escape(item.title)}</title>",
                    f"<link>{html.escape(item.link)}</link>",
                    f'<guid isPermaLink="true">{html.escape(item.guid)}</guid>',
                    f"<pubDate>{format_datetime(item.published_at)}</pubDate>",
                    "</item>",
                ]
            )
        parts.extend(["</channel>", "</rss>", ""])
        with open(
            os.path.join(self._site_dir, "feed.xml"), "w", encoding="utf-8"
        ) as fp:
            fp.write("\n".join(parts))
        self._write_index(feed)

    def _write_index(self, feed: Feed) -> None:
        rows = "\n".join(
            f'<li><a href="{html.escape(i.link)}">{html.escape(i.title)}</a> '
            f"<small>{i.published_at:%Y-%m-%d}</small></li>"
            for i in feed.items
        )
        page = (
            "<!DOCTYPE html>\n<html lang=\"ja\"><head><meta charset=\"utf-8\">"
            "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
            f"<title>{html.escape(feed.title)}</title></head><body>"
            f"<h1>{html.escape(feed.title)}</h1>"
            f'<p><a href="feed.xml">RSS フィード</a></p><ul>\n{rows}\n</ul>'
            "</body></html>\n"
        )
        with open(
            os.path.join(self._site_dir, "index.html"), "w", encoding="utf-8"
        ) as fp:
            fp.write(page)
