import { useQuery } from "@tanstack/react-query";
import { getStats, listPipelineRuns } from "@/api/client";
import {
  Database,
  FileText,
  CheckCircle2,
  Activity,
  Loader2,
} from "lucide-react";
import { cn } from "@/lib/utils";

const STAT_CARDS = [
  { key: "total_sources", label: "数据源", icon: Database, color: "text-blue-400" },
  { key: "total_drafts", label: "内容稿件", icon: FileText, color: "text-amber-400" },
  { key: "total_published", label: "已发布", icon: CheckCircle2, color: "text-emerald-400" },
  { key: "total_pipeline_runs", label: "流水线", icon: Activity, color: "text-purple-400" },
] as const;

function statusColor(status: string) {
  switch (status) {
    case "completed":
      return "bg-emerald-500/15 text-emerald-400 border-emerald-500/30";
    case "running":
      return "bg-blue-500/15 text-blue-400 border-blue-500/30";
    case "failed":
      return "bg-red-500/15 text-red-400 border-red-500/30";
    default:
      return "bg-gray-500/15 text-gray-400 border-gray-500/30";
  }
}

export default function DashboardPage() {
  const { data: stats, isLoading: statsLoading } = useQuery({
    queryKey: ["stats"],
    queryFn: getStats,
    refetchInterval: 30000,
  });

  const { data: runs, isLoading: runsLoading } = useQuery({
    queryKey: ["pipelineRuns"],
    queryFn: () => listPipelineRuns(10),
    refetchInterval: 15000,
  });

  return (
    <div className="max-w-6xl mx-auto space-y-8">
      {/* Page header */}
      <div>
        <h1 className="text-2xl font-bold">仪表盘</h1>
        <p className="text-gray-500 mt-1">系统运行概览</p>
      </div>

      {/* Stats grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {STAT_CARDS.map((card) => (
          <div key={card.key} className="glass rounded-xl p-5 glass-hover">
            <div className="flex items-center justify-between mb-3">
              <span className="text-sm text-gray-400">{card.label}</span>
              <card.icon className={cn("h-5 w-5", card.color)} />
            </div>
            <p className="text-3xl font-bold">
              {statsLoading ? (
                <Loader2 className="h-6 w-6 animate-spin text-gray-600" />
              ) : (
                (stats?.[card.key] ?? 0).toLocaleString()
              )}
            </p>
          </div>
        ))}
      </div>

      {/* Recent pipeline runs */}
      <div className="glass rounded-xl overflow-hidden">
        <div className="px-6 py-4 border-b border-gray-800/50">
          <h2 className="text-lg font-semibold">最近流水线执行</h2>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-800/50 text-gray-400">
                <th className="px-6 py-3 text-left font-medium">ID</th>
                <th className="px-6 py-3 text-left font-medium">触发方式</th>
                <th className="px-6 py-3 text-left font-medium">状态</th>
                <th className="px-6 py-3 text-left font-medium">抓取数</th>
                <th className="px-6 py-3 text-left font-medium">发布数</th>
                <th className="px-6 py-3 text-left font-medium">时间</th>
              </tr>
            </thead>
            <tbody>
              {runsLoading ? (
                <tr>
                  <td colSpan={6} className="px-6 py-8 text-center text-gray-500">
                    <Loader2 className="h-5 w-5 animate-spin mx-auto" />
                  </td>
                </tr>
              ) : !runs?.length ? (
                <tr>
                  <td colSpan={6} className="px-6 py-8 text-center text-gray-500">
                    暂无执行记录
                  </td>
                </tr>
              ) : (
                runs.map((run) => (
                  <tr
                    key={run.id}
                    className="border-b border-gray-800/30 hover:bg-gray-800/30 transition-colors"
                  >
                    <td className="px-6 py-3 font-mono text-xs text-gray-400">
                      {run.id.substring(0, 8)}...
                    </td>
                    <td className="px-6 py-3">{run.trigger_type || "-"}</td>
                    <td className="px-6 py-3">
                      <span
                        className={cn(
                          "inline-flex px-2.5 py-0.5 rounded-full text-xs font-medium border",
                          statusColor(run.status)
                        )}
                      >
                        {run.status}
                      </span>
                    </td>
                    <td className="px-6 py-3">{run.items_scraped ?? 0}</td>
                    <td className="px-6 py-3">{run.items_published ?? 0}</td>
                    <td className="px-6 py-3 text-gray-400">
                      {run.started_at
                        ? new Date(run.started_at).toLocaleString("zh-CN")
                        : "-"}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
