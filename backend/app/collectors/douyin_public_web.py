import re
import shutil
import subprocess
import tempfile
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse

from app.collectors.base import (
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


class DouyinPublicWebCollector:
    collector_type = "douyin_public_web"
    version = "douyin-public-web-v1"
    content_status = "unavailable"

    def __init__(self) -> None:
        self.warnings: list[str] = []

    def fetch_creator_profile(self, creator: CreatorAccount) -> CreatorProfile:
        if creator.platform != "douyin":
            raise CollectorValidationError("抖音公开主页采集器只能用于抖音账号")
        self._validate_profile_url(creator.profile_url)
        html = self._render_profile(creator.profile_url)
        profile = parse_douyin_profile_html(html, creator.platform_account_id)
        self.warnings = [
            "账号指标来自抖音公开主页；当前真实采集器尚未接入作品明细。"
        ]
        if "服务异常" in html:
            self.warnings = ["抖音作品列表本次返回服务异常；账号公开指标已正常采集。"]
        return profile

    def fetch_content_posts(self, creator: CreatorAccount) -> list[ContentProfile]:
        return []

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
            try:
                result = subprocess.run(
                    command,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=settings.douyin_render_timeout_seconds,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                    check=False,
                )
            except subprocess.TimeoutExpired as exc:
                raise CollectorRenderError("抖音公开主页渲染超时，请稍后重试") from exc

        if result.returncode != 0:
            detail = result.stderr.strip()[-300:] or f"退出码 {result.returncode}"
            raise CollectorRenderError(f"抖音公开主页渲染失败：{detail}")
        if len(result.stdout) < 1_000:
            raise CollectorRenderError("抖音公开主页未返回可解析内容")
        return result.stdout

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
        raise CollectorRenderError(
            "未找到 Microsoft Edge；请安装 Edge 或配置 DOUYIN_BROWSER_PATH"
        )
