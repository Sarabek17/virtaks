// Swagger UI ni ishga tushiradi. ALOHIDA fayl, chunki /api/v1/docs sahifasining
// CSP'si `script-src 'self'` — inline skript ishlamaydi (bu ataylab shunday:
// asosiy ilovadan qat'iyroq, chunki bu sahifada 'unsafe-inline' kerak emas).
//
// `SwaggerUIStandalonePreset` YUKLANMAYDI (u alohida fayl): u faqat yuqoridagi
// URL panelini va topbar'ni qo'shadi, bizga esa sxema qotirilgan — hamkor
// boshqa manzilni kiritmaydi.
window.addEventListener("load", function () {
  SwaggerUIBundle({
    url: "/api/v1/openapi.json",
    dom_id: "#swagger",
    presets: [SwaggerUIBundle.presets.apis],
    layout: "BaseLayout",
    deepLinking: true,
    tryItOutEnabled: true,
    docExpansion: "list",
    defaultModelsExpandDepth: 0,
    // Kalit brauzer omborida QOLDIRILMAYDI: umumiy kompyuterda ochilsa,
    // keyingi odam hamkorning hisobidan so'rov yuborardi.
    persistAuthorization: false,
    syntaxHighlight: { activate: true, theme: "nord" }
  });
});
