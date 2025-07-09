#테스트용 코드
import streamlit as st
import httpx
from datetime import datetime

# --- 1. 세션 상태(Session State) 초기화 ---
# 'view' 상태를 사용해 '초기 화면', '추천 화면', '대화 이어가기' 화면을 전환합니다.
if 'view' not in st.session_state:
    st.session_state.view = 'initial'  # 'initial', 'recommendations', 'conversation'
if 'recommendations' not in st.session_state:
    st.session_state.recommendations = []
if 'category' not in st.session_state:
    st.session_state.category = ""
if 'previous_sentence' not in st.session_state:
    st.session_state.previous_sentence = ""
if 'show_favorites' not in st.session_state:
    st.session_state.show_favorites = False
if 'favorites_list' not in st.session_state:
    st.session_state.favorites_list = []

# --- 2. API 호출 함수 ---
def get_recommendations_from_backend(manual_category, keywords, previous_sentence="", opponent_dialogue=""):
    """백엔드 API를 호출하여 추천 문장을 받아오는 함수"""
    backend_url = "http://127.0.0.1:8000/recommendations"
    params = {
        "manual_category": manual_category or "",
        "keywords": keywords or "",
        "previous_sentence": previous_sentence or "",
        "opponent_dialogue": opponent_dialogue or ""
    }
    try:
        with st.spinner("AI가 상황에 맞는 문장을 생각하고 있습니다..."):
            response = httpx.get(backend_url, params=params, timeout=60)
            response.raise_for_status()
            return response.json()
    except Exception as e:
        st.error(f"오류가 발생했습니다: {e}")
        return None

def get_favorites_from_backend():
    """백엔드에서 즐겨찾기 목록을 가져오는 함수"""
    try:
        response = httpx.get("http://127.0.0.1:8000/favorites")
        response.raise_for_status()
        st.session_state.favorites_list = response.json()
    except Exception as e:
        st.error(f"즐겨찾기 목록을 불러오는 데 실패했습니다: {e}")

def add_favorite_to_backend(sentence):
    """문장을 즐겨찾기에 추가합니다."""
    try:
        response = httpx.post("http://127.0.0.1:8000/favorites", json={"sentence": sentence})
        response.raise_for_status()
        st.toast(f'"{sentence}" 문장을 즐겨찾기에 추가했습니다! ✅')
        get_favorites_from_backend()
    except Exception as e:
        st.error(f"즐겨찾기 추가에 실패했습니다: {e}")

def delete_favorite_from_backend(favorite_id):
    """ID로 특정 즐겨찾기 문장을 삭제합니다."""
    try:
        response = httpx.delete(f"http://127.0.0.1:8000/favorites/{favorite_id}")
        response.raise_for_status()
        st.toast("즐겨찾기에서 삭제했습니다.")
        get_favorites_from_backend() # 목록 새로고침
    except Exception as e:
        st.error(f"즐겨찾기 삭제에 실패했습니다: {e}")

def update_favorites_order_in_backend(ordered_ids):
    """즐겨찾기 목록의 전체 순서를 업데이트합니다."""
    try:
        response = httpx.put("http://127.0.0.1:8000/favorites/order", json={"ordered_ids": ordered_ids})
        response.raise_for_status()
        st.toast("순서가 저장되었습니다.")
    except Exception as e:
        st.error(f"순서 저장에 실패했습니다: {e}")

def reset_all():
    """모든 대화 관련 세션 상태를 초기화합니다."""
    st.session_state.view = 'initial'
    st.session_state.recommendations = []
    st.session_state.category = ""
    st.session_state.previous_sentence = ""
    st.session_state.show_favorites = False

# --- 3. 화면 UI 구성 ---
st.set_page_config(layout="centered")

# --- 상단 헤더 ---
col1, col2, col3 = st.columns([1, 2, 1])
with col1:
    st.button("로고", use_container_width=True, disabled=True)
with col3:
    st.button("긴급호출", use_container_width=True, type="primary")

col1, col2 = st.columns(2)
col1.metric("현재 시간", datetime.now().strftime("%p %I:%M"))
col2.metric("위치", st.session_state.get('category', '알 수 없음'))

col1, col2, col3 = st.columns([0.7, 0.15, 0.15])
col1.text_input("문장 직접 입력창", placeholder="직접 문장을 입력하여 발화할 수 있습니다.", label_visibility="collapsed")
col2.button("⭐", help="즐겨찾기에서 찾기")
col3.button("🗣️", help="발화하기")

st.markdown("---")

