# app.py (모든 기능 통합 최종 버전)
import streamlit as st
import httpx
from datetime import datetime
import time
import random

# --- 1. 세션 상태(Session State) 초기화 ---
# 앱의 현재 상태를 기억하기 위한 변수들을 설정합니다.
if 'view' not in st.session_state:
    st.session_state.view = 'initial'  # 'initial', 'recommendations', 'conversation', 'practice_selection', 'practice_conversation'
if 'recommendations' not in st.session_state:
    st.session_state.recommendations = []
if 'category' not in st.session_state:
    st.session_state.category = ""
if 'previous_sentence' not in st.session_state:
    st.session_state.previous_sentence = ""
if 'show_favorites' not in st.session_state:
    st.session_state.show_favorites = False
if 'favorites_list' not in st.session_state:
    st.session_state.favorites_list = {}
# --- 말하기 연습용 세션 상태 ---
if 'practice_category' not in st.session_state:
    st.session_state.practice_category = ""
if 'practice_history' not in st.session_state:
    st.session_state.practice_history = []
if 'practice_turn_data' not in st.session_state:
    st.session_state.practice_turn_data = None
if 'shuffled_options' not in st.session_state:
    st.session_state.shuffled_options = None

# --- 2. API 호출 함수들 ---
def get_recommendations_from_backend(manual_category, keywords, lat=None, lon=None, previous_sentence="", opponent_dialogue=""):
    backend_url = "http://127.0.0.1:8000/recommendations"
    params = {"manual_category": manual_category or "", "keywords": keywords or "", "previous_sentence": previous_sentence or "", "opponent_dialogue": opponent_dialogue or ""}
    if lat is not None and lon is not None: params["lat"], params["lon"] = lat, lon
    try:
        with st.spinner("AI가 상황에 맞는 문장을 생각하고 있습니다..."):
            response = httpx.get(backend_url, params=params, timeout=60)
            response.raise_for_status()
            return response.json()
    except Exception as e:
        st.error(f"오류가 발생했습니다: {e}")
        return None

def get_practice_quiz_from_backend(category, history):
    backend_url = "http://127.0.0.1:8000/practice/quiz"
    payload = {"category": category, "conversation_history": history}
    try:
        with st.spinner("AI가 다음 대사를 생각하고 있습니다..."):
            response = httpx.post(backend_url, json=payload, timeout=60)
            response.raise_for_status()
            return response.json()
    except Exception as e:
        st.error(f"오류가 발생했습니다: {e}")
        return None
        
def get_favorites_from_backend():
    try:
        response = httpx.get("http://127.0.0.1:8000/favorites")
        response.raise_for_status()
        st.session_state.favorites_list = response.json()
    except Exception as e: st.error(f"즐겨찾기 목록을 불러오는 데 실패했습니다: {e}")

def add_favorite_to_backend(sentence, category):
    try:
        httpx.post("http://127.0.0.1:8000/favorites", json={"sentence": sentence, "category": category})
        st.toast(f'"{sentence}" 문장을 즐겨찾기에 추가했습니다! ✅')
        get_favorites_from_backend()
    except Exception as e: st.error(f"즐겨찾기 추가에 실패했습니다: {e}")

def delete_favorite_from_backend(favorite_id):
    try:
        httpx.delete(f"http://127.0.0.1:8000/favorites/{favorite_id}")
        st.toast("즐겨찾기에서 삭제했습니다.")
        get_favorites_from_backend()
    except Exception as e: st.error(f"즐겨찾기 삭제에 실패했습니다: {e}")

def update_favorites_order_in_backend(ordered_ids):
    try:
        httpx.put("http://127.0.0.1:8000/favorites/order", json={"ordered_ids": ordered_ids})
        st.toast("순서가 저장되었습니다.")
    except Exception as e: st.error(f"순서 저장에 실패했습니다: {e}")

