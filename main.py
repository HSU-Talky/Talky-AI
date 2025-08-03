import json
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import List, Optional
import httpx

from config import settings

# FastAPI 앱 및 모델 정의
app = FastAPI(
    title="Talky-AI Service",
    description="백엔드로부터 전달받은 컨텍스트를 기반으로 문장을 생성하는 AI 서비스",
    version="2025.08.04",  # 프롬프트 수정
)

# /recommendations API를 위한 모델들
class RecommendationRequest(BaseModel):
    keywords: List[str] = Field(..., description="장소, 상황 등을 나타내는 키워드 목록", example=["병원", "두통"])
    context: Optional[str] = Field(None, description="사용자가 직접 입력한 현재 상황 설명", example="머리가 아파서 왔어요") # null 허용
    conversation: Optional[List[str]] = Field(None, description="최근 대화 기록 (사용자, 상대방 포함)", example=["안녕하세요, 어떻게 오셨어요?", "진료받으러 왔습니다."]) # null 허용
    favorites: Optional[List[str]] = Field(default_factory=list, description="사용자가 즐겨찾기한 문장 목록", example=["이거 주세요", "감사합니다"]) # 없어도 빈 리스트로 처리될 수 있게 함

class Sentence(BaseModel):
    id: int
    text: str

class RecommendationResponse(BaseModel):
    category: str
    recommended_sentences: List[Sentence]


# AI 로직 함수 

async def find_relevant_favorites(request: RecommendationRequest) -> List[str]:
    """현재 상황과 직접적으로 관련된 즐겨찾기 문장을 찾아냅니다."""
    if not request.favorites:
        return []

    # 대화의 가장 마지막 내용
    last_dialogue = request.conversation[0] if request.conversation else "없음"
    
    prompt = f"""
        당신은 문장 관련성 분석 전문가입니다.
        주어진 현재 상황과 가장 직접적으로 관련이 높고, 바로 사용해도 어색하지 않은 문장을 즐겨찾기 목록에서 모두 골라주세요.

        [현재 상황]
        - 주요 키워드: {", ".join(request.keywords)}
        - 상세 설명: {request.context or "없음"}
        - 방금 들은 말: "{last_dialogue}"

        [즐겨찾기 목록]
        {", ".join(request.favorites)}

        [출력 형식]
        - 반드시 "relevant_favorites" 라는 키를 가진 JSON 객체여야 합니다.
        - 값은 당신이 고른 문장들이 담긴 문자열 배열입니다. 관련 있는 문장이 없으면 빈 배열 `[]`을 반환하세요.
    """
    api_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash-latest:generateContent?key={settings.GOOGLE_API_KEY}"
    payload = {"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"responseMimeType": "application/json", "temperature": 0.2}}
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(api_url, json=payload, timeout=20)
            response.raise_for_status()
            ai_response = response.json()
            text_content = ai_response["candidates"][0]["content"]["parts"][0]["text"]
            return json.loads(text_content).get("relevant_favorites", [])
    except Exception:
        return [] # 오류 발생 시 빈 리스트 반환

async def generate_additional_sentences(request: RecommendationRequest, existing_sentences: List[str]) -> List[str]:
    """이미 찾은 문장을 제외하고, 추가적인 추천 문장을 생성합니다."""
    
    keywords_str = ", ".join(request.keywords)
    conversation_str = "\n".join([f"- {line}" for line in (request.conversation or [])])
    favorites_str = ", ".join(request.favorites or [])
    context_str = request.context or "없음"
    existing_sentences_str = ", ".join(existing_sentences) if existing_sentences else "없음"

    prompt = f"""
        당신은 AAC 사용자를 위한 대화 문장 생성 AI입니다.
        주어진 모든 정보를 종합하여, 사용자의 입장에서 다음에 할 가장 자연스러운 문장을 생성해야 합니다.
        단, 이미 찾은 문장 목록에 있는 것과 똑같거나 매우 유사한 문장은 생성하면 안 됩니다.

        ### 입력 정보 ###
        1. **주요 키워드 (장소, 상황):** {keywords_str}
        2. **사용자가 직접 입력한 상황:** "{context_str}"
        3. **최근 대화 기록 (가장 최근 대화가 맨 위에 있음):**
           {conversation_str if conversation_str else "(대화 시작 전)"}
        4. **사용자의 즐겨찾기 문장 (평소 말투 힌트):** {favorites_str if favorites_str else "없음"}
        5. **이미 찾은 문장 (중복 생성 금지):** {existing_sentences_str}

        ### 생성 규칙 ###
        - 총 4개의 추천 문장이 필요합니다. [이미 찾은 문장]의 개수를 제외하고, 나머지 개수만큼만 새롭게 생성해주세요.
        - 예를 들어, 이미 찾은 문장이 1개라면 3개를, 2개라면 2개를 새로 생성하면 됩니다.
        - 생성된 문장은 반드시 사용자의 입장에서 말하는 것이어야 합니다.
        - 답변은 "generated_sentences" 키를 가진 JSON 객체여야 하며, 값은 생성된 문장들이 담긴 문자열 배열입니다.
    """
    
    api_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash-latest:generateContent?key={settings.GOOGLE_API_KEY}"
    payload = {"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"responseMimeType": "application/json", "temperature": 0.8}}
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(api_url, json=payload, timeout=30)
            response.raise_for_status()
            ai_response = response.json()
            text_content = ai_response["candidates"][0]["content"]["parts"][0]["text"]
            return json.loads(text_content).get("generated_sentences", [])
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI 서비스 처리 중 오류가 발생했습니다: {e}")


# API 엔드포인트

@app.post("/recommendations", response_model=RecommendationResponse, summary="AI 실시간 문장 추천 (컨텍스트 기반)")
async def get_recommendations(request: RecommendationRequest):
    """메인 백엔드로부터 전달받은 풍부한 컨텍스트로 AI 추천 문장을 생성합니다."""
    
    relevant_favorites = await find_relevant_favorites(request)
    
    # 나머지 필요한 문장들을 AI에게 추가로 생성해달라고 요청.
    additional_sentences = []
    if len(relevant_favorites) < 4:
        additional_sentences = await generate_additional_sentences(request, relevant_favorites)
    
    # 두 결과를 합쳐서 최종 추천 목록을 만듭니다.
    final_sentence_texts = relevant_favorites + additional_sentences
    
    if not final_sentence_texts:
        raise HTTPException(status_code=500, detail="AI가 문장을 생성하지 못했습니다.")
        
    final_sentences = [Sentence(id=i + 1, text=text) for i, text in enumerate(final_sentence_texts)]
    main_category = request.keywords[0] if request.keywords else "일상"
    
    return RecommendationResponse(
        category=main_category,
        recommended_sentences=final_sentences
    )