"""Archive AI pipeline: upload → classify → OCR if required → extract → normalise → validate → human review → approved record."""
from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

from ..config import DOCS_DIR, UPLOAD_DIR, load_settings
from . import ocr
from .providers import get_provider
from .schemas import EXTRACTION_FIELDS, NUMERIC_FIELDS, Document, Extraction, FieldValue

REGISTRY = DOCS_DIR / "registry.json"


def _load() -> dict:
    if REGISTRY.exists():
        return json.loads(REGISTRY.read_text())
    return {"documents": {}, "extractions": {}, "reviews": []}


def _save(reg: dict):
    REGISTRY.write_text(json.dumps(reg, indent=1, ensure_ascii=False))


def stored_file(d: dict) -> Path:
    """Where a registered document is on this machine.

    The registry records the path a file was written to. When that path no longer
    exists (the project was moved, or cloned somewhere else) the file is looked up
    by name in the two document folders instead.
    """
    p = Path(d["stored_path"])
    if p.exists():
        return p
    for folder in (DOCS_DIR, UPLOAD_DIR):
        if (folder / p.name).exists():
            return folder / p.name
    return p


def safe_name(name: str) -> str:
    name = Path(name).name
    return re.sub(r"[^A-Za-z0-9._\-]+", "_", name)[:120] or "upload"


def register(path: Path, bundled: bool = False, well_hint: str | None = None) -> Document:
    reg = _load()
    doc_id = "DOC-" + uuid.uuid4().hex[:8].upper()
    doc = Document(document_id=doc_id, file_name=path.name, stored_path=str(path), file_type=path.suffix.lower().lstrip("."), uploaded_at=datetime.now(timezone.utc).isoformat(), bundled=bundled, well_id=well_hint)
    reg["documents"][doc_id] = doc.model_dump()
    _save(reg)
    return doc


def save_upload(filename: str, data: bytes) -> Document:
    name = safe_name(filename)
    ext = Path(name).suffix.lower()
    if ext not in ocr.ALLOWED:
        raise ValueError(f"File type {ext or '(none)'} is not accepted. Accepted: {', '.join(sorted(ocr.ALLOWED))}")
    if len(data) > 25 * 1024 * 1024:
        raise ValueError("File is larger than 25 MB")
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    target = UPLOAD_DIR / f"{uuid.uuid4().hex[:6]}_{name}"
    target.write_bytes(data)
    return register(target)


def extract(doc_id: str, provider_name: str | None = None) -> Extraction:
    reg = _load()
    d = reg["documents"].get(doc_id)
    if not d:
        raise KeyError(doc_id)
    settings = load_settings()
    got = ocr.extract_pages(stored_file(d), settings["archive"]["ocr_languages"])
    pages = got["pages"]
    d["pages"] = max(1, len(pages))
    d["text_source"] = got["text_source"]
    d["ocr_confidence"] = got["ocr_confidence"]
    provider = get_provider(provider_name or settings["archive"]["llm_provider"])
    if got["text_source"] == "none" or sum(len(p) for p in pages) < 20 or ((got["ocr_confidence"] is not None) and got["ocr_confidence"] < 0.6):
        ex = Extraction(document_id=doc_id, source_file=d["file_name"], source_language="unknown", ocr_confidence=got["ocr_confidence"], llm_confidence=0.0, human_review_status="pending",
                        fields={f: FieldValue() for f in EXTRACTION_FIELDS}, raw_text_snippet="\n".join(pages)[:600], provider=provider.name)
        d["review_status"] = "pending"
        d["note"] = got["note"] or "No readable text: manual review required. Fields were NOT guessed."
    else:
        try:
            fields, lang, overall = provider.extract(pages)
            prov_name = provider.name
        except Exception as e:
            fields, lang, overall = get_provider("mock").extract(pages)
            prov_name = f"mock (fallback: {e})"
        # validation: numeric sanity
        for f in NUMERIC_FIELDS:
            fv = fields.get(f)
            if fv and fv.value is not None:
                try:
                    v = float(fv.value)
                    if f.startswith("water_cut") and v > 1.0:
                        fv.value = v / 100.0 if v <= 100 else None
                    if v < 0:
                        fv.value, fv.confidence = None, 0.0
                except Exception:
                    fv.value, fv.confidence = None, 0.0
        ex = Extraction(document_id=doc_id, source_file=d["file_name"], source_language=lang, ocr_confidence=got["ocr_confidence"], llm_confidence=round(overall, 3), human_review_status="pending", fields=fields,
                        raw_text_snippet="\n".join(pages)[:600], provider=prov_name)
        d["language"] = lang
        d["doc_type"] = str(fields["document_type"].value or "unknown")
        d["date"] = fields["date"].value if isinstance(fields["date"].value, str) else None
        d["well_id"] = d.get("well_id") or (str(fields["well_id"].value) if fields["well_id"].value else None)
        d["review_status"] = "pending"
        d["note"] = got["note"]
    reg["extractions"][doc_id] = ex.model_dump()
    reg["documents"][doc_id] = d
    reg.setdefault("texts", {})[doc_id] = pages
    _save(reg)
    return ex


