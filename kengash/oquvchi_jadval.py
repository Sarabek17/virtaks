# -*- coding: utf-8 -*-
"""XLSX -> Markdown jadvallar (har varaq alohida)."""
from pathlib import Path

from .sozlama import log


def _katak(v) -> str:
    if v is None:
        return ""
    if isinstance(v, float) and v == int(v):
        return str(int(v))
    return str(v).replace("\n", " ").strip()


def oqi(fayl: Path) -> dict:
    """XLSX ni o'qiydi -> {"varaqlar": [{"nom": ..., "markdown": ...}]}"""
    import openpyxl
    wb = openpyxl.load_workbook(str(fayl), data_only=True)
    varaqlar = []
    for sh in wb.worksheets:
        qatorlar = []
        for row in sh.iter_rows(values_only=True):
            kataklar = [_katak(v) for v in row]
            if any(kataklar):
                qatorlar.append(kataklar)
        if not qatorlar:
            continue
        eng_keng = max(len(q) for q in qatorlar)
        md = [f"## Varaq: {sh.title}", ""]
        for i, q in enumerate(qatorlar):
            q = q + [""] * (eng_keng - len(q))
            md.append("| " + " | ".join(q) + " |")
            if i == 0:
                md.append("|" + "---|" * eng_keng)
        varaqlar.append({"nom": sh.title, "markdown": "\n".join(md)})
        log(f"  varaq '{sh.title}': {len(qatorlar)} qator")
    return {"varaqlar": varaqlar}
