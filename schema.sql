--- 테이블 순서대로 생성해주세요.


-- 1. 기본 카테고리 및 태그 테이블
CREATE TABLE Categories (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(50) NOT NULL UNIQUE,
    selection_count INT DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE Tags (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(50) NOT NULL UNIQUE
);

-- 2. 고정 문장 관련 테이블 (DB 기반 추천 시 사용)
CREATE TABLE Sentences (
    id INT AUTO_INCREMENT PRIMARY KEY,
    text VARCHAR(255) NOT NULL,
    usage_count INT DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE Sentence_Category_Map (
    sentence_id INT,
    category_id INT,
    PRIMARY KEY (sentence_id, category_id),
    FOREIGN KEY (sentence_id) REFERENCES Sentences(id) ON DELETE CASCADE,
    FOREIGN KEY (category_id) REFERENCES Categories(id) ON DELETE CASCADE
);

CREATE TABLE Sentence_Tag_Map (
    sentence_id INT,
    tag_id INT,
    PRIMARY KEY (sentence_id, tag_id),
    FOREIGN KEY (sentence_id) REFERENCES Sentences(id) ON DELETE CASCADE,
    FOREIGN KEY (tag_id) REFERENCES Tags(id) ON DELETE CASCADE
);

-- 3. 위치 기반 트리거 테이블
CREATE TABLE Location_Triggers (
    id INT AUTO_INCREMENT PRIMARY KEY,
    trigger_type ENUM('NFC', 'QR') NOT NULL,
    trigger_value VARCHAR(255) NOT NULL UNIQUE,
    category_id INT,
    specific_sentence_id INT,
    FOREIGN KEY (category_id) REFERENCES Categories(id) ON DELETE SET NULL,
    FOREIGN KEY (specific_sentence_id) REFERENCES Sentences(id) ON DELETE SET NULL
);

-- 4. 사용자 및 보호자 관련 테이블
CREATE TABLE guardians (
    id INT AUTO_INCREMENT PRIMARY KEY,
    email VARCHAR(255) NOT NULL UNIQUE,
    password VARCHAR(255) NOT NULL,
    name VARCHAR(50) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    guardian_id INT,
    email VARCHAR(255) NOT NULL UNIQUE,
    password VARCHAR(255) NOT NULL,
    name VARCHAR(50) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (guardian_id) REFERENCES guardians(id) ON DELETE SET NULL
);

-- 5. 사용자 개인화 기능 테이블
CREATE TABLE favorites (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    sentence VARCHAR(255) NOT NULL,
    display_order INT NOT NULL DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE speech_logs (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    sentence VARCHAR(255) NOT NULL,
    location VARCHAR(100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- 초기 데이터 삽입
INSERT INTO Categories (name) VALUES
('병원'), ('식당'), ('카페'), ('편의점'), ('지하철역'), ('도서관'), ('기타'), ('일상 대화');

