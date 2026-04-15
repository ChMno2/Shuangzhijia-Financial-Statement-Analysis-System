import { TrendingUp, TrendingDown } from 'lucide-react'

export default function StatCard({ title, value, sub, growth, icon: Icon, color = 'blue' }) {
  const colorMap = {
    blue: 'bg-blue-50 text-blue-600',
    green: 'bg-green-50 text-green-600',
    orange: 'bg-orange-50 text-orange-600',
    purple: 'bg-purple-50 text-purple-600',
  }

  const isPositive = growth >= 0

  return (
    <div className="bg-white rounded-2xl p-5 shadow-sm border border-slate-100">
      <div className="flex items-start justify-between">
        <div>
          <p className="text-sm text-slate-500 font-medium">{title}</p>
          <p className="text-2xl font-bold text-slate-800 mt-1">{value}</p>
          {sub && <p className="text-xs text-slate-400 mt-1">{sub}</p>}
        </div>
        {Icon && (
          <div className={`p-2.5 rounded-xl ${colorMap[color]}`}>
            <Icon size={20} />
          </div>
        )}
      </div>
      {growth !== undefined && (
        <div className={`flex items-center gap-1 mt-3 text-sm font-medium ${isPositive ? 'text-green-600' : 'text-red-500'}`}>
          {isPositive ? <TrendingUp size={15} /> : <TrendingDown size={15} />}
          {isPositive ? '+' : ''}{growth}% 相較上週
        </div>
      )}
    </div>
  )
}
