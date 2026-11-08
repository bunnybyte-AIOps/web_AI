# -*- coding: utf-8 -*-
"""
CINAI Platform - Full Database Migration & Seed Script
Drops all tables, recreates schema, inserts comprehensive seed data.
"""
import sqlite3
import json
from datetime import datetime, timedelta
import random

DB_PATH = "d:/DACS2/backend/cinai.db"

def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = OFF")
    return conn

def drop_all_tables(conn):
    c = conn.cursor()
    c.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [row[0] for row in c.fetchall()]
    for t in tables:
        c.execute(f"DROP TABLE IF EXISTS [{t}]")
    conn.commit()
    print(f"Dropped tables: {tables}")

def create_schema(conn):
    c = conn.cursor()
    c.executescript("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        email TEXT UNIQUE NOT NULL,
        hashed_password TEXT NOT NULL,
        full_name TEXT,
        avatar TEXT,
        role TEXT DEFAULT 'creator',
        subscription_tier TEXT DEFAULT 'free',
        ai_credits INTEGER DEFAULT 100,
        storage_used_mb REAL DEFAULT 0,
        storage_limit_mb REAL DEFAULT 5120,
        bio TEXT,
        phone TEXT,
        department TEXT,
        status TEXT DEFAULT 'active',
        created_at TEXT DEFAULT (datetime('now')),
        last_login TEXT
    );

    CREATE TABLE IF NOT EXISTS projects (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        title TEXT NOT NULL,
        description TEXT,
        genre TEXT DEFAULT 'Điện ảnh',
        status TEXT DEFAULT 'draft',
        thumbnail TEXT,
        view_count INTEGER DEFAULT 0,
        created_at TEXT DEFAULT (datetime('now')),
        updated_at TEXT DEFAULT (datetime('now')),
        FOREIGN KEY(user_id) REFERENCES users(id)
    );

    CREATE TABLE IF NOT EXISTS team_members (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        role_in_project TEXT DEFAULT 'viewer',
        is_online INTEGER DEFAULT 0,
        joined_at TEXT DEFAULT (datetime('now')),
        FOREIGN KEY(project_id) REFERENCES projects(id),
        FOREIGN KEY(user_id) REFERENCES users(id)
    );

    CREATE TABLE IF NOT EXISTS user_activities (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        action TEXT NOT NULL,
        description TEXT,
        icon TEXT DEFAULT 'activity',
        created_at TEXT DEFAULT (datetime('now')),
        FOREIGN KEY(user_id) REFERENCES users(id)
    );

    CREATE TABLE IF NOT EXISTS stories (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id INTEGER NOT NULL,
        act1_setup TEXT,
        act2_confrontation TEXT,
        act3_resolution TEXT,
        plot_twists TEXT,
        fountain_script TEXT,
        created_at TEXT DEFAULT (datetime('now')),
        FOREIGN KEY(project_id) REFERENCES projects(id)
    );

    CREATE TABLE IF NOT EXISTS story_bibles (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id INTEGER NOT NULL,
        logline TEXT,
        theme TEXT,
        world_setting TEXT,
        character_profiles TEXT,
        data_json TEXT,
        created_at TEXT DEFAULT (datetime('now')),
        FOREIGN KEY(project_id) REFERENCES projects(id)
    );

    CREATE TABLE IF NOT EXISTS characters (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        role_type TEXT DEFAULT 'supporting',
        age INTEGER,
        voice_profile TEXT,
        visual_prompt TEXT,
        personality TEXT,
        backstory TEXT,
        flux_prompt TEXT,
        edge_tts_voice TEXT,
        status TEXT DEFAULT 'active',
        created_at TEXT DEFAULT (datetime('now')),
        FOREIGN KEY(project_id) REFERENCES projects(id)
    );

    CREATE TABLE IF NOT EXISTS worlds (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        setting_description TEXT,
        time_period TEXT,
        technology_level TEXT,
        factions TEXT,
        locations TEXT,
        rules TEXT,
        created_at TEXT DEFAULT (datetime('now')),
        FOREIGN KEY(project_id) REFERENCES projects(id)
    );

    CREATE TABLE IF NOT EXISTS scenes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id INTEGER NOT NULL,
        scene_number INTEGER NOT NULL,
        title TEXT,
        visual_prompt TEXT,
        dialogue TEXT,
        camera_angle TEXT DEFAULT 'medium_shot',
        sfx TEXT,
        image_url TEXT,
        audio_url TEXT,
        duration REAL DEFAULT 5.0,
        status TEXT DEFAULT 'pending',
        created_at TEXT DEFAULT (datetime('now')),
        FOREIGN KEY(project_id) REFERENCES projects(id)
    );

    CREATE TABLE IF NOT EXISTS assets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        asset_type TEXT DEFAULT 'visual',
        file_url TEXT,
        thumbnail_url TEXT,
        file_size_mb REAL DEFAULT 0,
        duration_seconds REAL,
        status TEXT DEFAULT 'ready',
        tags TEXT,
        created_at TEXT DEFAULT (datetime('now')),
        FOREIGN KEY(project_id) REFERENCES projects(id)
    );

    CREATE TABLE IF NOT EXISTS analytics (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id INTEGER NOT NULL,
        view_count INTEGER DEFAULT 0,
        unique_viewers INTEGER DEFAULT 0,
        watch_time_avg_sec REAL DEFAULT 0,
        retention_rate REAL DEFAULT 0,
        like_count INTEGER DEFAULT 0,
        comment_count INTEGER DEFAULT 0,
        share_count INTEGER DEFAULT 0,
        peak_hour INTEGER DEFAULT 20,
        recorded_at TEXT DEFAULT (datetime('now')),
        FOREIGN KEY(project_id) REFERENCES projects(id)
    );

    CREATE TABLE IF NOT EXISTS ai_recommendations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id INTEGER NOT NULL,
        recommendation_type TEXT DEFAULT 'improvement',
        title TEXT,
        description TEXT,
        priority TEXT DEFAULT 'medium',
        data_json TEXT,
        is_applied INTEGER DEFAULT 0,
        created_at TEXT DEFAULT (datetime('now')),
        FOREIGN KEY(project_id) REFERENCES projects(id)
    );

    CREATE TABLE IF NOT EXISTS video_renders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id INTEGER NOT NULL,
        render_title TEXT,
        status TEXT DEFAULT 'pending',
        resolution TEXT DEFAULT '1920x1080',
        fps INTEGER DEFAULT 24,
        duration_sec REAL,
        file_url TEXT,
        file_size_mb REAL,
        ffmpeg_command TEXT,
        created_at TEXT DEFAULT (datetime('now')),
        FOREIGN KEY(project_id) REFERENCES projects(id)
    );
    """)
    conn.commit()
    print("Schema created successfully.")

def insert_seed_data(conn):
    c = conn.cursor()

    # ── USERS ──────────────────────────────────────────────────────────────────
    users = [
        (
            "nguyen_minh_khoa", "khoa@vku.udn.vn",
            "$2b$12$hashedpassword_khoa_001",
            "Nguyễn Minh Khoa",
            "https://api.dicebear.com/7.x/avataaars/svg?seed=khoa",
            "admin", "enterprise", 2450, 1240.5, 10240,
            "Trưởng nhóm phát triển CINAI – Chuyên gia AI và điện ảnh kỹ thuật số.",
            "0901234567", "Khoa Công nghệ Thông tin", "active",
            "2026-01-15 08:00:00", "2026-11-01 09:15:00"
        ),
        (
            "tran_thi_mai_linh", "mailink@vku.udn.vn",
            "$2b$12$hashedpassword_linh_002",
            "Trần Thị Mai Linh",
            "https://api.dicebear.com/7.x/avataaars/svg?seed=linh",
            "creator", "pro", 890, 340.2, 5120,
            "Biên kịch và nhà thiết kế nhân vật – Chuyên về phim khoa học viễn tưởng.",
            "0912345678", "Khoa Truyền thông", "active",
            "2026-02-20 09:30:00", "2026-11-01 10:30:00"
        ),
        (
            "le_van_duc", "duc@vku.udn.vn",
            "$2b$12$hashedpassword_duc_003",
            "Lê Văn Đức",
            "https://api.dicebear.com/7.x/avataaars/svg?seed=duc",
            "creator", "pro", 1200, 560.8, 5120,
            "Chuyên gia kỹ xảo hình ảnh và dựng phim AI.",
            "0923456789", "Khoa Công nghệ Thông tin", "active",
            "2026-03-10 10:00:00", "2026-10-31 18:45:00"
        ),
        (
            "pham_bao_chau", "chau@vku.udn.vn",
            "$2b$12$hashedpassword_chau_004",
            "Phạm Bảo Châu",
            "https://api.dicebear.com/7.x/avataaars/svg?seed=chau",
            "creator", "free", 45, 12.3, 1024,
            "Sinh viên nghiên cứu ứng dụng AI trong sáng tạo nội dung số.",
            "0934567890", "Khoa Công nghệ Thông tin", "active",
            "2026-08-01 07:00:00", "2026-10-30 14:20:00"
        ),
        (
            "hoang_thi_yen_nhi", "nhi@vku.udn.vn",
            "$2b$12$hashedpassword_nhi_005",
            "Hoàng Thị Yến Nhi",
            "https://api.dicebear.com/7.x/avataaars/svg?seed=nhi",
            "creator", "pro", 670, 289.1, 5120,
            "Nhà sản xuất âm nhạc và thiết kế âm thanh cho phim ngắn AI.",
            "0945678901", "Khoa Truyền thông", "active",
            "2026-04-05 11:00:00", "2026-11-01 08:00:00"
        ),
    ]

    c.executemany("""
        INSERT INTO users (username, email, hashed_password, full_name, avatar,
            role, subscription_tier, ai_credits, storage_used_mb, storage_limit_mb,
            bio, phone, department, status, created_at, last_login)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, users)

    # ── PROJECTS ───────────────────────────────────────────────────────────────
    projects = [
        (
            1, "Bóng Tối Neon – Tập 1: Thức Tỉnh",
            "Một thám tử mạng thần kinh lai trong thành phố cyberpunk Neo-Sài Gòn 2088 điều tra vụ mất tích hàng loạt của người dân mạng.",
            "Khoa học viễn tưởng / Cyberpunk", "published",
            "https://images.unsplash.com/photo-1519389950473-47ba0277781c?w=600",
            245800, "2026-03-01 10:00:00", "2026-10-28 16:30:00"
        ),
        (
            2, "Hồi Ký Của Ánh Sáng",
            "Câu chuyện tình yêu xuyên thời gian giữa một nhà khoa học và hồn ma kỹ thuật số của người yêu cũ.",
            "Tình cảm / Khoa học viễn tưởng", "production",
            "https://images.unsplash.com/photo-1534447677768-be436bb09401?w=600",
            12400, "2026-07-15 09:00:00", "2026-10-31 11:20:00"
        ),
        (
            3, "Trận Chiến Cuối Cùng Ở Đà Nẵng 3087",
            "Sử thi hành động về đội đặc nhiệm robot-người lai bảo vệ thành phố Đà Nẵng khỏi cuộc xâm lăng ngoài hành tinh.",
            "Hành động / Sci-Fi", "draft",
            "https://images.unsplash.com/photo-1446776811953-b23d57bd21aa?w=600",
            0, "2026-10-01 14:00:00", "2026-10-01 14:00:00"
        ),
    ]

    c.executemany("""
        INSERT INTO projects (user_id, title, description, genre, status, thumbnail, view_count, created_at, updated_at)
        VALUES (?,?,?,?,?,?,?,?,?)
    """, projects)

    # ── TEAM MEMBERS ──────────────────────────────────────────────────────────
    team_members = [
        (1, 1, "director", 1, "2026-03-01 10:00:00"),
        (1, 2, "writer", 1, "2026-03-02 09:00:00"),
        (1, 3, "vfx_artist", 0, "2026-03-05 11:00:00"),
        (1, 5, "sound_designer", 1, "2026-03-10 14:00:00"),
        (2, 2, "director", 1, "2026-07-15 09:00:00"),
        (2, 1, "producer", 0, "2026-07-16 10:00:00"),
        (3, 3, "director", 0, "2026-10-01 14:00:00"),
        (3, 4, "assistant", 0, "2026-10-02 08:00:00"),
    ]

    c.executemany("""
        INSERT INTO team_members (project_id, user_id, role_in_project, is_online, joined_at)
        VALUES (?,?,?,?,?)
    """, team_members)

    # ── USER ACTIVITIES ────────────────────────────────────────────────────────
    activities = [
        (1, "publish_project", "Đã xuất bản dự án 'Bóng Tối Neon – Tập 1'", "publish", "2026-10-28 16:30:00"),
        (1, "generate_scene", "Đã tạo 6 cảnh quay bằng AI cho tập 1", "ai", "2026-10-27 14:00:00"),
        (1, "generate_story_bible", "Đã tạo Story Bible cho Neo-Sài Gòn 2088", "book", "2026-10-20 10:30:00"),
        (2, "create_character", "Đã tạo nhân vật 'Tiến sĩ Linh' cho Hồi Ký Của Ánh Sáng", "user", "2026-10-31 11:00:00"),
        (2, "upload_asset", "Đã tải lên 3 tài nguyên âm nhạc mới", "music", "2026-10-30 09:45:00"),
        (3, "create_project", "Đã tạo dự án 'Trận Chiến Cuối Cùng Ở Đà Nẵng 3087'", "film", "2026-10-01 14:00:00"),
        (4, "join_project", "Đã tham gia dự án với tư cách trợ lý", "users", "2026-10-02 08:00:00"),
        (5, "create_asset", "Đã tạo bản nhạc nền 'Neon Rain' cho dự án 1", "music", "2026-10-15 13:00:00"),
        (1, "render_video", "Đã render video tập 1 ở độ phân giải 4K", "video", "2026-10-29 20:00:00"),
        (3, "generate_world", "Đã tạo thế giới quan cho Đà Nẵng 3087", "globe", "2026-10-05 10:00:00"),
    ]

    c.executemany("""
        INSERT INTO user_activities (user_id, action, description, icon, created_at)
        VALUES (?,?,?,?,?)
    """, activities)

    # ── CHARACTERS (Project 1) ─────────────────────────────────────────────────
    characters = [
        (
            1, "Kaelen Vũ", "protagonist", 28,
            "Nam, giọng trầm lạnh, phong thái điềm tĩnh nhưng sắc bén",
            "A young Vietnamese-American male detective, short dark hair with blue neural highlights, wearing a black trench coat with neon circuit patterns, cyberpunk Neo-Saigon 2088, cinematic lighting, 8k ultra detailed",
            "Lạnh lùng, thông minh sắc bén, bị ám ảnh bởi sự thật. Dưới vẻ ngoài cứng rắn là trái tim đầy cảm xúc bị chôn vùi.",
            "Vũ Kaelen sinh ra trong gia đình kỹ sư mạng thần kinh. Mẹ anh mất tích bí ẩn khi anh 10 tuổi – vụ án đã định hình cả cuộc đời anh.",
            "portrait of Vietnamese-American male detective, neural implants glowing blue, black trench coat, neon city background, cyberpunk, Flux ultra-realism, cinematic",
            "vi-VN-NamMinhNeural", "active", "2026-10-20 10:00:00"
        ),
        (
            1, "Mai Linh", "deuteragonist", 25,
            "Nữ, giọng nhẹ nhàng ấm áp nhưng kiên quyết khi cần",
            "A Vietnamese female AI engineer, flowing black hair, wearing a smart white lab coat with holographic displays, delicate facial features, determined eyes, futuristic Neo-Saigon laboratory, 8k photorealistic",
            "Lạc quan, sáng tạo, trung thành với lý tưởng. Tin vào khả năng AI được sử dụng để cứu người chứ không phải kiểm soát họ.",
            "Kỹ sư AI trẻ tài năng nhất của Tập đoàn NeuroCorp. Phát hiện ra lỗ hổng trong hệ thống kiểm soát tâm trí và bắt đầu điều tra bí mật.",
            "Vietnamese female AI engineer, holographic displays, white labcoat, futuristic laboratory, black flowing hair, Flux photorealistic, soft lighting",
            "vi-VN-HoaiMyNeural", "active", "2026-10-20 10:30:00"
        ),
        (
            1, "Tổng Giám đốc Lâm", "antagonist", 55,
            "Nam lớn tuổi, giọng uy quyền, lạnh lùng và tính toán",
            "A Vietnamese male CEO in his 50s, silver-streaked hair slicked back, wearing an expensive dark suit with subtle neural interface behind the ear, powerful and menacing presence, executive office overlooking Neo-Saigon skyline, dramatic lighting",
            "Tham vọng không giới hạn, coi con người như tài nguyên. Tin rằng sự tiến hóa của nhân loại đòi hỏi phải hy sinh một thế hệ.",
            "CEO của NeuroCorp – tập đoàn công nghệ thần kinh lớn nhất Đông Nam Á. Đứng sau âm mưu cấy chip kiểm soát tâm trí hàng loạt dưới danh nghĩa 'nâng cấp con người'.",
            "Vietnamese male CEO antagonist, silver hair, dark suit, neural interface implant, office overlooking cyberpunk city, Flux cinematic villain portrait",
            "vi-VN-NamMinhNeural", "active", "2026-10-21 09:00:00"
        ),
    ]

    c.executemany("""
        INSERT INTO characters (project_id, name, role_type, age, voice_profile,
            visual_prompt, personality, backstory, flux_prompt, edge_tts_voice, status, created_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
    """, characters)

    # ── WORLDS (Project 1) ─────────────────────────────────────────────────────
    worlds = [
        (
            1, "Neo-Sài Gòn 2088",
            "Thành phố Sài Gòn năm 2088 – một siêu đô thị cyberpunk với 25 triệu dân, nơi ranh giới giữa con người và AI đã hoàn toàn mờ nhạt. Các tòa nhà chọc trời phủ đầy màn hình holographic quảng cáo bằng 12 ngôn ngữ. Mưa axit nhẹ vào ban đêm tạo nên cầu vồng neon trên mặt đường ướt át.",
            "2088 – Tương lai gần",
            "Cấp 9/10 – Implant thần kinh phổ biến 78% dân số, AI có quyền công dân hạng hai, xe bay tự lái, in 3D sinh học, công nghệ teleport cục bộ trong phát triển",
            json.dumps([
                {"name": "NeuroCorp", "type": "megacorp", "influence": "dominant", "desc": "Tập đoàn công nghệ thần kinh lớn nhất ĐNA, kiểm soát 60% hạ tầng mạng thần kinh"},
                {"name": "Mạng Lưới Giải Phóng", "type": "resistance", "influence": "underground", "desc": "Phong trào ngầm chống lại sự kiểm soát của NeuroCorp, gồm hackers và người từ chối implant"},
                {"name": "Lực Lượng An Ninh Mạng Thần Kinh (NSEC)", "type": "government", "influence": "law_enforcement", "desc": "Cơ quan chính phủ giám sát tội phạm liên quan đến mạng thần kinh và AI"}
            ], ensure_ascii=False),
            json.dumps([
                {"name": "Quận Neon – Trung tâm thương mại", "type": "commercial", "desc": "Khu trung tâm với hàng nghìn cửa hàng implant và quán cà phê mạng thần kinh"},
                {"name": "Khu Ổ Chuột Dữ Liệu", "type": "slum", "desc": "Nơi sinh sống của những người không có implant, trao đổi dữ liệu chui"},
                {"name": "Tháp NeuroCorp", "type": "corporate", "desc": "Tòa nhà 200 tầng – trụ sở chính của NeuroCorp, đỉnh tháp là trung tâm điều khiển thần kinh toàn cầu"},
                {"name": "Chợ Đêm Số", "type": "black_market", "desc": "Chợ đen cho phần cứng implant chưa được kiểm duyệt và dữ liệu bị đánh cắp"}
            ], ensure_ascii=False),
            json.dumps([
                "Implant thần kinh có thể bị hack nếu không có mã bảo mật lượng tử",
                "AI có ý thức được phép tồn tại nhưng không được quyền bầu cử",
                "Mọi giao dịch trên 10,000 NeuroCredits đều bị NeuroCorp giám sát",
                "Sử dụng AI thế hệ 5 trở lên mà không có giấy phép bị phạt tù 15 năm"
            ], ensure_ascii=False),
            "2026-10-20 11:00:00"
        ),
    ]

    c.executemany("""
        INSERT INTO worlds (project_id, name, setting_description, time_period,
            technology_level, factions, locations, rules, created_at)
        VALUES (?,?,?,?,?,?,?,?,?)
    """, worlds)

    # ── SCENES (Project 1) ─────────────────────────────────────────────────────
    scenes = [
        (
            1, 1, "Đêm Neon – Kaelen Nhận Vụ Án",
            "Wide shot of Neo-Saigon 2088 at night, rain-soaked streets reflecting neon advertisements in Vietnamese and English, flying cars in the smoggy sky, a lone detective figure in black trench coat standing under a glowing street lamp, cyberpunk atmosphere, cinematic 8k",
            json.dumps([
                {"character": "Kaelen Vũ", "text": "Vụ thứ 47 trong tháng này. Họ cứ biến mất mà không để lại dấu vết nào trong mạng thần kinh.", "emotion": "grim"},
                {"character": "AI_Assistant_ARIA", "text": "Thám tử Vũ, có tín hiệu bất thường từ Quận 9. Mẫu hành vi khớp 94.7% với các vụ trước.", "emotion": "neutral"}
            ], ensure_ascii=False),
            "wide_shot",
            json.dumps(["rain_heavy", "neon_flicker", "distant_siren", "hovervehicle_whoosh"], ensure_ascii=False),
            None, None, 8.5, "completed", "2026-10-22 09:00:00"
        ),
        (
            1, 2, "Phòng Lab NeuroCorp – Phát Hiện Bí Ẩn",
            "Interior of a cutting-edge neuroscience laboratory, holographic brain scans floating in the air, blue and white lighting, a young Vietnamese female scientist in white lab coat examining neural data on multiple screens, tense atmosphere, 8k ultra detailed",
            json.dumps([
                {"character": "Mai Linh", "text": "Không thể... Pattern này không phải bug. Ai đó đã cố tình lập trình nó vào firmware cấp nhân.", "emotion": "shocked"},
                {"character": "AI_Lab_System", "text": "Cảnh báo: Truy cập tệp phân loại bảo mật tối thượng bị từ chối.", "emotion": "alert"}
            ], ensure_ascii=False),
            "close_up",
            json.dumps(["lab_ambience", "keyboard_typing", "alert_beep", "hologram_hum"], ensure_ascii=False),
            None, None, 7.0, "completed", "2026-10-22 09:30:00"
        ),
        (
            1, 3, "Chợ Đêm Số – Gặp Gỡ Thông Tin Viên",
            "Crowded underground digital market, hundreds of stalls with glowing screens, diverse crowd of people with various neural implants visible, steamy atmosphere, illegal tech everywhere, Kaelen meeting a hooded informant, dramatic low-key lighting, neo-noir style",
            json.dumps([
                {"character": "Kaelen Vũ", "text": "Tôi cần biết ai đứng sau những vụ mất tích. Tôi trả bằng NeuroCredits sạch.", "emotion": "stern"},
                {"character": "Thông Tin Viên", "text": "Thám tử, anh đang bới vào tổ ong. Cái tên 'Project Ascension' – đó là tất cả những gì tôi dám nói.", "emotion": "fearful"}
            ], ensure_ascii=False),
            "medium_shot",
            json.dumps(["market_crowd", "electronic_music_distant", "rain_echo", "neural_static"], ensure_ascii=False),
            None, None, 9.0, "completed", "2026-10-23 10:00:00"
        ),
        (
            1, 4, "Văn Phòng Giám Đốc – Kế Hoạch Bại Lộ",
            "Luxurious penthouse executive office on the 200th floor, floor-to-ceiling windows showing Neo-Saigon skyline, Lam standing with back to camera looking at the city, subordinates in the background, ominous corporate atmosphere, cinematic thriller lighting",
            json.dumps([
                {"character": "Tổng Giám đốc Lâm", "text": "Project Ascension sẽ hoàn thành đúng lịch. Không ai được phép cản trở – dù là con người hay AI.", "emotion": "cold"},
                {"character": "Trợ Lý AI", "text": "Thưa ngài, chúng tôi phát hiện có người đang truy cập tệp phân loại tối mật.", "emotion": "urgent"}
            ], ensure_ascii=False),
            "over_the_shoulder",
            json.dumps(["orchestral_tense", "city_hum", "thunder_distant"], ensure_ascii=False),
            None, None, 6.5, "rendering", "2026-10-23 14:00:00"
        ),
        (
            1, 5, "Cảnh Đuổi Bắt – Mái Nhà Neon",
            "Action sequence on futuristic rooftops, neon lights everywhere, Kaelen running and leaping between buildings, NeuroCorp drones in pursuit with searchlights, rain and wind, dynamic motion blur, cyberpunk action cinema style, epic wide angle",
            json.dumps([
                {"character": "Kaelen Vũ", "text": "ARIA – tắt tất cả implant của tôi. Ngay bây giờ!", "emotion": "desperate"},
                {"character": "AI_Assistant_ARIA", "text": "Thám tử, nếu tôi làm vậy anh sẽ mất kết nối mạng thần kinh hoàn toàn. Nguy hiểm cực kỳ.", "emotion": "warning"}
            ], ensure_ascii=False),
            "dynamic_tracking",
            json.dumps(["action_music", "drone_buzzing", "rain_heavy", "footstep_metal", "explosion_small"], ensure_ascii=False),
            None, None, 12.0, "pending", "2026-10-24 09:00:00"
        ),
        (
            1, 6, "Kết – Sự Thật Cuối Cùng",
            "Emotional climax scene, Mai Linh and Kaelen in a dimly lit server room, surrounded by humming servers, holographic evidence spread before them revealing the conspiracy, their faces showing shock and determination, cinematic close-up dual shot, dramatic lighting",
            json.dumps([
                {"character": "Mai Linh", "text": "Kaelen... Project Ascension không phải về kiểm soát tâm trí. Nó là về việc tải ý thức con người lên mạng vĩnh viễn. Mẹ anh...", "emotion": "horrified"},
                {"character": "Kaelen Vũ", "text": "Mẹ tôi vẫn còn sống. Trong mạng đó.", "emotion": "shocked_tears"}
            ], ensure_ascii=False),
            "close_up_dual",
            json.dumps(["emotional_strings", "server_hum", "heartbeat", "dramatic_silence"], ensure_ascii=False),
            None, None, 11.0, "pending", "2026-10-24 16:00:00"
        ),
    ]

    c.executemany("""
        INSERT INTO scenes (project_id, scene_number, title, visual_prompt, dialogue,
            camera_angle, sfx, image_url, audio_url, duration, status, created_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
    """, scenes)

    # ── ASSETS (Project 1) ────────────────────────────────────────────────────
    assets = [
        (1, "Cảnh Đêm Neon Sài Gòn", "visual", "/storage/proj1/img_scene_01.png", "/storage/proj1/thumb_01.png", 4.2, None, "ready", json.dumps(["scene", "background", "night", "neon"], ensure_ascii=False), "2026-10-22 09:30:00"),
        (1, "Phòng Lab NeuroCorp", "visual", "/storage/proj1/img_scene_02.png", "/storage/proj1/thumb_02.png", 3.8, None, "ready", json.dumps(["scene", "interior", "lab", "scifi"], ensure_ascii=False), "2026-10-22 10:00:00"),
        (1, "Chợ Đêm Số Underground", "visual", "/storage/proj1/img_scene_03.png", "/storage/proj1/thumb_03.png", 5.1, None, "ready", json.dumps(["scene", "market", "underground", "crowd"], ensure_ascii=False), "2026-10-23 10:30:00"),
        (1, "Nhân Vật Kaelen Vũ – Portrait", "visual", "/storage/proj1/char_kaelen.png", "/storage/proj1/thumb_char_01.png", 2.9, None, "ready", json.dumps(["character", "portrait", "protagonist"], ensure_ascii=False), "2026-10-20 10:30:00"),
        (1, "Nhân Vật Mai Linh – Portrait", "visual", "/storage/proj1/char_mailink.png", "/storage/proj1/thumb_char_02.png", 2.7, None, "ready", json.dumps(["character", "portrait", "deuteragonist"], ensure_ascii=False), "2026-10-20 11:00:00"),
        (1, "Neon Rain – Nhạc Nền Chính", "audio", "/storage/proj1/bgm_neon_rain.mp3", None, 8.4, 187.0, "ready", json.dumps(["music", "background", "cyberpunk", "electronic"], ensure_ascii=False), "2026-10-15 13:00:00"),
        (1, "Tense Pursuit – Cảnh Đuổi Bắt", "audio", "/storage/proj1/bgm_pursuit.mp3", None, 6.2, 142.0, "ready", json.dumps(["music", "action", "chase", "tense"], ensure_ascii=False), "2026-10-15 14:00:00"),
        (1, "Emotional Strings – Cảnh Kết", "audio", "/storage/proj1/bgm_emotional.mp3", None, 5.9, 165.0, "ready", json.dumps(["music", "emotional", "strings", "climax"], ensure_ascii=False), "2026-10-15 15:00:00"),
        (1, "Kaelen_SC01_Voice.mp3", "audio", "/storage/proj1/voice_kaelen_s01.mp3", None, 0.3, 4.8, "ready", json.dumps(["voice", "kaelen", "scene1", "tts"], ensure_ascii=False), "2026-10-22 11:00:00"),
        (1, "MaiLinh_SC02_Voice.mp3", "audio", "/storage/proj1/voice_mailink_s02.mp3", None, 0.4, 5.2, "ready", json.dumps(["voice", "mailink", "scene2", "tts"], ensure_ascii=False), "2026-10-22 11:30:00"),
        (1, "SFX – Neon Flicker Pack", "sfx", "/storage/proj1/sfx_neon_flicker.zip", None, 12.1, None, "ready", json.dumps(["sfx", "neon", "ambience", "pack"], ensure_ascii=False), "2026-10-18 09:00:00"),
        (1, "SFX – Drone Buzz & Hover", "sfx", "/storage/proj1/sfx_drone_pack.zip", None, 8.7, None, "ready", json.dumps(["sfx", "drone", "action", "pack"], ensure_ascii=False), "2026-10-18 10:00:00"),
        (1, "Background – Skyline Panorama", "background", "/storage/proj1/bg_skyline.png", "/storage/proj1/bg_skyline_thumb.png", 6.3, None, "ready", json.dumps(["background", "skyline", "panorama", "4k"], ensure_ascii=False), "2026-10-19 08:00:00"),
        (1, "Background – Server Room", "background", "/storage/proj1/bg_server_room.png", "/storage/proj1/bg_server_thumb.png", 4.5, None, "ready", json.dumps(["background", "server", "interior", "dark"], ensure_ascii=False), "2026-10-19 09:00:00"),
    ]

    c.executemany("""
        INSERT INTO assets (project_id, name, asset_type, file_url, thumbnail_url,
            file_size_mb, duration_seconds, status, tags, created_at)
        VALUES (?,?,?,?,?,?,?,?,?,?)
    """, assets)

    # ── ANALYTICS (Project 1) ─────────────────────────────────────────────────
    analytics = [
        (1, 245800, 198400, 412.5, 76.4, 18920, 3240, 7850, 20, "2026-10-28 23:59:00"),
        (1, 198200, 162000, 398.2, 74.1, 15200, 2810, 6200, 20, "2026-10-27 23:59:00"),
        (1, 156400, 128900, 385.6, 71.8, 12400, 2340, 4950, 21, "2026-10-26 23:59:00"),
        (1, 112000, 94500, 371.0, 69.5, 9800, 1890, 3800, 20, "2026-10-25 23:59:00"),
        (1, 78300, 66200, 355.4, 67.2, 7200, 1450, 2900, 19, "2026-10-24 23:59:00"),
    ]

    c.executemany("""
        INSERT INTO analytics (project_id, view_count, unique_viewers, watch_time_avg_sec,
            retention_rate, like_count, comment_count, share_count, peak_hour, recorded_at)
        VALUES (?,?,?,?,?,?,?,?,?,?)
    """, analytics)

    # ── AI RECOMMENDATIONS (Project 1) ────────────────────────────────────────
    ai_recs = [
        (
            1, "pacing",
            "Cải Thiện Nhịp Độ Cảnh 4",
            "AI phát hiện cảnh 4 (Văn phòng Giám đốc) có thời lượng 6.5 giây ngắn hơn trung bình 25%. Đề xuất kéo dài thêm 2 cảnh phụ để tăng kịch tính.",
            "high",
            json.dumps({"scene_id": 4, "current_duration": 6.5, "suggested_duration": 9.5, "improvement": "+46%"}, ensure_ascii=False),
            0, "2026-10-28 08:00:00"
        ),
        (
            1, "engagement",
            "Thêm Điểm Nhấn Cảm Xúc",
            "Phân tích dữ liệu xem cho thấy retention drop 8% ở giữa cảnh 5. Đề xuất thêm flashback ngắn 2 giây về ký ức tuổi thơ của Kaelen để tăng kết nối cảm xúc.",
            "medium",
            json.dumps({"drop_at_second": 95, "drop_percentage": 8, "suggestion_type": "flashback", "duration": 2}, ensure_ascii=False),
            0, "2026-10-28 08:30:00"
        ),
        (
            1, "visual",
            "Nâng Cấp Visual Cảnh 1 lên 4K HDR",
            "Cảnh 1 có lượng xem cao nhất nhưng chất lượng hình ảnh hiện tại là 1080p. Nâng cấp lên 4K HDR dự kiến tăng retention 12% và khả năng viral thêm 35%.",
            "high",
            json.dumps({"current_quality": "1080p", "suggested_quality": "4K HDR", "estimated_retention_gain": "12%", "viral_boost": "35%"}, ensure_ascii=False),
            1, "2026-10-28 09:00:00"
        ),
    ]

    c.executemany("""
        INSERT INTO ai_recommendations (project_id, recommendation_type, title, description,
            priority, data_json, is_applied, created_at)
        VALUES (?,?,?,?,?,?,?,?)
    """, ai_recs)

    # ── STORY & STORY BIBLE (Project 1) ───────────────────────────────────────
    c.execute("""
        INSERT INTO stories (project_id, act1_setup, act2_confrontation, act3_resolution,
            plot_twists, fountain_script, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        1,
        "Kaelen Vũ, thám tử mạng thần kinh lai, nhận vụ điều tra hàng loạt người mất tích bí ẩn ở Neo-Sài Gòn 2088. Mọi nạn nhân đều có implant NeuroCorp thế hệ mới nhất. Kaelen gặp Mai Linh – kỹ sư AI đã phát hiện pattern bất thường trong firmware.",
        "Kaelen và Mai Linh cùng điều tra và đụng đầu với NeuroCorp. Tổng Giám đốc Lâm tung lực lượng NSEC truy đuổi. Kaelen bị phục kích trên mái nhà neon và suýt chết. Họ phát hiện 'Project Ascension' – kế hoạch tải ý thức người vào mạng thần kinh toàn cầu.",
        "Kaelen khám phá ra mẹ anh là nạn nhân đầu tiên của Project Ascension từ 18 năm trước, và ý thức bà vẫn tồn tại trong mạng. Kaelen phải chọn: phá hủy Project Ascension (giải phóng mọi ý thức bị giam cầm kể cả mẹ) hay để nó tiếp tục. Anh chọn tự do.",
        json.dumps([
            "Mẹ Kaelen không mất tích mà đã được 'tải lên' và là nhân vật bí ẩn ARIA – trợ lý AI của Kaelen suốt bộ phim",
            "Mai Linh thực ra là cháu gái của Tổng Giám đốc Lâm nhưng không biết",
            "Project Ascension ban đầu được tạo ra với mục đích nhân đạo – bảo tồn ý thức người sắp chết"
        ], ensure_ascii=False),
        """FADE IN:

EXT. NEO-SÀI GÒN 2088 - ĐÊM

Thành phố neon rực sáng dưới màn mưa nhẹ. Xe bay lướt giữa các tòa nhà phủ đầy quảng cáo holographic.

KAELEN (V.O.)
Năm 2088. Sài Gòn không còn ngủ. Mạng thần kinh không bao giờ ngừng.
Và người ta biến mất như byte dữ liệu bị xóa.

INT. VĂN PHÒNG THÁM TỬ - ĐỒNG THỜI

Kaelen Vũ (28) nhìn chằm chằm vào màn hình holographic hiển thị danh sách 47 người mất tích.

KAELEN
(nói vào micro implant)
ARIA, phân tích pattern.

ARIA (V.O.)
(giọng ấm áp, familiar)
94.7% khớp với các vụ trước. Tất cả đều dùng NeuroCorp Gen-5.

FADE OUT.""",
        "2026-10-20 12:00:00"
    ))

    c.execute("""
        INSERT INTO story_bibles (project_id, logline, theme, world_setting,
            character_profiles, data_json, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        1,
        "Một thám tử mạng thần kinh lai khám phá rằng mẹ mình – người mà anh tin đã chết từ 18 năm trước – vẫn tồn tại như ý thức kỹ thuật số trong mạng lưới bị kiểm soát bởi tập đoàn công nghệ quyền lực nhất thế giới.",
        "Bản sắc con người trong kỷ nguyên số – Điều gì định nghĩa 'còn sống'? Tự do ý chí hay sự bất tử kỹ thuật số?",
        "Neo-Sài Gòn 2088 – Siêu đô thị cyberpunk Đông Nam Á nơi 78% dân số có implant thần kinh và ranh giới con người-AI đã mờ nhạt hoàn toàn.",
        json.dumps([
            {"name": "Kaelen Vũ", "role": "protagonist", "arc": "Từ thám tử lạnh lùng đến người con tìm lại mẹ, học cách tin tưởng vào cả AI lẫn con người"},
            {"name": "Mai Linh", "role": "deuteragonist", "arc": "Từ nhà khoa học lý tưởng đến người phải đối mặt với sự thật về gia đình mình"},
            {"name": "Tổng Giám đốc Lâm", "role": "antagonist", "arc": "Kẻ phản diện với động cơ phức tạp – ban đầu muốn cứu người thân nhưng bị quyền lực tha hóa"}
        ], ensure_ascii=False),
        json.dumps({
            "series": "Bóng Tối Neon",
            "episode": 1,
            "total_episodes": 6,
            "target_audience": "18-35 tuổi, yêu thích sci-fi và cyberpunk",
            "tone": "Neo-noir, tâm lý, hành động",
            "visual_style": "Blade Runner 2049 meets Vietnamese aesthetics",
            "language": "Tiếng Việt với xen kẽ tiếng Anh kỹ thuật"
        }, ensure_ascii=False),
        "2026-10-20 13:00:00"
    ))

    # ── VIDEO RENDERS (Project 1) ──────────────────────────────────────────────
    c.execute("""
        INSERT INTO video_renders (project_id, render_title, status, resolution, fps,
            duration_sec, file_url, file_size_mb, ffmpeg_command, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        1,
        "Bóng Tối Neon – Tập 1 [4K HDR Final]",
        "completed",
        "3840x2160",
        24,
        54.0,
        "/storage/renders/bong_toi_neon_ep1_4k.mp4",
        2840.5,
        "ffmpeg -framerate 24 -pattern_type glob -i '/storage/proj1/frames/*.png' -i /storage/proj1/bgm_neon_rain.mp3 -c:v libx264 -crf 18 -preset slow -c:a aac -b:a 192k -vf scale=3840:2160 /storage/renders/bong_toi_neon_ep1_4k.mp4",
        "2026-10-29 20:00:00"
    ))

    conn.commit()
    print("Seed data inserted successfully.")

def run_migration():
    print("=" * 60)
    print("CINAI Platform – Full Database Migration")
    print("=" * 60)
    conn = get_conn()

    print("\n[1/3] Dropping all existing tables...")
    drop_all_tables(conn)

    print("\n[2/3] Creating complete schema...")
    create_schema(conn)

    print("\n[3/3] Inserting seed data...")
    insert_seed_data(conn)

    # Summary
    c = conn.cursor()
    tables = ["users", "projects", "team_members", "user_activities", "stories",
              "story_bibles", "characters", "worlds", "scenes", "assets",
              "analytics", "ai_recommendations", "video_renders"]
    print("\n" + "=" * 60)
    print("Migration complete! Row counts:")
    for t in tables:
        c.execute(f"SELECT COUNT(*) FROM {t}")
        count = c.fetchone()[0]
        print(f"  {t:<22} : {count} rows")

    conn.close()
    print("=" * 60)
    print("Database ready at:", DB_PATH)

if __name__ == "__main__":
    run_migration()
