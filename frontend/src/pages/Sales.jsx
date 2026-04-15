import { useEffect, useState } from 'react'
import { getDailySales } from '../api'
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer
} from 'recharts'

const fmt = (n) => `NT$ ${Number(n || 0).toLocaleString()}`

const DAYS_OPTIONS = [
  { label: '近 30 天', value: 30 },
  { label: '近 60 天', value: 60 },
  { label: '近 90 天', value: 90 },
]

export default function Sales() {
  const [data, setData] = useState([])
  const [days, setDays] = useState(30)
  const [loading, setLoading] = useState(true)
  const [useCustom, setUseCustom] = useState(false)
  const [startDate, setStartDate] = useState('')
  const [endDate, setEndDate] = useState('')

  const fetchData = (opts = {}) => {
    setLoading(true)
    const params = useCustom && startDate && endDate
      ? { startDate, endDate, topProducts: true }
      : { days: opts.days ?? days, topProducts: true }
    getDailySales(params).then(d => {
      setData(d.daily_sales || [])
      setLoading(false)
    })
  }

  useEffect(() => { fetchData() }, [days])

  const chartData = data.map(r => ({
    ...r,
    date: r.date?.slice(5),
    revenue: Number(r.revenue),
  }))

  const total = data.reduce((s, d) => s + d.revenue, 0)
  const avg = data.length ? total / data.length : 0
  const max = data.length ? Math.max(...data.map(d => d.revenue)) : 0

  return (
    <div className="space-y-5">
      {/* 標題 + 篩選 */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <h2 className="text-xl font-bold text-slate-800">銷售報表</h2>
        <div className="flex items-center gap-2 flex-wrap">
          {!useCustom && DAYS_OPTIONS.map(o => (
            <button key={o.value}
              onClick={() => { setUseCustom(false); setDays(o.value); fetchData({ days: o.value }) }}
              className={`px-4 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                days === o.value && !useCustom
                  ? 'bg-blue-600 text-white'
                  : 'bg-white text-slate-600 border border-slate-200 hover:border-blue-300'
              }`}>
              {o.label}
            </button>
          ))}
          <button onClick={() => setUseCustom(v => !v)}
            className={`px-4 py-1.5 rounded-lg text-sm font-medium border transition-colors ${
              useCustom ? 'bg-purple-600 text-white border-purple-600' : 'bg-white text-slate-600 border-slate-200 hover:border-purple-300'
            }`}>
            自訂日期
          </button>
        </div>
      </div>

      {/* 自訂日期列 */}
      {useCustom && (
        <div className="flex items-center gap-3 bg-white rounded-xl px-4 py-3 border border-slate-200 shadow-sm flex-wrap">
          <label className="text-sm text-slate-500">起始</label>
          <input type="date" value={startDate} onChange={e => setStartDate(e.target.value)}
            className="border border-slate-200 rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-300" />
          <span className="text-slate-400">—</span>
          <label className="text-sm text-slate-500">結束</label>
          <input type="date" value={endDate} onChange={e => setEndDate(e.target.value)}
            className="border border-slate-200 rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-300" />
          <button onClick={() => fetchData()}
            disabled={!startDate || !endDate}
            className="px-4 py-1.5 bg-blue-600 text-white rounded-lg text-sm font-medium disabled:opacity-40 hover:bg-blue-700 transition-colors">
            查詢
          </button>
        </div>
      )}

      {/* 統計摘要 */}
      <div className="grid grid-cols-3 gap-4">
        {[
          { label: '期間合計', value: fmt(total) },
          { label: '日均營收', value: fmt(avg) },
          { label: '單日最高', value: fmt(max) },
        ].map(({ label, value }) => (
          <div key={label} className="bg-white rounded-2xl p-5 shadow-sm border border-slate-100">
            <p className="text-sm text-slate-500">{label}</p>
            <p className="text-xl font-bold text-slate-800 mt-1">{value}</p>
          </div>
        ))}
      </div>

      {/* 面積圖 */}
      <div className="bg-white rounded-2xl p-5 shadow-sm border border-slate-100">
        <h3 className="font-semibold text-slate-700 mb-4">銷售趨勢</h3>
        {loading ? (
          <div className="h-64 flex items-center justify-center text-slate-400">載入中...</div>
        ) : (
          <ResponsiveContainer width="100%" height={280}>
            <AreaChart data={chartData}>
              <defs>
                <linearGradient id="revenueGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.15} />
                  <stop offset="95%" stopColor="#3b82f6" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
              <XAxis dataKey="date" tick={{ fontSize: 11 }}
                interval={chartData.length > 30 ? Math.floor(chartData.length / 15) : 'preserveStartEnd'} />
              <YAxis tick={{ fontSize: 11 }} tickFormatter={v => `${(v / 1000).toFixed(0)}K`} />
              <Tooltip formatter={v => fmt(v)} labelFormatter={l => `日期：${l}`} />
              <Area type="monotone" dataKey="revenue" stroke="#3b82f6" strokeWidth={2.5}
                fill="url(#revenueGrad)" name="營收" />
            </AreaChart>
          </ResponsiveContainer>
        )}
      </div>

      {/* 每日明細表（含 TOP2 商品）*/}
      <div className="bg-white rounded-2xl shadow-sm border border-slate-100 overflow-hidden">
        <div className="px-5 py-4 border-b border-slate-50">
          <h3 className="font-semibold text-slate-700">每日銷售明細</h3>
          <p className="text-xs text-slate-400 mt-0.5">含當日銷售最好的前 2 項商品</p>
        </div>
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-slate-50 border-b border-slate-100">
              <th className="text-left px-5 py-3 text-slate-500 font-medium">日期</th>
              <th className="text-right px-5 py-3 text-slate-500 font-medium">當日營收</th>
              <th className="text-right px-5 py-3 text-slate-500 font-medium">件數</th>
              <th className="text-left px-5 py-3 text-slate-500 font-medium">TOP 1 商品</th>
              <th className="text-left px-5 py-3 text-slate-500 font-medium">TOP 2 商品</th>
            </tr>
          </thead>
          <tbody>
            {[...data].reverse().map((d, i) => {
              const top = d.top_products || []
              return (
                <tr key={i} className="border-b border-slate-50 hover:bg-slate-50/50">
                  <td className="px-5 py-2.5 text-slate-600 font-mono text-xs">{d.date}</td>
                  <td className="px-5 py-2.5 text-right font-medium text-slate-800">{fmt(d.revenue)}</td>
                  <td className="px-5 py-2.5 text-right text-slate-500">{d.quantity ?? '-'}</td>
                  <td className="px-5 py-2.5">
                    {top[0]
                      ? <TopProductBadge name={top[0].name} revenue={top[0].revenue} rank={1} />
                      : <span className="text-slate-300">-</span>}
                  </td>
                  <td className="px-5 py-2.5">
                    {top[1]
                      ? <TopProductBadge name={top[1].name} revenue={top[1].revenue} rank={2} />
                      : <span className="text-slate-300">-</span>}
                  </td>
                </tr>
              )
            })}
            {data.length === 0 && !loading && (
              <tr>
                <td colSpan={5} className="px-5 py-10 text-center text-slate-400">
                  無資料，請調整日期範圍
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function TopProductBadge({ name, revenue, rank }) {
  const colors = [
    'bg-yellow-50 text-yellow-700 border-yellow-200',
    'bg-slate-50 text-slate-600 border-slate-200',
  ]
  return (
    <div className={`inline-flex items-center gap-1.5 px-2 py-1 rounded-lg border text-xs max-w-[180px] ${colors[rank - 1]}`}>
      <span className="font-bold">{rank}</span>
      <span className="truncate font-medium" title={name}>{name}</span>
      <span className="ml-auto shrink-0 opacity-70">{(revenue / 1000).toFixed(1)}K</span>
    </div>
  )
}
