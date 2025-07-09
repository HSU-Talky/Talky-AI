from pydantic_settings import BaseSettings, SettingsConfigDict
import os

# 설정 클래스 정의
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