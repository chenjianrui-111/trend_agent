import { SOURCES, PLATFORMS, type ContentType } from "@/lib/platform-constraints";
import { cn } from "@/lib/utils";
import { Loader2, Rocket, CheckCircle2, XCircle, Clock } from "lucide-react";

interface Props {
  sources: string[];
  contentType: ContentType;
  channels: string[];
  isRunning: boolean;
  pipelineStatus: "idle" | "running" | "completed" | "failed";
  pipelineRunId: string | null;
  onSubmit: () => void;
}

export default function PublishPreview({
  sources,
  contentType,
  channels,
  isRunning,
  pipelineStatus,
  pipelineRunId,
  onSubmit,
}: Props) {
  const sourceNames = sources.map(
    (id) => SOURCES.find((s) => s.id === id)?.name ?? id
  );
  const channelNames = channels.map(
    (id) => PLATFORMS.find((p) => p.id === id)?.name ?? id
  );

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-semibold">确认发布</h2>
        <p className="text-gray-400 mt-1">请确认以下配置后开始执行</p>
      </div>

      {/* Summary cards */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <div className="glass rounded-xl p-5">
          <p className="text-sm text-gray-400 mb-2">数据源</p>
          <div className="flex flex-wrap gap-2">
            {sourceNames.map((name) => (
              <span
                key={name}
                className="text-sm px-2.5 py-1 rounded-lg bg-blue-500/10 text-blue-400 border border-blue-500/20"
              >
                {name}
              </span>
            ))}
          </div>
        </div>

        <div className="glass rounded-xl p-5">
          <p className="text-sm text-gray-400 mb-2">内容类型</p>
          <span
            className={cn(
              "text-sm px-2.5 py-1 rounded-lg border",
              contentType === "article"
                ? "bg-amber-500/10 text-amber-400 border-amber-500/20"
                : "bg-purple-500/10 text-purple-400 border-purple-500/20"
            )}
          >
            {contentType === "article" ? "文稿（含配图）" : "AIGC 视频"}
          </span>
        </div>

        <div className="glass rounded-xl p-5">
          <p className="text-sm text-gray-400 mb-2">发布渠道</p>
          <div className="flex flex-wrap gap-2">
            {channelNames.map((name) => (
              <span
                key={name}
                className="text-sm px-2.5 py-1 rounded-lg bg-emerald-500/10 text-emerald-400 border border-emerald-500/20"
              >
                {name}
              </span>
            ))}
          </div>
        </div>
      </div>

      {/* Status */}
      {pipelineStatus !== "idle" && (
        <div
          className={cn(
            "flex items-center gap-3 p-4 rounded-xl border",
            pipelineStatus === "running" &&
              "bg-blue-500/10 border-blue-500/30",
            pipelineStatus === "completed" &&
              "bg-emerald-500/10 border-emerald-500/30",
            pipelineStatus === "failed" &&
              "bg-red-500/10 border-red-500/30"
          )}
          data-testid="pipeline-status"
          data-status={pipelineStatus}
        >
          {pipelineStatus === "running" && (
            <Loader2 className="h-5 w-5 text-blue-400 animate-spin" />
          )}
          {pipelineStatus === "completed" && (
            <CheckCircle2 className="h-5 w-5 text-emerald-400" />
          )}
          {pipelineStatus === "failed" && (
            <XCircle className="h-5 w-5 text-red-400" />
          )}

          <div>
            <p className="font-medium">
              {pipelineStatus === "running" && "流水线执行中..."}
              {pipelineStatus === "completed" && "流水线执行完成"}
              {pipelineStatus === "failed" && "流水线执行失败"}
            </p>
            {pipelineRunId && (
              <p className="text-sm text-gray-400 mt-0.5">
                <Clock className="inline h-3.5 w-3.5 mr-1" />
                Run ID: {pipelineRunId.substring(0, 12)}...
              </p>
            )}
          </div>
        </div>
      )}

      {/* Submit */}
      {pipelineStatus === "idle" && (
        <button
          onClick={onSubmit}
          disabled={isRunning}
          className="w-full py-3 rounded-xl gradient-primary text-white font-semibold hover:opacity-90 disabled:opacity-50 transition-all duration-200 flex items-center justify-center gap-2 text-lg"
          data-testid="submit-publish"
        >
          {isRunning ? (
            <Loader2 className="h-5 w-5 animate-spin" />
          ) : (
            <Rocket className="h-5 w-5" />
          )}
          开始执行
        </button>
      )}
    </div>
  );
}
