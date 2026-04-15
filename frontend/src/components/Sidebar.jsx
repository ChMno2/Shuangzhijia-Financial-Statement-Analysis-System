import { LayoutDashboard, Package, BarChart2, PieChart, MessageSquare, FileText, RefreshCw, Upload, TrendingUp, LogOut, User } from 'lucide-react'

const navItems = [
  { id: 'dashboard', label: '儀表板', icon: LayoutDashboard },
  { id: 'products', label: '商品管理', icon: Package },
  { id: 'sales', label: '銷售報表', icon: BarChart2 },
  { id: 'categories', label: '類別分析', icon: PieChart },
  { id: 'profit', label: '成本利潤分析', icon: TrendingUp },
  { id: 'chat', label: 'AI 問答', icon: MessageSquare },
  { id: 'report', label: 'AI 週報', icon: FileText },
]

export default function Sidebar({ active, onNavigate, onUpload, onRefresh, user, onLogout }) {
  return (
    <aside className="w-60 bg-white border-r border-slate-200 flex flex-col min-h-screen fixed top-0 left-0 z-20">
      {/* Logo */}
      <div className="px-6 py-5 border-b border-slate-100">
        <h1 className="text-lg font-bold text-slate-800">商業後台系統</h1>
        <p className="text-xs text-slate-400 mt-0.5">數據分析平台</p>
      </div>

      {/* Nav */}
      <nav className="flex-1 py-4 px-3 space-y-1">
        {navItems.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            onClick={() => onNavigate(id)}
            className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors ${
              active === id
                ? 'bg-blue-50 text-blue-600'
                : 'text-slate-600 hover:bg-slate-50 hover:text-slate-800'
            }`}
          >
            <Icon size={18} />
            {label}
          </button>
        ))}
      </nav>

      {/* 底部工具 */}
      <div className="px-3 py-4 border-t border-slate-100 space-y-1">
        <label className="w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium text-slate-600 hover:bg-slate-50 cursor-pointer transition-colors">
          <Upload size={18} />
          上傳 Excel
          <input type="file" accept=".xlsx,.xls,.csv" className="hidden" onChange={onUpload} />
        </label>
        <button
          onClick={onRefresh}
          className="w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium text-slate-600 hover:bg-slate-50 transition-colors"
        >
          <RefreshCw size={18} />
          重新整理資料
        </button>

        {/* 登入者資訊 + 登出 */}
        <div className="mt-2 pt-3 border-t border-slate-100">
          <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-slate-50">
            <div className="w-7 h-7 rounded-full bg-blue-100 flex items-center justify-center flex-shrink-0">
              <User size={14} className="text-blue-600" />
            </div>
            <span className="text-sm font-medium text-slate-700 flex-1 truncate">{user}</span>
            <button
              onClick={onLogout}
              title="登出"
              className="text-slate-400 hover:text-red-500 transition-colors"
            >
              <LogOut size={15} />
            </button>
          </div>
        </div>
      </div>
    </aside>
  )
}