# --- 4. 화면 상태에 따른 분기 처리 ---

# Case 1: 문장 추천을 받은 후 화면
if st.session_state.view == 'recommendations':
    st.subheader("추천 문장")

    # 추천 문장 목록 표시
    if st.session_state.recommendations:
        for sentence in st.session_state.recommendations:
            col_sent, col_fav = st.columns([0.85, 0.15])
            with col_sent:
                if st.button(sentence['text'], use_container_width=True, key=f"rec_{sentence['id']}"):
                    st.session_state.previous_sentence = sentence['text']
                    st.session_state.view = 'conversation' # '대화 이어가기' 상태로 전환
                    st.rerun()
            with col_fav:
                if st.button("⭐", key=f"fav_{sentence['id']}", help="즐겨찾기에 추가"):
                    add_favorite_to_backend(sentence['text'])
    else:
        st.warning("추천 문장을 불러오지 못했습니다.")

    # 새로고침 기능
    with st.expander("다른 문장 추천받기 (새로고침)"):
        refresh_keywords = st.text_input("새로운 키워드를 입력하여 다시 추천받을 수 있습니다:", key="refresh_keywords")
        if st.button("🔄 새로고침", key="refresh_button"):
            data = get_recommendations_from_backend(st.session_state.category, refresh_keywords)
            if data:
                st.session_state.recommendations = data['recommended_sentences']
                st.rerun()

    if st.button("새로운 대화 시작하기", type="secondary"):
        reset_all()
        st.rerun()

# Case 2: 대화 이어가기 화면
elif st.session_state.view == 'conversation':
    st.header("다음 대화 이어가기")
    st.write(f"**내가 한 말:** \"{st.session_state.previous_sentence}\"")
    
    opponent_dialogue = st.text_area("상대방이 한 말을 입력하세요 (선택 사항):", key="opponent_dialogue")
    next_keywords = st.text_input("다음에 할 말의 키워드를 입력하세요:", key="next_keywords")
    
    if st.button("다음 문장 추천받기", use_container_width=True):
        data = get_recommendations_from_backend(
            st.session_state.category,
            next_keywords,
            st.session_state.previous_sentence,
            opponent_dialogue
        )
        if data:
            st.session_state.view = 'recommendations'
            st.session_state.recommendations = data['recommended_sentences']
            st.session_state.previous_sentence = "" # 이전 문장 초기화
            st.rerun()
            
    if st.button("대화 끝내기", type="secondary"):
        reset_all()
        st.rerun()

# Case 3: 초기 화면
else:
    st.subheader("현재 상황을 설명해주세요!")
    
    keywords = st.text_input("상황 입력", placeholder="장소, 현재 상태를 간단하게 입력 (예: 식당, 주문)", label_visibility="collapsed")
    
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

st.markdown("---")

# --- 하단 기능 버튼 ---
col1, col2 = st.columns(2)
if col1.button("⭐ 즐겨찾기", use_container_width=True):
    st.session_state.show_favorites = not st.session_state.show_favorites
    if st.session_state.show_favorites:
        get_favorites_from_backend()

col2.button("🗣️ 말하기 연습", use_container_width=True)

# --- 즐겨찾기 목록 표시 ---
if st.session_state.show_favorites:
    st.subheader("⭐ 즐겨찾기 목록")
    if st.session_state.favorites_list:
        # 순서 변경 로직
        fav_list = st.session_state.favorites_list
        for i in range(len(fav_list)):
            col_num, col_text, col_up, col_down, col_del = st.columns([0.1, 0.6, 0.1, 0.1, 0.1])
            
            col_num.write(f"**{i+1}.**")
            col_text.write(fav_list[i]['sentence'])
            
            if col_up.button("▲", key=f"up_{i}", help="위로 이동"):
                if i > 0:
                    fav_list.insert(i-1, fav_list.pop(i))
                    ordered_ids = [fav['id'] for fav in fav_list]
                    update_favorites_order_in_backend(ordered_ids)
                    st.rerun()
            
            if col_down.button("▼", key=f"down_{i}", help="아래로 이동"):
                if i < len(fav_list) - 1:
                    fav_list.insert(i+1, fav_list.pop(i))
                    ordered_ids = [fav['id'] for fav in fav_list]
                    update_favorites_order_in_backend(ordered_ids)
                    st.rerun()

            if col_del.button("🗑️", key=f"del_{i}", help="삭제"):
                delete_favorite_from_backend(fav_list[i]['id'])
                st.rerun()
    else:
        st.write("아직 즐겨찾기한 문장이 없습니다.")
