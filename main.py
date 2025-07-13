import json
import asyncio
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel
from typing import List, Optional, Dict
import httpx

# DB 관련 코드는 모두 제거하고, 새로운 config만 import합니다.
from config import settings

# --- 1. FastAPI 앱 및 모델 정의 ---
app = FastAPI(
    title="Talky-AI Service",
    description="위치 분석, 문장 생성, 대화 연습 등 AI 관련 기능을 전문적으로 처리하는 마이크로서비스입니다.",
    version="2.0.0"
)

# /recommendations 용 모델
class Sentence(BaseModel): id: int; text: str
class RecommendationResponse(BaseModel): category: str; recommended_sentences: List[Sentence]

# /practice/quiz 용 모델
class PracticeReply(BaseModel): text: str; is_correct: bool
class PracticeTurnResponse(BaseModel): opponent_dialogue: str; user_replies: List[PracticeReply]
class PracticeTurnRequest(BaseModel): category: str; conversation_history: List[Dict[str, str]]

# --- 2. 핵심 로직 함수들 ---
async def get_location_category(lat: float, lon: float) -> Optional[str]:
    """카카오맵 API로 좌표 기반 장소 카테고리를 분석합니다."""
    print(f"카카오맵 API로 좌표 ({lat}, {lon})의 주변 장소를 검색합니다...")
    category_map = {"HP8": "병원", "FD6": "식당", "CS2": "편의점", "SW8": "지하철역", "CE7": "카페", "SC4": "학교", "CT1": "문화시설"}
    api_url = "https://dapi.kakao.com/v2/local/search/category.json"
    headers = {"Authorization": f"KakaoAK {settings.KAKAO_API_KEY}"}
    async def search_task(code: str, client: httpx.AsyncClient):
        params = {"category_group_code": code, "x": lon, "y": lat, "radius": 200, "size": 1, "sort": "distance"}
        try:
            response = await client.get(api_url, headers=headers, params=params)
            response.raise_for_status()
            result = response.json()
            if result.get("documents"):
                doc = result["documents"][0]
                return {"category": category_map[code], "distance": int(doc.get("distance", 999))}
        except Exception as e:
            print(f"카카오맵 API 호출 중 오류: {e}")
            return None
    async with httpx.AsyncClient() as client:
        tasks = [search_task(code, client) for code in category_map.keys()]
        results = await asyncio.gather(*tasks)
    found_places = [place for place in results if place]
    if not found_places: return None
    closest_place = min(found_places, key=lambda x: x['distance'])
    print(f"가장 가까운 장소는 '{closest_place['category']}'입니다 (거리: {closest_place['distance']}m).")
    return closest_place['category']

