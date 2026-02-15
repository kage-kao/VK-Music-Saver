#!/bin/bash
set -e

echo "========================================="
echo "  VK Music Saver - Быстрое развёртывание"
echo "========================================="

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

check_command() {
    if ! command -v "$1" &> /dev/null; then
        echo -e "${RED}[ОШИБКА] $1 не найден. Установите $1 и повторите.${NC}"
        exit 1
    fi
}

echo -e "${BLUE}[0/6] Проверка зависимостей...${NC}"
check_command python3
check_command pip
check_command node
check_command yarn

if ! command -v mongod &> /dev/null && ! pgrep -x mongod > /dev/null; then
    echo -e "${YELLOW}[ВНИМАНИЕ] MongoDB не обнаружена. Убедитесь что MongoDB запущена.${NC}"
fi

# 1. Установка Xray для VLESS прокси
echo -e "${BLUE}[1/6] Установка Xray для VLESS прокси...${NC}"
if ! command -v xray &> /dev/null && [ ! -f /usr/local/bin/xray ]; then
    ARCH=$(uname -m)
    if [ "$ARCH" = "x86_64" ]; then
        XRAY_ARCH="64"
    elif [ "$ARCH" = "aarch64" ]; then
        XRAY_ARCH="arm64-v8a"
    else
        echo -e "${YELLOW}[ВНИМАНИЕ] Неизвестная архитектура $ARCH, пробую x86_64${NC}"
        XRAY_ARCH="64"
    fi
    
    XRAY_VERSION="v25.6.8"
    XRAY_URL="https://github.com/XTLS/Xray-core/releases/download/${XRAY_VERSION}/Xray-linux-${XRAY_ARCH}.zip"
    
    echo "Скачиваю Xray ${XRAY_VERSION}..."
    TMP_DIR=$(mktemp -d)
    curl -sL "$XRAY_URL" -o "$TMP_DIR/xray.zip"
    
    if command -v unzip &> /dev/null; then
        unzip -q "$TMP_DIR/xray.zip" -d "$TMP_DIR/xray"
    else
        python3 -c "
import zipfile
with zipfile.ZipFile('$TMP_DIR/xray.zip', 'r') as z:
    z.extractall('$TMP_DIR/xray')
"
    fi
    
    chmod +x "$TMP_DIR/xray/xray"
    sudo cp "$TMP_DIR/xray/xray" /usr/local/bin/xray 2>/dev/null || cp "$TMP_DIR/xray/xray" /usr/local/bin/xray
    rm -rf "$TMP_DIR"
    
    echo -e "${GREEN}Xray установлен: $(xray version 2>/dev/null | head -1 || echo 'версия неизвестна')${NC}"
else
    echo -e "${GREEN}Xray уже установлен${NC}"
fi

# 2. Зависимости бэкенда
echo -e "${BLUE}[2/6] Установка зависимостей бэкенда...${NC}"
cd backend
pip install -q -r requirements.txt 2>&1 | tail -2
cd ..

# 3. Настройка окружения
echo -e "${BLUE}[3/6] Настройка окружения...${NC}"
if [ ! -f backend/.env ]; then
    cat > backend/.env << 'ENVEOF'
MONGO_URL="mongodb://localhost:27017"
DB_NAME="vk_music_saver"
CORS_ORIGINS="*"
ENVEOF
    echo "Создан backend/.env"
else
    echo "backend/.env уже существует"
fi

if [ ! -f frontend/.env ]; then
    cat > frontend/.env << 'ENVEOF'
REACT_APP_BACKEND_URL=http://localhost:8001
WDS_SOCKET_PORT=3000
ENVEOF
    echo "Создан frontend/.env"
else
    echo "frontend/.env уже существует"
fi

# 4. Зависимости фронтенда
echo -e "${BLUE}[4/6] Установка зависимостей фронтенда...${NC}"
cd frontend
yarn install 2>&1 | tail -2
cd ..

# 5. Создание директорий
echo -e "${BLUE}[5/6] Создание рабочих директорий...${NC}"
mkdir -p /tmp/vk_downloads
mkdir -p /tmp/xray_configs

# 6. Запуск сервисов
echo -e "${BLUE}[6/6] Запуск сервисов...${NC}"

cd backend
uvicorn server:app --host 0.0.0.0 --port 8001 --reload &
BACKEND_PID=$!
cd ..
echo -e "${GREEN}Бэкенд запущен (PID: $BACKEND_PID) на порту 8001${NC}"

sleep 2

cd frontend
PORT=3000 yarn start &
FRONTEND_PID=$!
cd ..
echo -e "${GREEN}Фронтенд запущен (PID: $FRONTEND_PID) на порту 3000${NC}"

echo ""
echo -e "${GREEN}=========================================${NC}"
echo -e "${GREEN}  VK Music Saver запущен!${NC}"
echo -e "${GREEN}=========================================${NC}"
echo ""
echo -e "  Бэкенд:   ${BLUE}http://localhost:8001${NC}"
echo -e "  Фронтенд: ${BLUE}http://localhost:3000${NC}"
echo -e "  API Docs:  ${BLUE}http://localhost:8001/docs${NC}"
echo ""
echo -e "${YELLOW}Возможности:${NC}"
echo "  - Скачивание плейлистов, треков и всей библиотеки VK"
echo "  - Массовое скачивание нескольких плейлистов"
echo "  - Поддержка HTTP/SOCKS5/VLESS прокси"
echo "  - Реальная проверка прокси (включая VLESS через Xray)"
echo "  - ID3 теги и тексты песен"
echo "  - Автоматическая загрузка на TempShare"
echo "  - Полностью русский интерфейс"
echo ""
echo "Нажмите Ctrl+C для остановки"

trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; echo 'Остановлено'; exit" INT TERM
wait
