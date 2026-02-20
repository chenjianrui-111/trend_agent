import { NavLink, useNavigate } from "react-router-dom";
import { LayoutDashboard, FileText, Database, LogOut, Zap } from "lucide-react";
import { clearToken } from "@/api/client";
import { cn } from "@/lib/utils";

const NAV_ITEMS = [
  { to: "/", icon: LayoutDashboard, label: "仪表盘" },
  { to: "/content", icon: FileText, label: "内容管理" },
  { to: "/sources", icon: Database, label: "数据源" },
];

export default function Sidebar() {
  const navigate = useNavigate();

  const handleLogout = () => {
    clearToken();
    navigate("/login");
  };

  return (
    <aside className="hidden lg:flex w-64 flex-col glass border-r border-gray-800/50">
      {/* Logo */}
      <div className="flex items-center gap-3 px-6 py-5 border-b border-gray-800/50">
        <div className="flex h-9 w-9 items-center justify-center rounded-lg gradient-primary">
          <Zap className="h-5 w-5 text-white" />
        </div>
        <div>
          <h1 className="text-lg font-bold gradient-text">TrendAgent</h1>
          <p className="text-xs text-gray-500">智能内容发布平台</p>
        </div>
      </div>

      {/* Navigation */}
      <nav className="flex-1 px-3 py-4 space-y-1">
        {NAV_ITEMS.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.to === "/"}
            className={({ isActive }) =>
              cn(
                "flex items-center gap-3 px-4 py-2.5 rounded-lg text-sm font-medium transition-all duration-200",
                isActive
                  ? "bg-primary-600/20 text-primary-400 border border-primary-500/30"
                  : "text-gray-400 hover:text-gray-200 hover:bg-gray-800/50"
              )
            }
          >
            <item.icon className="h-4.5 w-4.5" />
            {item.label}
          </NavLink>
        ))}
      </nav>

      {/* Logout */}
      <div className="px-3 py-4 border-t border-gray-800/50">
        <button
          onClick={handleLogout}
          className="flex items-center gap-3 w-full px-4 py-2.5 rounded-lg text-sm text-gray-400 hover:text-red-400 hover:bg-red-500/10 transition-all duration-200"
        >
          <LogOut className="h-4.5 w-4.5" />
          退出登录
        </button>
      </div>
    </aside>
  );
}
