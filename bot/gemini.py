import asyncio
import os
import tempfile
from typing import Any, Dict, List, Optional

import google.generativeai as genai
from google.api_core.exceptions import FailedPrecondition, GoogleAPICallError


class GeminiClient:
    def __init__(self, api_key: str, model: str = "gemini-1.5-flash", system_prompt: str | None = None) -> None:
        genai.configure(api_key=api_key)
        self.model_name = model
        self.system_prompt = system_prompt or ""

    def start_chat(self, history: Optional[List[Dict[str, Any]]] = None) -> Any:
        model = genai.GenerativeModel(self.model_name, system_instruction=self.system_prompt or None)
        hist = []
        # system prompt is passed via system_instruction; no need to add a 'system' role turn here
        if history:
            hist.extend(history)
        return model.start_chat(history=hist)

    def _upload_file_from_bytes(self, image_bytes: bytes, mime_type: str) -> Any:
        # Writes to a temp file to use the official upload flow
        tmp = tempfile.NamedTemporaryFile(delete=False)
        try:
            tmp.write(image_bytes)
            tmp.flush()
            tmp.close()
            return genai.upload_file(path=tmp.name, mime_type=mime_type)
        finally:
            try:
                os.unlink(tmp.name)
            except Exception:
                pass

    async def generate_with_image_and_text(
        self,
        image_bytes: bytes,
        mime_type: str,
        text: str,
    ) -> tuple[str, Any]:
        model = genai.GenerativeModel(self.model_name)
        # google-generativeai is sync; run in thread
        def _call() -> Any:
            uploaded = self._upload_file_from_bytes(image_bytes, mime_type)
            return model.generate_content([uploaded, text])

        # simple retries with backoff
        attempt = 0
        while True:
            try:
                resp = await asyncio.to_thread(_call)
                return (resp.text or "", resp)
            except FailedPrecondition as e:
                raise RuntimeError("gemini_region_blocked") from e
            except GoogleAPICallError as e:
                attempt += 1
                if attempt >= 2:
                    raise RuntimeError("gemini_api_error") from e
                await asyncio.sleep(0.8 * attempt)
            except Exception as e:
                attempt += 1
                if attempt >= 2:
                    raise RuntimeError("gemini_unknown_error") from e
                await asyncio.sleep(0.8 * attempt)

    def build_history_with_image(self, image_bytes: bytes, mime_type: str, text: str) -> List[Dict[str, Any]]:
        # Upload image and return a history turn referencing the uploaded file
        uploaded = self._upload_file_from_bytes(image_bytes, mime_type)
        return [
            {
                "role": "user",
                "parts": [uploaded, text],
            }
        ]

    async def start_chat_and_answer_first(self, image_bytes: bytes, mime_type: str, text: str) -> tuple[Any, str]:
        # Create chat with system_instruction applied and send first multimodal message in the chat
        history = self.build_history_with_image(image_bytes, mime_type, text)
        chat = self.start_chat(history=[])

        def _call() -> Any:
            uploaded = self._upload_file_from_bytes(image_bytes, mime_type)
            return chat.send_message([uploaded, text])

        attempt = 0
        while True:
            try:
                resp = await asyncio.to_thread(_call)
                return chat, (getattr(resp, "text", "") or "")
            except FailedPrecondition as e:
                raise RuntimeError("gemini_region_blocked") from e
            except GoogleAPICallError as e:
                attempt += 1
                if attempt >= 2:
                    raise RuntimeError("gemini_api_error") from e
                await asyncio.sleep(0.8 * attempt)
            except Exception as e:
                attempt += 1
                if attempt >= 2:
                    raise RuntimeError("gemini_unknown_error") from e
                await asyncio.sleep(0.8 * attempt)

    async def send_chat_message(self, chat: Any, text: str) -> str:
        def _call() -> Any:
            return chat.send_message(text)

        attempt = 0
        while True:
            try:
                resp = await asyncio.to_thread(_call)
                return getattr(resp, "text", "") or ""
            except FailedPrecondition as e:
                raise RuntimeError("gemini_region_blocked") from e
            except GoogleAPICallError as e:
                attempt += 1
                if attempt >= 2:
                    raise RuntimeError("gemini_api_error") from e
                await asyncio.sleep(0.8 * attempt)
            except Exception as e:
                attempt += 1
                if attempt >= 2:
                    raise RuntimeError("gemini_unknown_error") from e
                await asyncio.sleep(0.8 * attempt)