async def generate_ai_sentences(category: str, keywords: Optional[str], previous_sentence: Optional[str], opponent_dialogue: Optional[str]) -> List[str]:
    """Gemini AI를 호출하여 상황에 맞는 문장을 생성합니다."""
    if previous_sentence:
        prompt = f"""당신은 AAC 사용자를 위한 대화 전문가입니다. 당신은 항상 사용자(손님, 환자 등)의 입장에서 말해야 합니다. 다음 대화의 맥락을 파악하고, 사용자의 입장에서 자연스럽게 이어질 다음 문장 5개를 생성해주세요.
        [현재 장소]: {category}, [사용자가 방금 한 말]: "{previous_sentence}", [상대방이 방금 한 말]: "{opponent_dialogue or "(입력 없음)"}", [사용자가 다음에 하고 싶은 말의 키워드]: {keywords or "없음"}
        [출력 형식] "generated_sentences" 키를 가진 JSON 객체로, 값은 문자열 배열이어야 합니다."""
    else:
        prompt = f"""당신은 AAC 앱의 문장 생성 전문가입니다. 당신은 항상 사용자(손님, 환자 등)의 입장에서 대화를 시작하는 문장을 생성해야 합니다. "무엇을 도와드릴까요?"가 아닌, "주문할게요." 와 같은 사용자가 먼저 할 법한 요청이나 질문 5개를 생성해주세요.
        [현재 장소]: {category}, [키워드]: {keywords or "없음"}
        [출력 형식] "generated_sentences" 키를 가진 JSON 객체로, 값은 문자열 배열이어야 합니다."""
    api_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash-latest:generateContent?key={settings.GOOGLE_API_KEY}"
    payload = {"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"responseMimeType": "application/json", "temperature": 0.7}}
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(api_url, json=payload, timeout=30)
            response.raise_for_status()
            ai_response = response.json()
            text_content = ai_response["candidates"][0]["content"]["parts"][0]["text"]
            return json.loads(text_content).get("generated_sentences", [])
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI 서비스 처리 중 오류가 발생했습니다: {e}")

async def generate_practice_quiz(category: str, history: List[Dict[str, str]]) -> Dict:
    """AI에게 역할극 퀴즈(정답/오답 포함)를 생성하도록 요청합니다."""
    history_str = "\n".join([f"{turn['speaker']}: {turn['message']}" for turn in history])
    prompt = f"""
        당신은 AAC 사용자를 위한 역할극 퀴즈 출제자입니다. 당신의 역할은 주어진 [현재 장소]의 점원, 의사 등입니다.
        주어진 [대화 기록]을 바탕으로, 당신의 다음 대사 한 문장과, 그에 대한 사용자의 답변 선택지 3개를 생성해주세요.
        [규칙] 답변 선택지 3개 중, 1~2개는 정답, 나머지는 오답이어야 합니다.
        [출력 형식] "opponent_dialogue"(string)와 "user_replies"(array of objects with "text" and "is_correct" keys) 키를 가진 JSON 객체여야 합니다.
    """
    api_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash-latest:generateContent?key={settings.GOOGLE_API_KEY}"
    payload = {"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"responseMimeType": "application/json", "temperature": 0.9}}
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(api_url, json=payload, timeout=30)
            response.raise_for_status()
            ai_response = response.json()
            text_content = ai_response["candidates"][0]["content"]["parts"][0]["text"]
            return json.loads(text_content)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI 역할극 생성 중 오류 발생: {e}")


# --- 3. API 엔드포인트들 ---

@app.get("/recommendations", response_model=RecommendationResponse, summary="AI 실시간 문장 추천")
async def get_recommendations(
    # 정보는 Spring으로부터 전달받음.
    lat: Optional[float] = Query(None), lon: Optional[float] = Query(None),
    manual_category: Optional[str] = Query(None),
    keywords: Optional[str] = Query(None),
    previous_sentence: Optional[str] = Query(None),
    opponent_dialogue: Optional[str] = Query(None)
):
    """메인 백엔드로부터 전달받은 상황 정보로 AI 추천 문장을 생성합니다."""
    category = None
    if manual_category:
        category = manual_category
    elif lat is not None and lon is not None:
        category = await get_location_category(lat, lon)
    
    if not category:
        if previous_sentence: category = "일상 대화"
        else: raise HTTPException(status_code=400, detail="위치 정보(lat/lon) 또는 장소(manual_category) 중 하나는 반드시 필요합니다.")

    generated_sentences = await generate_ai_sentences(category, keywords, previous_sentence, opponent_dialogue)
    if not generated_sentences:
        raise HTTPException(status_code=500, detail="AI가 문장을 생성하지 못했습니다.")
    final_sentences = [Sentence(id=i + 1, text=text) for i, text in enumerate(generated_sentences)]
    return RecommendationResponse(category=category, recommended_sentences=final_sentences)

@app.post("/practice/quiz", response_model=PracticeTurnResponse, summary="AI 말하기 연습 퀴즈 받기")
async def get_practice_quiz(request: PracticeTurnRequest):
    """'말하기 연습'의 다음 턴에 필요한 상대방 대사와 선택지를 생성합니다."""
    result = await generate_practice_quiz(request.category, request.conversation_history)
    return PracticeTurnResponse(
        opponent_dialogue=result.get("opponent_dialogue", "다음 할 말을 생각하고 있어요..."),
        user_replies=result.get("user_replies", [])
    )
