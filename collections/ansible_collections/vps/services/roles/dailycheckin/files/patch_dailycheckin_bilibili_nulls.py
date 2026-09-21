from pathlib import Path

import dailycheckin.bilibili.main as bili_main_module


path = Path(bili_main_module.__file__)
source = path.read_text(encoding="utf-8")


def ensure_replace(old: str, new: str, *, count: int = 1) -> None:
    global source
    if new in source:
        return
    if old not in source:
        raise RuntimeError(f"patch target not found: {old[:80]!r}")
    source = source.replace(old, new, count)


ensure_replace(
    'import requests\n\nfrom dailycheckin import CheckIn\n',
    'import requests\n\nfrom dailycheckin import CheckIn\n\n\ndef safe_json(response, fallback: dict, context: str) -> dict:\n    try:\n        data = response.json()\n    except Exception as exc:\n        text = getattr(response, "text", "")[:200].replace("\\n", " ")\n        print(f"Bilibili {context} JSON 解析失败: {exc}; status={getattr(response, \'status_code\', \'unknown\')}; body={text}")\n        return fallback\n    return data if isinstance(data, dict) else fallback\n\n',
)

ensure_replace(
    'session.get(url=url).json().get("data").get("list")',
    '(session.get(url=url).json().get("data") or {}).get("list") or []',
    count=2,
)

ensure_replace(
    '        data = ret.get("data")\n',
    '        data = ret.get("data") or {}\n',
    count=1,
)

ensure_replace(
    'for one in ret.get("data", {}).get("archives", [])',
    'for one in (ret.get("data") or {}).get("archives") or []',
    count=1,
)

ensure_replace(
    '        ret = session.post(url=url, data=post_data).json()\n        return ret\n',
    '        ret = safe_json(session.post(url=url, data=post_data), {"code": -1, "message": "invalid json", "data": {}}, "vip_privilege_receive")\n        return ret\n',
    count=1,
)

ensure_replace(
    '        ret = session.post(url=url, json={"reason_id": 1}).json()\n        return ret\n',
    '        ret = safe_json(session.post(url=url, json={"reason_id": 1}), {"code": -1, "message": "invalid json", "data": {}}, "vip_manga_reward")\n        return ret\n',
    count=1,
)

ensure_replace(
    '        ret = session.post(url=url, data=post_data).json()\n        return ret\n',
    '        ret = safe_json(session.post(url=url, data=post_data), {"code": -1, "message": "invalid json", "data": {}}, "report_task")\n        return ret\n',
    count=1,
)

ensure_replace(
    '        ret = session.post(url=url, data=post_data).json()\n        return ret\n',
    '        ret = safe_json(session.post(url=url, data=post_data), {"code": -1, "message": "invalid json", "data": {}}, "share_task")\n        return ret\n',
    count=1,
)

silver_old = '''    @staticmethod
    def silver2coin(session, bili_jct) -> dict:
        """B站银瓜子换硬币"""
        url = "https://api.live.bilibili.com/xlive/revenue/v1/wallet/silver2coin"
        post_data = {"csrf": bili_jct}
        ret = session.post(url=url, data=post_data).json()
        return ret
'''
silver_new = '''    @staticmethod
    def silver2coin(session, bili_jct) -> dict:
        """B站银瓜子换硬币"""
        url = "https://api.live.bilibili.com/xlive/revenue/v1/wallet/silver2coin"
        post_data = {"csrf": bili_jct}
        ret = safe_json(session.post(url=url, data=post_data), {"code": -1, "message": "invalid json", "data": {}}, "silver2coin")
        return ret
'''
ensure_replace(silver_old, silver_new, count=1)

ensure_replace(
    '        ret = session.post(url=url, data=post_data).json()\n\n        return ret\n',
    '        ret = safe_json(session.post(url=url, data=post_data), {"code": -1, "message": "invalid json", "data": {}}, "coin_add")\n\n        return ret\n',
    count=1,
)

ensure_replace(
    '        ret = session.get(url=url, params=params).json()\n        return ret\n',
    '        ret = safe_json(session.get(url=url, params=params), {"code": -1, "message": "invalid json", "data": {}}, "get_followings")\n        return ret\n',
    count=1,
)

ensure_replace(
    '        ret = session.get(url=url, params=params).json()\n        count = 2\n',
    '        ret = safe_json(session.get(url=url, params=params), {"code": -1, "message": "invalid json", "data": {}}, "space_arc_search")\n        count = 2\n',
    count=1,
)

if '无可用视频，跳过观看任务' not in source:
    start_marker = '            aid = aid_list[0].get("aid")\n'
    end_marker = '            s2c_msg = "不兑换硬币"\n'
    start = source.find(start_marker)
    end = source.find(end_marker)
    if start == -1 or end == -1 or end <= start:
        raise RuntimeError('patch target not found: main aid_list block range')
    replacement = (
        '            report_msg = "无可用视频，跳过观看任务"\n'
        '            share_msg = "无可用视频，跳过分享任务"\n'
        '            if aid_list:\n'
        '                aid = aid_list[0].get("aid")\n'
        '                cid = aid_list[0].get("cid")\n'
        '                title = aid_list[0].get("title")\n'
        '                report_ret = self.report_task(session=session, bili_jct=bili_jct, aid=aid, cid=cid)\n'
        '                if report_ret.get("code") == 0:\n'
        '                    report_msg = f"观看《{title}》300秒"\n'
        '                else:\n'
        '                    report_msg = "任务失败"\n'
        '                share_ret = self.share_task(session=session, bili_jct=bili_jct, aid=aid)\n'
        '                if share_ret.get("code") == 0:\n'
        '                    share_msg = f"分享《{title}》成功"\n'
        '                else:\n'
        '                    share_msg = "分享失败"\n'
        '                    print(share_msg)\n'
        '            else:\n'
        '                print("Bilibili: 未获取到可用视频，跳过观看/分享任务")\n'
    )
    source = source[:start] + replacement + source[end:]

required_markers = [
    'def safe_json(response, fallback: dict, context: str) -> dict:',
    '(session.get(url=url).json().get("data") or {}).get("list") or []',
    'data = ret.get("data") or {}',
    '(ret.get("data") or {}).get("archives") or []',
    'vip_privilege_receive")',
    'vip_manga_reward")',
    'report_task")',
    'share_task")',
    'silver2coin")',
    'coin_add")',
    'get_followings")',
    'space_arc_search")',
    '无可用视频，跳过观看任务',
]
for marker in required_markers:
    if marker not in source:
        raise RuntimeError(f"patch marker missing: {marker}")

path.write_text(source, encoding="utf-8")
print(f"patched {path}")
