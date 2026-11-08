import sqlite3
import json
import os
from datetime import datetime, timedelta

DB_PATH = r"d:\DACS2\backend\cinai.db"

conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

# 1. DROP and RECREATE TABLES WITH COMPLETE USER SCHEMA
cur.execute("DROP TABLE IF EXISTS user_activities;")
cur.execute("DROP TABLE IF EXISTS team_members;")
cur.execute("DROP TABLE IF EXISTS scenes;")
cur.execute("DROP TABLE IF EXISTS story_bibles;")
cur.execute("DROP TABLE IF EXISTS projects;")
cur.execute("DROP TABLE IF EXISTS users;")

# Users Table
cur.execute("""
CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    email TEXT UNIQUE NOT NULL,
    hashed_password TEXT NOT NULL,
    full_name TEXT NOT NULL,
    avatar TEXT,
    role TEXT DEFAULT 'CREATOR',
    subscription_tier TEXT DEFAULT 'PRO',
    ai_credits INTEGER DEFAULT 2500,
    storage_used_mb REAL DEFAULT 1420.5,
    storage_limit_mb REAL DEFAULT 20480.0,
    bio TEXT,
    phone TEXT,
    department TEXT,
    status TEXT DEFAULT 'ACTIVE',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_login TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
""")

# User Activities Table
cur.execute("""
CREATE TABLE user_activities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    action TEXT NOT NULL,
    description TEXT NOT NULL,
    icon TEXT DEFAULT '⚡',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
);
""")

# Projects Table
cur.execute("""
CREATE TABLE projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    description TEXT,
    genre TEXT DEFAULT 'Điện ảnh',
    status TEXT DEFAULT 'draft',
    thumbnail TEXT,
    view_count INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
);
""")

# Team Members / Collaborators Table
cur.execute("""
CREATE TABLE team_members (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    role_in_project TEXT NOT NULL,
    is_online INTEGER DEFAULT 1,
    joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE,
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
);
""")

# Story Bibles Table
cur.execute("""
CREATE TABLE story_bibles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    logline TEXT,
    theme TEXT,
    world_setting TEXT,
    character_profiles TEXT,
    data_json TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
);
""")

# Scenes Table
cur.execute("""
CREATE TABLE scenes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    scene_number INTEGER NOT NULL,
    title TEXT NOT NULL,
    visual_prompt TEXT,
    dialogue TEXT,
    camera_angle TEXT,
    sfx TEXT,
    image_url TEXT,
    audio_url TEXT,
    duration REAL DEFAULT 4.0,
    status TEXT DEFAULT 'APPROVED',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
);
""")

print("Created all tables successfully!")

