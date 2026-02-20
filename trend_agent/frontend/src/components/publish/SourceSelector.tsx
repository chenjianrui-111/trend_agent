import { SOURCES } from "@/lib/platform-constraints";
import { cn } from "@/lib/utils";
import { Check, Globe, Youtube, Github } from "lucide-react";

const SOURCE_ICONS: Record<string, React.ReactNode> = {
  twitter: <Globe className="h-6 w-6" />,
  youtube: <Youtube className="h-6 w-6" />,
  weibo: <span className="text-lg font-bold">微</span>,
  bilibili: <span className="text-lg font-bold">B</span>,
  zhihu: <span className="text-lg font-bold">知</span>,
  github: <Github className="h-6 w-6" />,
};

const SOURCE_COLORS: Record<string, string> = {
  twitter: "from-sky-500 to-blue-600",
  youtube: "from-red-500 to-red-600",
  weibo: "from-orange-500 to-red-500",
  bilibili: "from-pink-400 to-blue-400",
  zhihu: "from-blue-500 to-blue-600",
  github: "from-gray-600 to-gray-700",
};

interface Props {
  selected: string[];
  onChange: (selected: string[]) => void;
}

export default function SourceSelector({ selected, onChange }: Props) {
  const toggle = (id: string) => {
    onChange(
      selected.includes(id)
        ? selected.filter((s) => s !== id)
        : [...selected, id]
    );
  };

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-semibold">选择数据源</h2>
        <p className="text-gray-400 mt-1">
          选择要抓取的热门内容来源，支持多选
        </p>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {SOURCES.map((source) => {
          const isSelected = selected.includes(source.id);
          return (
            <button
              key={source.id}
              onClick={() => toggle(source.id)}
              data-testid={`source-${source.id}`}
              className={cn(
                "relative flex items-start gap-4 p-5 rounded-xl border text-left transition-all duration-300",
                isSelected
                  ? "glass border-primary-500/50 ring-1 ring-primary-500/30 shadow-lg shadow-primary-500/5"
                  : "glass glass-hover border-gray-700/50"
              )}
            >
              {/* Icon */}
              <div
                className={cn(
                  "flex h-12 w-12 shrink-0 items-center justify-center rounded-lg bg-gradient-to-br text-white",
                  SOURCE_COLORS[source.id] || "from-gray-500 to-gray-600"
                )}
              >
                {SOURCE_ICONS[source.id]}
              </div>

              {/* Content */}
              <div className="flex-1 min-w-0">
                <p className="font-semibold">{source.name}</p>
                <p className="text-sm text-gray-400 mt-0.5">
                  {source.description}
                </p>
              </div>

              {/* Check */}
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