def reset_all():
    keys_to_reset = ['view', 'recommendations', 'category', 'previous_sentence', 'practice_category', 'practice_history', 'practice_turn_data', 'shuffled_options']
    for key in keys_to_reset:
        if key in st.session_state:
            del st.session_state[key]

# --- 3. 메인 UI 렌더링 ---
st.set_page_config(layout="centered")

# 상단 헤더
col1, col2, col3 = st.columns([1, 2, 1])
with col1: st.button("로고", use_container_width=True, disabled=True)
with col3: st.button("긴급호출", use_container_width=True, type="primary")

# --- 4. 화면 상태에 따른 분기 처리 ---

# [화면 1] 말하기 연습 - 장소 선택
if st.session_state.view == 'practice_selection':
    st.header("🗣️ 말하기 연습")
    st.subheader("연습하고 싶은 상황을 선택해보세요!")
    practice_locations = ["병원", "식당", "학교", "마트", "교통", "은행"]
    cols = st.columns(3)
    for i, location in enumerate(practice_locations):
        if cols[i % 3].button(location, key=f"prac_loc_{location}", use_container_width=True):
            st.session_state.practice_category = location
            st.session_state.practice_history = []
            data = get_practice_quiz_from_backend(location, [])
            if data:
                st.session_state.practice_turn_data = data
                st.session_state.shuffled_options = None
                st.session_state.view = 'practice_conversation'
                st.rerun()
    if st.button("메인으로 돌아가기", type="secondary"):
        reset_all()
        st.rerun()

# [화면 2] 말하기 연습 - 대화 진행 (퀴즈)
elif st.session_state.view == 'practice_conversation':
    category = st.session_state.practice_category
    turn_data = st.session_state.practice_turn_data
    col1, col2 = st.columns([2,1])
    col1.header(f"🗣️ 말하기 연습 ({category})")
    if col2.button("연습 끝내기", type="secondary", use_container_width=True):
        reset_all()
        st.rerun()
    if st.session_state.practice_history:
        for turn in st.session_state.practice_history:
            if turn['speaker'] == '나': st.info(f"**나:** {turn['message']}")
            else: st.success(f"**상대방:** {turn['message']}")
        st.markdown("---")
    if turn_data:
        st.success(f"**상대방:** {turn_data['opponent_dialogue']}")
        st.markdown("---")
        st.write("어떻게 대답할까요?")
        if not st.session_state.shuffled_options:
            options = turn_data['user_replies']
            random.shuffle(options)
            st.session_state.shuffled_options = options
        for reply in st.session_state.shuffled_options:
            if st.button(reply['text'], use_container_width=True, key=f"prac_ans_{reply['text']}"):
                placeholder = st.empty()
                with placeholder.container():
                    st.info(f"따라 말해 보세요!: \"{reply['text']}\"")
                    time.sleep(5)
                    if reply['is_correct']: st.success("✨ 대단해요!")
                    else: st.warning("🤔 어색한 표현이에요. 다른 답을 골라볼까요?")
                    time.sleep(5)
                placeholder.empty()
                if reply['is_correct']:
                    st.session_state.practice_history.append({'speaker': '상대방', 'message': turn_data['opponent_dialogue']})
                    st.session_state.practice_history.append({'speaker': '나', 'message': reply['text']})
                    next_turn_data = get_practice_quiz_from_backend(category, st.session_state.practice_history)
                    if next_turn_data:
                        st.session_state.practice_turn_data = next_turn_data
                        st.session_state.shuffled_options = None
                        st.rerun()
                else:
                    st.session_state.shuffled_options = None
                    st.rerun()

