import json
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import List, Optional
import httpx

from config import settings

# --- 1. FastAPI 앱 및 모델 정의 ---
app = FastAPI(
    title="Talky-AI Service",
    description="백엔드로부터 전달받은 컨텍스트를 기반으로 문장을 생성하는 AI 서비스",
    version="5.0.0" # 핵심 기능 집중 버전
)

# /recommendations API를 위한 모델들
class RecommendationRequest(BaseModel):
    keywords: List[str] = Field(..., description="장소, 상황 등을 나타내는 키워드 목록", example=["병원", "두통"])
    context: str = Field(..., description="사용자가 직접 입력한 현재 상황 설명", example="머리가 아파서 왔어요")
    conversation: List[str] = Field(..., description="최근 대화 기록 (사용자, 상대방 포함)", example=["안녕하세요, 어떻게 오셨어요?", "진료받으러 왔습니다."])
    favorites: List[str] = Field(..., description="사용자가 즐겨찾기한 문장 목록", example=["이거 주세요", "감사합니다"])

class Sentence(BaseModel):
    id: int
    text: str

class RecommendationResponse(BaseModel):
    category: str
    recommended_sentences: List[Sentence]


# --- 2. 핵심 AI 로직 함수 ---

async def generate_ai_sentences_with_rich_context(request: RecommendationRequest) -> List[str]:
    """컨텍스트를 기반으로 Gemini AI를 호출하여 문장을 생성합니다."""
    
    # 프롬프트에 전달할 정보들을 문자열로 변환
    keywords_str = ", ".join(request.keywords)
    conversation_str = "\n".join([f"- {line}" for line in request.conversation])
    favorites_str = ", ".join(request.favorites)

    print(f"AI 문장 생성 요청 수신: keywords='{keywords_str}'")

    prompt = f"""
        당신은 AAC 사용자를 위한 대화 문장 생성 AI입니다.
        당신은 항상 사용자(손님, 환자 등)의 입장에서, 주어진 모든 정보를 종합적으로 고려하여 가장 적절한 다음 문장 5개를 생성해야 합니다.

        [사용자 정보]
        - 주요 키워드(장소, 상황): {keywords_str}
        - 사용자가 직접 입력한 상황: "{request.context}"
        - 사용자가 즐겨찾기한 문장들 (사용자의 평소 말투 힌트): {favorites_str if request.favorites else "없음"}

        [최근 대화 기록]
        {conversation_str if request.conversation else "(대화 시작 전)"}

        [생성 규칙]
        1. 위 모든 정보를 바탕으로, 대화의 흐름을 자연스럽게 이어갈 다음 문장을 생성하세요.
        2. 사용자가 직접 입력한 상황(context)을 최우선으로 고려해야 합니다.
        3. 즐겨찾기 목록은 사용자의 평소 말투를 파악하는 힌트로만 사용하세요.
        
        [출력 형식]
        당신의 답변은 반드시 "generated_sentences" 라는 단 하나의 키를 가진 JSON 객체여야 하며, 값은 생성된 문장 4개가 담긴 문자열 배열입니다.
    """
    
    api_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash-latest:generateContent?key={settings.GOOGLE_API_KEY}"
    payload = {"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"responseMimeType": "application/json", "temperature": 0.7}}
    # temperate로 AI의 대답 깊이를 설정
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(api_url, json=payload, timeout=30)
            response.raise_for_status()
            ai_response = response.json()
            text_content = ai_response["candidates"][0]["content"]["parts"][0]["text"]
            return json.loads(text_content).get("generated_sentences", [])
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI 서비스 처리 중 오류가 발생했습니다: {e}")


# --- 3. API 엔드포인트 ---

@app.post("/recommendations", response_model=RecommendationResponse, summary="AI 실시간 문장 추천 (컨텍스트 기반)")
async def get_recommendations(request: RecommendationRequest):
    """메인 백엔드로부터 전달받은 풍부한 컨텍스트로 AI 추천 문장을 생성합니다."""
    
    # AI 문장 생성 함수 호출
    generated_sentences = await generate_ai_sentences_with_rich_context(request)
    
    if not generated_sentences:
        raise HTTPException(status_code=500, detail="AI가 문장을 생성하지 못했습니다.")
        
    final_sentences = [Sentence(id=i + 1, text=text) for i, text in enumerate(generated_sentences)]
    # 문장에 번호를 붙여서 전달
    
    # 대표 카테고리는 keywords의 첫 번째 항목으로 설정
    main_category = request.keywords[0] if request.keywords else "일상"
    
    return RecommendationResponse(
        category=main_category,
        recommended_sentences=final_sentences
    )
