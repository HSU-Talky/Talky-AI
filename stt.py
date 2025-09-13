import httpx
from fastapi import UploadFile
from config import settings

async def transcribe_audio(file: UploadFile) -> str:
    """
    OpenAI Whisper API를 사용하여 음성 파일을 텍스트로 변환합니다.
    """
    api_url = "https://api.openai.com/v1/audio/transcriptions"
    headers = {"Authorization": f"Bearer {settings.OPENAI_API_KEY}"}
    files = {
        "file": (file.filename, await file.read(), file.content_type),
    }
    data = {"model": "whisper-1",
            "language": "ko"}  # 한국어 설정

    async with httpx.AsyncClient() as client:
        response = await client.post(api_url, headers=headers, files=files, data=data)
        response.raise_for_status()
        return response.json()["text"]