# 2. SEED USERS DATA
users_data = [
    (
        1,
        "thanhthao_vku",
        "thanhthao.creator@cinai.io",
        "pbkdf2:sha256:600000$thao2026$hashkey",
        "Trần Huỳnh Thanh Thảo",
        "👩‍🎨",
        "LEAD_CREATOR",
        "PRO_STUDIO",
        2850,
        2450.0,
        20480.0,
        "Sinh viên ngành CNTT - Đồ án 2 VKU. Trưởng nhóm biên kịch & đạo diễn dự án 'Mắt Bão 2088'. Chuyên sâu AI Video Pipeline.",
        "+84 905 123 456",
        "Đại học CNTT & TT Việt - Hàn (VKU)",
        "ACTIVE",
        "2026-10-08 09:00:00",
        "2026-11-01 22:00:00"
    ),
    (
        2,
        "an_director",
        "an.director@cinai.io",
        "pbkdf2:sha256:600000$an2026$hashkey",
        "TS. Nguyễn Văn An",
        "👨‍🏫",
        "DIRECTOR_ADMIN",
        "ENTERPRISE",
        10000,
        15800.0,
        102400.0,
        "Cố vấn học thuật & Đạo diễn giám sát chất lượng nghệ thuật, chuẩn hóa cấu trúc 3 Hồi và quy chuẩn điện ảnh.",
        "+84 912 345 678",
        "Hội đồng Đánh giá & Giám sát Dự án VKU",
        "ACTIVE",
        "2026-10-05 08:30:00",
        "2026-11-01 21:15:00"
    ),
    (
        3,
        "nam_vfx",
        "nam.vfx@cinai.io",
        "pbkdf2:sha256:600000$nam2026$hashkey",
        "Lê Hoàng Nam",
        "🎧",
        "SOUND_ENGINEER",
        "PRO_STUDIO",
        1600,
        4200.0,
        20480.0,
        "Kỹ sư âm thanh & hậu kỳ VFX. Phụ trách tổng hợp giọng đọc Edge TTS tiếng Việt tự nhiên và thiết kế hiệu ứng âm thanh không gian.",
        "+84 934 567 890",
        "Phòng Hậu kỳ & Thiết kế Âm thanh CINAI",
        "ACTIVE",
        "2026-10-10 14:00:00",
        "2026-11-01 21:45:00"
    ),
    (
        4,
        "tri_ai",
        "tri.prompter@cinai.io",
        "pbkdf2:sha256:600000$tri2026$hashkey",
        "Đỗ Minh Trí",
        "🤖",
        "PROMPT_ENGINEER",
        "PRO_STUDIO",
        2100,
        5600.0,
        20480.0,
        "Chuyên gia Prompt Orchestration. Tinh chỉnh FLUX.1 & SDXL giữ Character Consistency nhân vật Kaelen Vũ và kiến trúc Cyberpunk.",
        "+84 978 901 234",
        "AI Innovation Lab - CinAI",
        "ACTIVE",
        "2026-10-12 10:15:00",
        "2026-11-01 20:30:00"
    ),
    (
        5,
        "demo_creator",
        "demo@cinai.io",
        "pbkdf2:sha256:600000$demo2026$hashkey",
        "Demo Content Creator",
        "🚀",
        "CREATOR",
        "FREE_TRIAL",
        500,
        350.0,
        5120.0,
        "Tài khoản trải nghiệm người dùng tự do. Khám phá toàn bộ 9 màn hình chức năng sinh phim với Gemini AI.",
        "+84 999 888 777",
        "Cộng đồng Sáng tạo Tự do",
        "ACTIVE",
        "2026-10-20 16:20:00",
        "2026-11-01 19:00:00"
    )
]

cur.executemany("""
INSERT INTO users (
    id, username, email, hashed_password, full_name, avatar, role, subscription_tier,
    ai_credits, storage_used_mb, storage_limit_mb, bio, phone, department, status, created_at, last_login
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
""", users_data)

print("Inserted 5 detailed users!")

# 3. SEED PROJECTS
projects_data = [
    (
        1,
        1,
        "Mắt Bão 2088 (Season 1 / Ep 1: Bóng Đêm Tân Cảng)",
        "Bối cảnh Sài Gòn 2088 bị nhấn chìm dưới triều cường công nghệ và cuộc đối đầu giữa Kaelen Vũ và Tập đoàn Vạn Hưng.",
        "Cyberpunk / Khoa học viễn tưởng",
        "APPROVED",
        "https://images.unsplash.com/photo-1578632767115-351597cf2477?w=800&q=80",
        245000,
        "2026-10-15 10:00:00",
        "2026-11-01 21:00:00"
    ),
    (
        2,
        1,
        "Ký Ức Đô Thị Cổ 2045 (Phim Ngắn 15 Phút)",
        "Khai thác câu chuyện về người phục chế ký ức số ở Hội An tương lai khi dữ liệu văn hóa cổ bị mã hóa biến mất.",
        "Tâm lý / Giả tưởng xã hội",
        "IN_REVIEW",
        "https://images.unsplash.com/photo-1509198397868-475647b2a1e5?w=800&q=80",
        84200,
        "2026-10-22 14:30:00",
        "2026-10-30 18:00:00"
    ),
    (
        3,
        2,
        "Hành Trình Di Cư Sao Hỏa 2120",
        "Bộ phim tài liệu viễn tưởng về đoàn thám hiểm người Việt đầu tiên hạ cánh lòng chảo Utopia Planitia.",
        "Phiêu lưu vũ trụ",
        "PLANNING",
        "https://images.unsplash.com/photo-1614728894747-a83421e2b9c9?w=800&q=80",
        15600,
        "2026-10-28 09:15:00",
        "2026-11-01 15:40:00"
    )
]

