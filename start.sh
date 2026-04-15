#!/bin/bash
# 商業後台分析系統 — 一鍵啟動腳本

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$PROJECT_DIR/backend"
FRONTEND_DIR="$PROJECT_DIR/frontend"

echo "======================================"
echo "  商業後台分析系統 啟動中..."
echo "======================================"

# 停止舊服務
echo ""
echo "[0/2] 停止舊服務..."
pkill -f "uvicorn main:app" 2>/dev/null && echo "  ✓ 已停止舊後端" || echo "  （無舊後端運行）"
pkill -f "vite" 2>/dev/null && echo "  ✓ 已停止舊前端" || echo "  （無舊前端運行）"
sleep 1

# 啟動後端
echo ""
echo "[1/2] 啟動後端 (FastAPI)..."
cd "$BACKEND_DIR"

# 建立 .env（如果不存在）
if [ ! -f ".env" ]; then
  cp .env.example .env
  echo "  ✓ 已建立 .env，請填入 ANTHROPIC_API_KEY"
fi

# 安裝依賴（如果需要）
if ! python3 -c "import fastapi" 2>/dev/null; then
  echo "  安裝 Python 依賴..."
  pip3 install -r requirements.txt -q
fi

# 後台啟動後端
python3 -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload &
BACKEND_PID=$!
echo "  ✓ 後端啟動中 (PID: $BACKEND_PID) → http://localhost:8000"

# 啟動前端
echo ""
echo "[2/2] 啟動前端 (React)..."
cd "$FRONTEND_DIR"

if [ ! -d "node_modules" ]; then
  echo "  安裝 npm 依賴..."
  npm install -q
fi

npm run dev &
FRONTEND_PID=$!
echo "  ✓ 前端啟動中 (PID: $FRONTEND_PID) → http://localhost:5173"

echo ""
echo "======================================"
echo "  系統啟動完成！"
echo "  後台網址：http://localhost:5173"
echo "  API 文件：http://localhost:8000/docs"
echo "======================================"
echo ""
echo "  按下 Ctrl+C 停止所有服務"
echo ""

# 等待並清理
trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; echo '已停止服務'" EXIT
wait