def review(doc_id: str, decision: str, edits: dict | None = None, reviewer: str = "engineer") -> dict:
    reg = _load()
    ex = reg["extractions"].get(doc_id)
    d = reg["documents"].get(doc_id)
    if not ex or not d:
        raise KeyError(doc_id)
    if decision == "edit" and edits:
        for k, v in edits.items():
            if k in ex["fields"]:
                ex["fields"][k]["value"] = v
                ex["fields"][k]["confidence"] = 1.0
                ex["fields"][k]["source"] = "human"
        ex["human_review_status"] = "edited"
        d["review_status"] = "approved"
    elif decision == "approve":
        ex["human_review_status"] = "approved"
        d["review_status"] = "approved"
    elif decision == "reject":
        ex["human_review_status"] = "rejected"
        d["review_status"] = "rejected"
    elif decision == "unreadable":
        ex["human_review_status"] = "unreadable"
        d["review_status"] = "unreadable"
    else:
        raise ValueError("decision must be approve|edit|reject|unreadable")
    reg["reviews"].append({"document_id": doc_id, "decision": decision, "reviewer": reviewer, "at": datetime.now(timezone.utc).isoformat(), "edited_fields": list((edits or {}).keys())})
    _save(reg)
    return {"document": d, "extraction": ex}


def documents() -> list[dict]:
    reg = _load()
    return sorted(reg["documents"].values(), key=lambda d: d.get("uploaded_at", ""), reverse=True)


def get(doc_id: str) -> dict:
    reg = _load()
    return {"document": reg["documents"].get(doc_id), "extraction": reg["extractions"].get(doc_id), "pages": reg.get("texts", {}).get(doc_id, [])}


def approved_records() -> list[dict]:
    reg = _load()
    out = []
    for doc_id, ex in reg["extractions"].items():
        if ex["human_review_status"] in ("approved", "edited"):
            rec = {k: v["value"] for k, v in ex["fields"].items()}
            rec["document_id"] = doc_id
            rec["source_file"] = ex["source_file"]
            rec["source_language"] = ex["source_language"]
            out.append(rec)
    return out


