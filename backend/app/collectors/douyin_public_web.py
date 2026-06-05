import os
import re
import shutil
import subprocess
import tempfile
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlparse

from app.collectors.base import (
    CollectorConfigurationError,
    CollectorParseError,
    CollectorRenderError,
    CollectorValidationError,
    ContentProfile,
    CreatorProfile,
)
from app.core.config import settings
from app.models.creator import CreatorAccount


class _DouyinPageParser(HTMLParser):
    _void_tags = {
        "area",
        "base",
        "br",
        "col",
        "embed",
        "hr",
        "img",
        "input",
        "link",
        "meta",
        "param",
        "source",
        "track",
        "wbr",
    }

    def __init__(self) -> None:
        super().__init__()
        self._marker_stack: list[str | None] = []
        self._in_title = False
        self._body_depth = 0
        self.title_parts: list[str] = []
        self.body_parts: list[str] = []
        self.marker_text: dict[str, list[str]] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = dict(attrs)
        if tag not in self._void_tags:
            self._marker_stack.append(attr_map.get("data-e2e"))
        if tag == "title":
            self._in_title = True
        if tag == "body":
            self._body_depth += 1

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        return

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._in_title = False
        if tag == "body":
            self._body_depth = max(0, self._body_depth - 1)
        if tag not in self._void_tags and self._marker_stack:
            self._marker_stack.pop()

    def handle_data(self, data: str) -> None:
        text = " ".join(data.split())
        if not text:
            return
        if self._in_title:
            self.title_parts.append(text)
        if self._body_depth:
            self.body_parts.append(text)
        for marker in dict.fromkeys(item for item in self._marker_stack if item):
            self.marker_text.setdefault(marker, []).append(text)

    def texts(self, marker: str) -> list[str]:
        return self.marker_text.get(marker, [])


class _DouyinContentParser(HTMLParser):
    """Only collect video links located inside the account's public post list."""

    _video_path = re.compile(r"/video/(\d{15,25})(?:[/?#]|$)")

    def __init__(self) -> None:
        super().__init__()
        self._post_list_stack: list[bool] = []
        self._current_anchor: dict | None = None
        self._seen_ids: set[str] = set()
        self.posts: list[ContentProfile] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = dict(attrs)
        parent_in_post_list = self._post_list_stack[-1] if self._post_list_stack else False
        in_post_list = parent_in_post_list or attr_map.get("data-e2e") == "user-post-list"
        if tag not in _DouyinPageParser._void_tags:
            self._post_list_stack.append(in_post_list)

        if in_post_list and tag == "a":
            href = attr_map.get("href") or ""
            match = self._video_path.search(href)
            if match:
                self._current_anchor = {
                    "platform_content_id": match.group(1),
                    "content_url": urljoin("https://www.douyin.com", href),
                    "title_parts": [
                        value
                        for value in (attr_map.get("aria-label"), attr_map.get("title"))
                        if value
                    ],
                    "cover_url": None,
                }
        elif in_post_list and tag == "img" and self._current_anchor is not None:
            self._current_anchor["cover_url"] = (
                attr_map.get("src") or attr_map.get("data-src") or attr_map.get("data-original")
            )
            alt = attr_map.get("alt")
            if alt:
                self._current_anchor["title_parts"].append(alt)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag not in _DouyinPageParser._void_tags:
            self.handle_endtag(tag)

    def handle_data(self, data: str) -> None:
        if self._current_anchor is None:
            return
        text = " ".join(data.split())
        if text:
            self._current_anchor["title_parts"].append(text)

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._current_anchor is not None:
            self._finish_anchor()
        if tag not in _DouyinPageParser._void_tags and self._post_list_stack:
            self._post_list_stack.pop()

    def _finish_anchor(self) -> None:
        item = self._current_anchor
        self._current_anchor = None
        if item is None or item["platform_content_id"] in self._seen_ids:
            return
        self._seen_ids.add(item["platform_content_id"])
        title = " ".join(dict.fromkeys(item["title_parts"])).strip()
        if not title:
            title = f"抖音作品 {item['platform_content_id']}"
        self.posts.append(
            ContentProfile(
                platform_content_id=item["platform_content_id"],
                title=title[:500],
                summary=None,
                content_type="video",
                content_url=item["content_url"],
                cover_url=item["cover_url"],
                published_at=None,
                like_count=0,
                comment_count=0,
                collect_count=0,
                share_count=0,
                metrics_status="unavailable",
                raw_data={
                    "source": "douyin_public_web",
                    "scope": "user-post-list",
                    "metrics_status": "unavailable",
                },
            )
        )


def parse_compact_number(value: str) -> int:
    normalized = value.strip().replace(",", "").replace(" ", "")
    match = re.fullmatch(r"(\d+(?:\.\d+)?)([万亿]?)", normalized)
    if match is None:
        raise CollectorParseError(f"无法解析公开指标数值：{value}")
    multiplier = {"": 1, "万": 10_000, "亿": 100_000_000}[match.group(2)]
    return round(float(match.group(1)) * multiplier)


def _metric_value(parser: _DouyinPageParser, marker: str, label: str) -> int:
    candidates = [text for text in parser.texts(marker) if text != label]
    if not candidates:
        raise CollectorParseError(f"公开主页缺少“{label}”指标")
    return parse_compact_number(candidates[-1])


