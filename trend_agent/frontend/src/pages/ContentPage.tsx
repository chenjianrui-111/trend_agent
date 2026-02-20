import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { listDrafts, deleteDraft, type ContentDraft } from "@/api/client";
import { PLATFORMS } from "@/lib/platform-constraints";
import { cn } from "@/lib/utils";
import {
  FileText,
  Video,
  Search,
  Trash2,
  Loader2,
  ChevronLeft,
  ChevronRight,
} from "lucide-react";
import ContentDrawer from "@/components/content/ContentDrawer";

const STATUS_OPTIONS = [
  { value: "", label: "全部状态" },
  { value: "summarized", label: "已生成" },
  { value: "quality_checked", label: "已审核" },
  { value: "published", label: "已发布" },
  { value: "rejected", label: "已拒绝" },
];

const PLATFORM_OPTIONS = [
  { value: "", label: "全部平台" },
  ...PLATFORMS.map((p) => ({ value: p.id, label: p.name })),
];

function statusColor(status: string) {
  switch (status) {
    case "published":
      return "bg-emerald-500/15 text-emerald-400 border-emerald-500/30";
    case "quality_checked":
    case "summarized":
      return "bg-blue-500/15 text-blue-400 border-blue-500/30";
    case "rejected":
      return "bg-red-500/15 text-red-400 border-red-500/30";
    default:
      return "bg-gray-500/15 text-gray-400 border-gray-500/30";
  }
}

function statusLabel(status: string) {
  const map: Record<string, string> = {
    summarized: "已生成",
    quality_checked: "已审核",
    published: "已发布",
    rejected: "已拒绝",
  };
  return map[status] || status;
}

function platformLabel(p: string) {
  const map: Record<string, string> = {
    wechat: "公众号",
    xiaohongshu: "小红书",
    douyin: "抖音",
    weibo: "微博",
  };
  return map[p] || p;
}

const PAGE_SIZE = 12;

