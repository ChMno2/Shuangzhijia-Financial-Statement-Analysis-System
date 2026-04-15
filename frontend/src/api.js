import axios from 'axios'

const BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000'

const api = axios.create({ baseURL: BASE, timeout: 30000 })

// 自動在每個請求帶入 Token
api.interceptors.request.use(config => {
  const token = localStorage.getItem('token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

// Token 過期或無效時自動登出
api.interceptors.response.use(
  res => res,
  err => {
    if (err.response?.status === 401) {
      localStorage.removeItem('token')
      localStorage.removeItem('username')
      window.location.reload()
    }
    return Promise.reject(err)
  }
)

export const getDashboard = () => api.get('/api/dashboard').then(r => r.data)
export const getProducts = () => api.get('/api/products').then(r => r.data)
export const getDailySales = ({ days = 30, startDate = null, endDate = null, topProducts = false } = {}) => {
  const params = new URLSearchParams({ days, top_products: topProducts })
  if (startDate) params.set('start_date', startDate)
  if (endDate) params.set('end_date', endDate)
  return api.get(`/api/sales/daily?${params}`).then(r => r.data)
}
export const getProfit = ({ days = 30, startDate = null, endDate = null } = {}) => {
  const params = new URLSearchParams({ days })
  if (startDate) params.set('start_date', startDate)
  if (endDate) params.set('end_date', endDate)
  return api.get(`/api/profit?${params}`).then(r => r.data)
}
export const getCategorySales = () => api.get('/api/sales/category').then(r => r.data)
export const getSummary = () => api.get('/api/summary').then(r => r.data)
export const sendChat = (question, history = []) =>
  api.post('/api/chat', { question, history }, { timeout: 120000 }).then(r => r.data)
export const getChatHistory = () => api.get('/api/chat/history').then(r => r.data)
export const clearChatHistory = () => api.delete('/api/chat/history').then(r => r.data)
export const getWeeklyReport = () => api.get('/api/report/weekly').then(r => r.data)
export const generateReport = () => api.post('/api/report/generate', {}, { timeout: 120000 }).then(r => r.data)
export const listReports = () => api.get('/api/reports').then(r => r.data)
export const getReport = (id) => api.get(`/api/reports/${id}`).then(r => r.data)
export const deleteReport = (id) => api.delete(`/api/reports/${id}`).then(r => r.data)
export const uploadExcel = (file) => {
  const form = new FormData()
  form.append('file', file)
  return api.post('/api/upload', form).then(r => r.data)
}
export const refreshData = () => api.post('/api/refresh').then(r => r.data)
