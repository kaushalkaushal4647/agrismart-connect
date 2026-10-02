"""
AgriSmart Connect - Local Ollama Vision-AI Assistant.
Integrates with the local 'llava:7b-v1.6' model on the user's laptop for:
1. Agronomy Q&A, fertilizer advice, and harvest planning.
2. Visual pest and crop disease diagnosis via multimodal image analysis.
"""

import json
import os
import re
import requests
from typing import Dict, Any, Optional, Generator, Iterator

try:
    from config import Config
except ImportError:
    from backend.config import Config

OLLAMA_BASE_URL = getattr(Config, 'OLLAMA_HOST', os.getenv('OLLAMA_HOST', 'http://localhost:11434'))
DEFAULT_MODEL = 'llava:7b-v1.6'

SYSTEM_PROMPT = (
    "You are AgriSmart AI, an expert agronomist, crop specialist, and plant pathologist. "
    "Provide clear, actionable, and scientifically sound advice for farmers and agricultural buyers. "
    "When answering agronomy questions, suggest organic and integrated pest management (IPM) techniques, "
    "proper N-P-K fertilizer balancing, and harvest handling best practices. Keep responses structured and practical."
)


class AgriSmartAI:
    @classmethod
    def check_health(cls) -> Dict[str, Any]:
        """Verify AI connectivity (Gemini Cloud API in production or local Ollama)."""
        gemini_key = getattr(Config, 'GEMINI_API_KEY', os.getenv('GEMINI_API_KEY', '')).strip()
        gemini_model = getattr(Config, 'GEMINI_MODEL', os.getenv('GEMINI_MODEL', 'gemini-1.5-flash')).strip()

        if gemini_key:
            return {
                'online': True,
                'provider': 'Google Gemini (Cloud)',
                'available_models': [gemini_model],
                'active_model': gemini_model,
                'model_ready': True
            }

        try:
            r = requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=3)
            if r.status_code == 200:
                models = [m['name'] for m in r.json().get('models', [])]
                has_target = any('llava' in m for m in models)
                return {
                    'online': True,
                    'provider': 'Ollama (Local)',
                    'available_models': models,
                    'active_model': DEFAULT_MODEL,
                    'model_ready': has_target
                }
            return {'online': False, 'error': f"Ollama HTTP {r.status_code}"}
        except Exception as e:
            return {'online': False, 'error': str(e), 'hint': 'Set GEMINI_API_KEY in cloud or run Ollama on localhost:11434'}

    @classmethod
    def _gemini_generate(cls, prompt: str, context: Optional[str] = None, base64_image: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Call Google Gemini REST API for fast cloud inference with multimodal vision."""
        gemini_key = getattr(Config, 'GEMINI_API_KEY', os.getenv('GEMINI_API_KEY', '')).strip()
        gemini_model = getattr(Config, 'GEMINI_MODEL', os.getenv('GEMINI_MODEL', 'gemini-3.1-flash-lite')).strip()
        if not gemini_key:
            return None

        # Try active model first, then reliable flash backups if experiencing peak traffic
        models_to_try = [gemini_model]
        for alt in ['gemini-3.1-flash-lite', 'gemini-3.8-flash', 'gemini-flash-latest']:
            if alt not in models_to_try:
                models_to_try.append(alt)

        parts = []
        if base64_image:
            mime_type = "image/jpeg"
            clean_b64 = base64_image
            if "data:" in base64_image and ";base64," in base64_image:
                prefix, clean_b64 = base64_image.split(";base64,", 1)
                mime_type = prefix.replace("data:", "").strip() or "image/jpeg"
            elif "," in base64_image:
                clean_b64 = base64_image.split(",", 1)[1]

            parts.append({
                "inline_data": {
                    "mime_type": mime_type,
                    "data": clean_b64.strip()
                }
            })

        user_text = f"Context: {context}\n\n" if context else ""
        user_text += prompt
        parts.append({"text": user_text})

        payload = {
            "system_instruction": {
                "parts": [{"text": SYSTEM_PROMPT}]
            },
            "contents": [
                {
                    "role": "user",
                    "parts": parts
                }
            ],
            "generationConfig": {
                "temperature": 0.4 if base64_image else 0.6,
                "maxOutputTokens": 800
            }
        }

        last_error = ""
        for m in models_to_try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent?key={gemini_key}"
            try:
                r = requests.post(url, json=payload, timeout=30)
                if r.status_code == 200:
                    data = r.json()
                    candidates = data.get('candidates', [])
                    if candidates:
                        parts_out = candidates[0].get('content', {}).get('parts', [])
                        text = "".join(p.get('text', '') for p in parts_out).strip()
                        return {
                            'status': 'success',
                            'model': f"Google Gemini ({m})",
                            'text': text
                        }
                last_error = f"Gemini HTTP {r.status_code}: {r.text}"
            except Exception as e:
                last_error = f"Gemini API request failed: {str(e)}"

        return {'status': 'error', 'message': last_error}

    @classmethod
    def _gemini_stream(cls, prompt: str, context: Optional[str] = None) -> Iterator[str]:
        """Stream Google Gemini output using Server-Sent Events (SSE)."""
        gemini_key = getattr(Config, 'GEMINI_API_KEY', os.getenv('GEMINI_API_KEY', '')).strip()
        gemini_model = getattr(Config, 'GEMINI_MODEL', os.getenv('GEMINI_MODEL', 'gemini-3.1-flash-lite')).strip()
        if not gemini_key:
            return

        models_to_try = [gemini_model]
        for alt in ['gemini-3.1-flash-lite', 'gemini-3.8-flash', 'gemini-flash-latest']:
            if alt not in models_to_try:
                models_to_try.append(alt)

        user_text = f"Context: {context}\n\n" if context else ""
        user_text += f"Farmer Question: {prompt}\n\nAgriSmart Expert Advice:"

        payload = {
            "system_instruction": {
                "parts": [{"text": SYSTEM_PROMPT}]
            },
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": user_text}]
                }
            ],
            "generationConfig": {
                "temperature": 0.6,
                "maxOutputTokens": 800
            }
        }

        for m in models_to_try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{m}:streamGenerateContent?alt=sse&key={gemini_key}"
            try:
                r = requests.post(url, json=payload, stream=True, timeout=40)
                if r.status_code == 200:
                    for line in r.iter_lines():
                        if not line:
                            continue
                        line_str = line.decode('utf-8', errors='ignore') if isinstance(line, bytes) else line
                        if line_str.startswith('data:'):
                            data_json = line_str[5:].strip()
                            if not data_json:
                                continue
                            try:
                                chunk = json.loads(data_json)
                                candidates = chunk.get('candidates', [])
                                if candidates:
                                    parts = candidates[0].get('content', {}).get('parts', [])
                                    token = "".join(p.get('text', '') for p in parts)
                                    if token:
                                        yield f"data: {json.dumps({'token': token, 'model': f'Google Gemini ({m})'})}\n\n"
                            except json.JSONDecodeError:
                                continue
                    yield "data: [DONE]\n\n"
                    return
            except Exception:
                continue


    @classmethod
    def ask_agronomy(cls, prompt: str, context: Optional[str] = None) -> Dict[str, Any]:
        """
        Text-based agricultural advisory chat.
        Uses Google Gemini in production if GEMINI_API_KEY is configured,
        or local Ollama (llava:7b-v1.6 / llama3.2) for local offline development.
        """
        # 1. Try Gemini Cloud first if key configured
        gemini_res = cls._gemini_generate(prompt=prompt, context=context)
        if gemini_res and gemini_res.get('status') == 'success':
            return {
                'status': 'success',
                'model': gemini_res.get('model'),
                'response': gemini_res.get('text')
            }

        # 2. Local Ollama fallback
        full_prompt = f"{SYSTEM_PROMPT}\n\n"
        if context:
            full_prompt += f"Context: {context}\n\n"
        full_prompt += f"Farmer Question: {prompt}\n\nAgriSmart Expert Advice:"

        try:
            res = requests.post(
                f"{OLLAMA_BASE_URL}/api/generate",
                json={
                    'model': DEFAULT_MODEL,
                    'prompt': full_prompt,
                    'stream': False,
                    'options': {
                        'temperature': 0.6,
                        'top_p': 0.9,
                        'num_predict': 280,
                        'num_ctx': 2048
                    }
                },
                timeout=180
            )

            if res.status_code == 200:
                answer = res.json().get('response', '').strip()
                return {
                    'status': 'success',
                    'model': DEFAULT_MODEL,
                    'response': answer
                }
            return {
                'status': 'error',
                'message': f"Ollama returned HTTP {res.status_code}: {res.text}"
            }

        except Exception as e:
            # Fallback to lightweight llama3.2 if available for fast text agronomy
            try:
                fb_res = requests.post(
                    f"{OLLAMA_BASE_URL}/api/generate",
                    json={
                        'model': 'llama3.2:latest',
                        'prompt': full_prompt,
                        'stream': False,
                        'options': {'num_predict': 250}
                    },
                    timeout=30
                )
                if fb_res.status_code == 200:
                    fb_answer = fb_res.json().get('response', '').strip()
                    return {
                        'status': 'success',
                        'model': 'llama3.2:latest (speed optimized)',
                        'response': fb_answer
                    }
            except Exception:
                pass

            err_msg = f"AI service error: {str(e)}."
            if not getattr(Config, 'GEMINI_API_KEY', ''):
                err_msg += " (Tip: set GEMINI_API_KEY in cloud environment variables for 24/7 free cloud AI, or run Ollama locally)."
            return {'status': 'error', 'message': err_msg}

    @classmethod
    def stream_agronomy(cls, prompt: str, context: Optional[str] = None) -> Iterator[str]:
        """
        Stream text-based agricultural advisory chat using SSE.
        Uses Google Gemini in production or local Ollama when developing locally.
        """
        gemini_key = getattr(Config, 'GEMINI_API_KEY', os.getenv('GEMINI_API_KEY', '')).strip()
        if gemini_key:
            streamed_any = False
            for chunk in cls._gemini_stream(prompt=prompt, context=context):
                streamed_any = True
                yield chunk
            if streamed_any:
                return

        # Fallback to local Ollama
        full_prompt = f"{SYSTEM_PROMPT}\n\n"
        if context:
            full_prompt += f"Context: {context}\n\n"
        full_prompt += f"Farmer Question: {prompt}\n\nAgriSmart Expert Advice:"

        models_to_try = [DEFAULT_MODEL, 'llama3.2:latest']

        for model in models_to_try:
            try:
                res = requests.post(
                    f"{OLLAMA_BASE_URL}/api/generate",
                    json={
                        'model': model,
                        'prompt': full_prompt,
                        'stream': True,
                        'options': {
                            'temperature': 0.6,
                            'top_p': 0.9,
                            'num_predict': 280,
                            'num_ctx': 2048
                        }
                    },
                    stream=True,
                    timeout=180
                )

                if res.status_code != 200:
                    continue

                for raw_line in res.iter_lines():
                    if not raw_line:
                        continue
                    try:
                        chunk = json.loads(raw_line)
                        token = chunk.get('response', '')
                        done = chunk.get('done', False)
                        if token:
                            yield f"data: {json.dumps({'token': token, 'model': model})}\n\n"
                        if done:
                            yield "data: [DONE]\n\n"
                            return
                    except (json.JSONDecodeError, KeyError):
                        continue
                return

            except Exception:
                continue

        # All models failed
        yield f"data: {json.dumps({'error': 'AI unavailable. Set GEMINI_API_KEY on your cloud server or ensure Ollama is running locally.'})}\n\n"
        yield "data: [DONE]\n\n"

    @classmethod
    def diagnose_crop_disease(cls, base64_image: str, question: Optional[str] = None) -> Dict[str, Any]:
        """
        Multimodal visual pest & disease inspection.
        Uses Google Gemini 1.5 Flash in cloud production (fast & accurate),
        or local llava:7b-v1.6 in local development.
        """
        prompt = (
            "Analyze this agricultural crop image carefully as a certified plant pathologist. "
            "Identify the following in structured bullet points:\n"
            "1. Crop / Plant Identification\n"
            "2. Observed Symptoms & Visual Anomalies\n"
            "3. Probable Diagnosis (Pest infestation, Fungal, Bacterial, Viral, or Nutrient deficiency)\n"
            "4. Immediate Treatment / Organic Remedy\n"
            "5. Preventive Actions for Future Harvests"
        )
        if question:
            prompt += f"\n\nFarmer Specific Inquiry: {question}"

        # 1. Try Gemini Cloud first
        gemini_res = cls._gemini_generate(prompt=prompt, base64_image=base64_image)
        if gemini_res and gemini_res.get('status') == 'success':
            return {
                'status': 'success',
                'model': gemini_res.get('model'),
                'diagnosis': gemini_res.get('text')
            }

        # 2. Local Ollama fallback
        raw_b64 = base64_image
        if ',' in raw_b64:
            raw_b64 = raw_b64.split(',', 1)[1]

        try:
            res = requests.post(
                f"{OLLAMA_BASE_URL}/api/generate",
                json={
                    'model': DEFAULT_MODEL,
                    'prompt': prompt,
                    'images': [raw_b64.strip()],
                    'stream': False,
                    'options': {
                        'temperature': 0.4,
                        'num_predict': 350
                    }
                },
                timeout=180
            )

            if res.status_code == 200:
                diagnosis = res.json().get('response', '').strip()
                return {
                    'status': 'success',
                    'model': DEFAULT_MODEL,
                    'diagnosis': diagnosis
                }
            return {
                'status': 'error',
                'message': f"Ollama returned HTTP {res.status_code}: {res.text}"
            }

        except Exception as e:
            err_msg = f"Vision analysis failed: {str(e)}."
            if not getattr(Config, 'GEMINI_API_KEY', ''):
                err_msg += " (Tip: set GEMINI_API_KEY in cloud environment variables for instant free cloud vision diagnosis)."
            return {'status': 'error', 'message': err_msg}

