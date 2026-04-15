"""LLM-basierte Extraktion von Vereinswünschen aus Freitext.

Unterstützt:
  - Ollama (lokal, z.B. llama3, mistral)
  - OpenAI-kompatible APIs (OpenAI, Groq, Together, etc.)
"""

import json
import os
import re
from typing import Optional

import requests

from src.spielplanerstellung.wuensche import (
    Wunsch, WunschKategorie, WunschPrio, VereinsWuensche,
)

SYSTEM_PROMPT = """\
Du bist ein Assistent für die Spieltagsplanung im Jugendfußball.
Du erhältst den Freitext-Wunsch eines Vereins und extrahierst strukturierte Flags.

Antworte NUR mit einem JSON-Array von Objekten. Jedes Objekt hat:
- "kategorie": einer von: sperrtag, heimwunsch, auswaertswunsch, wochentag, anstosszeit, platzsharing, gleichzeitig, abwechselnd, reihenfolge, sonstiges
- "prioritaet": "hart" (muss beachtet werden, z.B. Platzsperrung) oder "weich" (Wunsch, wenn möglich)
- "beschreibung": kurzer deutscher Satz
- "datum": ISO-Datum wenn im Text erwähnt, sonst null
- "wochentag": Wochentag wenn relevant, sonst null
- "uhrzeit": Uhrzeit wenn relevant, sonst null
- "bezug_mannschaft": Name der anderen Mannschaft wenn relevant, sonst null

Kategorien-Erklärung:
- sperrtag: Verein kann an bestimmtem Datum NICHT spielen (Vereinsfest, Platzsperrung, etc.)
- heimwunsch: Verein wünscht Heimspiel an bestimmtem Datum
- auswaertswunsch: Verein wünscht Auswärtsspiel an bestimmtem Datum
- wochentag: Bevorzugter Spieltag (z.B. "spielen am liebsten samstags")
- anstosszeit: Gewünschte Anstoßzeit
- platzsharing: Teilen sich den Platz mit einer anderen Mannschaft
- gleichzeitig: Sollen am gleichen Tag/Zeit spielen wie andere Mannschaft
- abwechselnd: Sollen abwechselnd Heim haben mit einer anderen Mannschaft
- reihenfolge: Wunsch zur Reihenfolge Heim/Auswärts (z.B. "erst auswärts")
- sonstiges: Alles was in keine Kategorie passt

Antworte NUR mit dem JSON-Array, kein weiterer Text.\
"""


def parse_wuensche_llm(
    freitext: str,
    mannschaft: str,
    verein: str,
    provider: str = "ollama",
    model: str = "llama3.1:8b",
    api_base: Optional[str] = None,
    api_key: Optional[str] = None,
) -> VereinsWuensche:
    """Parst Freitext-Wünsche per LLM in strukturierte Flags.

    Args:
        freitext: Der Freitext vom Verein
        mannschaft: Mannschaftsname (z.B. "TSV Öhringen 2")
        verein: Vereinsname
        provider: "ollama" oder "openai"
        model: Modellname (z.B. "llama3", "gpt-4o-mini", "llama-3.1-8b-instant")
        api_base: Base-URL der API (Standard: Ollama localhost)
        api_key: API-Key (nur für OpenAI-kompatible)

    Returns:
        VereinsWuensche mit extrahierten Flags
    """
    if not freitext.strip():
        return VereinsWuensche(mannschaft=mannschaft, verein=verein)

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"Mannschaft: {mannschaft}\nVerein: {verein}\n\nWünsche:\n{freitext}"},
    ]

    raw = _call_llm(messages, provider, model, api_base, api_key)
    wuensche = _parse_response(raw, freitext)

    return VereinsWuensche(mannschaft=mannschaft, verein=verein, wuensche=wuensche)


def _call_llm(
    messages: list[dict],
    provider: str,
    model: str,
    api_base: Optional[str],
    api_key: Optional[str],
) -> str:
    """Ruft die LLM-API auf und gibt die Antwort zurück."""
    if provider == "ollama":
        url = (api_base or "http://localhost:11434") + "/api/chat"
        resp = requests.post(url, json={
            "model": model,
            "messages": messages,
            "stream": False,
            "format": "json",
        }, timeout=60)
        resp.raise_for_status()
        return resp.json()["message"]["content"]

    elif provider == "openai":
        url = (api_base or "https://api.openai.com/v1") + "/chat/completions"
        key = api_key or os.environ.get("OPENAI_API_KEY", "")
        resp = requests.post(url, json={
            "model": model,
            "messages": messages,
            "temperature": 0.1,
        }, headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        }, timeout=60)
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]

    else:
        raise ValueError(f"Unbekannter Provider: {provider}")


def _parse_response(raw: str, original_text: str) -> list[Wunsch]:
    """Parst die JSON-Antwort des LLM in Wunsch-Objekte."""
    # Extrahiere JSON-Array aus der Antwort (LLMs geben manchmal Markdown-Blöcke)
    match = re.search(r'\[.*\]', raw, re.DOTALL)
    if not match:
        return [Wunsch(
            kategorie=WunschKategorie.SONSTIGES,
            prioritaet=WunschPrio.WEICH,
            beschreibung=original_text[:200],
            original_text=original_text,
        )]

    try:
        items = json.loads(match.group())
    except json.JSONDecodeError:
        return [Wunsch(
            kategorie=WunschKategorie.SONSTIGES,
            prioritaet=WunschPrio.WEICH,
            beschreibung=original_text[:200],
            original_text=original_text,
        )]

    wuensche = []
    for item in items:
        try:
            kat = WunschKategorie(item.get("kategorie", "sonstiges"))
        except ValueError:
            kat = WunschKategorie.SONSTIGES

        try:
            prio = WunschPrio(item.get("prioritaet", "weich"))
        except ValueError:
            prio = WunschPrio.WEICH

        wuensche.append(Wunsch(
            kategorie=kat,
            prioritaet=prio,
            beschreibung=item.get("beschreibung", ""),
            datum=item.get("datum"),
            wochentag=item.get("wochentag"),
            uhrzeit=item.get("uhrzeit"),
            bezug_mannschaft=item.get("bezug_mannschaft"),
            original_text=original_text,
        ))

    return wuensche