def stats() -> dict:
    reg = _load()
    docs = reg["documents"]
    exs = reg["extractions"]
    settings = load_settings()
    thr = settings["archive"]["auto_approve_confidence"]
    fields_extracted = sum(1 for e in exs.values() for f in e["fields"].values() if f["value"] is not None)
    low = sum(1 for e in exs.values() for f in e["fields"].values() if f["value"] is not None and f["confidence"] < 0.7)
    auto = sum(1 for e in exs.values() if e["llm_confidence"] >= thr)
    reviewed = sum(1 for e in exs.values() if e["human_review_status"] in ("approved", "edited", "rejected", "unreadable"))
    edited = [r for r in reg["reviews"] if r["decision"] == "edit"]
    approved = [r for r in reg["reviews"] if r["decision"] in ("approve", "edit")]
    # accuracy on validated sample: share of fields the reviewer did not need to change
    total_fields = 0
    changed = 0
    for r in approved:
        ex = exs.get(r["document_id"])
        if ex:
            total_fields += sum(1 for f in ex["fields"].values() if f["value"] is not None)
            changed += len(r.get("edited_fields", []))
    acc = round(1 - changed / total_fields, 3) if total_fields else None
    return {"documents_processed": len(exs), "documents_total": len(docs), "fields_extracted": fields_extracted, "auto_approve_candidates": auto, "human_reviewed": reviewed, "low_confidence_fields": low,
            "accuracy_on_validated_sample": acc, "validated_documents": len(approved), "languages": {l: sum(1 for d in docs.values() if d.get("language") == l) for l in ("ru", "az", "en", "unknown")},
            "ocr_available": ocr.tesseract_available(), "ocr_languages": ocr.available_ocr_languages(), "provider": settings["archive"]["llm_provider"]}


def search(query: str, limit: int = 20) -> dict:
    """Keyword retrieval with citations. Never answers beyond the documents."""
    reg = _load()
    q = query.lower().strip()
    terms = [t for t in re.split(r"\s+", q) if len(t) > 1]
    hits = []
    filters = {}
    m = re.search(r"water cut (?:above|over|>)\s*(\d+)", q)
    if m:
        filters["water_cut_min"] = float(m.group(1)) / 100.0
    for doc_id, pages in reg.get("texts", {}).items():
        text = "\n".join(pages)
        low = text.lower()
        ex = reg["extractions"].get(doc_id, {})
        rec = {k: v.get("value") for k, v in ex.get("fields", {}).items()}
        score = sum(low.count(t) for t in terms)
        # semantic-ish synonyms for intervention types
        it = str(rec.get("intervention_type") or "").lower()
        for t in terms:
            if t.replace(" ", "_") in it or (t == "pump" and "pump" in it) or (t in ("shutoff", "water") and "water_shutoff" in it):
                score += 3
        if "water_cut_min" in filters:
            wc = rec.get("water_cut_before")
            if wc is None or float(wc) < filters["water_cut_min"]:
                continue
            score += 1
        if score <= 0:
            continue
        snippets = []
        for t in terms[:3]:
            k = low.find(t)
            if k >= 0:
                snippets.append(text[max(0, k - 60): k + 80].replace("\n", " "))
        hits.append({"document_id": doc_id, "file_name": reg["documents"][doc_id]["file_name"], "well_id": rec.get("well_id"), "date": rec.get("date"), "intervention_type": rec.get("intervention_type"), "score": score,
                     "review_status": reg["documents"][doc_id].get("review_status"), "snippets": snippets[:2], "language": reg["documents"][doc_id].get("language")})
    hits.sort(key=lambda h: -h["score"])
    return {"query": query, "hits": hits[:limit], "note": "Results are retrieved from document text and reviewed extractions; every hit cites its source document." if hits else "No document supports this query."}


def reset_bundled():
    """Drop uploads and reviews, re-register bundled sample documents."""
    if REGISTRY.exists():
        REGISTRY.unlink()
    for f in UPLOAD_DIR.glob("*"):
        if f.is_file():
            f.unlink()
    for p in sorted(DOCS_DIR.glob("*")):
        if p.suffix.lower() in (".txt", ".pdf", ".png") and p.name != "registry.json":
            register(p, bundled=True)


