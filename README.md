#AAC 문장 추천 앱 - 백엔드 서버

## 기능
-   위치(수동/ 위도 / QR) 기반 상황 인지
-   AI를 이용한 실시간 문장 생성 및 추천
-   대화의 맥락을 이해하는 연속적인 문장 추천

## 설치 및 실행 방법
1.  **가상환경 생성 및 활성화:**
    ```bash
    python3 -m venv .venv
    source .venv/bin/activate
    ```

2.  **필요 라이브러리 설치:**
    ```bash
    pip install -r requirements.txt
    ```

3.  **.env 파일 생성:**
    `.env.example` 파일을 복사하여 `.env` 파일을 만들고, 각자의 API 키와 DB 정보를 입력해주세요.

4.  **서버 실행:**
    ```bash
    uvicorn main:app --reload
    ```
