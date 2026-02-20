import type { ContentType } from "@/lib/platform-constraints";
import { cn } from "@/lib/utils";
import { FileText, Video, Check } from "lucide-react";

const CONTENT_TYPES: {
  id: ContentType;
  label: string;
  description: string;
  icon: typeof FileText;
  gradient: string;
  platforms: string;
}[] = [
  {
    id: "article",
    label: "文稿（含配图）",
    description: "AI 生成图文内容，适合深度阅读场景",
    icon: FileText,
    gradient: "from-amber-500 to-orange-500",
    platforms: "微信公众号、小红书、微博",
  },
  {
    id: "video",
    label: "AIGC 视频",
    description: "AI 生成短视频内容，适合短视频平台",
    icon: Video,
    gradient: "from-purple-500 to-pink-500",
    platforms: "抖音、小红书、微博",
  },
];

interface Props {
  selected: ContentType | null;
  onChange: (type: ContentType) => void;
}

export default function ContentTypeSelector({ selected, onChange }: Props) {
  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-semibold">选择内容类型</h2>
        <p className="text-gray-400 mt-1">
          选择生成的内容形式，不同渠道支持的类型不同
        </p>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
        {CONTENT_TYPES.map((type) => {
          const isSelected = selected === type.id;
          return (
            <button
              key={type.id}
              onClick={() => onChange(type.id)}
              data-testid={`content-type-${type.id}`}
              className={cn(
                "relative flex flex-col items-center gap-4 p-8 rounded-xl border text-center transition-all duration-300",
                isSelected
                  ? "glass border-primary-500/50 ring-1 ring-primary-500/30 shadow-lg shadow-primary-500/5"
                  : "glass glass-hover border-gray-700/50"
              )}
            >
              <div
                className={cn(
                  "flex h-16 w-16 items-center justify-center rounded-2xl bg-gradient-to-br text-white",
                  type.gradient
                )}
              >
                <type.icon className="h-8 w-8" />
              </div>

              <div>
                <p className="text-lg font-semibold">{type.label}</p>
                <p className="text-sm text-gray-400 mt-1">
                  {type.description}
                </p>
              </div>

              <div className="flex items-center gap-1.5 text-xs text-gray-500">
                <span>适用渠道：</span>
                <span className="text-gray-300">{type.platforms}</span>
              </div>

              {isSelected && (
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
