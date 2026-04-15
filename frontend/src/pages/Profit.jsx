import { useEffect, useState } from 'react'
import { getProfit } from '../api'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend,
  ResponsiveContainer
} from 'recharts'

const fmt = (n) => `NT$ ${Number(n || 0).toLocaleString()}`
const COLORS = { revenue: '#6366f1', cost: '#f59e0b', profit: '#10b981' }
const CAT_COLORS = ['#3b82f6', '#10b981', '#f59e0b', '#8b5cf6', '#ef4444']

const DAYS_OPTIONS = [
  { label: '近 30 天', value: 30 },
  { label: '近 60 天', value: 60 },
  { label: '近 90 天', value: 90 },
]

export default function Profit() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [days, setDays] = useState(30)
  const [startDate, setStartDate] = useState('')
  const [endDate, setEndDate] = useState('')
  const [useCustom, setUseCustom] = useState(false)

  const fetchData = () => {
    setLoading(true)
    const params = useCustom && startDate && endDate
      ? { startDate, endDate }
      : { days }
    getProfit(params).then(d => { setData(d); setLoading(false) })
  }

  useEffect(() => { fetchData() }, [days])

  const s = data?.summary || {}
  const hasCost = s.has_cost_data

  const catData = (data?.category_profit || []).map(c => ({
    ...c,
    margin: c.margin ?? null,
  }))

  // 前20商品（依利潤或售額）
  const prodData = data?.product_profit || []

  return (
    <div className="space-y-5">
      {/* 標題 + 篩選 */}
      <div className="flex items-start justify-between flex-wrap gap-3">
        <div>
          <h2 className="text-xl font-bold text-slate-800">成本與利潤分析</h2>
          <p className="text-xs text-slate-400 mt-0.5">
            {hasCost
            ? `含成本資料：${s.cost_coverage_rows} 筆 / 共 ${s.transactions} 筆（${s.cost_coverage_pct}% 覆蓋）— 毛利率僅計算有成本記錄的部分`
            : '目前期間無成本資料，僅顯示銷售額'}
          </p>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          {!useCustom && DAYS_OPTIONS.map(o => (
            <button key={o.value} onClick={() => { setUseCustom(false); setDays(o.value) }}
              className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                days === o.value && !useCustom
                  ? 'bg-blue-600 text-white' : 'bg-white text-slate-600 border border-slate-200 hover:border-blue-300'
              }`}>
              {o.label}
            </button>
          ))}
          <button onClick={() => setUseCustom(v => !v)}
            className={`px-3 py-1.5 rounded-lg text-sm font-medium border transition-colors ${
              useCustom ? 'bg-purple-600 text-white border-purple-600' : 'bg-white text-slate-600 border-slate-200 hover:border-purple-300'
            }`}>
            自訂日期
          </button>
        </div>
      </div>

      {/* 自訂日期列 */}
      {useCustom && (
        <div className="flex items-center gap-3 bg-white rounded-xl px-4 py-3 border border-slate-200 shadow-sm flex-wrap">
          <label className="text-sm text-slate-500">起始日期</label>
          <input type="date" value={startDate} onChange={e => setStartDate(e.target.value)}
            className="border border-slate-200 rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-300" />
          <span className="text-slate-400">—</span>
          <label className="text-sm text-slate-500">結束日期</label>
          <input type="date" value={endDate} onChange={e => setEndDate(e.target.value)}
            className="border border-slate-200 rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-300" />
          <button onClick={fetchData} disabled={!startDate || !endDate}
            className="px-4 py-1.5 bg-blue-600 text-white rounded-lg text-sm font-medium disabled:opacity-40 hover:bg-blue-700 transition-colors">
            查詢
          </button>
        </div>
      )}

      {loading ? (
        <div className="h-40 flex items-center justify-center text-slate-400">載入中...</div>
      ) : (
        <>
          {/* 整體摘要卡片 */}
          <div className={`grid gap-4 ${hasCost ? 'grid-cols-2 xl:grid-cols-4' : 'grid-cols-2'}`}>
            <SumCard label="總銷售額" value={fmt(s.total_revenue)} color="indigo" />
            {hasCost && <SumCard label="總成本" value={fmt(s.total_cost)} color="amber" />}
            {hasCost && <SumCard label="總毛利" value={fmt(s.total_profit)} color="green" />}
            {hasCost
              ? <SumCard label="整體毛利率" value={`${s.overall_margin}%`} color="purple" />
              : <SumCard label="交易筆數" value={`${s.transactions} 筆`} color="blue" />
            }
          </div>

          {/* 各類別對比圖 */}
          <div className="bg-white rounded-2xl p-5 shadow-sm border border-slate-100">
            <h3 className="font-semibold text-slate-700 mb-1">各大類 銷售額 {hasCost ? '/ 成本 / 毛利' : ''} 比較</h3>
            <p className="text-xs text-slate-400 mb-4">
              驗證假設：服飾毛利率高 vs 食品量多但毛利率較低
            </p>
            <ResponsiveContainer width="100%" height={280}>
              <BarChart data={catData} barGap={4}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                <XAxis dataKey="category" tick={{ fontSize: 12 }} />
                <YAxis tick={{ fontSize: 11 }} tickFormatter={v => `${(v / 1000).toFixed(0)}K`} />
                <Tooltip formatter={v => fmt(v)} />
                <Legend />
                <Bar dataKey="revenue" name="銷售額" fill={COLORS.revenue} radius={[3, 3, 0, 0]} />
                {hasCost && <Bar dataKey="cost" name="成本" fill={COLORS.cost} radius={[3, 3, 0, 0]} />}
                {hasCost && <Bar dataKey="profit" name="毛利" fill={COLORS.profit} radius={[3, 3, 0, 0]} />}
              </BarChart>
            </ResponsiveContainer>
          </div>

          {/* 類別明細表 */}
          <div className="bg-white rounded-2xl shadow-sm border border-slate-100 overflow-hidden">
            <div className="px-5 py-4 border-b border-slate-50">
              <h3 className="font-semibold text-slate-700">各大類利潤明細</h3>
            </div>
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-slate-50 border-b border-slate-100">
                  <th className="text-left px-5 py-3 text-slate-500 font-medium">類別</th>
                  <th className="text-right px-5 py-3 text-slate-500 font-medium">銷售額</th>
                  {hasCost && <th className="text-right px-5 py-3 text-slate-500 font-medium">成本</th>}
                  {hasCost && <th className="text-right px-5 py-3 text-slate-500 font-medium">毛利</th>}
                  {hasCost && <th className="text-right px-5 py-3 text-slate-500 font-medium">毛利率</th>}
                  <th className="text-right px-5 py-3 text-slate-500 font-medium">件數</th>
                  <th className="text-right px-5 py-3 text-slate-500 font-medium">平均客單價</th>
                </tr>
              </thead>
              <tbody>
                {catData.map((c, i) => (
                  <tr key={i} className="border-b border-slate-50 hover:bg-slate-50/50">
                    <td className="px-5 py-3">
                      <div className="flex items-center gap-2">
                        <div className="w-3 h-3 rounded-full" style={{ background: CAT_COLORS[i % CAT_COLORS.length] }} />
                        <span className="font-medium text-slate-700">{c.category}</span>
                      </div>
                    </td>
                    <td className="px-5 py-3 text-right font-medium text-slate-800">{fmt(c.revenue)}</td>
                    {hasCost && <td className="px-5 py-3 text-right text-amber-600">{fmt(c.cost)}</td>}
                    {hasCost && <td className="px-5 py-3 text-right text-green-600 font-medium">{fmt(c.profit)}</td>}
                    {hasCost && (
                      <td className="px-5 py-3 text-right">
                        <MarginBadge value={c.margin} />
                      </td>
                    )}
                    <td className="px-5 py-3 text-right text-slate-600">{c.quantity}</td>
                    <td className="px-5 py-3 text-right text-slate-600">{fmt(c.avg_price)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* 商品利潤 TOP20 */}
          {prodData.length > 0 && (
            <div className="bg-white rounded-2xl shadow-sm border border-slate-100 overflow-hidden">
              <div className="px-5 py-4 border-b border-slate-50">
                <h3 className="font-semibold text-slate-700">商品利潤 TOP 20</h3>
              </div>
              <table className="w-full text-sm">
                <thead>
                  <tr className="bg-slate-50 border-b border-slate-100">
                    <th className="text-left px-5 py-3 text-slate-500 font-medium w-8">#</th>
                    <th className="text-left px-5 py-3 text-slate-500 font-medium">商品名稱</th>
                    <th className="text-left px-5 py-3 text-slate-500 font-medium">類別</th>
                    <th className="text-right px-5 py-3 text-slate-500 font-medium">銷售額</th>
                    {hasCost && <th className="text-right px-5 py-3 text-slate-500 font-medium">成本</th>}
                    {hasCost && <th className="text-right px-5 py-3 text-slate-500 font-medium">毛利</th>}
                    {hasCost && <th className="text-right px-5 py-3 text-slate-500 font-medium">毛利率</th>}
                    <th className="text-right px-5 py-3 text-slate-500 font-medium">件數</th>
                  </tr>
                </thead>
                <tbody>
                  {prodData.map((p, i) => (
                    <tr key={i} className="border-b border-slate-50 hover:bg-slate-50/50">
                      <td className="px-5 py-2.5 text-slate-400 text-xs">{i + 1}</td>
                      <td className="px-5 py-2.5 font-medium text-slate-800 max-w-[200px] truncate" title={p['品名']}>
                        {p['品名']}
                      </td>
                      <td className="px-5 py-2.5">
                        <span className="px-2 py-0.5 bg-blue-50 text-blue-600 rounded-full text-xs">{p.category || '-'}</span>
                      </td>
                      <td className="px-5 py-2.5 text-right font-medium text-slate-800">{fmt(p.revenue)}</td>
                      {hasCost && (
                        <td className="px-5 py-2.5 text-right">
                          {p.cost != null
                            ? <span className="text-amber-600">{fmt(p.cost)}</span>
                            : <span className="text-slate-300 text-xs">表單未填寫</span>}
                        </td>
                      )}
                      {hasCost && (
                        <td className="px-5 py-2.5 text-right text-green-600 font-medium">
                          {p.profit != null ? fmt(p.profit) : <span className="text-slate-300 text-xs">—</span>}
                        </td>
                      )}
                      {hasCost && (
                        <td className="px-5 py-2.5 text-right">
                          <MarginBadge value={p.margin} />
                        </td>
                      )}
                      <td className="px-5 py-2.5 text-right text-slate-600">{p.quantity ?? '-'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </div>
  )
}

function SumCard({ label, value, color }) {
  const colors = {
    indigo: 'border-indigo-100 bg-indigo-50 text-indigo-700',
    amber: 'border-amber-100 bg-amber-50 text-amber-700',
    green: 'border-green-100 bg-green-50 text-green-700',
    purple: 'border-purple-100 bg-purple-50 text-purple-700',
    blue: 'border-blue-100 bg-blue-50 text-blue-700',
  }
  return (
    <div className={`rounded-2xl p-5 border ${colors[color]}`}>
      <p className="text-sm font-medium opacity-70">{label}</p>
      <p className="text-2xl font-bold mt-1">{value}</p>
    </div>
  )
}

function MarginBadge({ value }) {
  if (value == null) return <span className="text-slate-300">-</span>
  const color = value >= 60 ? 'bg-green-100 text-green-700'
    : value >= 45 ? 'bg-blue-100 text-blue-700'
    : 'bg-orange-100 text-orange-700'
  return (
    <span className={`px-2 py-0.5 rounded-full text-xs font-semibold ${color}`}>
      {value}%
    </span>
  )
}
