import {
  PLATFORMS,
  isPlatformAvailable,
  type ContentType,
} from "@/lib/platform-constraints";
import { cn } from "@/lib/utils";
import { Check, Lock, MessageSquare } from "lucide-react";

const CHANNEL_ICONS: Record<string, React.ReactNode> = {
  wechat: <span className="text-lg font-bold">微</span>,
  xiaohongshu: <span className="text-lg font-bold">红</span>,
  douyin: <span className="text-lg font-bold">抖</span>,
  weibo: <span className="text-lg font-bold">微</span>,
};

const CHANNEL_COLORS: Record<string, string> = {
  wechat: "from-green-500 to-green-600",
  xiaohongshu: "from-red-400 to-pink-500",
  douyin: "from-gray-800 to-gray-900",
  weibo: "from-orange-500 to-red-500",
};

interface Props {
  contentType: ContentType;
  selected: string[];
  onChange: (selected: string[]) => void;
}

export default function ChannelSelector({
  contentType,
  selected,
  onChange,
}: Props) {
  const toggle = (id: string) => {
    if (!isPlatformAvailable(id, contentType)) return;
    onChange(
      selected.includes(id)
        ? selected.filter((s) => s !== id)
        : [...selected, id]
    );
  };

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-semibold">选择发布渠道</h2>
        <p className="text-gray-400 mt-1">
          根据内容类型，部分渠道可能不可选
        </p>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        {PLATFORMS.map((platform) => {
          const available = isPlatformAvailable(platform.id, contentType);
          const isSelected = selected.includes(platform.id);

          return (
            <button
              key={platform.id}
              onClick={() => toggle(platform.id)}
              disabled={!available}
              data-testid={`channel-${platform.id}`}
              data-available={available}
              className={cn(
                "relative flex items-start gap-4 p-5 rounded-xl border text-left transition-all duration-300",
                !available
                  ? "opacity-40 cursor-not-allowed bg-gray-900/30 border-gray-800/30"
                  : isSelected
                    ? "glass border-primary-500/50 ring-1 ring-primary-500/30 shadow-lg shadow-primary-500/5"
                    : "glass glass-hover border-gray-700/50"
              )}
            >
              {/* Icon */}
              <div
                className={cn(
                  "flex h-12 w-12 shrink-0 items-center justify-center rounded-lg bg-gradient-to-br text-white",
                  available
                    ? CHANNEL_COLORS[platform.id] || "from-gray-500 to-gray-600"
                    : "from-gray-700 to-gray-800"
                )}
              >
                {available ? (
                  CHANNEL_ICONS[platform.id] || (
                    <MessageSquare className="h-5 w-5" />
                  )
                ) : (
                  <Lock className="h-5 w-5 text-gray-500" />
                )}
              </div>

              {/* Content */}
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <p className="font-semibold">{platform.name}</p>
                  {!available && (
                    <span className="text-xs text-gray-500 bg-gray-800/50 px-2 py-0.5 rounded">
                      不支持{contentType === "article" ? "文稿" : "视频"}
                    </span>
                  )}
                </div>
                <p className="text-sm text-gray-400 mt-0.5">
                  {platform.description}
                </p>
                <div className="flex gap-1.5 mt-2">
                  {platform.supports.article && (
                    <span className="text-xs px-2 py-0.5 rounded bg-amber-500/10 text-amber-400 border border-amber-500/20">
                      文稿
                    </span>
                  )}
                  {platform.supports.video && (
                    <span className="text-xs px-2 py-0.5 rounded bg-purple-500/10 text-purple-400 border border-purple-500/20">
                      视频
                    </span>
                  )}
                </div>
              </div>

              {/* Check */}
              {isSelected && available && (
                <div className="absolute top-3 right-3 h-6 w-6 rounded-full gradient-primary flex items-center justify-center">
                  <Check className="h-3.5 w-3.5 text-white" />
                </div>
              )}
            </button>
          );
        })}
      </div>
    </div>
  );
}
