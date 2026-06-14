import html
import re

import blivedm.models.web as web_models

DANMAKU_EMOTICON_MAX_HEIGHT = 34
DANMAKU_EMOTICON_MAX_WIDTH = 140
MEDAL_BADGE_COLOR = "#FF79C6"
WEALTH_BADGE_COLOR = "#C9B6FF"


def _badge(text: str, css_class: str, *, title: str = "", style: str = "") -> str:
    safe_text = html.escape(text, quote=True)
    safe_title = html.escape(title, quote=True)
    title_attr = f' title="{safe_title}"' if safe_title else ""
    style_attr = f' style="{style}"' if style else ""
    return f'<span class="meta-badge {css_class}"{title_attr}{style_attr}>{safe_text}</span>'


def _privilege_icon(privilege_type: int) -> str:
    return {
        1: "🛳︎",
        2: "⛴︎",
        3: "⚓︎",
    }.get(privilege_type, "")


def _privilege_color(privilege_type: int) -> str:
    return {
        1: "#FFD700",
        2: "#C9B6FF",
        3: "#86C8FF",
    }.get(privilege_type, "")


def danmaku_author_badges_html(message: web_models.DanmakuMessage) -> str:
    badges = []
    for badge in danmaku_author_badges(message):
        css_class = f"{badge['type']}-badge"
        style = f"color: {badge['color']};"
        badges.append(_badge(badge["text"], css_class, title=badge["title"], style=style))

    if not badges:
        return ""
    return "&nbsp;".join(badges) + "&nbsp;"


def danmaku_author_badges(message: web_models.DanmakuMessage) -> list[dict[str, str]]:
    badges: list[dict[str, str]] = []

    medal_name = str(getattr(message, "medal_name", "") or "").strip()
    medal_level = int(getattr(message, "medal_level", 0) or 0)
    if medal_name and medal_level > 0:
        badges.append(
            {
                "type": "medal",
                "text": f"{medal_name} {medal_level}",
                "title": "粉丝牌",
                "color": MEDAL_BADGE_COLOR,
            }
        )

    wealth_level = int(getattr(message, "wealth_level", 0) or 0)
    if wealth_level > 0:
        badges.append(
            {
                "type": "wealth",
                "text": f"✦ {wealth_level}",
                "title": "财富等级",
                "color": WEALTH_BADGE_COLOR,
            }
        )

    privilege_type = int(getattr(message, "privilege_type", 0) or 0)
    privilege_icon = _privilege_icon(privilege_type)
    if privilege_icon:
        badges.append(
            {
                "type": "privilege",
                "text": privilege_icon,
                "title": "大航海",
                "color": _privilege_color(privilege_type),
            }
        )

    return badges


def danmaku_reply_text(message: web_models.DanmakuMessage) -> str:
    extra = message.extra_dict
    if extra.get("show_reply") is False:
        return ""
    reply_uname = str(extra.get("reply_uname") or "").strip()
    if not reply_uname:
        return ""
    return f"@{reply_uname} "


def _danmaku_reply_html(message: web_models.DanmakuMessage) -> str:
    reply_text = danmaku_reply_text(message).rstrip()
    if not reply_text:
        return ""
    return f'<span class="reply">{html.escape(reply_text, quote=True)}&nbsp;</span>'


def _emoticon_option_url(options: dict) -> str:
    url = str(options.get("url") or "").strip()
    if not url.startswith(("http://", "https://")):
        return ""
    return url


def danmaku_emoticon_url(message: web_models.DanmakuMessage) -> str:
    if message.dm_type != 1:
        return ""
    return _emoticon_option_url(message.emoticon_options_dict)


def danmaku_inline_emoticons(message: web_models.DanmakuMessage) -> dict[str, dict]:
    emots = message.extra_dict.get("emots")
    if not isinstance(emots, dict):
        return {}

    inline_emoticons = {}
    for token, options in emots.items():
        if not token or not isinstance(options, dict):
            continue
        if not _emoticon_option_url(options):
            continue
        inline_emoticons[str(token)] = options
    return inline_emoticons


def danmaku_emoticon_scaled_size(options: dict) -> tuple[int, int]:
    try:
        source_width = int(options.get("width") or 0)
        source_height = int(options.get("height") or 0)
    except (TypeError, ValueError):
        source_width = 0
        source_height = 0

    if source_width <= 0 or source_height <= 0:
        return DANMAKU_EMOTICON_MAX_HEIGHT, DANMAKU_EMOTICON_MAX_HEIGHT

    scale = DANMAKU_EMOTICON_MAX_HEIGHT / source_height
    width = max(1, round(source_width * scale))
    height = DANMAKU_EMOTICON_MAX_HEIGHT
    if width > DANMAKU_EMOTICON_MAX_WIDTH:
        width = DANMAKU_EMOTICON_MAX_WIDTH
        height = max(1, round(source_height * (DANMAKU_EMOTICON_MAX_WIDTH / source_width)))
    return width, height


def _danmaku_emoticon_image_html(token: str, options: dict) -> str:
    width, height = danmaku_emoticon_scaled_size(options)
    alt = html.escape(token.strip() or "表情", quote=True)
    src = html.escape(_emoticon_option_url(options), quote=True)
    return f'<img class="emoticon" src="{src}" width="{width}" height="{height}" alt="{alt}" />'


def danmaku_inline_emoticon_content_html(message: web_models.DanmakuMessage) -> str:
    text = message.msg.strip()
    inline_emoticons = {
        token: options
        for token, options in danmaku_inline_emoticons(message).items()
        if token in text
    }
    if not inline_emoticons:
        return html.escape(text, quote=True)

    tokens = sorted(inline_emoticons, key=len, reverse=True)
    pattern = re.compile("|".join(re.escape(token) for token in tokens))
    parts = []
    last_end = 0
    for match in pattern.finditer(text):
        parts.append(html.escape(text[last_end:match.start()], quote=True))
        token = match.group(0)
        parts.append(_danmaku_emoticon_image_html(token, inline_emoticons[token]))
        last_end = match.end()
    parts.append(html.escape(text[last_end:], quote=True))
    return "".join(parts)


def danmaku_message_content_html(message: web_models.DanmakuMessage) -> str:
    reply_html = _danmaku_reply_html(message)
    emoticon_url = danmaku_emoticon_url(message)
    if emoticon_url:
        return reply_html + _danmaku_emoticon_image_html(message.msg, message.emoticon_options_dict)
    return reply_html + danmaku_inline_emoticon_content_html(message)


def danmaku_message_emoticon_urls(message: web_models.DanmakuMessage) -> list[str]:
    urls = []
    seen = set()

    pure_emoticon_url = danmaku_emoticon_url(message)
    if pure_emoticon_url:
        urls.append(pure_emoticon_url)
        seen.add(pure_emoticon_url)

    for token, options in danmaku_inline_emoticons(message).items():
        if token not in message.msg.strip():
            continue
        url = _emoticon_option_url(options)
        if url and url not in seen:
            urls.append(url)
            seen.add(url)

    return urls
