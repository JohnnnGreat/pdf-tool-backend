from __future__ import annotations

import base64
import json
from typing import AsyncGenerator

from fastapi import HTTPException, status

from app.core.config import settings

# ── Prompts ────────────────────────────────────────────────────────────────

_CHAT_SYSTEM = """You are DocForge AI, a helpful assistant that answers questions about documents.
Be concise, accurate, and cite specific parts of the document when relevant.
If the answer is not in the document, say so clearly."""

_SUMMARIZE_PROMPTS = {
    "bullets":   "Summarize this document as a concise bullet-point list of the most important facts and key points. Use • for bullets.",
    "paragraph": "Write a clear, flowing paragraph summary of this document in 3-5 sentences covering the main points.",
    "executive": "Write an executive summary of this document. Include: Purpose, Key Findings, Main Conclusions, and Recommended Actions.",
    "takeaways": "List the top 5-7 key takeaways from this document. Number each one and explain why it matters.",
}

_EXTRACT_PROMPTS = {
    "invoice":  """Extract all data from this invoice as valid JSON with these fields:
{"vendor":{"name":"","address":"","email":"","phone":""},"buyer":{"name":"","address":""},"invoice_number":"","date":"","due_date":"","line_items":[{"description":"","qty":0,"unit_price":0,"total":0}],"subtotal":0,"tax":0,"discount":0,"total":0,"currency":"","notes":""}
Return ONLY the JSON, no explanation.""",

    "contract": """Extract key information from this contract as valid JSON:
{"parties":[{"name":"","role":""}],"effective_date":"","expiry_date":"","governing_law":"","key_obligations":[{"party":"","obligation":""}],"payment_terms":"","termination_clause":"","confidentiality":"yes/no","non_compete":"yes/no","important_clauses":[]}
Return ONLY the JSON, no explanation.""",

    "receipt":  """Extract all data from this receipt as valid JSON:
{"merchant":{"name":"","address":"","phone":""},"date":"","time":"","items":[{"name":"","qty":0,"price":0}],"subtotal":0,"tax":0,"tip":0,"total":0,"payment_method":"","last_4_digits":""}
Return ONLY the JSON, no explanation.""",

    "resume":   """Extract all information from this resume as valid JSON:
{"name":"","email":"","phone":"","location":"","linkedin":"","summary":"","experience":[{"company":"","title":"","start":"","end":"","bullets":[]}],"education":[{"school":"","degree":"","field":"","year":""}],"skills":[],"certifications":[],"languages":[]}
Return ONLY the JSON, no explanation.""",

    "custom":   "Extract all key information from this document as structured JSON. Include all important data points, dates, names, numbers, and facts. Return ONLY the JSON.",
}

_OCR_CLEANUP_PROMPT = """Clean up this raw OCR text. Fix:
- Spelling errors caused by OCR misreads
- Broken words split across lines
- Incorrect spacing and punctuation
- Garbled characters (e.g. 'rn' misread as 'm')
- Preserve original formatting where clear (paragraphs, lists)
Return ONLY the cleaned text, no explanations.

RAW TEXT:
{text}"""


# ── Helpers ────────────────────────────────────────────────────────────────

def _pdf_part(file_bytes: bytes, mime_type: str = "application/pdf") -> dict:
    return {
        "inline_data": {
            "mime_type": mime_type,
            "data": base64.standard_b64encode(file_bytes).decode(),
        }
    }


def _require_gemini():
    if not settings.GEMINI_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="GEMINI_API_KEY is not configured. Get a free key at aistudio.google.com.",
        )
    import google.generativeai as genai
    genai.configure(api_key=settings.GEMINI_API_KEY)
    return genai.GenerativeModel("gemini-1.5-flash")


def _require_groq():
    if not settings.GROQ_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="GROQ_API_KEY is not configured. Get a free key at console.groq.com.",
        )
    from groq import Groq
    return Groq(api_key=settings.GROQ_API_KEY)


# ── AI Service ─────────────────────────────────────────────────────────────

class AIService:

    # ------------------------------------------------------------------ #
    #  PDF Chat (streaming)                                                #
    # ------------------------------------------------------------------ #

    async def chat_stream(
        self,
        file_bytes: bytes,
        mime_type: str,
        message: str,
        history: list[dict],
    ) -> AsyncGenerator[str, None]:
        model = _require_gemini()

        # Build the content list: system + PDF + history + new message
        parts: list = [_CHAT_SYSTEM, _pdf_part(file_bytes, mime_type)]

        for turn in history:
            role    = turn.get("role", "user")
            content = turn.get("content", "")
            parts.append(f"\n[{role.upper()}]: {content}")

        parts.append(f"\n[USER]: {message}\n[ASSISTANT]:")

        try:
            response = await model.generate_content_async(
                parts,
                stream=True,
                generation_config={"temperature": 0.3, "max_output_tokens": 2048},
            )
            async for chunk in response:
                if chunk.text:
                    yield f"data: {json.dumps({'text': chunk.text})}\n\n"
        except Exception as exc:
            yield f"data: {json.dumps({'error': str(exc)})}\n\n"

        yield "data: [DONE]\n\n"

    # ------------------------------------------------------------------ #
    #  Summarize                                                           #
    # ------------------------------------------------------------------ #

    async def summarize(
        self,
        file_bytes: bytes,
        mime_type: str,
        format_type: str = "bullets",
        length: str = "standard",
    ) -> str:
        model  = _require_gemini()
        prompt = _SUMMARIZE_PROMPTS.get(format_type, _SUMMARIZE_PROMPTS["bullets"])

        length_note = {
            "brief":    " Keep it brief — no more than 150 words.",
            "standard": " Aim for a comprehensive but focused response.",
            "detailed": " Be thorough and detailed, covering all major points.",
        }.get(length, "")

        try:
            response = await model.generate_content_async(
                [_pdf_part(file_bytes, mime_type), prompt + length_note],
                generation_config={"temperature": 0.2, "max_output_tokens": 2048},
            )
            return response.text
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Gemini error: {exc}")

    # ------------------------------------------------------------------ #
    #  Data Extractor                                                      #
    # ------------------------------------------------------------------ #

    async def extract(
        self,
        file_bytes: bytes,
        mime_type: str,
        doc_type: str = "custom",
    ) -> dict:
        model  = _require_gemini()
        prompt = _EXTRACT_PROMPTS.get(doc_type, _EXTRACT_PROMPTS["custom"])

        try:
            response = await model.generate_content_async(
                [_pdf_part(file_bytes, mime_type), prompt],
                generation_config={"temperature": 0.1, "max_output_tokens": 4096},
            )
            raw = response.text.strip()
            # Strip markdown code fences if present
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

            try:
                return {"data": json.loads(raw), "raw": raw}
            except json.JSONDecodeError:
                return {"data": None, "raw": raw}

        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Gemini error: {exc}")

    # ------------------------------------------------------------------ #
    #  OCR Cleanup (Groq — fast)                                          #
    # ------------------------------------------------------------------ #

    async def cleanup_ocr_stream(
        self, text: str
    ) -> AsyncGenerator[str, None]:
        client = _require_groq()
        prompt = _OCR_CLEANUP_PROMPT.format(text=text)

        try:
            stream = client.chat.completions.create(
                model="llama-3.1-70b-versatile",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=4096,
                stream=True,
            )
            for chunk in stream:
                delta = chunk.choices[0].delta.content
                if delta:
                    yield f"data: {json.dumps({'text': delta})}\n\n"
        except Exception as exc:
            yield f"data: {json.dumps({'error': str(exc)})}\n\n"

        yield "data: [DONE]\n\n"
