import html
import re

import blivedm.models.web as web_models

DANMAKU_EMOTICON_MAX_HEIGHT = 34
DANMAKU_EMOTICON_MAX_WIDTH = 140


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
    emoticon_url = danmaku_emoticon_url(message)
    if emoticon_url:
        return _danmaku_emoticon_image_html(message.msg, message.emoticon_options_dict)
    return danmaku_inline_emoticon_content_html(message)


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
