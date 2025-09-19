import httpx
from fastapi import UploadFile
from config import settings

async def transcribe_audio(file: UploadFile) -> str:
    """
    OpenAI Whisper API를 사용하여 음성 파일을 텍스트로 변환합니다.
    """
    print(f"🔍 STT 디버깅: 파일명={file.filename}, Content-Type={file.content_type}, 크기={file.size}")
    
    api_url = "https://api.openai.com/v1/audio/transcriptions"
    headers = {"Authorization": f"Bearer {settings.OPENAI_API_KEY}"}
    
    # 파일 내용 읽기
    file_content = await file.read()
    print(f"🔍 파일 내용 크기: {len(file_content)} bytes")
    
    files = {
        "file": (file.filename, file_content, file.content_type),
    }
    data = {"model": "whisper-1",
            "language": "ko"}  # 한국어 설정

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(api_url, headers=headers, files=files, data=data)
            print(f"🔍 Whisper API 응답 상태: {response.status_code}")
            response.raise_for_status()
            result = response.json()["text"]
            print(f"🔍 STT 결과: {result}")
            return result
    except Exception as e:
        print(f"❌ STT 오류: {e}")
        raise e