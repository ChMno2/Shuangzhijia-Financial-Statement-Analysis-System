import { useEffect, useState } from 'react'
import { getDashboard } from '../api'
import StatCard from '../components/StatCard'
import { DollarSign, ShoppingBag, Tag, TrendingUp } from 'lucide-react'
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from 'recharts'

const fmt = (n) => `NT$ ${Number(n || 0).toLocaleString()}`

export default function Dashboard() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    getDashboard().then(d => { setData(d); setLoading(false) }).catch(() => setLoading(false))
  }, [])

  if (loading) return <div className="p-8 text-slate-500">載入中...</div>
  if (!data) return <div className="p-8 text-red-500">無法連線到後端，請確認後端服務已啟動。</div>

  const s = data.summary || {}
  const daily = data.daily_sales || []

  const chartData = daily.slice(-14).map(d => ({
    ...d,
    date: d.date?.slice(5),
    revenue: Number(d.revenue),
  }))

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-bold text-slate-800">儀表板總覽</h2>
        {s.data_latest_date && (
          <p className="text-xs text-slate-400 mt-0.5">資料最新日期：{s.data_latest_date}（近 30 天為基準）</p>
        )}
      </div>

      {/* KPI 卡片 */}
      <div className="grid grid-cols-2 xl:grid-cols-4 gap-4">
        <StatCard
          title="本週營收"
          value={fmt(s.this_week_revenue)}
          growth={s.week_growth}
          icon={DollarSign}
          color="blue"
        />
        <StatCard
          title="本月累計"
          value={fmt(s.this_month_revenue)}
          sub="本月至今"
          icon={ShoppingBag}
          color="green"
        />
        <StatCard
          title="近30天商品種類"
          value={`${s.unique_products ?? 0} 種`}
          sub="有銷售紀錄"
          icon={Tag}
          color="purple"
        />
        <StatCard
          title="近30天交易筆數"
          value={`${s.total_transactions ?? 0} 筆`}
          sub="銷售交易"
          icon={TrendingUp}
          color="orange"
        />
      </div>

      {/* 銷售趨勢圖 */}
      <div className="bg-white rounded-2xl p-5 shadow-sm border border-slate-100">
        <h3 className="font-semibold text-slate-700 mb-4">近 14 天銷售趨勢</h3>
        <ResponsiveContainer width="100%" height={260}>
          <LineChart data={chartData}>
            <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
            <XAxis dataKey="date" tick={{ fontSize: 12 }} />
            <YAxis tick={{ fontSize: 12 }} tickFormatter={v => `${(v / 1000).toFixed(0)}K`} />
            <Tooltip formatter={v => fmt(v)} labelFormatter={l => `日期：${l}`} />
            <Line type="monotone" dataKey="revenue" stroke="#3b82f6" strokeWidth={2.5} dot={false} name="營收" />
          </LineChart>
        </ResponsiveContainer>
      </div>

      {/* 各大類 + 各營業點並排 */}
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-5">
        {/* 類別銷售 */}
        {data.category_sales?.length > 0 && (
          <div className="bg-white rounded-2xl p-5 shadow-sm border border-slate-100">
            <h3 className="font-semibold text-slate-700 mb-3">各大類銷售（近30天）</h3>
            <div className="space-y-3">
              {data.category_sales.map((c, i) => (
                <div key={i}>
                  <div className="flex justify-between text-sm mb-1">
                    <span className="text-slate-600 font-medium">{c.category}</span>
                    <span className="text-slate-800 font-semibold">{fmt(c.revenue)}</span>
                  </div>
                  <div className="h-2 bg-slate-100 rounded-full overflow-hidden">
                    <div className="h-full rounded-full bg-blue-500 transition-all"
                      style={{ width: `${c.percentage}%` }} />
                  </div>
                  <div className="text-xs text-slate-400 mt-0.5 text-right">{c.percentage}%</div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* 營業點銷售 */}
        {data.location_sales?.length > 0 && (
          <div className="bg-white rounded-2xl p-5 shadow-sm border border-slate-100">
            <h3 className="font-semibold text-slate-700 mb-3">各營業點銷售（近30天）</h3>
            <div className="space-y-3">
              {data.location_sales.map((loc, i) => (
                <div key={i}>
                  <div className="flex justify-between text-sm mb-1">
                    <span className="text-slate-600 font-medium">{loc.location}</span>
                    <span className="text-slate-800 font-semibold">{fmt(loc.revenue)}</span>
                  </div>
                  <div className="h-2 bg-slate-100 rounded-full overflow-hidden">
                    <div className="h-full rounded-full bg-purple-500 transition-all"
                      style={{ width: `${loc.percentage}%` }} />
                  </div>
                  <div className="text-xs text-slate-400 mt-0.5 text-right">{loc.percentage}%</div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* 暢銷商品 TOP 5 */}
      {data.products?.length > 0 && (
        <div className="bg-white rounded-2xl p-5 shadow-sm border border-slate-100">
          <h3 className="font-semibold text-slate-700 mb-3">近30天暢銷商品 TOP 5</h3>
          <div className="space-y-2">
            {data.products.slice(0, 5).map((p, i) => (
              <div key={i} className="flex items-center gap-3 py-1.5">
                <span className={`w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold flex-shrink-0 ${
                  i === 0 ? 'bg-yellow-100 text-yellow-700' :
                  i === 1 ? 'bg-slate-100 text-slate-600' :
                  i === 2 ? 'bg-orange-100 text-orange-600' : 'bg-slate-50 text-slate-400'
                }`}>{i + 1}</span>
                <span className="flex-1 text-sm text-slate-700 font-medium truncate">{p['品名']}</span>
                <span className="text-xs text-slate-400 px-2 py-0.5 bg-blue-50 text-blue-600 rounded-full">{p.category}</span>
                <span className="text-sm font-semibold text-slate-800 w-28 text-right">{fmt(p.revenue)}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
