"""
LLM Prompt 模板 - 分类、摘要、质量检查
"""

CATEGORIES = [
    "AI", "政治", "娱乐", "科技", "财经",
    "体育", "健康", "科学", "生活", "教育", "其他",
]

CATEGORY_LABELS_EN = {
    "AI": "AI", "政治": "politics", "娱乐": "entertainment",
    "科技": "tech", "财经": "finance", "体育": "sports",
    "健康": "health", "科学": "science", "生活": "lifestyle",
    "教育": "education", "其他": "other",
}


def categorize_prompt(items_text: str) -> str:
    categories_str = ", ".join(CATEGORIES)
    return f"""你是一个内容分类专家。请对以下热门内容进行分类。

可用类别: {categories_str}

请为每条内容分配一个主要类别和最多3个标签。以JSON数组格式输出，每个元素包含:
- "id": 内容编号
- "category": 主要类别(必须从上述类别中选择)
- "tags": 标签列表(最多3个)
- "confidence": 置信度(0-1)

内容列表:
{items_text}

请直接输出JSON数组，不要包含其他内容:"""


def summarize_prompt_wechat(title: str, description: str, category: str) -> str:
    return f"""你是一个资深的微信公众号运营编辑。请基于以下热门内容，撰写一篇微信公众号文章。

原始标题: {title}
原始内容: {description}
类别: {category}

要求:
1. 标题: 吸引眼球但不标题党，15-30字
2. 正文: 800-1500字，结构清晰，段落分明
3. 开头: 引人入胜的导语
4. 主体: 深入分析，加入观点和见解
5. 结尾: 总结或引发思考
6. 风格: 专业但易读，适合公众号阅读

请以JSON格式输出:
{{"title": "文章标题", "body": "正文内容", "summary": "一句话摘要", "hashtags": ["#标签1", "#标签2"]}}"""


def summarize_prompt_xiaohongshu(title: str, description: str, category: str) -> str:
    return f"""你是一个小红书爆款笔记创作者。请基于以下热门内容，创作一篇小红书笔记。

原始标题: {title}
原始内容: {description}
类别: {category}

要求:
1. 标题: 带emoji，吸引点击，15-25字
2. 正文: 300-500字，口语化，分段清晰
3. 使用emoji装饰段落
4. 加入个人观点和态度
5. 结尾加互动引导(评论/收藏/关注)
6. 话题标签5-8个

请以JSON格式输出:
{{"title": "笔记标题", "body": "正文内容", "summary": "一句话摘要", "hashtags": ["#话题1", "#话题2"]}}"""


def summarize_prompt_douyin(title: str, description: str, category: str) -> str:
    return f"""你是一个抖音短视频脚本创作者。请基于以下热门内容，创作一个短视频口播脚本。

原始标题: {title}
原始内容: {description}
类别: {category}

要求:
1. 标题: 简短有力，10-20字
2. 脚本: 60秒内可读完(约200-300字)
3. 开头3秒要有hook(引起好奇)
4. 内容节奏紧凑，信息密度高
5. 口语化表达，适合口播
6. 结尾引导关注/评论
7. 话题标签3-5个

请以JSON格式输出:
{{"title": "视频标题", "body": "口播脚本", "summary": "一句话摘要", "hashtags": ["#话题1", "#话题2"]}}"""


def summarize_prompt_weibo(title: str, description: str, category: str) -> str:
    return f"""你是一个微博运营专家。请基于以下热门内容，创作一条微博。

原始标题: {title}
原始内容: {description}
类别: {category}

要求:
1. 正文: 100-140字(微博字数限制)
2. 信息精炼，观点鲜明
3. 适当加入emoji
4. 话题标签2-3个(用#话题#格式)
5. 可以加入互动提问

请以JSON格式输出:
{{"title": "", "body": "微博正文", "summary": "一句话摘要", "hashtags": ["#话题1#", "#话题2#"]}}"""


PLATFORM_PROMPTS = {
    "wechat": summarize_prompt_wechat,
    "xiaohongshu": summarize_prompt_xiaohongshu,
    "douyin": summarize_prompt_douyin,
    "weibo": summarize_prompt_weibo,
}


def quality_check_prompt(title: str, body: str, platform: str) -> str:
    return f"""你是一个内容审核专家。请检查以下待发布内容的质量。

目标平台: {platform}
标题: {title}
正文: {body}

请检查以下方面并以JSON格式输出:
1. "score": 总体质量分(0-1)
2. "passed": 是否通过(true/false)
3. "issues": 问题列表(数组)
4. "suggestions": 改进建议列表(数组)

检查维度:
- 内容准确性和可信度
- 是否含有敏感或违规内容
- 语言质量和可读性
- 是否符合目标平台风格
- 标题与正文是否匹配

请直接输出JSON:"""


def video_prompt(title: str, summary: str, category: str) -> str:
    return f"""基于以下内容，生成一个适合AI视频生成的英文prompt。

标题: {title}
摘要: {summary}
类别: {category}

要求:
- 英文输出
- 描述一个具体的视觉场景
- 50-100词
- 风格: 专业、现代、信息丰富
- 适合作为新闻类短视频的画面描述

直接输出英文prompt，不要包含其他内容:"""
