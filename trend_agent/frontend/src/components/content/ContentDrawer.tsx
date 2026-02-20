import { useState, useEffect } from "react";
import {
  updateDraft,
  publishDrafts,
  type ContentDraft,
} from "@/api/client";
import {
  PLATFORMS,
  isPlatformAvailable,
  type ContentType,
} from "@/lib/platform-constraints";
import { cn } from "@/lib/utils";
import {
  X,
  Save,
  Send,
  Loader2,
  Check,
  Lock,
  AlertCircle,
  CheckCircle2,
} from "lucide-react";

interface Props {
  draft: ContentDraft;
  onClose: () => void;
}

export default function ContentDrawer({ draft, onClose }: Props) {
  const [title, setTitle] = useState(draft.title);
  const [body, setBody] = useState(draft.body);
  const [summary, setSummary] = useState(draft.summary);
  const [hashtagInput, setHashtagInput] = useState(
    (draft.hashtags || []).join(", ")
  );
  const [selectedChannels, setSelectedChannels] = useState<string[]>([]);

  const [saving, setSaving] = useState(false);
  const [saveSuccess, setSaveSuccess] = useState(false);
  const [publishing, setPublishing] = useState(false);
  const [publishResult, setPublishResult] = useState<
    "idle" | "success" | "error"
  >("idle");
  const [error, setError] = useState("");

  // Determine content type based on video_url presence
  const contentType: ContentType = draft.video_url ? "video" : "article";

  // Reset form when draft changes
  useEffect(() => {
    setTitle(draft.title);
    setBody(draft.body);
    setSummary(draft.summary);
    setHashtagInput((draft.hashtags || []).join(", "));
    setSelectedChannels([]);
    setPublishResult("idle");
    setError("");
    setSaveSuccess(false);
  }, [draft.id, draft.title, draft.body, draft.summary, draft.hashtags]);

  const toggleChannel = (id: string) => {
    if (!isPlatformAvailable(id, contentType)) return;
    setSelectedChannels((prev) =>
      prev.includes(id) ? prev.filter((c) => c !== id) : [...prev, id]
    );
  };

  const handleSave = async () => {
    setSaving(true);
    setSaveSuccess(false);
    setError("");
    try {
      const hashtags = hashtagInput
        .split(/[,，]/)
        .map((t) => t.trim())
        .filter(Boolean);
      await updateDraft(draft.id, { title, body, summary, hashtags });
      setSaveSuccess(true);
      setTimeout(() => setSaveSuccess(false), 2000);
    } catch (err) {
      setError(err instanceof Error ? err.message : "保存失败");
    } finally {
      setSaving(false);
    }
  };

  const handlePublish = async () => {
    if (!selectedChannels.length) return;
    setPublishing(true);
    setPublishResult("idle");
    setError("");
    try {
      await publishDrafts([draft.id], selectedChannels);
      setPublishResult("success");
    } catch (err) {
      setPublishResult("error");
      setError(err instanceof Error ? err.message : "发布失败");
    } finally {
      setPublishing(false);
    }
  };

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-black/50 backdrop-blur-sm z-40"
        onClick={onClose}
        data-testid="drawer-backdrop"
      />

      {/* Drawer */}
      <div
        className="fixed top-0 right-0 h-full w-full max-w-2xl z-50 bg-gray-900 border-l border-gray-800/50 overflow-y-auto shadow-2xl animate-in slide-in-from-right"
        data-testid="content-drawer"
      >
        {/* Header */}
        <div className="sticky top-0 z-10 flex items-center justify-between px-6 py-4 bg-gray-900/95 backdrop-blur-sm border-b border-gray-800/50">
          <div>
            <h2 className="text-lg font-semibold">编辑内容</h2>
            <p className="text-xs text-gray-500 mt-0.5">
              目标平台：
              {
                PLATFORMS.find((p) => p.id === draft.target_platform)?.name ||
                draft.target_platform
              }
              {draft.video_url && " · 视频内容"}
            </p>
          </div>
          <button
            onClick={onClose}
            className="p-2 rounded-lg hover:bg-gray-800 text-gray-400 hover:text-gray-200 transition-colors"
            data-testid="close-drawer"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="p-6 space-y-6">
          {/* Info bar */}
          <div className="flex gap-3 text-xs text-gray-500">
            <span>
              质量分: {(draft.quality_score || 0).toFixed(2)}
            </span>
            <span>·</span>
            <span>状态: {draft.status}</span>
            <span>·</span>
            <span>
              创建:{" "}
              {draft.created_at
                ? new Date(draft.created_at).toLocaleString("zh-CN")
                : "-"}
            </span>
          </div>

          {/* Edit fields */}
          <div className="space-y-4">
            <div>
              <label className="block text-sm text-gray-400 mb-1.5">
                标题
              </label>
              <input
                type="text"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                className="w-full px-4 py-2.5 rounded-lg bg-gray-800/50 border border-gray-700/50 text-gray-100 focus:outline-none focus:ring-2 focus:ring-primary-500/50 transition-all"
                data-testid="edit-title"
              />
            </div>

            <div>
              <label className="block text-sm text-gray-400 mb-1.5">
                摘要
              </label>
              <textarea
                value={summary}
                onChange={(e) => setSummary(e.target.value)}
                rows={3}
                className="w-full px-4 py-2.5 rounded-lg bg-gray-800/50 border border-gray-700/50 text-gray-100 focus:outline-none focus:ring-2 focus:ring-primary-500/50 transition-all resize-none"
                data-testid="edit-summary"
              />
            </div>

            <div>
              <label className="block text-sm text-gray-400 mb-1.5">
                正文
              </label>
              <textarea
                value={body}
                onChange={(e) => setBody(e.target.value)}
                rows={10}
                className="w-full px-4 py-2.5 rounded-lg bg-gray-800/50 border border-gray-700/50 text-gray-100 focus:outline-none focus:ring-2 focus:ring-primary-500/50 transition-all resize-y font-mono text-sm leading-relaxed"
                data-testid="edit-body"
              />
            </div>

            <div>
              <label className="block text-sm text-gray-400 mb-1.5">
                标签（逗号分隔）
              </label>
              <input
                type="text"
                value={hashtagInput}
                onChange={(e) => setHashtagInput(e.target.value)}
                placeholder="标签1, 标签2, 标签3"
                className="w-full px-4 py-2.5 rounded-lg bg-gray-800/50 border border-gray-700/50 text-gray-100 placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-primary-500/50 transition-all"
                data-testid="edit-hashtags"
              />
            </div>
          </div>

          {/* Save button */}
          <button
            onClick={handleSave}
            disabled={saving}
            className="flex items-center gap-2 px-5 py-2.5 rounded-lg glass glass-hover text-sm font-medium text-gray-200 disabled:opacity-50"
            data-testid="save-draft"
          >
            {saving ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : saveSuccess ? (
              <CheckCircle2 className="h-4 w-4 text-emerald-400" />
            ) : (
              <Save className="h-4 w-4" />
            )}
            {saveSuccess ? "已保存" : "保存修改"}
          </button>

          {/* Divider */}
          <div className="border-t border-gray-800/50" />

          {/* Publish section */}
          <div className="space-y-4">
            <div>
              <h3 className="text-base font-semibold">选择发布渠道</h3>
              <p className="text-xs text-gray-500 mt-0.5">
                当前内容类型：{contentType === "article" ? "文稿" : "视频"}
                ，部分渠道可能不可选
              </p>
            </div>

            <div className="grid grid-cols-2 gap-3">
              {PLATFORMS.map((platform) => {
                const available = isPlatformAvailable(
                  platform.id,
                  contentType
                );
                const isSelected = selectedChannels.includes(platform.id);

                return (
                  <button
                    key={platform.id}
                    onClick={() => toggleChannel(platform.id)}
                    disabled={!available}
                    data-testid={`publish-channel-${platform.id}`}
                    data-available={available}
                    className={cn(
                      "flex items-center gap-3 p-3 rounded-lg border text-left text-sm transition-all",
                      !available
                        ? "opacity-35 cursor-not-allowed bg-gray-900/30 border-gray-800/30"
                        : isSelected
                          ? "glass border-primary-500/50 ring-1 ring-primary-500/30"
                          : "glass glass-hover border-gray-700/50"
                    )}
                  >
                    <div className="flex-1">
                      <p className="font-medium">{platform.name}</p>
                      <p className="text-xs text-gray-500">
                        {platform.description}
                      </p>
                    </div>
                    {!available ? (
                      <Lock className="h-4 w-4 text-gray-600" />
                    ) : isSelected ? (
                      <Check className="h-4 w-4 text-primary-400" />
                    ) : null}
                  </button>
                );
              })}
            </div>

            {/* Publish status */}
            {error && (
              <div className="flex items-center gap-2 p-3 rounded-lg bg-red-500/10 border border-red-500/30 text-sm text-red-400">
                <AlertCircle className="h-4 w-4 shrink-0" />
                {error}
              </div>
            )}

            {publishResult === "success" && (
              <div
                className="flex items-center gap-2 p-3 rounded-lg bg-emerald-500/10 border border-emerald-500/30 text-sm text-emerald-400"
                data-testid="publish-success"
              >
                <CheckCircle2 className="h-4 w-4 shrink-0" />
                发布请求已提交
              </div>
            )}

            {/* Publish button */}
            <button
              onClick={handlePublish}
              disabled={
                publishing ||
                selectedChannels.length === 0 ||
                publishResult === "success"
              }
              className={cn(
                "w-full flex items-center justify-center gap-2 py-3 rounded-xl text-white font-semibold transition-all",
                selectedChannels.length > 0 && publishResult !== "success"
                  ? "gradient-primary hover:opacity-90"
                  : "bg-gray-800/50 text-gray-500 cursor-not-allowed"
              )}
              data-testid="publish-button"
            >
              {publishing ? (
                <Loader2 className="h-5 w-5 animate-spin" />
              ) : (
                <Send className="h-5 w-5" />
              )}
              {selectedChannels.length > 0
                ? `发布到 ${selectedChannels.length} 个渠道`
                : "请选择发布渠道"}
            </button>
          </div>
        </div>
      </div>
    </>
  );
}
