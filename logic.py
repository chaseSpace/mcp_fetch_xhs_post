import asyncio
import sys
import typing
from asyncio import Queue, to_thread
from urllib.parse import urlparse

from DrissionPage import ChromiumOptions, WebPage
from DrissionPage.items import MixTab
from lxml import html

from model import DetailPageInfo
from util import send_dingtalk_markdown, readable_time, countdown

tab_q = Queue()

SAFE_CHECK_TRIGGERED = False


def get_os_type():
    if sys.platform.startswith("darwin"):
        return "macOS"
    elif sys.platform.startswith("linux"):
        return "Linux"
    else:
        return "Windows"


def new_browser() -> WebPage:
    ostyp = get_os_type()
    print('ostyp:', ostyp)
    # ostyp = 'Linux'
    co = ChromiumOptions()
    if ostyp == 'Linux':
        co = (co.headless().set_argument('--disable-blink-features', 'AutomationControlled'))
        co.set_argument('--no-sandbox')
        co.set_argument('--disable-infobars')
        co.set_argument('--enable-automation')
    page = WebPage(chromium_options=co)
    page.set.user_agent(
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36')
    return page


def anti_headless_check(tab: MixTab) -> bool:
    if tab.title == '安全限制':
        return True
    print('无安全限制。')
    with open('qrcode.html', 'wb') as f:
        f.write(tab.html.encode('utf-8'))
    return False


def is_user_loggined(tab: MixTab, timeout: float = 5) -> typing.Callable[[], bool]:
    # me = tab.ele('@@tag()=li@@class="user side-bar-component"', timeout=timeout)
    def core():
        me = tab.ele('xpath://li[@class="user side-bar-component"]', timeout=timeout)
        return True if me else False

    return core


async def new_browser_and_search(search: str) -> tuple[dict, str]:
    tab = new_browser().latest_tab
    # tab.change_mode()  # silent mode
    notes_api = 'edith.xiaohongshu.com/api/sns/web/v1/search/notes'

    tab.get(f'https://www.xiaohongshu.com/search_result?keyword={search}')

    # 若已登录，显示【我】
    if not is_user_loggined(tab)():
        # 若未登录，应该显示二维码
        qrcode = tab.ele('xpath://img[@class="qrcode-img"]', timeout=5)
        if not qrcode:
            print(tab.user_agent)
            anti_headless_check(tab)
            return {}, "网页错误，请联系开发者检查"
        qrcode = qrcode.attrs['src']  # data:image...
        resp = send_dingtalk_markdown('扫码登录',
                                      f'- 时间: {readable_time()}\n'
                                      f'- OS: {get_os_type()}\n'
                                      f'- 提示：请使用手机版小红书app扫码登录，程序等待30s',
                                      [qrcode])
        if resp['errcode'] != 0:
            return {}, "发送钉钉消息失败，请联系开发者检查"
        ok = countdown('等待扫码中', 30, is_user_loggined(tab, timeout=.1))
        if not ok:
            return {}, "等待登录超时，程序结束。"
        # js读取用户信息
        js_res = tab.run_js("x = JSON.stringify(window.__INITIAL_STATE__['user']['userInfo'].value); JSON.parse(x)",
                            as_expr=True)
        if js_res and js_res.get("nickname"):
            send_dingtalk_markdown('登录成功',
                                   f'- 时间: {readable_time()}\n- 提示：用户【{js_res.get("nickname")}】登录成功！')
        else:
            print('Warning：登录成功，但未能读取到用户信息！')

    tab.listen.start(notes_api)
    # 访问搜索页
    tab.get(f'https://www.xiaohongshu.com/search_result?keyword={search}')

    packet = tab.listen.wait(timeout=5)
    if (not packet or packet.response.status != 200 or
            not isinstance(packet.response.body, dict)
            or packet.response.body['code'] != 0):
        # 检查浏览器是否触发验证，需手动处理
        print('Error: 错误的body格式', packet.response.body, type(packet.response.body))
        return {}, f"监听请求失败：/search/notes"

    req = packet.request
    req.postData['sort'] = 'popularity_descending'
    req.postData['note_type'] = 2  # 图文
    headers = dict(req.headers)
    headers.pop('content-length')
    resp = tab.post('https://' + notes_api, headers=headers, cookies=tab.cookies().as_dict(), json=req.postData,
                    timeout=3)
    if not resp or resp.status_code != 200:
        return {}, f"请求失败：{resp.status_code}"
    return resp.json(), ''


async def fetch_posts_detail_core(i: int, url: str) -> DetailPageInfo:
    if SAFE_CHECK_TRIGGERED:
        return DetailPageInfo()
    tab: MixTab = await tab_q.get()
    await asyncio.to_thread(tab.get, url)

    if await safe_check_triggered(tab):
        return DetailPageInfo()

    note_id = urlparse(url).path.split('/')[-1]

    desc = await to_thread(tab, 'xpath://div[@id="detail-desc"]/span[@class="note-text"]/span[1]', timeout=5)
    desc = desc.text if desc else ''

    tree = html.fromstring(tab.html)
    player = tree.xpath('//video[@mediatype="video"]')

    video_url = ''
    if player:
        video_url = player[0].get('src', '').removeprefix('blob:')
    tags = tree.xpath('//div[@id="detail-desc"]/span[@class="note-text"]/a[@id="hash-tag"]')
    if tags:
        tags = [tag.text for tag in tags]
    await tab_q.put(tab)

    print(f'获取到第{i}个详情')
    return DetailPageInfo(
        note_id=note_id,
        url=url,
        video_url=video_url,
        desc=desc,
        tags=tags
    )


async def fetch_posts_detail(items: dict) -> dict[str, DetailPageInfo]:
    tab_list = []
    for _ in range(3):  # 详情页的并发数
        t = new_browser().new_tab()
        t.set.load_mode.none()
        tab_list.append(t)
        await tab_q.put(t)

    urls = []
    for note_id, xsec_token in items.items():
        u = f'https://www.xiaohongshu.com/search_result/{note_id}?xsec_token={xsec_token}&xsec_source=pc_search'
        urls.append(u)

    global SAFE_CHECK_TRIGGERED
    SAFE_CHECK_TRIGGERED = False

    # 创建任务列表
    tasks = [fetch_posts_detail_core(i, url) for i, url in enumerate(urls)]

    # 并发运行任务
    results: list[DetailPageInfo] = await asyncio.gather(*tasks)
    ret = {v.note_id: v for v in results}

    await quit_browser(tab_list)
    return ret


async def safe_check_triggered(tab: MixTab) -> bool:
    if tab.title == '安全验证':
        global SAFE_CHECK_TRIGGERED
        SAFE_CHECK_TRIGGERED = True
        print('触发滑动验证！！！请手动访问小红书网站处理')
        send_dingtalk_markdown('触发验证',
                               f'- 时间：{readable_time()}\n- 提示：账户触发滑动验证码，请手动访问小红书网站处理！')
        return True
    return False


def clean_browser_tab():
    try:
        tab_list = new_browser().get_tabs()
        if tab_list:
            tab_list = tab_list[:-1]  # 保留1个
            for t in tab_list:
                t.close()
    except Exception as e:
        print(f'关闭浏览器异常: {e}')


async def quit_browser(tab_list: list[MixTab]):
    try:
        # 释放资源
        for t in tab_list:
            t.close()
        # new_browser().quit()
    except Exception as e:
        print(f'退出异常: {e}')


async def main():
    try:
        data, msg = await new_browser_and_search('装机')
        items = data.get('data', {}).get('items')
        if not msg:
            if len(items) > 5:
                items = items[:5]
            r = await fetch_posts_detail({v['id']: v['xsec_token'] for v in items})
            for v in r.values():
                print(v.desc)
        print(msg)
    finally:
        ...


if __name__ == '__main__':
    from util import load_env

    load_env()
    asyncio.run(main())