cur.executemany("""
INSERT INTO projects (
    id, user_id, title, description, genre, status, thumbnail, view_count, created_at, updated_at
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
""", projects_data)

print("Inserted 3 realistic projects!")

# 4. SEED TEAM MEMBERS FOR PROJECT 1
team_data = [
    (1, 1, 1, "Lead Creator & Biên kịch", 1, "2026-10-15 10:00:00"),
    (2, 1, 2, "Đạo diễn Giám sát & Review", 1, "2026-10-16 08:30:00"),
    (3, 1, 3, "Sound & Voice Engineer", 1, "2026-10-16 09:00:00"),
    (4, 1, 4, "Prompt & Visual Concept", 0, "2026-10-17 11:20:00")
]

cur.executemany("""
INSERT INTO team_members (id, project_id, user_id, role_in_project, is_online, joined_at)
VALUES (?, ?, ?, ?, ?, ?);
""", team_data)

# 5. SEED USER ACTIVITIES FOR USER 1 & OTHERS
activities_data = [
    (1, 1, "Tạo ý tưởng mới", "Đã khởi tạo Concept và 3 câu hỏi đào sâu cho 'Mắt Bão 2088'", "💡", "2026-11-01 21:50:00"),
    (2, 1, "Biên tập kịch bản", "Đã hoàn thành phân rã 6 Scene kịch bản chuẩn Fountain cấu trúc 3 Hồi", "📜", "2026-11-01 21:25:00"),
    (3, 4, "Tối ưu Visual Prompt", "Đã cập nhật bộ Prompt FLUX.1 cho nhân vật Kaelen Vũ đạt tính nhất quán 98%", "👤", "2026-11-01 20:42:00"),
    (4, 3, "Thu âm & Voice Render", "Đã xuất 6 bản lồng tiếng Edge TTS giọng miền Nam tự nhiên", "🎙️", "2026-11-01 20:05:00"),
    (5, 1, "Kết xuất Video", "Đã render bản dựng Preview FFmpeg 4K UHD với phụ đề tự động", "🎥", "2026-11-01 19:15:00"),
    (6, 2, "Duyệt chất lượng", "TS. Nguyễn Văn An đã phê duyệt kịch bản và cấp chứng nhận bản quyền", "✅", "2026-11-01 18:30:00")
]

cur.executemany("""
INSERT INTO user_activities (id, user_id, action, description, icon, created_at)
VALUES (?, ?, ?, ?, ?, ?);
""", activities_data)

# 6. SEED STORY BIBLE FOR PROJECT 1
bible_data = {
    "project_id": 1,
    "logline": "Năm 2088 tại Neo-Sài Gòn ngập nước, kỹ sư robot ngầm Kaelen Vũ phát hiện lõi dữ liệu bí mật có thể đảo ngược biến đổi khí hậu nhưng bị truy sát bởi Tập đoàn Vạn Hưng.",
    "theme": "Công nghệ, lòng trung thành và hy vọng của con người trước thảm họa sinh thái.",
    "world_setting": "Sài Gòn Neo-2088: Hệ thống đê kè tự động, chợ nổi công nghệ cao Tân Cảng, xe bay lướt trên kênh Nhiêu Lộc neon.",
    "character_profiles": [
        {"name": "Kaelen Vũ", "role": "Nhân vật chính", "voice": "Nam miền Nam, 28 tuổi, kiên nghị, trầm ấm", "visual": "Áo khoác chống nước dạ quang, kính AR Holo-Lens, cánh tay cơ khí trái"},
        {"name": "Mai Linh", "role": "Hacker đồng minh", "voice": "Nữ miền Bắc, 24 tuổi, nhanh nhẹn, sắc sảo", "visual": "Tóc neon xanh ngắn, găng tay truyền dẫn dữ liệu thần kinh"},
        {"name": "Tổng Giám đốc Lâm", "role": "Phản diện", "voice": "Nam trung niên quyền lực, lạnh lùng", "visual": "Âu phục Cyber-silk xám tro, mắt nhân tạo phát sáng đỏ"}
    ]
}

