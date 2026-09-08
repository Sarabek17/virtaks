#!/usr/bin/env bash
# =============================================================================
#  Deploy / yangilash. Dropletda, /opt/virtaks/joylash ichida ishlatiladi.
#
#      bash yangilash.sh              # kodni qayta yig'ib, servislarni almashtirish
#      bash yangilash.sh --tort       # avval `git pull`
#      bash yangilash.sh --toza       # keshsiz build (birinchi marta yoki paket o'zgarsa)
#
#  Skript deploy oldidan MUHITNI TEKSHIRADI: yarim to'ldirilgan `.env` bilan
#  konteynerlar ko'tarilib, keyin jimgina yiqilishidan ko'ra shu yerda
#  to'xtagani yaxshi.
# =============================================================================
set -euo pipefail
cd "$(dirname "$(readlink -f "$0")")"

XATO() { echo -e "\n\033[31m[XATO]\033[0m $*\n" >&2; exit 1; }
OGOH() { echo -e "\033[33m[OGOH]\033[0m $*"; }
QADAM() { echo -e "\n\033[1m==> $*\033[0m"; }

TORT=0; TOZA=0
for a in "$@"; do
  case "$a" in
    --tort) TORT=1 ;;
    --toza) TOZA=1 ;;
    *) XATO "noma'lum argument: $a" ;;
  esac
done

# ------------------------------------------------------------ 1. muhit ko'rigi
QADAM "1/6 Muhit ko'rigi"
[[ -f .env ]] || XATO ".env yo'q. Yarating: cp env.namuna .env && nano .env"

# shellcheck disable=SC1091
set -a; . ./.env; set +a

for nom in DOMEN PUBLIC_URL ACME_EMAIL PG_BAZA PG_USER PG_PAROL \
           S3_KIRISH S3_MAXFIY S3_BAKET GEMINI_API_KEY TELEGRAM_BOT_TOKEN; do
  [[ -n "${!nom:-}" ]] || XATO ".env dagi $nom bo'sh"
done

# PUBLIC_URL va DOMEN mos kelmasa: sayt ochiladi, lekin Telegram webhook
# boshqa manzilga o'rnatiladi va bot JIM QOLADI. Buni deploydan keyin
# topish qiyin, shuning uchun shu yerda to'xtatamiz.
[[ "$PUBLIC_URL" == "https://$DOMEN" ]] \
  || XATO "PUBLIC_URL ($PUBLIC_URL) va DOMEN ($DOMEN) mos emas — kutilgan: https://$DOMEN"

[[ ${#S3_MAXFIY} -ge 8 ]] || XATO "S3_MAXFIY kamida 8 belgi bo'lishi kerak (MinIO talabi)"

# Xavfsizlik bayroqlari jonli muhitda ochiq qolmasin.
for nom in DEV_KIRISH ZAXIRA_KIRISH KENGASH_BOT_OFF; do
  [[ -z "${!nom:-}" ]] || OGOH "$nom=${!nom} — jonli tizimda BO'SH bo'lishi kerak"
done

# Domen shu dropletga qarab turibdimi (Caddy sertifikatni shunga qarab oladi).
MEN=$(curl -fsS --max-time 5 https://api.ipify.org 2>/dev/null || echo "")
DNS=$(getent hosts "$DOMEN" | awk '{print $1}' | head -1 || echo "")
if [[ -n "$MEN" && -n "$DNS" && "$MEN" != "$DNS" ]]; then
  OGOH "$DOMEN -> $DNS, bu droplet esa $MEN. TLS sertifikati olinmasligi mumkin."
elif [[ -z "$DNS" ]]; then
  OGOH "$DOMEN hali DNS da ko'rinmayapti."
fi
echo "    muhit joyida"

# --------------------------------------------------------------- 2. kod
OLDINGI=$(git -C .. rev-parse --short HEAD 2>/dev/null || echo "")
if [[ $TORT -eq 1 ]]; then
  QADAM "2/6 git pull"
  git -C .. pull --ff-only
else
  QADAM "2/6 kod (git pull otkazib yuborildi, --tort bilan torting)"
fi
JORIY=$(git -C .. rev-parse --short HEAD 2>/dev/null || echo "?")
echo "    joriy commit: $JORIY"
if [[ -n "$OLDINGI" && "$OLDINGI" != "$JORIY" ]]; then
  # Rollback uchun eslatib qo'yamiz: deploydan keyin muammo chiqsa qidirib
  # o'tirilmasin.
  echo "    oldingi commit: $OLDINGI   (qaytish: git -C .. checkout $OLDINGI && bash yangilash.sh)"
  echo "$OLDINGI" > .oldingi_commit
fi

# --------------------------------------------------------------- 3. build
QADAM "3/6 Imijlarni yig'ish"
if [[ $TOZA -eq 1 ]]; then
  docker compose build --no-cache --pull
else
  docker compose build --pull
fi

# --------------------------------------------------------------- 4. baza
# Web ham, worker ham ishga tushganda migratsiya qiladi (pg.py da konsultativ
# qulf bor, poyga bo'lmaydi). Baza konteynerini oldindan ko'taramiz — birinchi
# ishga tushishda initdb bir necha o'n soniya oladi.
QADAM "4/6 Baza va ombor"
docker compose up -d db minio
for i in $(seq 1 30); do
  holat=$(docker inspect -f '{{.State.Health.Status}}' virtaks-db 2>/dev/null || echo "yo'q")
  [[ "$holat" == "healthy" ]] && break
  sleep 3
done
[[ "${holat:-}" == "healthy" ]] || XATO "db sog'lomlashmadi: docker compose logs db"
echo "    db + minio tayyor"

# --------------------------------------------------------------- 5. ilova
QADAM "5/6 Servislarni almashtirish"
docker compose up -d --remove-orphans

# --------------------------------------------------------------- 6. tekshiruv
QADAM "6/6 Salomatlik"
for i in $(seq 1 40); do
  holat=$(docker inspect -f '{{.State.Health.Status}}' virtaks-web 2>/dev/null || echo "yo'q")
  [[ "$holat" == "healthy" ]] && break
  sleep 3
done
if [[ "${holat:-}" != "healthy" ]]; then
  echo "--- web loglari (oxirgi 40 qator) ---"
  docker compose logs --tail 40 web || true
  XATO "web sog'lomlashmadi"
fi

docker compose ps
echo
curl -fsS "https://$DOMEN/salomatlik" && echo || \
  OGOH "https://$DOMEN/salomatlik javob bermadi — Caddy sertifikat olayotgan bo'lishi mumkin (1-2 daqiqa kuting), keyin: docker compose logs caddy"

# Eski imijlar diskni yeydi (har build ~1.8 GB qatlam qoldiradi).
docker image prune -f >/dev/null
echo -e "\n\033[32mDEPLOY TAYYOR:\033[0m https://$DOMEN"