SAMPLE_DOCS = {
    "otchet_remont_SYN-031_ru.txt": """АКТ О ПРОВЕДЕНИИ ПОДЗЕМНОГО РЕМОНТА
Скважина № SYN-031
Месторождение: Synthetic Field A
Дата окончания работ: 14.03.2023
Вид работ: Замена насоса (ШГН)
Причина остановки: снижение дебита, износ плунжерной пары, засорение приёмного клапана
Основание: анализ динамики дебита за 3 месяца
Тип насоса: ШГН 44-мм
Выполненные работы: подъём НКТ, замена насоса, ревизия клапанов, спуск на 1180 м
Заменены: плунжер, приёмный клапан, штанговая колонна (частично)
Подрядчик: СервисРемонт ООО
Продолжительность: 6 суток
Стоимость: 46 500 USD
Дебит нефти до ремонта: 21,4 м3/сут
Дебит нефти после ремонта: 28,9 м3/сут
Обводнённость до: 78 %
Обводнённость после: 76 %
Давление на устье: 14 атм
Простой: 9 суток
Инженер: Гасанов Р.А.
Результат: восстановление подачи, режим стабильный
Рекомендация: контроль динамического уровня через 30 дней
""",
    "temir_hesabati_SYN-077_az.txt": """QUYU TƏMİRİ HAQQINDA HESABAT
Quyu № SYN-077
Yataq: Synthetic Field B
Tarix: 02.09.2022
Təmir növü: Su izolyasiyası
Dayanma səbəbi: sulaşmanın kəskin artması, neft debitinin azalması
Əsas: son 6 ay ərzində sulaşma 82%-dən 94%-ə qədər artmışdır
Nasos tipi: EMN
Görülən işlər: sement körpüsünün quraşdırılması, perforasiya intervalının izolyasiyası, sınaq
Dəyişdirilən hissələr: paker, NKT (12 boru)
Podratçı: Xəzər Servis MMC
Müddət: 11 gün
Dəyər: 118 000 USD
Neft debiti təmirdən əvvəl: 9,8 m3/gün
Neft debiti təmirdən sonra: 14,2 m3/gün
Sulaşma təmirdən əvvəl: 94 %
Sulaşma təmirdən sonra: 81 %
Təzyiq: 11 atm
Boşdayanma: 14 gün
Mühəndis: Məmmədov E.
Nəticə: sulaşma azaldı, neft debiti artdı
Tövsiyə: 3 aydan sonra sulaşma dinamikasına nəzarət
""",
    "workover_report_SYN-104_en.txt": """WORKOVER REPORT
Well: SYN-104
Field: Synthetic Field C
Date: 2021-11-20
Job type: Workover
Problem reported: well shut in after tubing leak and loss of circulation
Reason for job: return well to production
Pump type: PCP
Work performed: pulled tubing, replaced leaking joints, cleaned perforations, ran new PCP, tested
Parts replaced: 8 tubing joints, PCP rotor and stator
Contractor: Northline Well Services
Duration: 14 days
Cost: 205,000 USD
Oil rate before: 0 m3/d (shut in)
Oil rate after: 18.5 m3/d
Water cut before: n/a
Water cut after: 71 %
Pressure: 9 bar
Downtime: 210 days
Engineer: J. Carter
Outcome: well returned to production; rate stable over first month
Follow-up: monitor torque and fluid level weekly
""",
    "scan_unreadable_note.txt": """—— фотокопия низкого качества ——
.... .... ...... 19..
скв ... ... ...
(текст не читается)
""",
}


def write_samples():
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    for name, text in SAMPLE_DOCS.items():
        (DOCS_DIR / name).write_text(text, encoding="utf-8")
    # a PDF version of the Russian report to exercise the PDF path
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        from reportlab.pdfgen import canvas
        import glob
        font = None
        for cand in glob.glob("/usr/share/fonts/**/DejaVuSans.ttf", recursive=True) + glob.glob("/usr/share/fonts/**/LiberationSans-Regular.ttf", recursive=True):
            try:
                pdfmetrics.registerFont(TTFont("Uni", cand))
                font = "Uni"
                break
            except Exception:
                continue
        if font:
            c = canvas.Canvas(str(DOCS_DIR / "otchet_remont_SYN-031_ru.pdf"), pagesize=A4)
            c.setFont(font, 10)
            y = 800
            for line in SAMPLE_DOCS["otchet_remont_SYN-031_ru.txt"].splitlines():
                c.drawString(40, y, line)
                y -= 16
            c.save()
    except Exception:
        pass
