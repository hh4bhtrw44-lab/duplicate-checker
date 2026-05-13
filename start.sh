#!/bin/bash
# =========================================
# 客户查重管理系统 - 生产环境启动脚本
# =========================================

APP_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_NAME="duplicate-checker"
PID_FILE="/tmp/${APP_NAME}.pid"
LOG_DIR="${APP_DIR}/logs"
ACCESS_LOG="${LOG_DIR}/access.log"
ERROR_LOG="${LOG_DIR}/error.log"
GUNICORN_BIN="python3 -m gunicorn"
BIND="0.0.0.0:5000"
WORKERS=4
TIMEOUT=120

# 颜色
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

# 创建日志目录
mkdir -p "$LOG_DIR"

case "${1:-start}" in
    start)
        if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
            echo -e "${YELLOW}⚠️  服务已在运行 (PID: $(cat $PID_FILE))${NC}"
            exit 1
        fi
        echo -e "${GREEN}🚀 启动客户查重管理系统...${NC}"
        cd "$APP_DIR"
        # 确保数据库目录可写
        touch data.db 2>/dev/null
        $GUNICORN_BIN \
            --bind "$BIND" \
            --workers "$WORKERS" \
            --timeout "$TIMEOUT" \
            --pid "$PID_FILE" \
            --access-logfile "$ACCESS_LOG" \
            --error-logfile "$ERROR_LOG" \
            --access-logformat '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s"' \
            --daemon \
            wsgi:app
        sleep 2
        if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
            echo -e "${GREEN}✅ 服务启动成功!${NC}"
            echo -e "${GREEN}   PID: $(cat $PID_FILE)${NC}"
            echo -e "${GREEN}   🌐 http://localhost:5000${NC}"
            echo -e "${GREEN}   📝 日志: $LOG_DIR/${NC}"
        else
            echo -e "${RED}❌ 服务启动失败，查看日志:${NC}"
            tail -20 "$ERROR_LOG"
            exit 1
        fi
        ;;

    stop)
        if [ ! -f "$PID_FILE" ]; then
            echo -e "${YELLOW}⚠️  服务未运行${NC}"
            exit 0
        fi
        PID=$(cat "$PID_FILE")
        echo -e "${YELLOW}🛑 停止服务 (PID: $PID)...${NC}"
        kill "$PID" 2>/dev/null
        sleep 2
        if kill -0 "$PID" 2>/dev/null; then
            kill -9 "$PID" 2>/dev/null
        fi
        rm -f "$PID_FILE"
        echo -e "${GREEN}✅ 服务已停止${NC}"
        ;;

    restart)
        $0 stop
        sleep 1
        $0 start
        ;;

    status)
        if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
            PID=$(cat "$PID_FILE")
            echo -e "${GREEN}✅ 服务运行中 (PID: $PID)${NC}"
            echo -e "   🌐 http://localhost:5000"
            ps -p "$PID" -o pid,etime,%cpu,%mem,args --no-headers 2>/dev/null
        else
            echo -e "${YELLOW}⚠️  服务未运行${NC}"
        fi
        ;;

    logs)
        echo "=== 访问日志 (最后30行) ==="
        tail -30 "$ACCESS_LOG" 2>/dev/null || echo "(无日志)"
        echo ""
        echo "=== 错误日志 (最后30行) ==="
        tail -30 "$ERROR_LOG" 2>/dev/null || echo "(无日志)"
        ;;

    *)
        echo "用法: $0 {start|stop|restart|status|logs}"
        echo ""
        echo "  start   - 启动服务 (Gunicorn 生产模式)"
        echo "  stop    - 停止服务"
        echo "  restart - 重启服务"
        echo "  status  - 查看服务状态"
        echo "  logs    - 查看最近日志"
        exit 1
        ;;
esac
