import logging

from mcp.server.fastmcp import FastMCP
from tenacity import retry, stop_after_attempt, wait_fixed

from logic import new_browser_and_search, fetch_posts_detail, clean_browser_tab
from model import MultiPost
from util import tool_hook_before, load_env

load_env()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

mcp = FastMCP("XhsServer", host="0.0.0.0", port=9090)

url = "https://edith.xiaohongshu.com/api/sns/web/v1/search/notes"


@mcp.tool()
@retry(stop=stop_after_attempt(3), wait=wait_fixed(.2),
       before=tool_hook_before(logger, logging.INFO, [clean_browser_tab]))
async def fetch_xhs_hot_post(search: str, limit: int = 5) -> str | Exception:
    """
    从 小红书 获取爆款帖子数据
    :param search: 搜索主题，长度不超过15个字
    :param limit: 获取帖子数量，较多会增加耗时，不超过10
    :return: markdown形式的帖子数据
    """
    if len(search) > 15:
        return "Error: 搜索字符串长度不能超过15个字"
    data, msg = await new_browser_and_search(search)
    if msg:
        raise Exception(msg)
    if not data or not data.get('data', {}).get('items'):
        return Exception('无数据')
    items = data.get('data', {}).get('items')
    if len(items) > limit:
        items = items[:limit]

    detail_dict = await fetch_posts_detail({v['id']: v['xsec_token'] for v in items})
    output = await MultiPost(items, detail_dict).to_markdown()
    if output:
        print(f'本次调用成功，返回{len(detail_dict)}个结果')
    else:
        print('本次调用失败')
    return output


def main():
    mcp.run(transport='sse')


if __name__ == '__main__':
    # v = asyncio.run(fetch_xhs_hot_post("装机"))
    # print(v)
    # exit(1)
    main()
