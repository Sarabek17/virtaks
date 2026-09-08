#!/usr/bin/env bash
# =============================================================================
#  Yangi DigitalOcean dropletini noldan tayyorlaydi (bir marta ishlatiladi).
#
#  Talab: Ubuntu 24.04 LTS, kamida 4 GB RAM / 2 vCPU / 80 GB SSD.
#  root bo'lib ishga tushiring:
#
#      bash joylash/boshlash.sh
#
#  Skript qayta ishga tushirilsa ham xavfsiz (idempotent).
# =============================================================================
set -euo pipefail

XATO() { echo -e "\n[XATO] $*\n" >&2; exit 1; }
QADAM() { echo -e "\n\033[1m==> $*\033[0m"; }

[[ $EUID -eq 0 ]] || XATO "root kerak: sudo bash joylash/boshlash.sh"

# ----------------------------------------------------------------- 1. tizim
QADAM "1/6 Tizim paketlari"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get upgrade -y -qq
apt-get install -y -qq ca-certificates curl git ufw fail2ban \
                      unattended-upgrades postgresql-client-common

# ------------------------------------------------------------------ 2. swap
# 4 GB dropletda LibreOffice + ffmpeg + Postgres bir vaqtda ishlaganda
# xotira tugab, yadro eng katta jarayonni (odatda Postgres'ni) o'ldiradi.
# Swap tezlik bermaydi, lekin OOM dan saqlaydi.
QADAM "2/6 Swap fayli"
if swapon --show | grep -q .; then
  echo "    swap allaqachon bor — o'tkazib yuborildi"
else
  fallocate -l 4G /swapfile
  chmod 600 /swapfile
  mkswap /swapfile >/dev/null
  swapon /swapfile
  grep -q '^/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
  sysctl -w vm.swappiness=10 >/dev/null
  grep -q '^vm.swappiness' /etc/sysctl.conf || echo 'vm.swappiness=10' >> /etc/sysctl.conf
  echo "    4 GB swap yoqildi"
fi

# ---------------------------------------------------------------- 3. docker
QADAM "3/6 Docker"
if command -v docker >/dev/null 2>&1; then
  echo "    docker allaqachon o'rnatilgan: $(docker --version)"
else
  curl -fsSL https://get.docker.com | sh
fi
docker compose version >/dev/null 2>&1 || XATO "docker compose plagini yo'q"
systemctl enable --now docker

# Konteyner loglari diskni to'ldirmasin (compose'dagi sozlama faqat
# bizning servislarga tegishli — bu esa umumiy standart).
mkdir -p /etc/docker
if [[ ! -f /etc/docker/daemon.json ]]; then
  cat > /etc/docker/daemon.json <<'JSON'
{
  "log-driver": "json-file",
  "log-opts": { "max-size": "10m", "max-file": "5" }
}
JSON
  systemctl restart docker
  echo "    /etc/docker/daemon.json yozildi (log rotatsiyasi)"
fi

# --------------------------------------------------------------- 4. fayrvol
QADAM "4/6 Fayrvol (ufw)"
ufw allow OpenSSH >/dev/null
ufw allow 80/tcp  >/dev/null
ufw allow 443/tcp >/dev/null
ufw allow 443/udp >/dev/null            # HTTP/3
ufw --force enable >/dev/null
ufw status numbered | sed 's/^/    /'

# DIQQAT: Docker o'z qoidalarini ufw'dan CHETLAB O'TADI (iptables DOCKER
# zanjiri). Shuning uchun docker-compose.yml da db va minio portlari
# ataylab 127.0.0.1 ga bog'langan — aks holda ufw yopiq bo'lsa ham
# internetdan ochiq bo'lardi.

# ------------------------------------------------------ 5. avto-yangilanish
QADAM "5/6 Xavfsizlik yangilanishlari"
dpkg-reconfigure -f noninteractive unattended-upgrades >/dev/null 2>&1 || true
systemctl enable --now fail2ban >/dev/null 2>&1 || true

# ------------------------------------------------------------- 6. papkalar
QADAM "6/6 Loyiha papkasi"
mkdir -p /opt/virtaks
echo "    /opt/virtaks tayyor"

cat <<'KEYIN'

============================================================
  DROPLET TAYYOR. Keyingi qadamlar:

  1) Kodni oling:
       git clone https://github.com/Sarabek17/virtaks.git /opt/virtaks
       # yoki mavjud papkada:  cd /opt/virtaks && git pull

  2) Muhitni to'ldiring:
       cd /opt/virtaks/joylash
       cp env.namuna .env && nano .env

  3) Domen A-yozuvini shu dropletning IP siga qarating,
     tarqalganini tekshiring:
       dig +short <domen>

  4) Ishga tushiring:
       bash yangilash.sh --toza

  To'liq qo'llanma: DEPLOY_DO.md
============================================================
KEYIN
