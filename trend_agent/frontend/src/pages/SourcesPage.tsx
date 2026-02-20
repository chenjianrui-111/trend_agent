import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  listSources,
  runPipeline,
  type TrendSource,
} from "@/api/client";
import { SOURCES } from "@/lib/platform-constraints";
import { cn } from "@/lib/utils";
import {
  Database,
  Loader2,
  Rocket,
  ExternalLink,
  ChevronLeft,
  ChevronRight,
  Flame,
  Check,
} from "lucide-react";

const SOURCE_OPTIONS = [
  { value: "", label: "全部来源" },
  ...SOURCES.map((s) => ({ value: s.id, label: s.name })),
];

const PAGE_SIZE = 20;

export default function SourcesPage() {
  const [platformFilter, setPlatformFilter] = useState("");
  const [page, setPage] = useState(0);

  // Pipeline trigger state
  const [showTrigger, setShowTrigger] = useState(false);
  const [selectedSources, setSelectedSources] = useState<string[]>([
    "twitter",
    "youtube",
  ]);
  const [triggering, setTriggering] = useState(false);
  const [triggerResult, setTriggerResult] = useState("");

  const { data: sources, isLoading } = useQuery({
    queryKey: ["sources", platformFilter, page],
    queryFn: () =>
      listSources(
        platformFilter || undefined,
        PAGE_SIZE,
        page * PAGE_SIZE
      ),
    refetchInterval: 30000,
  });

  const handleTrigger = async () => {
    if (!selectedSources.length) return;
    setTriggering(true);
    try {
      const result = await runPipeline({
        sources: selectedSources,
        target_platforms: ["wechat", "xiaohongshu", "weibo"],
        generate_video: false,
      });
      setTriggerResult(`Pipeline 已启动: ${result.pipeline_run_id.substring(0, 12)}...`);
      setTimeout(() => setTriggerResult(""), 5000);
      setShowTrigger(false);
    } catch (err) {
      setTriggerResult(
        `失败: ${err instanceof Error ? err.message : "未知错误"}`
      );
    } finally {
      setTriggering(false);
    }
  };

  const toggleSource = (id: string) => {
    setSelectedSources((prev) =>
      prev.includes(id) ? prev.filter((s) => s !== id) : [...prev, id]
    );
  };

  return (
    <div className="max-w-6xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">数据源</h1>
          <p className="text-gray-500 mt-1">浏览已抓取的原始内容</p>
        </div>
        <button
          onClick={() => setShowTrigger(!showTrigger)}
          className="flex items-center gap-2 px-4 py-2 rounded-lg gradient-primary text-white text-sm font-medium hover:opacity-90 transition-all"
          data-testid="trigger-scrape-btn"
        >
          <Rocket className="h-4 w-4" />
          触发抓取
        </button>
      </div>

      {/* Trigger panel */}
      {showTrigger && (
        <div
          className="glass rounded-xl p-5 space-y-4"
          data-testid="trigger-panel"
        >
          <p className="text-sm font-medium">选择要抓取的数据源：</p>
          <div className="flex flex-wrap gap-2">
            {SOURCES.map((src) => {
              const selected = selectedSources.includes(src.id);
              return (
                <button
                  key={src.id}
                  onClick={() => toggleSource(src.id)}
                  data-testid={`trigger-source-${src.id}`}
                  className={cn(
                    "flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm border transition-all",
                    selected
                      ? "border-primary-500/50 bg-primary-500/10 text-primary-400"
                      : "border-gray-700/50 text-gray-400 hover:text-gray-200 hover:border-gray-600/50"
                  )}
                >
                  {selected && <Check className="h-3 w-3" />}
                  {src.name}
                </button>
              );
            })}
          </div>
          <button
            onClick={handleTrigger}
            disabled={triggering || !selectedSources.length}
            className="flex items-center gap-2 px-4 py-2 rounded-lg gradient-primary text-white text-sm font-medium hover:opacity-90 disabled:opacity-50 transition-all"
            data-testid="trigger-submit"
          >
            {triggering && <Loader2 className="h-4 w-4 animate-spin" />}
            开始抓取
          </button>
        </div>
      )}

      {/* Trigger result */}
      {triggerResult && (
        <div className="text-sm px-4 py-2 rounded-lg bg-primary-500/10 border border-primary-500/30 text-primary-400">
          {triggerResult}
        </div>
      )}

      {/* Filters */}
      <div className="flex items-center gap-3">
        <select
          value={platformFilter}
          onChange={(e) => {
            setPlatformFilter(e.target.value);
            setPage(0);
          }}
          className="px-3 py-2 rounded-lg bg-gray-800/50 border border-gray-700/50 text-sm text-gray-200 focus:outline-none focus:ring-2 focus:ring-primary-500/50"
          data-testid="source-filter-platform"
        >
          {SOURCE_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
      </div>

      {/* Sources list */}
      {isLoading ? (
        <div className="flex items-center justify-center py-20">
          <Loader2 className="h-6 w-6 animate-spin text-gray-500" />
        </div>
      ) : !sources?.length ? (
        <div className="text-center py-20 text-gray-500">
          <Database className="h-12 w-12 mx-auto mb-3 opacity-30" />
          <p>暂无抓取数据</p>
          <p className="text-sm mt-1">点击「触发抓取」开始采集内容</p>
        </div>
      ) : (
        <div className="glass rounded-xl overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-800/50 text-gray-400">
                <th className="px-5 py-3 text-left font-medium">来源</th>
                <th className="px-5 py-3 text-left font-medium">标题</th>
                <th className="px-5 py-3 text-left font-medium">热度</th>
                <th className="px-5 py-3 text-left font-medium">解析</th>
                <th className="px-5 py-3 text-left font-medium">时间</th>
                <th className="px-5 py-3 text-left font-medium">链接</th>
              </tr>
            </thead>
            <tbody data-testid="sources-table">
              {sources.map((src: TrendSource) => (
                <tr
                  key={src.id}
                  className="border-b border-gray-800/30 hover:bg-gray-800/30 transition-colors"
                >
                  <td className="px-5 py-3">
                    <span className="text-xs px-2 py-0.5 rounded bg-gray-700/50 text-gray-300">
                      {src.source_platform}
                    </span>
                  </td>
                  <td className="px-5 py-3 max-w-xs">
                    <p className="line-clamp-2" title={src.title}>
                      {src.title || src.description?.substring(0, 60) || "-"}
                    </p>
                  </td>
                  <td className="px-5 py-3">
                    <div className="flex items-center gap-1.5">
                      <Flame
                        className={cn(
                          "h-3.5 w-3.5",
                          src.normalized_heat_score > 0.7
                            ? "text-red-400"
                            : src.normalized_heat_score > 0.4
                              ? "text-amber-400"
                              : "text-gray-500"
                        )}
                      />
                      <span>
                        {(src.normalized_heat_score || 0).toFixed(2)}
                      </span>
                    </div>
                  </td>
                  <td className="px-5 py-3">
                    <span
                      className={cn(
                        "text-xs px-2 py-0.5 rounded-full border",
                        src.parse_status === "completed"
                          ? "bg-emerald-500/15 text-emerald-400 border-emerald-500/30"
                          : src.parse_status === "failed"
                            ? "bg-red-500/15 text-red-400 border-red-500/30"
                            : "bg-gray-500/15 text-gray-400 border-gray-500/30"
                      )}
                    >
                      {src.parse_status}
                    </span>
                  </td>
                  <td className="px-5 py-3 text-gray-400">
                    {src.scraped_at
                      ? new Date(src.scraped_at).toLocaleString("zh-CN")
                      : "-"}
                  </td>
                  <td className="px-5 py-3">
                    {src.source_url && (
                      <a
                        href={src.source_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-primary-400 hover:text-primary-300"
                      >
                        <ExternalLink className="h-4 w-4" />
                      </a>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Pagination */}
      {(sources?.length ?? 0) > 0 && (
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
            disabled={(sources?.length ?? 0) < PAGE_SIZE}
            className="flex items-center gap-1 px-3 py-1.5 rounded-lg text-sm text-gray-400 hover:text-gray-200 glass glass-hover disabled:opacity-30 disabled:cursor-not-allowed"
          >
            下一页
            <ChevronRight className="h-4 w-4" />
          </button>
        </div>
      )}
    </div>
  );
}
