#!/usr/bin/env bash
# =============================================================================
#  Tizim ko'rigi: "hozir hamma narsa joyidami?" degan savolga bir ekranda javob.
#
#      bash holat.sh
#
#  Hech narsani o'zgartirmaydi, faqat o'qiydi. Sirlar chop etilmaydi.
# =============================================================================
set -uo pipefail
cd "$(dirname "$(readlink -f "$0")")"

BOLIM() { echo -e "\n\033[1m--- $* ---------------------------------------\033[0m"; }

# Natija bo'sh bo'lsa o'rniga tushunarli matn qo'yadi.
#
# DIQQAT: buni `${qiymat:-(yo'q)}` bilan yozib bo'lmaydi — bash `:-` dan
# keyingi so'zda apostrofni TIRNOQ deb o'qiydi va "bad substitution" beradi.
# O'zbekcha matnda apostrof ko'p, shuning uchun naqsh ataylab funksiyaga
# ko'chirilgan.
YOKI() { local q="$1"; shift; [[ -n "$q" ]] && echo "$q" || echo "$*"; }

[[ -f .env ]] && { set -a; . ./.env; set +a; }

SQL() {
  docker compose exec -T db psql -U "${PG_USER:-virtaks}" -d "${PG_BAZA:-virtaks}" \
    -t -A -F"$1" -c "$2" 2>/dev/null
}

BOLIM "Servislar"
docker compose ps --format "table {{.Name}}\t{{.Service}}\t{{.Status}}"

BOLIM "Resurslar"
# `free` Ubuntu da bor; boshqa hostda (masalan Git Bash) bo'lmasligi mumkin.
if command -v free >/dev/null; then free -h | sed -n '1,2p'; else echo "  (free yo'q)"; fi
df -h / | sed -n '1,2p'
echo "docker: $(docker system df --format '{{.Type}}={{.Size}}' 2>/dev/null | tr '\n' ' ')"

BOLIM "Salomatlik"
if [[ -n "${DOMEN:-}" ]]; then
  echo -n "  https://$DOMEN/salomatlik -> "
  curl -fsS --max-time 10 "https://$DOMEN/salomatlik" || echo "JAVOB YO'Q"
  echo
  # Sertifikat muddati — Caddy o'zi yangilaydi, lekin 30 kundan kam qolsa
  # yangilanish ishlamayotgan bo'lishi mumkin.
  muddat=$(echo | openssl s_client -connect "$DOMEN:443" -servername "$DOMEN" 2>/dev/null \
           | openssl x509 -noout -enddate 2>/dev/null | cut -d= -f2)
  echo "  TLS sertifikati: $(YOKI "$muddat" aniqlanmadi)"
fi

BOLIM "Navbat (jobs)"
navbat=$(SQL " " "SELECT holat, count(*) FROM jobs GROUP BY holat ORDER BY 1;")
YOKI "$navbat" "(navbat bo'sh yoki bazaga ulanib bo'lmadi)" | sed "s/^/  /"

echo "  oxirgi yiqilgan joblar:"
yiqilgan=$(SQL " | " "SELECT id, tur, left(coalesce(xato,''), 70) FROM jobs
                      WHERE holat='xato' ORDER BY id DESC LIMIT 5;")
YOKI "$yiqilgan" "(yo'q)" | sed "s/^/    /"

BOLIM "Zaxira nusxalari"
zax=$(docker run --rm --network virtaks_ichki --entrypoint sh minio/mc -c \
  "mc alias set n http://minio:9000 '${S3_KIRISH:-}' '${S3_MAXFIY:-}' >/dev/null 2>&1 && \
   mc ls n/'${S3_BAKET:-kengash}'/zaxira/ 2>/dev/null | tail -5" 2>/dev/null)
YOKI "$zax" "(zaxira nusxa yo'q — birinchisi haftalik job bilan yasaladi)" | sed "s/^/  /"

BOLIM "Oxirgi xatolar (web)"
web_x=$(docker compose logs --tail 400 web 2>/dev/null | grep -iE "error|xato|traceback" | tail -8)
YOKI "$web_x" "(xato yo'q)" | sed "s/^/  /"

BOLIM "Oxirgi xatolar (ishchi)"
ish_x=$(docker compose logs --tail 400 ishchi 2>/dev/null | grep -iE "error|xato|traceback" | tail -8)
YOKI "$ish_x" "(xato yo'q)" | sed "s/^/  /"

echo
