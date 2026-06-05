import re
from urllib.parse import urlparse

_PUBLIC_URL_PATTERN = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)
_TRAILING_SHARE_PUNCTUATION = "，。！？；：、,.;!?)]}】》”’"
_DOUYIN_SHARE_HOSTS = {"v.douyin.com", "iesdouyin.com", "www.iesdouyin.com"}


def normalize_profile_url(value: str) -> str:
    """Extract a single public URL from copied platform share text."""

    raw_value = value.strip()
    match = _PUBLIC_URL_PATTERN.search(raw_value)
    if match is None:
        raise ValueError("账号主页地址必须是有效的 HTTP(S) 链接")

    normalized = match.group(0).rstrip(_TRAILING_SHARE_PUNCTUATION)
    matched_url = urlparse(normalized)
    is_share_text = match.start() > 0 or matched_url.hostname in _DOUYIN_SHARE_HOSTS

    if any(character.isspace() for character in raw_value) and not is_share_text:
        raise ValueError("账号主页地址不能包含空格，请粘贴完整主页链接或平台分享文案")

    parsed = urlparse(normalized)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("账号主页地址必须是有效的 HTTP(S) 链接")
    return normalized
