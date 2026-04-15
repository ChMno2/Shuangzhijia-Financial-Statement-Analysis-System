import { useEffect, useState } from 'react'
import { getProducts } from '../api'
import { Search } from 'lucide-react'

export default function Products() {
  const [products, setProducts] = useState([])
  const [search, setSearch] = useState('')
  const [category, setCategory] = useState('全部')
  const [loading, setLoading] = useState(true)
  const [sortBy, setSortBy] = useState('revenue')

  useEffect(() => {
    getProducts().then(d => { setProducts(d.products || []); setLoading(false) })
  }, [])

  const categories = ['全部', ...new Set(products.map(p => p.category).filter(Boolean))]

  const filtered = products.filter(p => {
    const name = p['品名'] || p.name || ''
    const matchSearch = !search || name.includes(search)
    const matchCat = category === '全部' || p.category === category
    return matchSearch && matchCat
  })

  const sorted = [...filtered].sort((a, b) => {
    if (sortBy === 'revenue') return (b.revenue || 0) - (a.revenue || 0)
    if (sortBy === 'quantity') return (b.quantity || 0) - (a.quantity || 0)
    if (sortBy === 'name') return (a['品名'] || '').localeCompare(b['品名'] || '')
    return 0
  })

  if (loading) return <div className="p-8 text-slate-500">載入中...</div>

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-bold text-slate-800">商品銷售排行</h2>
          <p className="text-xs text-slate-400 mt-0.5">近 30 天銷售資料</p>
        </div>
        <span className="text-sm text-slate-400">共 {filtered.length} 項商品</span>
      </div>

      {/* 篩選列 */}
      <div className="flex gap-3 flex-wrap">
        <div className="relative">
          <Search size={16} className="absolute left-3 top-2.5 text-slate-400" />
          <input
            className="pl-9 pr-4 py-2 rounded-lg border border-slate-200 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-blue-300 w-52"
            placeholder="搜尋商品名稱"
            value={search}
            onChange={e => setSearch(e.target.value)}
          />
        </div>
        {/* 類別篩選 */}
        <div className="flex gap-2 flex-wrap">
          {categories.map(c => (
            <button
              key={c}
              onClick={() => setCategory(c)}
              className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                category === c ? 'bg-blue-600 text-white' : 'bg-white text-slate-600 border border-slate-200 hover:border-blue-300'
              }`}
            >
              {c}
            </button>
          ))}
        </div>
        {/* 排序 */}
        <select
          value={sortBy}
          onChange={e => setSortBy(e.target.value)}
          className="ml-auto px-3 py-2 rounded-lg border border-slate-200 text-sm bg-white text-slate-600 focus:outline-none"
        >
          <option value="revenue">依銷售額排序</option>
          <option value="quantity">依銷售數量排序</option>
          <option value="name">依名稱排序</option>
        </select>
      </div>

      {/* 商品表格 */}
      <div className="bg-white rounded-2xl shadow-sm border border-slate-100 overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-slate-50 border-b border-slate-100">
              <th className="text-left px-5 py-3 text-slate-500 font-medium">排名</th>
              <th className="text-left px-5 py-3 text-slate-500 font-medium">商品名稱</th>
              <th className="text-left px-5 py-3 text-slate-500 font-medium">大類</th>
              <th className="text-right px-5 py-3 text-slate-500 font-medium">銷售數量</th>
              <th className="text-right px-5 py-3 text-slate-500 font-medium">銷售總額</th>
              <th className="px-5 py-3 text-slate-500 font-medium">佔比</th>
            </tr>
          </thead>
          <tbody>
            {(() => {
              const totalRev = sorted.reduce((s, p) => s + (p.revenue || 0), 0)
              return sorted.map((p, i) => {
                const name = p['品名'] || p.name || '未知商品'
                const revenue = p.revenue || 0
                const qty = p.quantity || 0
                const pct = totalRev > 0 ? (revenue / totalRev * 100).toFixed(1) : 0

                return (
                  <tr key={i} className="border-b border-slate-50 hover:bg-slate-50/50 transition-colors">
                    <td className="px-5 py-3">
                      <span className={`inline-flex items-center justify-center w-6 h-6 rounded-full text-xs font-bold ${
                        i === 0 ? 'bg-yellow-100 text-yellow-700' :
                        i === 1 ? 'bg-slate-100 text-slate-600' :
                        i === 2 ? 'bg-orange-100 text-orange-600' :
                        'text-slate-400'
                      }`}>
                        {i + 1}
                      </span>
                    </td>
                    <td className="px-5 py-3 font-medium text-slate-800 max-w-xs truncate" title={name}>
                      {name}
                    </td>
                    <td className="px-5 py-3">
                      {p.category ? (
                        <span className="px-2 py-0.5 bg-blue-50 text-blue-600 rounded-full text-xs font-medium">
                          {p.category}
                        </span>
                      ) : '-'}
                    </td>
                    <td className="px-5 py-3 text-right text-slate-600">{qty}</td>
                    <td className="px-5 py-3 text-right font-medium text-slate-800">
                      NT$ {Number(revenue).toLocaleString()}
                    </td>
                    <td className="px-5 py-3 w-36">
                      <div className="flex items-center gap-2">
                        <div className="flex-1 h-1.5 bg-slate-100 rounded-full overflow-hidden">
                          <div
                            className="h-full bg-blue-400 rounded-full"
                            style={{ width: `${Math.min(pct * 5, 100)}%` }}
                          />
                        </div>
                        <span className="text-xs text-slate-400 w-10 text-right">{pct}%</span>
                      </div>
                    </td>
                  </tr>
                )
              })
            })()}
            {sorted.length === 0 && (
              <tr>
                <td colSpan={6} className="px-5 py-10 text-center text-slate-400">
                  無符合條件的商品
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}