export default function ContentPage() {
  const queryClient = useQueryClient();
  const [statusFilter, setStatusFilter] = useState("");
  const [platformFilter, setPlatformFilter] = useState("");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(0);
  const [selectedDraft, setSelectedDraft] = useState<ContentDraft | null>(null);

  const { data: drafts, isLoading } = useQuery({
    queryKey: ["drafts", statusFilter, platformFilter, page],
    queryFn: () =>
      listDrafts(
        statusFilter || undefined,
        platformFilter || undefined,
        PAGE_SIZE,
        page * PAGE_SIZE
      ),
    refetchInterval: 15000,
  });

  const filtered = search
    ? drafts?.filter(
        (d) =>
          d.title.toLowerCase().includes(search.toLowerCase()) ||
          d.summary.toLowerCase().includes(search.toLowerCase())
      )
    : drafts;

  const handleDelete = async (id: string) => {
    if (!confirm("确定删除此稿件？")) return;
    await deleteDraft(id);
    queryClient.invalidateQueries({ queryKey: ["drafts"] });
  };

  const handleDrawerClose = () => {
    setSelectedDraft(null);
    queryClient.invalidateQueries({ queryKey: ["drafts"] });
  };

  return (
    <div className="max-w-7xl mx-auto space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold">内容管理</h1>
        <p className="text-gray-500 mt-1">
          浏览、编辑抓取的内容，选择渠道发布
        </p>
      </div>

      {/* Filters */}
      <div
        className="flex flex-wrap items-center gap-3"
        data-testid="content-filters"
      >
        <select
          value={platformFilter}
          onChange={(e) => {
            setPlatformFilter(e.target.value);
            setPage(0);
          }}
          className="px-3 py-2 rounded-lg bg-gray-800/50 border border-gray-700/50 text-sm text-gray-200 focus:outline-none focus:ring-2 focus:ring-primary-500/50"
          data-testid="filter-platform"
        >
          {PLATFORM_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>

        <select
          value={statusFilter}
          onChange={(e) => {
            setStatusFilter(e.target.value);
            setPage(0);
          }}
          className="px-3 py-2 rounded-lg bg-gray-800/50 border border-gray-700/50 text-sm text-gray-200 focus:outline-none focus:ring-2 focus:ring-primary-500/50"
          data-testid="filter-status"
        >
          {STATUS_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>

        <div className="relative flex-1 min-w-[200px] max-w-sm">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-500" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="搜索标题或摘要..."
            className="w-full pl-9 pr-4 py-2 rounded-lg bg-gray-800/50 border border-gray-700/50 text-sm text-gray-200 placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-primary-500/50"
            data-testid="search-input"
          />
        </div>
      </div>

      {/* Content grid */}
      {isLoading ? (
        <div className="flex items-center justify-center py-20">
          <Loader2 className="h-6 w-6 animate-spin text-gray-500" />
        </div>
      ) : !filtered?.length ? (
        <div className="text-center py-20 text-gray-500">
          <FileText className="h-12 w-12 mx-auto mb-3 opacity-30" />
          <p>暂无内容</p>
          <p className="text-sm mt-1">请先通过数据源页面触发抓取任务</p>
        </div>
      ) : (
        <div
          className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4"
          data-testid="content-grid"
        >
          {filtered.map((draft) => (
            <div
              key={draft.id}
              className="glass rounded-xl p-5 glass-hover cursor-pointer group relative"
              onClick={() => setSelectedDraft(draft)}
              data-testid={`content-card-${draft.id}`}
            >
              {/* Header row */}
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2">
                  <span className="text-xs px-2 py-0.5 rounded bg-gray-700/50 text-gray-300">
                    {platformLabel(draft.target_platform)}
                  </span>
                  {draft.video_url && (
                    <Video className="h-3.5 w-3.5 text-purple-400" />
                  )}
                </div>
                <span
                  className={cn(
                    "text-xs px-2 py-0.5 rounded-full border",
                    statusColor(draft.status)
                  )}
                >
                  {statusLabel(draft.status)}
                </span>
              </div>

              {/* Title */}
              <h3 className="font-semibold text-gray-100 line-clamp-2 mb-2 group-hover:text-primary-400 transition-colors">
                {draft.title || "无标题"}
              </h3>

              {/* Summary */}
              <p className="text-sm text-gray-400 line-clamp-3 mb-4">
                {draft.summary || draft.body?.substring(0, 120) || "无内容"}
              </p>

              {/* Footer */}
              <div className="flex items-center justify-between text-xs text-gray-500">
                <span>
                  质量分: {(draft.quality_score || 0).toFixed(2)}
                </span>
                <span>
                  {draft.created_at
                    ? new Date(draft.created_at).toLocaleDateString("zh-CN")
                    : "-"}
                </span>
              </div>

              {/* Delete button */}
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  handleDelete(draft.id);
                }}
                className="absolute top-3 right-3 p-1.5 rounded-lg opacity-0 group-hover:opacity-100 hover:bg-red-500/20 text-gray-500 hover:text-red-400 transition-all"
                data-testid={`delete-${draft.id}`}
              >
                <Trash2 className="h-3.5 w-3.5" />
              </button>
            </div>
          ))}
        </div>
      )}

      {/* Pagination */}
      {(drafts?.length ?? 0) > 0 && (
        <div className="flex items-center justify-center gap-4">
          <button
            onClick={() => setPage((p) => Math.max(0, p - 1))}
            disabled={page === 0}
            className="flex items-center gap-1 px-3 py-1.5 rounded-lg text-sm text-gray-400 hover:text-gray-200 glass glass-hover disabled:opacity-30 disabled:cursor-not-allowed"
          >
            <ChevronLeft className="h-4 w-4" />
            上一页
          </button>
          <span className="text-sm text-gray-500">第 {page + 1} 页</span>
          <button
            onClick={() => setPage((p) => p + 1)}
            disabled={(drafts?.length ?? 0) < PAGE_SIZE}
            className="flex items-center gap-1 px-3 py-1.5 rounded-lg text-sm text-gray-400 hover:text-gray-200 glass glass-hover disabled:opacity-30 disabled:cursor-not-allowed"
          >
            下一页
            <ChevronRight className="h-4 w-4" />
          </button>
        </div>
      )}

      {/* Drawer */}
      {selectedDraft && (
        <ContentDrawer
          draft={selectedDraft}
          onClose={handleDrawerClose}
        />
      )}
    </div>
  );
}
