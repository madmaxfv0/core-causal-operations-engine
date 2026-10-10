"""Pluggable extraction providers. LLM_PROVIDER=mock|anthropic|openai|local.

The mock provider is a deterministic rule-based extractor for Russian, Azerbaijani and English intervention
reports, so the demo works offline. It never invents a value: a field it cannot read stays empty.
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime

from .schemas import EXTRACTION_FIELDS, NUMERIC_FIELDS, FieldValue

# language → field → list of regex patterns (first capture group = value)
PATTERNS = {
    "ru": {
        "well_id": [r"[Сс]кважин[аеы]\s*№?\s*([A-ZА-Я0-9\-]+)", r"[Сс]кв\.\s*№?\s*([A-ZА-Я0-9\-]+)"],
        "field": [r"[Мм]есторождение[:\s]+([А-Яа-яA-Za-z0-9\-\s]+?)(?:\n|,|\.)"],
        "date": [r"[Дд]ата[^\n:]*[:\s]+(\d{1,2}[\./]\d{1,2}[\./]\d{2,4})"],
        "intervention_type": [r"[Вв]ид работ[:\s]+([^\n]+)", r"[Тт]ип ремонта[:\s]+([^\n]+)"],
        "problem_reported": [r"[Пп]ричина остановки[:\s]+([^\n]+)", r"[Пп]роблема[:\s]+([^\n]+)"],
        "reason_for_intervention": [r"[Оо]снование[:\s]+([^\n]+)", r"[Пп]ричина ремонта[:\s]+([^\n]+)"],
        "pump_type": [r"[Тт]ип насоса[:\s]+([^\n]+)"],
        "work_performed": [r"[Вв]ыполненные работы[:\s]+([^\n]+)"],
        "contractor": [r"[Пп]одрядчик[:\s]+([^\n]+)"],
        "duration": [r"[Пп]родолжительность[^\d\n]*(\d+[\.,]?\d*)"],
        "cost": [r"[Сс]тоимость[^\d\n]*([\d\s]+[\.,]?\d*)"],
        "currency": [r"[Сс]тоимость[^\n]*?(USD|AZN|руб|долл)"],
        "oil_before": [r"[Дд]ебит нефти до[^\d\n]*(\d+[\.,]?\d*)"],
        "oil_after": [r"[Дд]ебит нефти после[^\d\n]*(\d+[\.,]?\d*)"],
        "water_cut_before": [r"[Оо]бводн[её]нность до[^\d\n]*(\d+[\.,]?\d*)"],
        "water_cut_after": [r"[Оо]бводн[её]нность после[^\d\n]*(\d+[\.,]?\d*)"],
        "pressure": [r"[Дд]авление[^\d\n]*(\d+[\.,]?\d*)"],
        "downtime": [r"[Пп]ростой[^\d\n]*(\d+[\.,]?\d*)"],
        "parts_replaced": [r"[Зз]аменен[ыо]?[:\s]+([^\n]+)"],
        "engineer_name": [r"[Ии]нженер[:\s]+([^\n]+)"],
        "outcome_description": [r"[Рр]езультат[:\s]+([^\n]+)"],
        "follow_up_action": [r"[Рр]екомендаци[яи][:\s]+([^\n]+)"],
    },
    "az": {
        "well_id": [r"[Qq]uyu\s*№?\s*([A-Z0-9\-]+)"],
        "field": [r"[Yy]ataq[:\s]+([^\n,]+)"],
        "date": [r"[Tt]arix[:\s]+(\d{1,2}[\./]\d{1,2}[\./]\d{2,4})"],
        "intervention_type": [r"[Tt]əmir növü[:\s]+([^\n]+)", r"[İi]ş növü[:\s]+([^\n]+)"],
        "problem_reported": [r"[Dd]ayanma səbəbi[:\s]+([^\n]+)", r"[Pp]roblem[:\s]+([^\n]+)"],
        "reason_for_intervention": [r"[Əə]sas[:\s]+([^\n]+)"],
        "pump_type": [r"[Nn]asos tipi[:\s]+([^\n]+)"],
        "work_performed": [r"[Gg]örülən işlər[:\s]+([^\n]+)"],
        "contractor": [r"[Pp]odratçı[:\s]+([^\n]+)"],
        "duration": [r"[Mm]üddət[^\d\n]*(\d+[\.,]?\d*)"],
        "cost": [r"[Dd]əyər[^\d\n]*([\d\s]+[\.,]?\d*)", r"[Xx]ərc[^\d\n]*([\d\s]+[\.,]?\d*)"],
        "currency": [r"(?:[Dd]əyər|[Xx]ərc)[^\n]*?(USD|AZN|manat)"],
        "oil_before": [r"[Nn]eft debiti[^\n]*?əvvəl[^\d\n]*(\d+[\.,]?\d*)", r"[Tt]əmirdən əvvəl neft[^\d\n]*(\d+[\.,]?\d*)"],
        "oil_after": [r"[Nn]eft debiti[^\n]*?sonra[^\d\n]*(\d+[\.,]?\d*)", r"[Tt]əmirdən sonra neft[^\d\n]*(\d+[\.,]?\d*)"],
        "water_cut_before": [r"[Ss]ulaşma[^\n]*?əvvəl[^\d\n]*(\d+[\.,]?\d*)"],
        "water_cut_after": [r"[Ss]ulaşma[^\n]*?sonra[^\d\n]*(\d+[\.,]?\d*)"],
        "pressure": [r"[Tt]əzyiq[^\d\n]*(\d+[\.,]?\d*)"],
        "downtime": [r"[Bb]oşdayanma[^\d\n]*(\d+[\.,]?\d*)"],
        "parts_replaced": [r"[Dd]əyişdirilən hissələr[:\s]+([^\n]+)"],
        "engineer_name": [r"[Mm]ühəndis[:\s]+([^\n]+)"],
        "outcome_description": [r"[Nn]əticə[:\s]+([^\n]+)"],
        "follow_up_action": [r"[Tt]övsiyə[:\s]+([^\n]+)"],
    },
    "en": {
        "well_id": [r"[Ww]ell\s*(?:ID|No\.?|#)?\s*[:\s]\s*([A-Z0-9\-]+)"],
        "field": [r"[Ff]ield[:\s]+([^\n,]+)"],
        "date": [r"[Dd]ate[:\s]+(\d{4}-\d{2}-\d{2}|\d{1,2}[\./]\d{1,2}[\./]\d{2,4})"],
        "intervention_type": [r"(?:[Jj]ob|[Ii]ntervention) type[:\s]+([^\n]+)"],
        "problem_reported": [r"[Pp]roblem reported[:\s]+([^\n]+)", r"[Rr]eason for shut-?in[:\s]+([^\n]+)"],
        "reason_for_intervention": [r"[Rr]eason for (?:intervention|job)[:\s]+([^\n]+)"],
        "pump_type": [r"[Pp]ump type[:\s]+([^\n]+)"],
        "work_performed": [r"[Ww]ork performed[:\s]+([^\n]+)"],
        "contractor": [r"[Cc]ontractor[:\s]+([^\n]+)"],
        "duration": [r"[Dd]uration[^\d\n]*(\d+[\.,]?\d*)"],
        "cost": [r"[Cc]ost[^\d\n]*([\d,]+[\.]?\d*)"],
        "currency": [r"[Cc]ost[^\n]*?(USD|AZN|\$)"],
        "oil_before": [r"[Oo]il (?:rate )?before[^\d\n]*(\d+[\.,]?\d*)"],
        "oil_after": [r"[Oo]il (?:rate )?after[^\d\n]*(\d+[\.,]?\d*)"],
        "water_cut_before": [r"[Ww]ater cut before[^\d\n]*(\d+[\.,]?\d*)"],
        "water_cut_after": [r"[Ww]ater cut after[^\d\n]*(\d+[\.,]?\d*)"],
        "pressure": [r"[Pp]ressure[^\d\n]*(\d+[\.,]?\d*)"],
        "downtime": [r"[Dd]owntime[^\d\n]*(\d+[\.,]?\d*)"],
        "parts_replaced": [r"[Pp]arts replaced[:\s]+([^\n]+)"],
        "engineer_name": [r"[Ee]ngineer[:\s]+([^\n]+)"],
        "outcome_description": [r"[Oo]utcome[:\s]+([^\n]+)"],
        "follow_up_action": [r"[Ff]ollow-?up[:\s]+([^\n]+)"],
    },
}

TYPE_NORMALISE = {
    "замена насоса": "pump_replacement", "смена насоса": "pump_replacement", "nasos dəyişdirilməsi": "pump_replacement", "pump replacement": "pump_replacement",
    "промывка": "cleanout", "очистка": "cleanout", "təmizləmə": "cleanout", "cleanout": "cleanout",
    "водоизоляция": "water_shutoff", "изоляция водопритока": "water_shutoff", "su izolyasiyası": "water_shutoff", "water shutoff": "water_shutoff", "water shut-off": "water_shutoff",
    "интенсификация": "stimulation", "кислотная обработка": "stimulation", "stimulyasiya": "stimulation", "turşu ilə işləmə": "stimulation", "stimulation": "stimulation", "acid": "stimulation",
    "капитальный ремонт": "workover", "крс": "workover", "əsaslı təmir": "workover", "workover": "workover",
    "пуск": "restart", "запуск": "restart", "işə salma": "restart", "restart": "restart",
}


def detect_language(text: str) -> str:
    t = text.lower()
    az_hits = sum(t.count(c) for c in "əğışöüç") + sum(t.count(w) for w in ("quyu", "tarix", "neft", "təmir"))
    ru_hits = len(re.findall(r"[а-яё]", t))
    en_hits = len(re.findall(r"\b(well|date|pump|water cut|oil|report|cost|contractor)\b", t))
    if az_hits > 5 and az_hits >= ru_hits * 0.2:
        return "az"
    if ru_hits > 20:
        return "ru"
    if en_hits > 2:
        return "en"
    return "unknown"


def _num(s: str):
    s = s.replace(" ", "").replace("\u00a0", "")
    if re.fullmatch(r"\d{1,3}(,\d{3})+(\.\d+)?", s):
        s = s.replace(",", "")
    else:
        s = s.replace(",", ".")
    try:
        return float(re.findall(r"\d+\.?\d*", s)[0])
    except Exception:
        return None


def normalise_type(raw: str | None) -> str | None:
    if not raw:
        return None
    t = raw.lower().strip()
    for k, v in TYPE_NORMALISE.items():
        if k in t:
            return v
    return None


def normalise_date(raw: str | None) -> str | None:
    if not raw:
        return None
    for fmt in ("%d.%m.%Y", "%d/%m/%Y", "%Y-%m-%d", "%d.%m.%y"):
        try:
            return datetime.strptime(raw.strip(), fmt).strftime("%Y-%m-%d")
        except Exception:
            continue
    return None


class MockProvider:
    name = "mock"

    def extract(self, pages: list[str]) -> tuple[dict[str, FieldValue], str, float]:
        text = "\n".join(pages)
        lang = detect_language(text)
        pats = PATTERNS.get(lang, PATTERNS["en"])
        fields: dict[str, FieldValue] = {}
        for f in EXTRACTION_FIELDS:
            fv = FieldValue(source="mock:rule")
            for pat in pats.get(f, []):
                for pi, page in enumerate(pages):
                    m = re.search(pat, page)
                    if m:
                        raw = m.group(1).strip()
                        val = _num(raw) if f in NUMERIC_FIELDS else raw
                        conf = 0.0 if val is None or val == "" else (0.9 if f in NUMERIC_FIELDS else 0.85)
                        if f == "intervention_type":
                            norm = normalise_type(raw)
                            fv = FieldValue(value=norm or raw, confidence=0.92 if norm else 0.5, page=pi + 1, span=[m.start(1), m.end(1)], snippet=page[max(0, m.start() - 20): m.end() + 20], source="mock:rule")
                        elif f == "date":
                            nd = normalise_date(raw)
                            fv = FieldValue(value=nd or raw, confidence=0.95 if nd else 0.4, page=pi + 1, span=[m.start(1), m.end(1)], snippet=page[max(0, m.start() - 20): m.end() + 20], source="mock:rule")
                        else:
                            fv = FieldValue(value=val, confidence=conf, page=pi + 1, span=[m.start(1), m.end(1)], snippet=page[max(0, m.start() - 20): m.end() + 20], source="mock:rule")
                        break
                if fv.value is not None:
                    break
            fields[f] = fv
        if fields["document_type"].value is None:
            fields["document_type"] = FieldValue(value="intervention_report" if fields["intervention_type"].value else "unknown", confidence=0.7 if fields["intervention_type"].value else 0.2, source="mock:rule")
        filled = [v.confidence for v in fields.values() if v.value is not None]
        overall = float(sum(filled) / max(len(EXTRACTION_FIELDS), 1)) if filled else 0.0
        return fields, lang, overall


SYSTEM_PROMPT = """You extract structured data from oilfield intervention reports written in Russian, Azerbaijani or English.
Return ONLY a JSON object with keys: %s.
For each key return {"value": <string|number|null>, "confidence": <0..1>, "snippet": "<short quote from the text supporting the value>"}.
Never guess: if a field is not in the text, value must be null with confidence 0. Do not compute anything (no NPV, no uplift). Normalise intervention_type to one of: pump_replacement, cleanout, water_shutoff, stimulation, workover, restart, or the original text if none applies. Normalise dates to YYYY-MM-DD.""" % ", ".join(EXTRACTION_FIELDS)


class AnthropicProvider:
    name = "anthropic"

    def extract(self, pages):
        import httpx
        key = os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            raise RuntimeError("ANTHROPIC_API_KEY is not set")
        text = "\n\n".join(f"[page {i + 1}]\n{p}" for i, p in enumerate(pages))
        r = httpx.post("https://api.anthropic.com/v1/messages", headers={"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
                       json={"model": os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6"), "max_tokens": 2000, "system": SYSTEM_PROMPT, "messages": [{"role": "user", "content": text[:20000]}]}, timeout=60)
        r.raise_for_status()
        content = "".join(b.get("text", "") for b in r.json().get("content", []))
        return _parse_llm_json(content, pages)


class OpenAIProvider:
    name = "openai"

    def extract(self, pages):
        import httpx
        key = os.environ.get("OPENAI_API_KEY")
        if not key:
            raise RuntimeError("OPENAI_API_KEY is not set")
        text = "\n\n".join(f"[page {i + 1}]\n{p}" for i, p in enumerate(pages))
        r = httpx.post("https://api.openai.com/v1/chat/completions", headers={"Authorization": f"Bearer {key}"},
                       json={"model": os.environ.get("OPENAI_MODEL", "gpt-4o-mini"), "messages": [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": text[:20000]}], "temperature": 0}, timeout=60)
        r.raise_for_status()
        return _parse_llm_json(r.json()["choices"][0]["message"]["content"], pages)


class LocalProvider:
    """Placeholder for an OpenAI-compatible local server (e.g. Ollama/vLLM). Set LOCAL_LLM_URL."""
    name = "local"

    def extract(self, pages):
        import httpx
        url = os.environ.get("LOCAL_LLM_URL")
        if not url:
            raise RuntimeError("LOCAL_LLM_URL is not set")
        text = "\n\n".join(f"[page {i + 1}]\n{p}" for i, p in enumerate(pages))
        r = httpx.post(url, json={"model": os.environ.get("LOCAL_LLM_MODEL", "llama3"), "messages": [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": text[:20000]}], "temperature": 0}, timeout=120)
        r.raise_for_status()
        return _parse_llm_json(r.json()["choices"][0]["message"]["content"], pages)


def _parse_llm_json(content: str, pages: list[str]):
    content = content.strip()
    content = re.sub(r"^```(?:json)?|```$", "", content, flags=re.M).strip()
    data = json.loads(content)
    fields = {}
    for f in EXTRACTION_FIELDS:
        d = data.get(f) or {}
        val = d.get("value")
        snippet = d.get("snippet")
        page, span = None, None
        if snippet:
            for pi, p in enumerate(pages):
                k = p.find(snippet[:40])
                if k >= 0:
                    page, span = pi + 1, [k, k + len(snippet)]
                    break
        conf = float(d.get("confidence", 0) or 0)
        if val is None:
            conf = 0.0
        if snippet and page is None:
            conf = min(conf, 0.5)  # unverifiable citation → cannot exceed review threshold
        fields[f] = FieldValue(value=val, confidence=conf, page=page, span=span, snippet=snippet, source="llm")
    lang = detect_language("\n".join(pages))
    filled = [v.confidence for v in fields.values() if v.value is not None]
    return fields, lang, float(sum(filled) / len(EXTRACTION_FIELDS)) if filled else 0.0


def get_provider(name: str | None = None):
    name = (name or os.environ.get("LLM_PROVIDER", "mock")).lower()
    return {"mock": MockProvider, "anthropic": AnthropicProvider, "openai": OpenAIProvider, "local": LocalProvider}.get(name, MockProvider)()