def parse_douyin_profile_html(html: str, expected_account_id: str) -> CreatorProfile:
    parser = _DouyinPageParser()
    parser.feed(html)

    title = "".join(parser.title_parts)
    nickname = title.removesuffix("的抖音 - 抖音").strip()
    user_info = parser.texts("user-info")
    if not nickname and user_info:
        nickname = user_info[0]
    if not nickname:
        raise CollectorParseError("公开主页缺少账号昵称")

    joined_info = " ".join(user_info)
    account_match = re.search(r"抖音号[：:]\s*([^\s]+)", joined_info)
    if account_match is None:
        raise CollectorParseError("公开主页缺少抖音号")
    actual_account_id = account_match.group(1)
    if actual_account_id != expected_account_id:
        raise CollectorValidationError(
            f"公开主页抖音号 {actual_account_id} 与配置账号 {expected_account_id} 不一致"
        )

    location_match = re.search(r"IP属地[：:]\s*([^\s]+)", joined_info)
    location = location_match.group(1) if location_match else None
    excluded = {
        nickname,
        "关注",
        "粉丝",
        "获赞",
        *parser.texts("user-info-follow"),
        *parser.texts("user-info-fans"),
        *parser.texts("user-info-like"),
    }
    bio_candidates = [
        text
        for text in user_info
        if text not in excluded
        and not text.startswith(("抖音号", "IP属地"))
        and not re.fullmatch(r"\d+(?:\.\d+)?[万亿]?", text)
    ]

    return CreatorProfile(
        nickname=nickname,
        avatar_url=None,
        bio=bio_candidates[-1] if bio_candidates else None,
        verified_info=None,
        location=location,
        follower_count=_metric_value(parser, "user-info-fans", "粉丝"),
        following_count=_metric_value(parser, "user-info-follow", "关注"),
        total_like_count=_metric_value(parser, "user-info-like", "获赞"),
        content_count=_metric_value(parser, "user-tab-count", "作品"),
    )


def parse_douyin_content_html(html: str) -> list[ContentProfile]:
    parser = _DouyinContentParser()
    parser.feed(html)
    return parser.posts


class DouyinPublicWebCollector:
    collector_type = "douyin_public_web"
    version = "douyin-public-web-v2"

    def __init__(self) -> None:
        self.content_status = "unavailable"
        self.warnings: list[str] = []
        self._rendered_html: str | None = None

    def fetch_creator_profile(self, creator: CreatorAccount) -> CreatorProfile:
        if creator.platform != "douyin":
            raise CollectorValidationError("抖音公开主页采集器只能用于抖音账号")
        self._validate_profile_url(creator.profile_url)
        html = self._render_profile(creator.profile_url)
        self._rendered_html = html
        profile = parse_douyin_profile_html(html, creator.platform_account_id)
        self.warnings = []
        if "服务异常" in html:
            self.warnings = ["抖音作品列表本次返回服务异常；账号公开指标已正常采集。"]
        return profile

    def fetch_content_posts(self, creator: CreatorAccount) -> list[ContentProfile]:
        html = self._rendered_html or self._render_profile(creator.profile_url)
        posts = parse_douyin_content_html(html)
        if posts:
            self.content_status = "partial"
            self.warnings.append(
                "已发现公开作品；当前作品列表未公开发布时间和互动指标，相关字段标记为不可用。"
            )
        elif not self.warnings:
            self.warnings.append("公开主页本次未返回可归属于该账号的作品卡片。")
        return posts

    @staticmethod
    def _validate_profile_url(profile_url: str) -> None:
        hostname = (urlparse(profile_url).hostname or "").lower()
        if hostname != "douyin.com" and not hostname.endswith(".douyin.com"):
            raise CollectorValidationError("真实抖音采集仅支持 douyin.com 公开主页或分享链接")

    def _render_profile(self, profile_url: str) -> str:
        browser_path = self._resolve_browser_path()
        with tempfile.TemporaryDirectory(prefix="creator-monitor-douyin-") as profile_dir:
            command = [
                browser_path,
                "--headless=new",
                "--disable-gpu",
                "--no-first-run",
                "--dump-dom",
                f"--virtual-time-budget={settings.douyin_virtual_time_budget_ms}",
                f"--user-data-dir={profile_dir}",
                profile_url,
            ]
            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(
                subprocess, "CREATE_NEW_PROCESS_GROUP", 0
            )
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=creationflags,
            )
            try:
                stdout, stderr = process.communicate(
                    timeout=settings.douyin_render_timeout_seconds,
                )
            except subprocess.TimeoutExpired as exc:
                self._terminate_process_tree(process)
                raise CollectorRenderError("抖音公开主页渲染超时，请稍后重试") from exc

        if process.returncode != 0:
            detail = stderr.strip()[-300:] or f"退出码 {process.returncode}"
            raise CollectorRenderError(f"抖音公开主页渲染失败：{detail}")
        if len(stdout) < 1_000:
            raise CollectorRenderError("抖音公开主页未返回可解析内容")
        return stdout

    @staticmethod
    def _terminate_process_tree(process: subprocess.Popen) -> None:
        """Terminate Edge and every child process created for this render."""

        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                capture_output=True,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                check=False,
            )
        if process.poll() is None:
            process.kill()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()

    @staticmethod
    def _resolve_browser_path() -> str:
        configured = settings.douyin_browser_path
        candidates = [
            configured,
            shutil.which("msedge"),
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        ]
        for candidate in candidates:
            if candidate and Path(candidate).is_file():
                return str(candidate)
        raise CollectorConfigurationError(
            "未找到 Microsoft Edge；请安装 Edge 或配置 DOUYIN_BROWSER_PATH"
        )
