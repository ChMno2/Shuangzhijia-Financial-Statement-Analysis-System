import { useState } from 'react'
import Login from './pages/Login'
import Sidebar from './components/Sidebar'
import Dashboard from './pages/Dashboard'
import Products from './pages/Products'
import Sales from './pages/Sales'
import Categories from './pages/Categories'
import Profit from './pages/Profit'
import Chat from './pages/Chat'
import Report from './pages/Report'
import { uploadExcel, refreshData } from './api'

const pages = {
  dashboard: Dashboard,
  products: Products,
  sales: Sales,
  categories: Categories,
  profit: Profit,
  chat: Chat,
  report: Report,
}

function App() {
  const [user, setUser] = useState(() => localStorage.getItem('username'))
  const [page, setPage] = useState('dashboard')
  const [toast, setToast] = useState(null)

  // 未登入 → 顯示登入頁
  if (!user) {
    return <Login onLogin={setUser} />
  }

  const showToast = (msg, type = 'success') => {
    setToast({ msg, type })
    setTimeout(() => setToast(null), 3500)
  }

  const handleLogout = () => {
    localStorage.removeItem('token')
    localStorage.removeItem('username')
    setUser(null)
  }

  const handleUpload = async (e) => {
    const file = e.target.files?.[0]
    if (!file) return
    try {
      const res = await uploadExcel(file)
      showToast(res.message)
    } catch {
      showToast('上傳失敗，請確認檔案格式', 'error')
    }
    e.target.value = ''
  }

  const handleRefresh = async () => {
    try {
      await refreshData()
      showToast('資料已更新')
      window.location.reload()
    } catch {
      showToast('更新失敗', 'error')
    }
  }

  const PageComponent = pages[page]

  return (
    <div className="flex min-h-screen bg-slate-50">
      <Sidebar
        active={page}
        onNavigate={setPage}
        onUpload={handleUpload}
        onRefresh={handleRefresh}
        user={user}
        onLogout={handleLogout}
      />
      <main className="flex-1 ml-60 p-6 min-h-screen">
        <PageComponent />
      </main>
      {toast && (
        <div className={`fixed bottom-6 right-6 px-5 py-3 rounded-xl text-white text-sm font-medium shadow-lg z-50 ${
          toast.type === 'error' ? 'bg-red-500' : 'bg-green-500'
        }`}>
          {toast.msg}
        </div>
      )}
    </div>
  )
}

export default App
