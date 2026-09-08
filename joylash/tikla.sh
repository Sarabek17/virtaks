#!/usr/bin/env bash
# =============================================================================
#  Zaxira `.dump` faylidan bazani tiklaydi.
#
#      bash tikla.sh --dump /root/zaxira/20260908_222548.dump
#      bash tikla.sh --dump <fayl> --ombor <papka>   # + MinIO nusxasi
#
#  DIQQAT: bu skript BIRINCHI o'rnatish uchun EMAS. Eski server
#  (169.58.79.192) butunlay o'chgan va undan zaxira qolmagan — yangi
#  dropletni to'ldirish `joylash/urugla.ps1` bilan qilinadi (DEPLOY_DO.md §6).
#
#  Bu yerda esa KELAJAKDAGI avariya uchun: haftalik `zaxira` job'i
#  MinIO ga `zaxira/*.dump` yozib turadi, shundan tiklanadi.
#
#  Zaxirani MinIO dan olish:
#    docker run --rm --network virtaks_ichki -v /root/zaxira:/z \
#      --entrypoint sh minio/mc -c \
#      "mc alias set n http://minio:9000 <kirish> <maxfiy> && \
#       mc cp n/kengash/zaxira/<fayl>.dump /z/"
#
#  Yoki to'g'ridan-to'g'ri yangi dump olish:
#    docker compose exec -T db pg_dump -U virtaks -d virtaks -Fc --no-owner \
#      > /root/zaxira/$(date +%F).dump
#
#  MAVJUD bazani ustiga yozadi (--clean).
# =============================================================================
set -euo pipefail
cd "$(dirname "$(readlink -f "$0")")"

XATO() { echo -e "\n\033[31m[XATO]\033[0m $*\n" >&2; exit 1; }
QADAM() { echo -e "\n\033[1m==> $*\033[0m"; }

DUMP=""; OMBOR=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --dump)  DUMP="${2:-}"; shift 2 ;;
    --ombor) OMBOR="${2:-}"; shift 2 ;;
    *) XATO "noma'lum argument: $1" ;;
  esac
done

[[ -f .env ]] || XATO ".env yo'q"
# shellcheck disable=SC1091
set -a; . ./.env; set +a
[[ -n "$DUMP" && -f "$DUMP" ]] || XATO "--dump fayli topilmadi: ${DUMP:-<berilmagan>}"

echo "Baza    : $PG_BAZA (foydalanuvchi $PG_USER)"
echo "Dump    : $DUMP ($(du -h "$DUMP" | cut -f1))"
echo "Ombor   : ${OMBOR:-(berilmagan, otkazib yuboriladi)}"
echo
echo "MAVJUD BAZA USTIGA YOZILADI."
read -r -p "Davom etilsinmi? (ha / yoq) " javob
[[ "$javob" == "ha" ]] || XATO "bekor qilindi"

# ------------------------------------------------- 1. yozuvchilarni to'xtatish
QADAM "1/4 web va ishchi to'xtatiladi (tiklash paytida yozuv bo'lmasin)"
docker compose stop web ishchi || true
docker compose up -d db minio
for i in $(seq 1 30); do
  [[ "$(docker inspect -f '{{.State.Health.Status}}' virtaks-db 2>/dev/null)" == "healthy" ]] && break
  sleep 3
done

# ------------------------------------------------------------ 2. pg_restore
QADAM "2/4 Baza tiklanmoqda"
# --clean --if-exists: eski obyektlar tushiriladi. `vector` kengaytmasi
# dumpda bor, lekin bo'lmasa ham migratsiya keyin yaratadi.
# Chiqish kodi 0 bo'lmasligi mumkin (mavjud bo'lmagan obyektni DROP qilish
# ogohlantirish beradi) — shuning uchun xatolar sanab ko'riladi.
set +e
docker compose exec -T db pg_restore -U "$PG_USER" -d "$PG_BAZA" \
    --clean --if-exists --no-owner --no-privileges \
    < "$DUMP" 2> /tmp/tikla_xato.log
kod=$?
set -e
jiddiy=$(grep -c "^pg_restore: error" /tmp/tikla_xato.log || true)
echo "    pg_restore kodi=$kod, jiddiy xato=$jiddiy"
if [[ "$jiddiy" -gt 0 ]]; then
  tail -20 /tmp/tikla_xato.log
  XATO "tiklashda jiddiy xatolar bor — yuqoriga qarang (/tmp/tikla_xato.log)"
fi

QADAM "   tekshiruv: jadvallardagi yozuvlar"
docker compose exec -T db psql -U "$PG_USER" -d "$PG_BAZA" -t -c \
  "SELECT 'userlar=' || (SELECT count(*) FROM userlar)
        || ' twinlar=' || (SELECT count(*) FROM twinlar)
        || ' bolaklar=' || (SELECT count(*) FROM bolaklar)
        || ' suhbatlar=' || (SELECT count(*) FROM suhbatlar);" | sed 's/^/    /'

# ---------------------------------------------------------------- 3. ombor
if [[ -n "$OMBOR" ]]; then
  QADAM "3/4 Fayl ombori ko'chirilmoqda"
  [[ -d "$OMBOR" ]] || XATO "--ombor papkasi topilmadi: $OMBOR"
  docker run --rm --network virtaks_ichki -v "$(readlink -f "$OMBOR")":/manba:ro \
    --entrypoint sh minio/mc -c \
    "mc alias set nishon http://minio:9000 '$S3_KIRISH' '$S3_MAXFIY' >/dev/null && \
     mc mb --ignore-existing nishon/'$S3_BAKET' >/dev/null && \
     mc mirror --overwrite /manba nishon/'$S3_BAKET'"
else
  QADAM "3/4 Ombor o'tkazib yuborildi (--ombor berilmagan)"
fi

# --------------------------------------------------------------- 4. qaytarish
QADAM "4/4 Servislar qaytarilmoqda"
docker compose up -d
echo -e "\n\033[32mTIKLASH TUGADI.\033[0m Endi ko'rik: bash holat.sh"
