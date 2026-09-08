<#
================================================================================
  Yangi (bo'sh) dropletni lokal materiallardan to'ldirish — "urug'lantirish".

  Eski server (169.58.79.192) butunlay yo'q va bazadan zaxira nusxa qolmagan.
  Lekin bilim bazasining MANBASI shu kompyuterda saqlanib qolgan, shuning uchun
  hammasi qaytadan quriladi. Vektorlar ham lokal Qdrant'da bor — ya'ni 2897
  bo'lakni qayta embedding qilishga PUL KETMAYDI.

  Skript SHU KOMPYUTERDA ishlaydi (ma'lumot shu yerda), dropletga SSH tunnel
  ochib, uning Postgres va MinIO siga to'g'ridan-to'g'ri yozadi.

  ISHLATISH (PowerShell, loyiha ildizidan):

      .\joylash\urugla.ps1 -IP <droplet-ip> -Asos          # 1-bosqich, bepul
      .\joylash\urugla.ps1 -IP <droplet-ip> -Media         # 2-bosqich, sekin
      .\joylash\urugla.ps1 -IP <droplet-ip> -Pdf           # 3-bosqich, ~$7
      .\joylash\urugla.ps1 -IP <droplet-ip> -Asos -Quruq   # hech narsa yozmaydi

  Bosqichlar MUSTAQIL va qayta ishga tushirish XAVFSIZ (idempotent):
  allaqachon ko'chirilgan yozuv/fayl ikkinchi marta qo'shilmaydi.

    -Asos   twinlar, 7 direktor, 2897 bo'lak + vektor, 13 shablon,
            eski suhbat/majlis tarixi.        LLM puli: 0
    -Media  asl audio/PDF fayllar -> MinIO (audio fragment ishlashi uchun).
            Sekin uplinkda soatlab ketishi mumkin.
    -Pdf    E:\Zakazlar\Muslim aka dagi 36 PDF (3595 sahifa) -> ingest
            navbatiga. OCR taxminan $7, worker'da bir necha soat bajariladi.

  926 ta CJM/EJM savoli ALOHIDA yuklanmaydi — u `012_savollar.sql`
  migratsiyasi ichida, konteyner ko'tarilganda o'zi tushadi.
================================================================================
#>
param(
  [Parameter(Mandatory = $true)][string]$IP,
  [string]$SshUser = "root",
  [string]$Yol = "/opt/virtaks/joylash/.env",
  [switch]$Asos,
  [switch]$Media,
  [switch]$Pdf,
  [switch]$Quruq,
  [int]$PgPort = 55432,
  [int]$S3Port = 59000,
  [string]$PdfPapka = "E:\Zakazlar\Muslim aka",
  [int]$PdfTwin = 2
)

$ErrorActionPreference = "Stop"

function Qadam($m) { Write-Host "`n==> $m" -ForegroundColor Cyan }
function Ogoh($m)  { Write-Host "[OGOH] $m" -ForegroundColor Yellow }
function Xato($m)  { Write-Host "[XATO] $m" -ForegroundColor Red; exit 1 }

if (-not ($Asos -or $Media -or $Pdf)) {
  Xato "Bosqich tanlanmagan. -Asos, -Media yoki -Pdf bering (izohga qarang)."
}

$Ildiz = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Ildiz
$Py = Join-Path $Ildiz ".venv\Scripts\python.exe"
if (-not (Test-Path $Py)) { Xato ".venv topilmadi: $Py" }
if (-not (Get-Command ssh -ErrorAction SilentlyContinue)) { Xato "ssh topilmadi (Windows OpenSSH kerak)" }

# --------------------------------------------------------- 1. droplet muhiti
Qadam "1/4 Droplet muhitini o'qish ($SshUser@$IP)"
# Sirlarni bu kompyuterga NUSXALAMAYMIZ — har safar dropletdan o'qiymiz va
# faqat shu jarayonning muhitida ushlab turamiz.
$xom = ssh -o BatchMode=no -o StrictHostKeyChecking=accept-new "$SshUser@$IP" "cat $Yol"
if ($LASTEXITCODE -ne 0) { Xato "dropletdan $Yol o'qilmadi" }

$muhit = @{}
foreach ($q in ($xom -split "`n")) {
  $q = $q.Trim()
  if ($q -and -not $q.StartsWith("#") -and $q.Contains("=")) {
    $k, $v = $q -split "=", 2
    $muhit[$k.Trim()] = $v.Trim()
  }
}
foreach ($n in @("PG_BAZA", "PG_USER", "PG_PAROL", "S3_KIRISH", "S3_MAXFIY", "S3_BAKET")) {
  if (-not $muhit[$n]) { Xato "dropletning .env faylida $n bo'sh" }
}
Write-Host "    baza=$($muhit['PG_BAZA'])  baket=$($muhit['S3_BAKET'])"

# ------------------------------------------------------------- 2. SSH tunnel
Qadam "2/4 SSH tunnel ($PgPort -> 5432, $S3Port -> 9000)"
# db va minio dropletda faqat 127.0.0.1 da tinglaydi (ataylab) — shuning uchun
# ularga yagona yo'l SSH tunneli.
$sshArg = @("-N",   # nomi ataylab $args EMAS: u PowerShell'ning avtomatik o'zgaruvchisi

          "-o", "ExitOnForwardFailure=yes",
          "-o", "ServerAliveInterval=30",
          "-L", "${PgPort}:127.0.0.1:5432",
          "-L", "${S3Port}:127.0.0.1:9000",
          "$SshUser@$IP")
$tunnel = Start-Process ssh -ArgumentList $sshArg -PassThru -WindowStyle Hidden

try {
  $ochiq = $false
  foreach ($i in 1..20) {
    Start-Sleep -Milliseconds 700
    try {
      $k = New-Object System.Net.Sockets.TcpClient
      $k.Connect("127.0.0.1", $PgPort); $k.Close(); $ochiq = $true; break
    } catch { }
  }
  if (-not $ochiq) { Xato "tunnel ochilmadi (SSH kaliti/paroli to'g'rimi?)" }
  Write-Host "    tunnel tayyor (PID $($tunnel.Id))"

  # -------------------------------------------------------- 3. muhit o'zgaruvchilari
  # PROD ATAYLAB QO'YILMAYDI: sozlama.py PROD bo'lmaganda S3_ENDPOINT_TASHQI ni
  # oladi — aynan bizga kerak bo'lgan tunnel manzili. PROD=1 qo'yilsa u
  # konteyner nomini (http://minio:9000) izlab, bu kompyuterdan topolmasdi.
  $env:PG_URL            = "postgresql://$($muhit['PG_USER']):$($muhit['PG_PAROL'])@127.0.0.1:$PgPort/$($muhit['PG_BAZA'])"
  $env:S3_ENDPOINT_TASHQI = "http://127.0.0.1:$S3Port"
  $env:S3_KIRISH         = $muhit['S3_KIRISH']
  $env:S3_MAXFIY         = $muhit['S3_MAXFIY']
  $env:S3_BAKET          = $muhit['S3_BAKET']
  $env:PROD              = ""
  $env:KENGASH_BOT_OFF   = "1"     # hech qanday webhook o'rnatilmasin

  & $Py -c "from platforma import pg; print('    PG ulanish: OK,', pg.bitta('SELECT count(*) FROM migratsiyalar')[0], 'migratsiya')"
  if ($LASTEXITCODE -ne 0) { Xato "bazaga ulanib bo'lmadi" }

  if ($Quruq) {
    Qadam "4/4 -Quruq: ulanish tekshirildi, hech narsa yozilmadi"
    return
  }

  # -------------------------------------------------------------- 4. bosqichlar
  if ($Asos) {
    Qadam "4/4 ASOS — twin, direktor, 2897 bo'lak + vektor, tarix, shablonlar"
    & $Py -m platforma.migratsiya_eski
    if ($LASTEXITCODE -ne 0) { Xato "migratsiya_eski yiqildi" }
    & $Py -m platforma.migratsiya_shablon --papka (Join-Path $Ildiz "kengash\shablonlar")
    if ($LASTEXITCODE -ne 0) { Ogoh "shablonlar ko'chmadi (yuqoridagi xatoga qarang)" }

    # Raqamlarni migratsiyaning o'zi chiqaradi (migratsiya_eski.hisob) —
    # PowerShell ichida Python matni yozishdan qochamiz.
  }

  if ($Media) {
    Qadam "4/4 MEDIA — asl audio/PDF fayllar MinIO ga"
    Ogoh "Bu bosqich sekin: yuklanadigan hajm gigabaytlarda, uplink tor."
    # Fayllar bir necha joyda yotadi; migratsiya_asl nom bo'yicha topib,
    # allaqachon yuklanganini o'tkazib yuboradi.
    $papkalar = @(
      (Join-Path $env:USERPROFILE "OneDrive"),
      (Join-Path $env:USERPROFILE "Desktop"),
      (Join-Path $Ildiz "transkript")
    ) | Where-Object { Test-Path $_ }
    $arg = @("-m", "platforma.migratsiya_asl", "--render")
    foreach ($p in $papkalar) { $arg += @("--papka", $p) }
    Write-Host "    qidiriladigan papkalar: $($papkalar -join '; ')"
    & $Py $arg
    if ($LASTEXITCODE -ne 0) { Ogoh "migratsiya_asl xato bilan tugadi" }
  }

  if ($Pdf) {
    Qadam "4/4 PDF — $PdfPapka -> twin #$PdfTwin ingest navbati"
    if (-not (Test-Path $PdfPapka)) { Xato "papka topilmadi: $PdfPapka" }
    Ogoh "36 PDF / 3595 sahifa OCR ~= `$7. Skript ro'yxatni ko'rsatib tasdiq so'raydi."
    & $Py -m platforma.manba_yukla --twin $PdfTwin --papka $PdfPapka --render
    if ($LASTEXITCODE -ne 0) { Ogoh "manba_yukla xato bilan tugadi" }
    Write-Host "`n    Ingest worker'da davom etadi. Kuzatish:"
    Write-Host "      ssh $SshUser@$IP 'cd /opt/virtaks/joylash && bash holat.sh'"
  }

  Write-Host "`nURUG'LANTIRISH TUGADI" -ForegroundColor Green
}
finally {
  if ($tunnel -and -not $tunnel.HasExited) {
    Stop-Process -Id $tunnel.Id -Force -ErrorAction SilentlyContinue
    Write-Host "    tunnel yopildi"
  }
}
