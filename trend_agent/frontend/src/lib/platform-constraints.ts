export type ContentType = "article" | "video";

export interface PlatformInfo {
  id: string;
  name: string;
  description: string;
  supports: Record<ContentType, boolean>;
}

export interface SourceInfo {
  id: string;
  name: string;
  description: string;
}

export const SOURCES: SourceInfo[] = [
  { id: "twitter", name: "Twitter / X", description: "全球热门推文与话题趋势" },
  { id: "youtube", name: "YouTube", description: "热门视频与创作者动态" },
  { id: "weibo", name: "微博", description: "微博热搜与热门话题" },
  { id: "bilibili", name: "哔哩哔哩", description: "B站热门视频与趋势" },
  { id: "zhihu", name: "知乎", description: "知乎热榜与高赞回答" },
  { id: "github", name: "GitHub", description: "开源项目趋势与技术动态" },
];

export const PLATFORMS: PlatformInfo[] = [
  {
    id: "wechat",
    name: "微信公众号",
    description: "图文内容推送",
    supports: { article: true, video: false },
  },
  {
    id: "xiaohongshu",
    name: "小红书",
    description: "图文笔记与短视频",
    supports: { article: true, video: true },
  },
  {
    id: "douyin",
    name: "抖音",
    description: "短视频内容发布",
    supports: { article: false, video: true },
  },
  {
    id: "weibo",
    name: "微博",
    description: "微博图文与视频",
    supports: { article: true, video: true },
  },
];

export function getAvailablePlatforms(contentType: ContentType): PlatformInfo[] {
  return PLATFORMS.filter((p) => p.supports[contentType]);
}

export function isPlatformAvailable(
  platformId: string,
  contentType: ContentType
): boolean {
  const platform = PLATFORMS.find((p) => p.id === platformId);
  return platform ? platform.supports[contentType] : false;
}
