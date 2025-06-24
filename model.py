import asyncio
import json


class DetailPageInfo:
    def __init__(self, **kwargs):
        self.note_id = kwargs.get('note_id')
        self.url = kwargs.get('url')
        self.video_url = kwargs.get('video_url', '')
        self.is_video = self.video_url != ''
        self.desc = kwargs.get('desc')
        self.tags = kwargs.get('tags')


class Comment:
    def __init__(self, **kwargs):
        self.user_name = kwargs.get('user_name')
        self.content = kwargs.get('content')
        self.liked_count = kwargs.get('liked_count')


class Post:
    note_id: str = ""
    title: str = ""
    desc: str = ""
    url: str = ""
    publish_time: str = ""  # 2023-01-01
    publish_user_name: str = ""
    publish_user_id: str = ""
    ptype: str = ""  # image+text video+text
    liked_count: int = 0
    collected_count: int = 0
    comment_count: int = 0
    shared_count: int = 0
    cover_url: str = ""
    video_url: str = ""
    images: list[str] = []
    tags: list[str] = []
    comments: list[Comment] = []  # todo

    # ip_location: str = ''

    def __init__(self, detail: DetailPageInfo, **kwargs):
        self.note_id = kwargs.get('note_id')
        self.title = kwargs.get('title')
        self.publish_time = kwargs.get('publish_time')
        self.publish_user_name = kwargs.get('publish_user_name')
        self.ptype = kwargs.get('ptype')
        self.liked_count = kwargs.get('liked_count')
        self.collected_count = kwargs.get('collected_count')
        self.comment_count = kwargs.get('comment_count')
        self.shared_count = kwargs.get('shared_count')
        self.cover_url = kwargs.get('cover_url')
        self.images = kwargs.get('images', [])

        # detail页面信息
        self.desc = detail.desc
        self.tags = detail.tags
        self.video_url = detail.video_url
        self.url = detail.url

    def json(self):
        return json.dumps(self.__dict__)

    async def to_markdown(self) -> str:
        markdown_str = f"**标题** {self.title}\n"
        markdown_str += f"**内容**:{self.desc}\n"
        # markdown_str += f"**URL**:{self.url}\n"
        markdown_str += f"**帖子id**: {self.note_id}\n"
        markdown_str += f"**发布日期**: {self.publish_time}\n"
        markdown_str += f"**发布者**: {self.publish_user_name}\n"
        markdown_str += f"**发布类型**: {self.ptype}\n"
        markdown_str += f"**点赞数**: {self.liked_count}\n"
        markdown_str += f"**收藏数**: {self.collected_count}\n"
        markdown_str += f"**评论数**: {self.comment_count}\n"
        markdown_str += f"**分享数**: {self.shared_count}\n"
        markdown_str += f"**标签**: {self.tags}\n"
        # markdown_str += f"**封面图片**: {self.cover_url}\n"
        # markdown_str += f"**IP 地址**: {self.ip_location}\n"

        # if self.images:
        #     markdown_str += f"**图片**:\n"
        #     for img in self.images:
        #         markdown_str += f"- {img}\n"
        # print(markdown_str)
        return markdown_str


class MultiPost:
    posts: list[Post]

    def __init__(self, items: dict, detail_dict: dict):
        self.posts = []
        for item in items:
            note_id = item.get('id')
            model_type = item.get('model_type')
            if model_type != 'note':
                continue
            note_card = item.get('note_card')
            title = note_card.get('display_title')
            if not title or not note_id:
                continue

            publish_time = self.parse_pubtime(note_card)
            cover_url = note_card.get('cover', {}).get('url_default')
            images = self.parse_images(note_card)
            ptype = self.parse_type(note_card.get('type'))
            liked_count = note_card.get('interact_info', {}).get('liked_count', 0)
            collected_count = note_card.get('interact_info', {}).get('collected_count', 0)
            comment_count = note_card.get('interact_info', {}).get('comment_count', 0)
            shared_count = note_card.get('interact_info', {}).get('shared_count', 0)
            publisher = note_card.get('user', {}).get('nickname')
            publisher_uid = note_card.get('user', {}).get('user_id')
            self.posts.append(Post(
                detail_dict.get(note_id, DetailPageInfo()),
                note_id=note_id,
                title=title,
                publish_time=publish_time,
                cover_url=cover_url,
                images=images,
                ptype=ptype,
                liked_count=liked_count,
                collected_count=collected_count,
                comment_count=comment_count,
                shared_count=shared_count,
                publish_user_name=publisher,
                publish_user_id=publisher_uid,
            ))

    def parse_pubtime(self, item: dict):
        ss = item.get('corner_tag_info', [{}])
        for s in ss:
            if s['type'] == 'publish_time':
                return s.get('text')
        return ''

    def parse_images(self, item: dict):
        images = []
        for img in item.get('image_list', []):
            ss = img.get('info_list', [])
            url = ss[0]['url'] if ss else ''
            if url:
                images.append(url)
        return images

    def parse_type(self, typ: str):
        if typ == 'normal':
            return 'image+text'
        elif typ == 'video':
            return 'video+text'
        else:
            return typ

    async def to_markdown(self) -> str:
        output = ''
        for i, post in enumerate(self.posts):
            output += f"\n############ 第 {i + 1} 篇帖子 ############\n\n"
            output += await post.to_markdown()
        return output


if __name__ == '__main__':
    p = Post(
        DetailPageInfo(),
        note_id="6847a7b4000000002100af92",
        title="我的第一篇帖子",
        content="这是一个测试帖子的内容。",
        publish_time="2023-01-01",
        publish_user_name="张三",
        publish_user_id="user123",
        ptype="image+text",
        liked_count=10,
        collected_count=5,
        comment_count=3,
        shared_count=2,
        cover_url="https://example.com/cover.jpg",
        images=["https://example.com/image1.jpg", "https://example.com/image2.jpg"],
        tags=["测试", "Python", "Markdown"],
        ip_location="北京"
    )

    asyncio.run(p.to_markdown())
