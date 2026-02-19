"""
Template-driven generation constraints.
"""

from dataclasses import dataclass
from typing import Dict, List


@dataclass(frozen=True)
class PlatformConstraint:
    title_min: int
    title_max: int
    body_min: int
    body_max: int
    style: str
    rules: List[str]


PLATFORM_CONSTRAINTS: Dict[str, PlatformConstraint] = {
    "wechat": PlatformConstraint(
        title_min=15,
        title_max=30,
        body_min=800,
        body_max=1500,
        style="专业、清晰、结构化，避免夸张承诺",
        rules=[
            "三段以上结构，包含导语、主体、结论",
            "避免绝对化结论和未经证实的数据",
        ],
    ),
    "xiaohongshu": PlatformConstraint(
        title_min=12,
        title_max=28,
        body_min=250,
        body_max=650,
        style="口语化、真实体验感、轻量表达",
        rules=[
            "分段清晰，避免堆砌营销话术",
            "保留互动引导但不过度诱导",
        ],
    ),
    "douyin": PlatformConstraint(
        title_min=10,
        title_max=22,
        body_min=150,
        body_max=380,
        style="节奏紧凑，口播友好，信息密度高",
        rules=[
            "开头5秒有抓手",
            "结尾有明确互动动作",
        ],
    ),
    "weibo": PlatformConstraint(
        title_min=0,
        title_max=24,
        body_min=90,
        body_max=180,
        style="信息浓缩、观点明确、适度话题性",
        rules=[
            "正文尽量控制在微博常见阅读长度",
            "标签控制2-3个，避免刷屏式堆叠",
        ],
    ),
}


def get_platform_constraint(platform: str) -> PlatformConstraint:
    return PLATFORM_CONSTRAINTS.get(
        platform,
        PlatformConstraint(
            title_min=8,
            title_max=40,
            body_min=120,
            body_max=1500,
            style="准确、简洁、可读",
            rules=["输出结构清晰", "避免虚假与违规表述"],
        ),
    )


def build_constraint_block(platform: str, banned_words: List[str]) -> str:
    c = get_platform_constraint(platform)
    banned = ", ".join(banned_words) if banned_words else "无"
    rules = "\n".join([f"- {r}" for r in c.rules])
    return (
        "【前置约束模板】\n"
        f"- 平台: {platform}\n"
        f"- 标题长度: {c.title_min}-{c.title_max} 字\n"
        f"- 正文长度: {c.body_min}-{c.body_max} 字\n"
        f"- 风格要求: {c.style}\n"
        f"- 禁词列表: {banned}\n"
        "- 平台规则:\n"
        f"{rules}\n"
        "- 输出必须是合法 JSON，不要附加解释。"
    )