cur.execute("""
INSERT INTO story_bibles (project_id, logline, theme, world_setting, character_profiles, data_json)
VALUES (1, ?, ?, ?, ?, ?);
""", (bible_data["logline"], bible_data["theme"], bible_data["world_setting"], json.dumps(bible_data["character_profiles"], ensure_ascii=False), json.dumps(bible_data, ensure_ascii=False)))

# 7. SEED SCENES FOR PROJECT 1
scenes_data = [
    (
        1, 1, 1, "Toàn cảnh Sài Gòn Neo-2088 về đêm",
        "Cinematic wide angle, Neo-Saigon year 2088, futuristic floating market, heavy rain, neon lights reflecting on water canal, hovering sky-cars, high detail 8k photorealistic.",
        "Kaelen (Voiceover): Năm 2088... khi mặt đất chìm dưới sóng nước, những kẻ sống sót đã học cách thắp sáng bóng đêm.",
        "Góc máy rộng (Wide Establishing Shot)",
        "Tiếng mưa rơi trên mái tôn hợp kim, tiếng động cơ xe bay rít nhẹ từ xa",
        "https://images.unsplash.com/photo-1518709268805-4e9042af9f23?w=800&q=80",
        "/storage/voice_scene1.mp3",
        4.5, "APPROVED"
    ),
    (
        2, 1, 2, "Xưởng cơ khí ngầm của Kaelen",
        "Interior dimly lit high-tech cyberpunk workshop, tools floating in magnetic trays, cables hanging, holographic screens displaying circuit schematics.",
        "Kaelen: Lõi năng lượng này... không thuộc về thế giới trên mặt nước. Nó chứa mã nguồn của Trạm Tân Cảng.",
        "Góc máy trung (Medium Close-Up)",
        "Tiếng hàn hồ quang xì xẹt, âm thanh cảnh báo tút tút từ màn hình holographic",
        "https://images.unsplash.com/photo-1508739773434-c26b3d09e071?w=800&q=80",
        "/storage/voice_scene2.mp3",
        4.0, "APPROVED"
    ),
    (
        3, 1, 3, "Cuộc đột kích của biệt đội Drone",
        "Action shot, stealth attack drones breaching glass skylight, red targeting laser beams slicing through smoke, sparks flying.",
        "Mai Linh qua bộ đàm: Kaelen, chạy mau! Vệ binh Vạn Hưng đã định vị được tín hiệu phản hồi!",
        "Góc máy thấp kịch tính (Low Angle Dynamic Camera)",
        "Tiếng kính vỡ choảng, tiếng còi báo động khẩn cấp hú vang",
        "https://images.unsplash.com/photo-1578632767115-351597cf2477?w=800&q=80",
        "/storage/voice_scene3.mp3",
        3.8, "APPROVED"
    )
]

cur.executemany("""
INSERT INTO scenes (
    id, project_id, scene_number, title, visual_prompt, dialogue, camera_angle, sfx, image_url, audio_url, duration, status
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
""", scenes_data)

conn.commit()
conn.close()

print("ALL DATA (USERS, PROJECTS, TEAM, ACTIVITIES, BIBLE, SCENES) POPULATED SUCCESSFULLY!")
