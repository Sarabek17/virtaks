/* ==========================================================================
   Virtaks — umumiy UI kutubxonasi (client, kabinet, admin uchun bitta).
   Global obyekt: window.UI
   Bog'liqlik yo'q (framework, CDN — hech narsa). CSP: script-src 'self'.
   ========================================================================== */
(function () {
  "use strict";

  const UI = {};

  /* ------------------------------------------------------------ asoslar */
  const $  = UI.$  = (s, t) => (t || document).querySelector(s);
  const $$ = UI.$$ = (s, t) => Array.from((t || document).querySelectorAll(s));

  /** HTML dan qochirish. innerHTML ga tushadigan HAR QANDAY tashqi matn
   *  shundan o'tishi shart (manba nomlari, foydalanuvchi ismi, model matni). */
  const esc = UI.esc = (s) => String(s == null ? "" : s)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;").replace(/'/g, "&#39;");

  /** Element yasash: h("div.karta", {onclick}, "matn", h("b", "qalin")) */
  UI.h = function (tavsif, ...bolalar) {
    const m = String(tavsif).match(/^([a-z0-9]+)?([.#][^\s]*)?$/i) || [];
    const el = document.createElement(m[1] || "div");
    (m[2] || "").split(/(?=[.#])/).forEach((q) => {
      if (q.startsWith(".")) el.classList.add(q.slice(1));
      else if (q.startsWith("#")) el.id = q.slice(1);
    });
    if (bolalar[0] && typeof bolalar[0] === "object" &&
        !(bolalar[0] instanceof Node)) {
      const p = bolalar.shift();
      for (const k in p) {
        if (k.startsWith("on") && typeof p[k] === "function") {
          el.addEventListener(k.slice(2), p[k]);
        } else if (k === "html") { el.innerHTML = p[k]; }
        else if (p[k] != null && p[k] !== false) { el.setAttribute(k, p[k]); }
      }
    }
    bolalar.flat().forEach((b) => {
      if (b == null || b === false) return;
      el.appendChild(b instanceof Node ? b : document.createTextNode(String(b)));
    });
    return el;
  };

  UI.saqla = (k, v) => { try { localStorage.setItem(k, JSON.stringify(v)); } catch (e) {} };
  UI.ol = (k, z) => {
    try { const v = localStorage.getItem(k); return v === null ? z : JSON.parse(v); }
    catch (e) { return z; }
  };

  /* ------------------------------------------------------------ mavzu */
  const MAVZU_KALIT = "twin-mavzu";
  UI.mavzu = {
    ol: () => UI.ol(MAVZU_KALIT, "tizim"),
    qoy(m) {
      UI.saqla(MAVZU_KALIT, m);
      if (m === "tizim") document.documentElement.removeAttribute("data-mavzu");
      else document.documentElement.setAttribute("data-mavzu", m);
      document.dispatchEvent(new CustomEvent("mavzu-almashdi", { detail: m }));
    },
    almash() {
      const hozir = document.documentElement.getAttribute("data-mavzu") ||
        (matchMedia("(prefers-color-scheme: dark)").matches ? "tun" : "kun");
      UI.mavzu.qoy(hozir === "tun" ? "kun" : "tun");
    },
    tundami: () => (document.documentElement.getAttribute("data-mavzu") ||
      (matchMedia("(prefers-color-scheme: dark)").matches ? "tun" : "kun")) === "tun",
  };
  UI.mavzu.qoy(UI.ol(MAVZU_KALIT, "tizim"));

  /* ------------------------------------------------------------ tarmoq */
  class ApiXato extends Error {
    constructor(xabar, kod, tan) { super(xabar); this.kod = kod; this.tan = tan; }
  }
  UI.ApiXato = ApiXato;

  async function sorov(usul, yol, tan) {
    let j = null, r;
    try {
      r = await fetch(yol, {
        method: usul,
        headers: tan === undefined ? {} : { "Content-Type": "application/json" },
        body: tan === undefined ? undefined : JSON.stringify(tan),
      });
    } catch (e) {
      throw new ApiXato("Tarmoq bilan aloqa yo'q — ulanishni tekshiring", 0, null);
    }
    const tur = r.headers.get("content-type") || "";
    if (tur.includes("application/json")) { try { j = await r.json(); } catch (e) {} }
    if (!r.ok) {
      const xabar = (j && (j.xato || j.xabar)) ||
        (r.status === 401 ? "Kirish kerak" :
         r.status === 403 ? "Ruxsat yo'q" :
         r.status === 404 ? "Topilmadi" :
         r.status === 429 ? "Juda ko'p urinish — biroz kuting" :
         "Xatolik (" + r.status + ")");
      throw new ApiXato(xabar, r.status, j);
    }
    return j;
  }
  UI.api = {
    ol:      (y)    => sorov("GET", y),
    yubor:   (y, t) => sorov("POST", y, t || {}),
    yangila: (y, t) => sorov("PUT", y, t || {}),
    ochir:   (y)    => sorov("DELETE", y),
  };

  /* ------------------------------------------------------------ toast */
  function toastQuti() {
    let q = $(".toast-quti");
    if (!q) {
      q = UI.h("div.toast-quti", { role: "status", "aria-live": "polite" });
      document.body.appendChild(q);
    }
    return q;
  }
  UI.toast = function (matn, tur, muddat) {
    const t = UI.h("div.toast" + (tur ? "." + tur + "-t" : ""), String(matn));
    toastQuti().appendChild(t);
    setTimeout(() => {
      t.style.transition = "opacity .2s, transform .2s";
      t.style.opacity = "0"; t.style.transform = "translateY(8px)";
      setTimeout(() => t.remove(), 220);
    }, muddat || (tur === "xato" ? 4200 : 2600));
    return t;
  };
  UI.xatoToast = (e) => UI.toast(e && e.message ? e.message : String(e), "xato");

  /* ------------------------------------------------------------ modal */
  const FOKUSLI = 'a[href],button:not([disabled]),input:not([disabled]),' +
                  'select:not([disabled]),textarea:not([disabled]),[tabindex]:not([tabindex="-1"])';
  let modalStek = [];

  /**
   * UI.modal({sarlavha, tan(Node|html), amallar:[{nom,uslub,onclick,yopmasin}],
   *           keng, yopilganda})
   * Qaytaradi: {yop(), el, parda}
   */
  UI.modal = function (o) {
    const oldingiFokus = document.activeElement;
    const tan = UI.h("div.modal-tan");
    if (o.tan instanceof Node) tan.appendChild(o.tan);
    else tan.innerHTML = o.tan || "";

    const yopish = UI.h("button.tug-ikon", {
      type: "button", "aria-label": "Yopish", onclick: () => yop(),
    }, "✕");

    const modal = UI.h("div.modal" + (o.keng ? ".keng-m" : ""), {
      role: "dialog", "aria-modal": "true", "aria-label": o.sarlavha || "Oyna",
    },
      UI.h("div.modal-bosh", UI.h("h3", o.sarlavha || ""), yopish),
      tan);

    if (o.amallar && o.amallar.length) {
      const oyoq = UI.h("div.modal-oyoq");
      o.amallar.forEach((a) => {
        oyoq.appendChild(UI.h("button.tug" + (a.uslub ? "." + a.uslub : ""), {
          type: "button",
          onclick: async (e) => {
            if (a.onclick) { const n = await a.onclick(e, { yop }); if (n === false) return; }
            if (!a.yopmasin) yop();
          },
        }, a.nom));
      });
      modal.appendChild(oyoq);
    }

    const parda = UI.h("div.parda", {
      onclick: (e) => { if (e.target === parda && !o.qatiy) yop(); },
    }, modal);
    document.body.appendChild(parda);
    document.body.style.overflow = "hidden";

    function tugma(e) {
      if (e.key === "Escape" && modalStek[modalStek.length - 1] === boshqaruv) {
        e.stopPropagation(); yop();
      } else if (e.key === "Tab") {
        const el = $$(FOKUSLI, modal).filter((x) => x.offsetParent !== null);
        if (!el.length) return;
        const bir = el[0], oxir = el[el.length - 1];
        if (e.shiftKey && document.activeElement === bir) { e.preventDefault(); oxir.focus(); }
        else if (!e.shiftKey && document.activeElement === oxir) { e.preventDefault(); bir.focus(); }
      }
    }
    parda.addEventListener("keydown", tugma);

    function yop() {
      const i = modalStek.indexOf(boshqaruv);
      if (i >= 0) modalStek.splice(i, 1);
      parda.remove();
      if (!modalStek.length) document.body.style.overflow = "";
      if (oldingiFokus && oldingiFokus.focus) oldingiFokus.focus();
      if (o.yopilganda) o.yopilganda();
    }

    const boshqaruv = { yop, el: modal, tan, parda };
    modalStek.push(boshqaruv);
    const birinchi = $$(FOKUSLI, tan).filter((x) => x.offsetParent !== null)[0];
    (birinchi || yopish).focus();
    return boshqaruv;
  };

  /** Xavfli amal tasdig'i. `yozish` berilsa — foydalanuvchi shu matnni
   *  yozmaguncha tugma ochilmaydi (twin/bilim o'chirish kabi qaytmas ishlar). */
  UI.tasdiq = function (o) {
    return new Promise((javob) => {
      const tan = UI.h("div");
      tan.appendChild(UI.h("div", { style: "line-height:1.6" }, o.matn || ""));
      let kirit = null;
      if (o.yozish) {
        tan.appendChild(UI.h("div.izoh", { style: "margin:14px 0 6px" },
          "Tasdiqlash uchun quyidagi matnni yozing: "));
        tan.appendChild(UI.h("div", { style: "margin-bottom:8px;font-weight:600" }, o.yozish));
        kirit = UI.h("input", { type: "text", autocomplete: "off",
          "aria-label": "Tasdiqlash matni" });
        tan.appendChild(kirit);
      }
      let hal = false;
      const m = UI.modal({
        sarlavha: o.sarlavha || "Tasdiqlang",
        tan,
        qatiy: true,
        amallar: [
          { nom: o.bekor || "Bekor qilish", uslub: "shaffof",
            onclick: () => { hal = true; javob(false); } },
          { nom: o.tasdiq || "Ha, davom etish", uslub: o.xavfli ? "xavf" : "asosiy",
            onclick: () => {
              if (kirit && kirit.value.trim() !== o.yozish) {
                UI.toast("Matn mos kelmadi", "xato"); return false;
              }
              hal = true; javob(true);
            } },
        ],
        yopilganda: () => { if (!hal) javob(false); },
      });
      if (kirit) kirit.focus();
      return m;
    });
  };

  /* ------------------------------------------------------------ holatlar */
  UI.holat = {
    yuklanmoqda(el, matn) {
      el.innerHTML = "";
      el.appendChild(UI.h("div.holat-quti",
        UI.h("div.aylanma"),
        UI.h("div.tan", matn || "Yuklanmoqda...")));
    },
    bosh(el, o) {
      el.innerHTML = "";
      const q = UI.h("div.holat-quti",
        UI.h("div.ikon", (o && o.ikon) || "📭"),
        UI.h("div.sarlavha", (o && o.sarlavha) || "Hozircha bo'sh"),
        (o && o.tan) ? UI.h("div.tan", o.tan) : null);
      if (o && o.amal) {
        q.appendChild(UI.h("button.tug.asosiy", { type: "button", onclick: o.amal.onclick },
          o.amal.nom));
      }
      el.appendChild(q);
    },
    xato(el, xato, qayta) {
      el.innerHTML = "";
      const q = UI.h("div.holat-quti.xato-h",
        UI.h("div.ikon", "⚠️"),
        UI.h("div.sarlavha", "Ochilmadi"),
        UI.h("div.tan", (xato && xato.message) || String(xato || "Noma'lum xatolik")));
      if (qayta) {
        q.appendChild(UI.h("button.tug", { type: "button", onclick: qayta }, "↻ Qayta urinish"));
      }
      el.appendChild(q);
    },
    /** Yuklash + xato + bo'sh holatni bitta joyda boshqaradi. */
    async yur(el, olish, chizish, o) {
      o = o || {};
      UI.holat.yuklanmoqda(el, o.yuklanmoqda);
      try {
        const d = await olish();
        if (o.boshmi ? o.boshmi(d) : (Array.isArray(d) && !d.length)) {
          UI.holat.bosh(el, o.bosh); return d;
        }
        el.innerHTML = "";
        chizish(d, el);
        return d;
      } catch (e) {
        UI.holat.xato(el, e, () => UI.holat.yur(el, olish, chizish, o));
        return null;
      }
    },
  };

  /* ------------------------------------------------------------ jadval */
  /**
   * UI.jadval(el, {
   *   ustunlar: [{nom, kalit?, chiz?(q)->Node|string, saralanadi?, sinf?}],
   *   qatorlar: [...], qidiruv?: (q, matn)->bool, sahifa?: 25,
   *   bosh?: {..}, kalit?: (q)->id
   * })
   * Qidiruv + saralash + sahifalash — "50 tadan N ko'rsatilyapti" bilan.
   */
  UI.jadval = function (el, o) {
    const sahifaHajm = o.sahifa || 25;
    let saralash = { ustun: null, teskari: false };
    let qidiruv = "";
    let sahifa = 0;

    function filtr() {
      let r = o.qatorlar.slice();
      if (qidiruv.trim()) {
        const q = qidiruv.trim().toLowerCase();
        r = r.filter((x) => o.qidiruv ? o.qidiruv(x, q)
          : JSON.stringify(x).toLowerCase().includes(q));
      }
      if (saralash.ustun != null) {
        const u = o.ustunlar[saralash.ustun];
        const olish = u.qiymat || ((x) => (u.kalit ? x[u.kalit] : ""));
        r.sort((a, b) => {
          const x = olish(a), y = olish(b);
          if (x == null) return 1;
          if (y == null) return -1;
          const n = (typeof x === "number" && typeof y === "number")
            ? x - y : String(x).localeCompare(String(y), "uz");
          return saralash.teskari ? -n : n;
        });
      }
      return r;
    }

    function chiz() {
      const hammasi = filtr();
      const sahifalar = Math.max(1, Math.ceil(hammasi.length / sahifaHajm));
      if (sahifa >= sahifalar) sahifa = sahifalar - 1;
      const korinadi = hammasi.slice(sahifa * sahifaHajm, (sahifa + 1) * sahifaHajm);

      el.innerHTML = "";
      if (o.qidiruvJoy !== false) {
        const qk = UI.h("input", {
          type: "search", placeholder: o.qidiruvMatn || "Qidirish...",
          value: qidiruv, style: "max-width:280px",
          "aria-label": "Jadvalda qidirish",
        });
        let kutish;
        qk.addEventListener("input", () => {
          clearTimeout(kutish);
          kutish = setTimeout(() => { qidiruv = qk.value; sahifa = 0; chiz();
            const y = $("input[type=search]", el); if (y) { y.focus();
              y.setSelectionRange(y.value.length, y.value.length); } }, 220);
        });
        el.appendChild(UI.h("div.qator", { style: "margin-bottom:12px" }, qk,
          o.ustki || null));
      }

      if (!hammasi.length) {
        const q = UI.h("div.karta");
        UI.holat.bosh(q, qidiruv ? {
          ikon: "🔍", sarlavha: "Hech narsa topilmadi",
          tan: "«" + qidiruv + "» bo'yicha natija yo'q.",
        } : (o.bosh || {}));
        el.appendChild(q);
        return;
      }

      const thead = UI.h("thead");
      const tr = UI.h("tr");
      o.ustunlar.forEach((u, i) => {
        const th = UI.h("th" + (u.saralanadi ? ".saralanadi" : ""),
          { scope: "col" }, u.nom);
        if (u.saralanadi) {
          th.setAttribute("aria-sort", saralash.ustun === i
            ? (saralash.teskari ? "descending" : "ascending") : "none");
          th.tabIndex = 0;
          const bos = () => {
            if (saralash.ustun === i) saralash.teskari = !saralash.teskari;
            else saralash = { ustun: i, teskari: false };
            chiz();
          };
          th.addEventListener("click", bos);
          th.addEventListener("keydown", (e) => {
            if (e.key === "Enter" || e.key === " ") { e.preventDefault(); bos(); }
          });
        }
        tr.appendChild(th);
      });
      thead.appendChild(tr);

      const tbody = UI.h("tbody");
      korinadi.forEach((q) => {
        const satr = UI.h("tr");
        o.ustunlar.forEach((u) => {
          const td = UI.h("td" + (u.sinf ? "." + u.sinf : ""));
          const v = u.chiz ? u.chiz(q) : (u.kalit ? q[u.kalit] : "");
          if (v instanceof Node) td.appendChild(v);
          else if (u.html) td.innerHTML = v == null ? "" : v;
          else td.textContent = v == null ? "" : String(v);
          satr.appendChild(td);
        });
        tbody.appendChild(satr);
      });

      const quti = UI.h("div.jadval-quti",
        UI.h("table.jadval", thead, tbody));

      const bosh = sahifa * sahifaHajm + 1;
      const oxir = Math.min(hammasi.length, (sahifa + 1) * sahifaHajm);
      const oyoq = UI.h("div.jadval-oyoq",
        UI.h("span", hammasi.length + " tadan " + bosh + "–" + oxir + " ko'rsatilyapti" +
          (o.jamiIzoh ? " · " + o.jamiIzoh : "")));
      if (sahifalar > 1) {
        oyoq.appendChild(UI.h("div.osdi",
          UI.h("button.tug.kichik-t", {
            type: "button", disabled: sahifa === 0 ? "" : null,
            onclick: () => { sahifa--; chiz(); },
          }, "← Oldingi"),
          UI.h("span", (sahifa + 1) + " / " + sahifalar),
          UI.h("button.tug.kichik-t", {
            type: "button", disabled: sahifa >= sahifalar - 1 ? "" : null,
            onclick: () => { sahifa++; chiz(); },
          }, "Keyingi →")));
      }
      quti.appendChild(oyoq);
      el.appendChild(quti);
    }

    chiz();
    return { chiz, yangi: (q) => { o.qatorlar = q; chiz(); } };
  };

  /* ------------------------------------------------------------ tablar */
  UI.tablar = function (el, tablar, ozgardi) {
    const quti = UI.h("div.tablar", { role: "tablist" });
    const tugmalar = [];
    tablar.forEach((t, i) => {
      const b = UI.h("button", {
        type: "button", role: "tab", id: "tab-" + t.kod,
        "aria-selected": i === 0 ? "true" : "false",
        "aria-controls": "panel-" + t.kod, tabindex: i === 0 ? "0" : "-1",
        onclick: () => tanla(i),
        onkeydown: (e) => {
          const y = e.key === "ArrowRight" ? 1 : e.key === "ArrowLeft" ? -1 : 0;
          if (y) { e.preventDefault(); tanla((i + y + tablar.length) % tablar.length); }
        },
      }, t.nom);
      tugmalar.push(b); quti.appendChild(b);
    });
    function tanla(i) {
      tugmalar.forEach((b, j) => {
        b.setAttribute("aria-selected", i === j ? "true" : "false");
        b.tabIndex = i === j ? 0 : -1;
      });
      tugmalar[i].focus();
      if (ozgardi) ozgardi(tablar[i], i);
    }
    el.appendChild(quti);
    return { tanla, tugmalar };
  };

  /* ------------------------------------------------------------ router */
  /** Oddiy hash-router: #/bolim/arg — sahifa yangilanganda joyida qoladi. */
  UI.router = function (yollar, standart) {
    function yur() {
      const h = (location.hash || "").replace(/^#\/?/, "");
      const qism = h.split("/").filter(Boolean);
      const nom = qism[0] || standart;
      const fn = yollar[nom] || yollar[standart];
      if (fn) fn(qism.slice(1), nom);
    }
    window.addEventListener("hashchange", yur);
    return { yur, otish: (y) => { location.hash = "#/" + y; } };
  };

  /* ------------------------------------------------------------ format */
  UI.vaqt = function (s, toliq) {
    if (!s) return "";
    const d = new Date(s);
    if (isNaN(d)) return "";
    const farq = (Date.now() - d.getTime()) / 1000;
    if (!toliq) {
      if (farq < 60) return "hozir";
      if (farq < 3600) return Math.floor(farq / 60) + " daq oldin";
      if (farq < 86400) return Math.floor(farq / 3600) + " soat oldin";
      if (farq < 172800) return "kecha";
      if (farq < 604800) return Math.floor(farq / 86400) + " kun oldin";
    }
    return d.toLocaleString("uz-UZ", {
      year: "numeric", month: "2-digit", day: "2-digit",
      hour: "2-digit", minute: "2-digit",
    });
  };
  /** Suhbat ro'yxatini Claude kabi guruhlash uchun. */
  UI.davr = function (s) {
    const d = new Date(s);
    const bugun = new Date(); bugun.setHours(0, 0, 0, 0);
    const kun = (bugun - new Date(d.getFullYear(), d.getMonth(), d.getDate())) / 86400000;
    if (kun <= 0) return "Bugun";
    if (kun === 1) return "Kecha";
    if (kun < 7) return "Shu hafta";
    if (kun < 30) return "Shu oy";
    return "Avvalroq";
  };
  UI.hajm = (b) => {
    if (!b) return "—";
    const bir = ["B", "KB", "MB", "GB"];
    let i = 0; let x = b;
    while (x >= 1024 && i < 3) { x /= 1024; i++; }
    return x.toFixed(x < 10 && i > 0 ? 1 : 0) + " " + bir[i];
  };
  UI.davomiylik = (s) => {
    if (s == null) return "";
    const soat = Math.floor(s / 3600), daq = Math.floor((s % 3600) / 60);
    if (soat) return soat + " soat " + daq + " daq";
    if (daq) return daq + " daq " + (s % 60) + " s";
    return s + " s";
  };
  UI.pul = (n) => "$" + Number(n || 0).toFixed(Number(n) < 1 ? 4 : 2);
  UI.som = (n) => Number(n || 0).toLocaleString("uz-UZ") + " so'm";

  /* ------------------------------------------------------------ nusxa */
  UI.nusxa = async function (matn) {
    try {
      await navigator.clipboard.writeText(matn);
      UI.toast("Nusxalandi", "ok", 1400); return true;
    } catch (e) {
      const t = UI.h("textarea", { style: "position:fixed;opacity:0" });
      t.value = matn; document.body.appendChild(t); t.select();
      try { document.execCommand("copy"); UI.toast("Nusxalandi", "ok", 1400); }
      catch (e2) { UI.toast("Nusxalab bo'lmadi", "xato"); }
      t.remove(); return true;
    }
  };

  /* ------------------------------------------------------------ mobil yon panel */
  UI.yonPanel = function (yon, tugma) {
    let parda = null;
    function yop() {
      yon.classList.remove("ochiq");
      if (parda) { parda.remove(); parda = null; }
      if (tugma) tugma.setAttribute("aria-expanded", "false");
    }
    function och() {
      yon.classList.add("ochiq");
      parda = UI.h("div.yon-parda", { onclick: yop });
      document.body.appendChild(parda);
      if (tugma) tugma.setAttribute("aria-expanded", "true");
    }
    if (tugma) {
      tugma.setAttribute("aria-expanded", "false");
      tugma.addEventListener("click", () => yon.classList.contains("ochiq") ? yop() : och());
    }
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && yon.classList.contains("ochiq")) yop();
    });
    return { och, yop };
  };

  window.UI = UI;
})();