# === 여기가 수정된 부분입니다! (메인 기능 UI 복원) ===
# [화면 3] 일반 대화 기능 (초기, 추천, 대화 이어가기)
else:
    col1, col2 = st.columns(2)
    col1.metric("현재 시간", datetime.now().strftime("%p %I:%M"))
    col2.metric("위치", st.session_state.get('category', '알 수 없음'))
    col1, col2, col3 = st.columns([0.7, 0.15, 0.15])
    col1.text_input("문장 직접 입력창", placeholder="직접 문장을 입력하여 발화할 수 있습니다.", label_visibility="collapsed")
    col2.button("⭐", help="즐겨찾기에서 찾기")
    col3.button("🗣️", help="발화하기")
    st.markdown("---")

    # Case 3-1: 추천 문장 표시
    if st.session_state.view == 'recommendations':
        st.subheader("추천 문장")
        if st.session_state.recommendations:
            for sentence in st.session_state.recommendations:
                col_sent, col_fav = st.columns([0.85, 0.15])
                with col_sent:
                    if st.button(sentence['text'], use_container_width=True, key=f"rec_{sentence['id']}"):
                        st.session_state.previous_sentence = sentence['text']
                        st.session_state.view = 'conversation'
                        st.rerun()
                with col_fav:
                    if st.button("⭐", key=f"fav_{sentence['id']}", help="즐겨찾기에 추가"):
                        add_favorite_to_backend(sentence['text'], st.session_state.category)
        else:
            st.warning("추천 문장을 불러오지 못했습니다.")
        if st.button("새로운 대화 시작하기", type="secondary"):
            reset_all()
            st.rerun()

    # Case 3-2: 대화 이어가기
    elif st.session_state.view == 'conversation':
        st.header("다음 대화 이어가기")
        st.write(f"**내가 한 말:** \"{st.session_state.previous_sentence}\"")
        opponent_dialogue = st.text_area("상대방이 한 말을 입력하세요 (선택 사항):", key="opponent_dialogue")
        next_keywords = st.text_input("다음에 할 말의 키워드를 입력하세요:", key="next_keywords")
        if st.button("다음 문장 추천받기", use_container_width=True):
            data = get_recommendations_from_backend(st.session_state.category, next_keywords, previous_sentence=st.session_state.previous_sentence, opponent_dialogue=opponent_dialogue)
            if data:
                st.session_state.view = 'recommendations'
                st.session_state.recommendations = data['recommended_sentences']
                st.session_state.previous_sentence = ""
                st.rerun()
        if st.button("대화 끝내기", type="secondary"):
            reset_all()
            st.rerun()

    # Case 3-3: 초기 화면
    else:
        st.subheader("현재 상황을 설명해주세요!")
        keywords = st.text_input("상황 입력", placeholder="장소, 현재 상태를 간단하게 입력", label_visibility="collapsed")
        locations = ["병원", "식당", "학교", "마트", "교통", "은행", "약국", "기타"]
        cols = st.columns(4)
        for i, location in enumerate(locations):
            if cols[i % 4].button(location, key=f"loc_{location}", use_container_width=True):
                category_to_send = "일상" if location == "기타" else location
                data = get_recommendations_from_backend(category_to_send, keywords)
                if data:
                    st.session_state.view = 'recommendations'
                    st.session_state.recommendations = data['recommended_sentences']
                    st.session_state.category = data['category']
                    st.rerun()

    # 하단 기능 버튼
    st.markdown("---")
    col1, col2 = st.columns(2)
    if col1.button("⭐ 즐겨찾기", use_container_width=True):
        st.session_state.show_favorites = not st.session_state.show_favorites
        if st.session_state.show_favorites: get_favorites_from_backend()
    
    if col2.button("🗣️ 말하기 연습", use_container_width=True):
        reset_all()
        st.session_state.view = 'practice_selection'
        st.rerun()

    if st.session_state.show_favorites:
        st.subheader("⭐ 즐겨찾기 목록")
        if st.session_state.favorites_list:
            for category, fav_list in st.session_state.favorites_list.items():
                with st.expander(f"**{category}** ({len(fav_list)}개)"):
                    for fav in fav_list:
                        st.info(fav['sentence'])
        else:
            st.write("아직 즐겨찾기한 문장이 없습니다.")