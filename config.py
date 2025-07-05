# config.py (디버깅 강화 최종 버전)
from pydantic_settings import BaseSettings, SettingsConfigDict
import os

# --- 디버깅 섹션 ---
# 1. 현재 코드가 실행되는 위치와 .env 파일의 예상 경로를 출력합니다.
print("--- .env 파일 경로 확인 ---")
current_working_directory = os.getcwd()
env_path = os.path.join(current_working_directory, '.env')
print(f"현재 작업 폴더: {current_working_directory}")

# 2. 실제로 .env 파일이 그 위치에 있는지 확인합니다.
if os.path.exists(env_path):
    print(f"✅ .env 파일을 찾았습니다: {env_path}")
else:
    print(f"❌ 경고: 현재 폴더에서 .env 파일을 찾을 수 없습니다!")
print("--------------------------\n")


# --- 설정 클래스 정의 ---
class Settings(BaseSettings):
    """
    .env 파일에서 환경 변수를 읽어와 파이썬 객체로 관리합니다.
    """
    GOOGLE_API_KEY: str
    KAKAO_API_KEY: str
    DB_HOST: str = "localhost"
    DB_USER: str = "root"
    DB_PASSWORD: str = ""
    DB_NAME: str = "aac_project_db"

    # .env 파일을 읽도록 설정하고, 추가적인 변수는 무시합니다.
    model_config = SettingsConfigDict(env_file=".env", extra='ignore')

# 설정 객체를 생성합니다. 이 시점에 .env 파일의 값이 로드됩니다.
settings = Settings()


# --- 최종 확인 섹션 ---
# 3. 모든 과정을 거쳐 최종적으로 메모리에 로드된 API 키 값을 출력합니다.
print("--- 최종적으로 로드된 API 키 값 확인 ---")
print(f"GOOGLE_API_KEY: {settings.GOOGLE_API_KEY}")
print("-------------------------------------\n")
