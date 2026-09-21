from pathlib import Path

import dailycheckin.utils.message as message_module


def replace_once(source: str, old: str, new: str) -> str:
    if old not in source:
        raise RuntimeError(f"patch target not found: {old[:80]!r}")
    return source.replace(old, new, 1)


path = Path(message_module.__file__)
source = path.read_text(encoding="utf-8")

source = replace_once(
    source,
    """def message2telegram(tg_api_host, tg_proxy, tg_bot_token, tg_user_id, content):
    print("Telegram 推送开始")
    send_data = {
        "chat_id": tg_user_id,
        "text": content,
        "disable_web_page_preview": "true",
    }
    if tg_api_host:
        url = f"https://{tg_api_host}/bot{tg_bot_token}/sendMessage"
    else:
        url = f"https://api.telegram.org/bot{tg_bot_token}/sendMessage"
    if tg_proxy:
        proxies = {
            "http": tg_proxy,
            "https": tg_proxy,
        }
    else:
        proxies = None
    requests.post(url=url, data=send_data, proxies=proxies)
""",
    """def message2telegram(tg_api_host, tg_proxy, tg_bot_token, tg_user_id, content):
    print("Telegram 推送开始")
    send_data = {
        "chat_id": tg_user_id,
        "text": content,
        "disable_web_page_preview": "true",
    }
    if tg_api_host:
        url = f"https://{tg_api_host}/bot{tg_bot_token}/sendMessage"
    else:
        url = f"https://api.telegram.org/bot{tg_bot_token}/sendMessage"
    if tg_proxy:
        proxies = {
            "http": tg_proxy,
            "https": tg_proxy,
        }
    else:
        proxies = None
    preview_head = content[:300].replace("\\n", "\\\\n")
    preview_tail = content[-300:].replace("\\n", "\\\\n")
    print(f"Telegram 消息长度: {len(content)}")
    print(f"Telegram 消息预览(前300): {preview_head}")
    if len(content) > 300:
        print(f"Telegram 消息预览(后300): {preview_tail}")
    response = requests.post(url=url, data=send_data, proxies=proxies)
    print(f"Telegram 响应状态: {response.status_code}")
    print(f"Telegram 响应体: {response.text[:1000]}")
    response.raise_for_status()
    payload = response.json()
    if not payload.get("ok", False):
        raise ValueError(f"Telegram API 返回失败: {payload}")
""",
)

source = replace_once(
    source,
    """    if not merge_push:
        message_list = content_list
    for message in message_list:
""",
    """    if not merge_push:
        message_list = content_list
    print(f"推送消息数: {len(message_list)}")
    for index, message in enumerate(message_list, start=1):
        print(f"第 {index} 条推送长度: {len(message)}")
        if index <= 3:
            preview = message[:200].replace(chr(10), "\\\\n")
            print(f"第 {index} 条推送预览(前200): {preview}")
""",
)

path.write_text(source, encoding="utf-8")
print(f"patched {path}")
