# syntax=docker/dockerfile:1.7
# =============================================================================
#  Virtaks platformasi — ikki nishonli (target) imij
#
#    asos    → umumiy: python + kutubxonalar + platforma kodi
#    web     → asos + curl salomatlik tekshiruvi        (~640 MB)
#    ishchi  → asos + ffmpeg, LibreOffice, pg_dump-18   (~1.8 GB)
#
#  Nega ikkita: web'da ffmpeg ham, LibreOffice ham CHAQIRILMAYDI (og'ir ish
#  faqat worker'da — CLAUDE.md qoidasi). Bitta og'ir imijni ikkalasiga berish
#  har deployda 1.1 GB ni bekorga ko'chirish demakdi.
#
#  Build konteksti — REPO ILDIZI (docker-compose.yml da `context: ..`).
# =============================================================================

# ----------------------------------------------------------------- asos
# bookworm ATAYLAB qotirilgan: PGDG ombori kodli nom bo'yicha ishlaydi va
# `slim` tegi bir kun trixie'ga ko'chsa, postgresql-client-18 topilmay qoladi.
FROM python:3.11-slim-bookworm AS asos

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    TZ=Asia/Tashkent \
    HOME=/home/virtaks

RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates curl tzdata \
 && rm -rf /var/lib/apt/lists/* \
 && useradd --uid 10001 --create-home --home-dir /home/virtaks --shell /usr/sbin/nologin virtaks

WORKDIR /app

# Bog'liqliklar kod o'zgarishidan ALOHIDA qatlamda — kod tahriri pip'ni
# qayta ishga tushirmaydi (deploy 6 daqiqadan 40 soniyaga tushadi).
COPY joylash/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY platforma ./platforma

# Muhit o'zgaruvchilari konteynerga compose orqali beriladi; `.env` fayli
# imijga HECH QACHON tushmaydi (.dockerignore ni ham qarang).

# ----------------------------------------------------------------- web
FROM asos AS web
USER virtaks
EXPOSE 8900
# start-period: birinchi ishga tushishda migratsiyalar qo'llanadi va TG
# webhook o'rnatiladi — bu 20-30 soniya olishi mumkin.
HEALTHCHECK --interval=30s --timeout=5s --start-period=90s --retries=3 \
  CMD curl -fsS http://127.0.0.1:8900/salomatlik >/dev/null || exit 1
CMD ["python", "-m", "platforma.web"]

# ----------------------------------------------------------------- ishchi
FROM asos AS ishchi

# ffmpeg              — audio bo'laklash va fragment kesish
# libreoffice-impress — PPTX -> PDF (slaydni rasm qilib berish uchun)
# fonts-dejavu-core   — konvertatsiyada matn to'g'ri chiqsin
# postgresql-client-18 — pg_dump (haftalik zaxira job'i)
#
# DIQQAT: Debian'ning o'z `postgresql-client` paketi 17-versiyani beradi,
# bizning baza esa PG 18 — pg_dump katta versiya farqida ishlashdan BOSH
# TORTADI ("aborting because of server version mismatch"). Shuning uchun
# rasmiy PGDG omboridan aynan 18-mijoz o'rnatiladi.
USER root
RUN apt-get update \
 && apt-get install -y --no-install-recommends gnupg \
 && . /etc/os-release \
 && install -d /usr/share/postgresql-common/pgdg \
 && curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc \
      -o /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc \
 && echo "deb [signed-by=/usr/share/postgresql-common/pgdg/apt.postgresql.org.asc]" \
      "https://apt.postgresql.org/pub/repos/apt ${VERSION_CODENAME}-pgdg main" \
      > /etc/apt/sources.list.d/pgdg.list \
 && apt-get update \
 && apt-get install -y --no-install-recommends \
      ffmpeg libreoffice-impress fonts-dejavu-core postgresql-client-18 \
 && apt-get purge -y gnupg && apt-get autoremove -y \
 && rm -rf /var/lib/apt/lists/*

# LibreOffice ishga tushganda $HOME ichida profil yaratadi. Root'siz
# konteynerda HOME yozuvchan bo'lmasa `soffice` jimgina yiqiladi va
# PPTX manba "PPTX->PDF bo'lmadi" xatosi bilan qaytadi.
RUN mkdir -p /home/virtaks/.config && chown -R virtaks:virtaks /home/virtaks

USER virtaks
# Worker'da HTTP port yo'q. Uni jimgina to'xtatib qo'yadigan yagona
# narsa - bazaga ulanolmaslik (job olinmaydi, jarayon esa tirik
# ko'rinadi), shuning uchun tiriklik belgisi aynan shu: PG javob
# beryaptimi.
HEALTHCHECK --interval=60s --timeout=15s --start-period=90s --retries=3 \
  CMD python -c "from platforma import pg; pg.bitta('SELECT 1')" || exit 1
CMD ["python", "-m", "platforma.worker"]
