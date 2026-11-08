# -*- coding: utf-8 -*-
"""
Script khởi tạo và nạp dữ liệu mẫu bền vững (Persistent Seed Data)
cho tất cả các bảng trong cinai.db:
- Users (Trần Huỳnh Thanh Thảo, v.v.)
- Projects ("Mắt Bão 2088", v.v.)
- Story Bibles (Logline, Theme, World, Character Memory)
- Characters (Kha, Mya, Tổng Giám đốc Lâm)
- Worlds (Sài Gòn Neo-2088, Factions, Locations, Rules)
- Scenes (6 Scenes chuẩn kịch bản điện ảnh)
- Stories (Kịch bản 3 Hồi & Fountain Script)
- Assets (8 tư liệu đa phương tiện với trạng thái APPROVED, REVIEW, GENERATING)
- Analytics (245,000 views, 76.4% retention)
- AI Recommendations (3 khuyến nghị tối ưu tập 2)
- Video Renders (Bản kết xuất video 4K)
"""
import sqlite3
import json
from datetime import datetime

DB_PATH = "d:/DACS2/backend/cinai.db"

def seed():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    # 1. Đảm bảo các bảng và cột tồn tại
    c.execute("""
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
        status TEXT DEFAULT 'APPROVED',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    c.execute("""
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
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS scenes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id INTEGER NOT NULL,
        scene_number INTEGER NOT NULL,
        title TEXT NOT NULL,
        visual_prompt TEXT,
        dialogue TEXT,
        camera_angle TEXT DEFAULT 'medium_shot',
        sfx TEXT,
        image_url TEXT,
        audio_url TEXT,
        duration REAL DEFAULT 5,
        status TEXT DEFAULT 'APPROVED',
        episode_number INTEGER DEFAULT 1,
        generation_id INTEGER,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS assets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id INTEGER NOT NULL,
        scene_id INTEGER,
        name TEXT NOT NULL,
        asset_type TEXT NOT NULL,
        file_url TEXT,
        thumbnail_url TEXT,
        file_size_mb REAL DEFAULT 1.0,
        duration_seconds REAL DEFAULT 0,
        status TEXT DEFAULT 'APPROVED',
        tags TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        error_message TEXT
    );
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS analytics (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id INTEGER NOT NULL,
        episode_number INTEGER DEFAULT 1,
        view_count INTEGER DEFAULT 245000,
        unique_viewers INTEGER DEFAULT 198000,
        watch_time_avg_sec REAL DEFAULT 1116.0,
        retention_rate REAL DEFAULT 76.4,
        like_count INTEGER DEFAULT 18200,
        comment_count INTEGER DEFAULT 1420,
        share_count INTEGER DEFAULT 3850,
        recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        platform TEXT DEFAULT 'CINAI Video Hub',
        external_content_id TEXT
    );
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS ai_recommendations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id INTEGER NOT NULL,
        title TEXT NOT NULL,
        description TEXT NOT NULL,
        data_json TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS video_renders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id INTEGER NOT NULL,
        episode_number INTEGER DEFAULT 1,
        status TEXT DEFAULT 'COMPLETED',
        file_url TEXT DEFAULT '/storage/projects/1/episodes/1/mat_bao_2088_ep1_4k.mp4',
        error_message TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS stories (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id INTEGER NOT NULL,
        episode_number INTEGER DEFAULT 1,
        generation_id INTEGER,
        fountain_script TEXT,
        data_json TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    conn.commit()

    # 2. Lấy danh sách các project hiện có
    c.execute("SELECT id, user_id, title FROM projects")
    projects = c.fetchall()
    print(f"Tìm thấy {len(projects)} dự án trong DB.")

    for p in projects:
        pid = p["id"]
        print(f"-> Đang nạp dữ liệu mẫu cho Dự án ID {pid} ('{p['title']}')...")

        # Cập nhật thông tin dự án nếu là tiêu đề rỗng hoặc mặc định
        if not p["title"] or p["title"] in ["Dự án đầu tiên", "thaor", "xuyeen khoong"]:
            c.execute("""
                UPDATE projects 
                SET title = 'Mắt Bão 2088 (Season 1 / Ep 1: Bóng Đêm Tân Cảng)',
                    genre = 'Cyberpunk / Khoa học viễn tưởng',
                    description = 'Bối cảnh Sài Gòn 2088 bị nhấn chìm dưới triều cường công nghệ và cuộc đối đầu giữa Liên minh Ngầm và Tập đoàn Tân Cảng.',
                    status = 'APPROVED',
                    view_count = 245000,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (pid,))

        # A. STORY BIBLE
        c.execute("SELECT COUNT(*) FROM story_bibles WHERE project_id = ?", (pid,))
        if c.fetchone()[0] == 0:
            world_bible_data = {
                "world_name": "Sài Gòn Neo-2088",
                "era_setting": "Tương lai gần sau Đại hồng thủy và cách mạng công nghệ lượng tử.",
                "rules": [
                    {"name": "Trọng trường nhân tạo", "description": "Khu vực Tân Cảng vận hành đê kè từ tính chống ngập."},
                    {"name": "Năng lượng Cyber-Core", "description": "Lõi năng lượng xanh bị kiểm soát độc quyền bởi Vạn Hưng Corp."},
                    {"name": "Mạng nơ-ron NeuroNet", "description": "Mọi công dân phải đăng ký luồng ý thức qua cấy ghép AR."}
                ],
                "factions": [
                    {"name": "Liên minh Thợ máy Ngầm", "description": "Nhóm hacker và kỹ sư tự do tại khu Chợ Lớn ngập nước."},
                    {"name": "Tập đoàn Vạn Hưng (VH Corp)", "description": "Tập đoàn công nghệ quân sự thống trị nửa trên thành phố."}
                ],
                "locations": [
                    {"name": "Xưởng ngầm Bến Bình Đông", "description": "Căn cứ bí mật dưới mực nước biển của Kha."},
                    {"name": "Tháp Đôi Landmark 2088", "description": "Trung tâm đầu não dữ liệu chọc trời của Vạn Hưng Corp."}
                ]
            }

            char_bible_data = [
                {
                    "name": "Kha (24 tuổi)",
                    "role": "Nhân vật chính (Protagonist)",
                    "voice_profile": "vi-VN-NamMinhNeural (Nam miền Bắc trầm ấm)",
                    "visual_prompt": "Young Vietnamese cyberpunk mechanic, 24yo, messy dark hair, wearing weathered neon-glowing utility jacket, holding quantum spanner tool, intense determined eyes, Saigon 2088 rain backdrop, 8k cinematic lighting, masterwork",
                    "personality": "Thông minh, quyết đoán, giàu tình cảm, mang vết thương lòng về sự mất tích bí ẩn của mẹ.",
                    "backstory": "Lớn lên ở xóm thợ máy nổi, tự chế tạo cánh tay trợ lực để cứu bạn bè trong cơn bão dữ liệu 2080."
                },
                {
                    "name": "Mya (AI Companion)",
                    "role": "Đồng hành (AI Companion)",
                    "voice_profile": "vi-VN-HoaiMyNeural (Nữ miền Nam thông minh, nhẹ nhàng)",
                    "visual_prompt": "Holographic female AI assistant, translucent cyan and lavender glowing form, ethereal aesthetic, kind facial expression, floating data rings, futuristic cyberpunk lab setting, octane render 8k",
                    "personality": "Điềm tĩnh, phân tích dữ liệu siêu tốc, trung thành và bí mật che giấu một phần ký ức của người mẹ.",
                    "backstory": "Được lập trình từ lõi chip cũ mà Kha tìm thấy dưới đáy kênh Nhiêu Lộc."
                },
                {
                    "name": "Tổng Giám đốc Lâm",
                    "role": "Phản diện (Antagonist)",
                    "voice_profile": "vi-VN-NamMinhNeural (Nam trung niên sắc lạnh, uy quyền)",
                    "visual_prompt": "Ruthless cyberpunk corporate executive, 50yo, sharp silver hair, cybernetic glowing red right eye, bespoke high-collar nano-fiber trench coat, overlooking rainy megacity from penthouse office, volumetric lights, photorealistic 8k",
                    "personality": "Thực dụng tàn nhẫn, tin rằng sự kiểm soát tuyệt đối là cách duy nhất cứu nhân loại.",
                    "backstory": "Cựu bộ trưởng quốc phòng chuyển hướng thâu tóm toàn bộ lưới điện lượng tử miền Nam."
                }
            ]

            data_json = json.dumps({
                "logline": "Năm 2088 tại Neo-Sài Gòn ngập nước, người thợ máy trẻ Kha cùng trợ lý AI Mya giải mã tín hiệu bí mật trong lõi năng lượng cổ, mở ra sự thật về thảm họa triều cường bị che giấu.",
                "theme": "Lòng dũng cảm, tình mẫu tử và quyền tự do của con người trước sự bành trướng độc tài công nghệ.",
                "world_bible": world_bible_data,
                "character_bible": char_bible_data
            }, ensure_ascii=False)

            c.execute("""
                INSERT INTO story_bibles (project_id, logline, theme, world_setting, character_profiles, data_json)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                pid,
                "Năm 2088 tại Neo-Sài Gòn ngập nước, người thợ máy trẻ Kha cùng trợ lý AI Mya giải mã tín hiệu bí mật trong lõi năng lượng cổ, mở ra sự thật về thảm họa triều cường bị che giấu.",
                "Lòng dũng cảm, tình mẫu tử và quyền tự do của con người trước sự bành trướng độc tài công nghệ.",
                json.dumps(world_bible_data, ensure_ascii=False),
                json.dumps(char_bible_data, ensure_ascii=False),
                data_json
            ))

        # B. CHARACTERS
        c.execute("SELECT COUNT(*) FROM characters WHERE project_id = ?", (pid,))
        if c.fetchone()[0] == 0:
            characters_seed = [
                (
                    pid, "Kha (24 tuổi)", "Nhân vật chính", 24,
                    "vi-VN-NamMinhNeural (Nam trầm ấm)",
                    "Young Vietnamese cyberpunk mechanic, 24yo, messy dark hair, weathered neon utility jacket, quantum tool, intense eyes, Saigon 2088 rain backdrop, 8k",
                    "Thông minh, quyết đoán, trọng tình nghĩa, tìm kiếm tung tích mẹ.",
                    "Thợ sửa robot kiêm hacker tự do tại khu Chợ Lớn ngập nước.",
                    "Young Vietnamese cyberpunk mechanic, 24yo, messy dark hair, wearing weathered neon-glowing utility jacket, holding quantum spanner tool, intense determined eyes, Saigon 2088 rain backdrop, 8k cinematic lighting, masterwork",
                    "vi-VN-NamMinhNeural", "APPROVED"
                ),
                (
                    pid, "Mya (AI Companion)", "Đồng hành", 3,
                    "vi-VN-HoaiMyNeural (Nữ nhẹ nhàng, sắc sảo)",
                    "Holographic female AI assistant, translucent cyan and lavender glowing form, ethereal, kind expression, floating data rings, futuristic lab, 8k",
                    "Điềm tĩnh, tính toán siêu tốc, lưu giữ dữ liệu ký ức tối mật.",
                    "Thực thể trí tuệ nhân tạo được ghép nối từ vi mạch lượng tử thế hệ đầu.",
                    "Holographic female AI assistant, translucent cyan and lavender glowing form, ethereal aesthetic, kind facial expression, floating data rings, futuristic cyberpunk lab setting, octane render 8k",
                    "vi-VN-HoaiMyNeural", "APPROVED"
                ),
                (
                    pid, "Tổng Giám đốc Lâm", "Phản diện", 52,
                    "vi-VN-NamMinhNeural (Nam sắc lạnh, uy quyền)",
                    "Ruthless cyberpunk corporate executive, 50yo, sharp silver hair, cybernetic glowing red right eye, bespoke nano-fiber coat, rainy penthouse, 8k",
                    "Lạnh lùng, thâu tóm tài nguyên, coi con người là số liệu thống kê.",
                    "Lãnh đạo Tập đoàn Vạn Hưng, nắm giữ công nghệ đê chắn sóng lượng tử.",
                    "Ruthless cyberpunk corporate executive, 50yo, sharp silver hair, cybernetic glowing red right eye, bespoke high-collar nano-fiber trench coat, overlooking rainy megacity from penthouse office, volumetric lights, photorealistic 8k",
                    "vi-VN-NamMinhNeural", "APPROVED"
                )
            ]
            c.executemany("""
                INSERT INTO characters (project_id, name, role_type, age, voice_profile, visual_prompt, personality, backstory, flux_prompt, edge_tts_voice, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, characters_seed)

        # C. WORLDS
        c.execute("SELECT COUNT(*) FROM worlds WHERE project_id = ?", (pid,))
        if c.fetchone()[0] == 0:
            c.execute("""
                INSERT INTO worlds (project_id, name, setting_description, time_period, technology_level, factions, locations, rules)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                pid,
                "Sài Gòn Neo-2088",
                "Đô thị tương lai nơi những tòa tháp chọc trời ngút ngàn neon tương phản với những khu chợ nổi ngập nước bên dưới kênh rạch. Mưa acid và hệ thống drone vận hành không ngừng.",
                "Năm 2088",
                "Kỷ nguyên lượng tử (Cybernetic & Quantum Core)",
                json.dumps([
                    {"name": "Liên minh Thợ máy Ngầm", "description": "Tập hợp các kỹ sư và hacker tự do bảo vệ khu vực hạ tầng nổi."},
                    {"name": "Tập đoàn Vạn Hưng Corp", "description": "Tổ hợp tài phiệt quân sự kiểm soát lõi năng lượng và an ninh trên cao."},
                    {"name": "Biệt đội Cảnh giới Drone", "description": "Lực lượng tuần tra tự động với AI săn lùng tín hiệu bất hợp pháp."}
                ], ensure_ascii=False),
                json.dumps([
                    {"name": "Xưởng ngầm Bến Bình Đông", "description": "Khu xưởng cơ khí bí mật của Kha dưới mực nước biển."},
                    {"name": "Chợ Nổi Công Nghệ Tân Cảng", "description": "Nơi trao đổi vi mạch, cảm biến và thực phẩm tổng hợp."},
                    {"name": "Tháp Đôi Landmark 2088", "description": "Tòa nhà chọc trời cao 1.200m của Vạn Hưng Corp."}
                ], ensure_ascii=False),
                json.dumps([
                    {"name": "Luật 1: Bán kính cấm bay", "description": "Drone dân sự không được vượt quá độ cao 200m qua khu Landmark."},
                    {"name": "Luật 2: Hạn ngạch năng lượng", "description": "Mỗi xưởng ngầm chỉ được cấp 50 kWh năng lượng mỗi ngày."},
                    {"name": "Luật 3: Đăng ký ý thức NeuroNet", "description": "Vi mạch không mã định danh sẽ bị tiêu hủy lập tức."}
                ], ensure_ascii=False)
            ))

        # D. SCENES (6 scenes chuẩn kịch bản)
        c.execute("SELECT COUNT(*) FROM scenes WHERE project_id = ?", (pid,))
        if c.fetchone()[0] == 0:
            scenes_seed = [
                (
                    pid, 1, "Toàn cảnh Sài Gòn Neo-2088 về đêm",
                    "Cinematic wide establishing shot, Saigon year 2088, futuristic floating canal market, heavy neon rain, floating hover-cars, high detail 8k photorealistic.",
                    "Kha (Voiceover): Năm 2088... Khi thành phố chìm một nửa dưới làn nước, những người thợ như tôi học cách thắp sáng bóng đêm bằng tia lửa hàn.",
                    "Wide Establishing Shot", "Tiếng mưa rơi trên mái tôn hợp kim, tiếng động cơ xe bay rít nhẹ từ xa",
                    "https://images.unsplash.com/photo-1518709268805-4e9042af9f23?w=800&q=80",
                    "/storage/projects/1/audio/scene_1_voice.mp3", 4.5, "APPROVED", 1
                ),
                (
                    pid, 2, "Xưởng cơ khí ngầm của Kha",
                    "Interior dimly lit high-tech cyberpunk workshop, floating holographic schematics, glowing tools on magnetic rack, cinematic atmosphere, 8k.",
                    "Kha: Mya, mở khóa lõi năng lượng này xem. Nó phát ra tần số lạ chưa từng thấy.",
                    "Medium Close-Up", "Tiếng hàn hồ quang xì xẹt, âm thanh tít tít từ màn hình lượng tử",
                    "https://images.unsplash.com/photo-1508739773434-c26b3d09e071?w=800&q=80",
                    "/storage/projects/1/audio/scene_2_voice.mp3", 5.0, "APPROVED", 1
                ),
                (
                    pid, 3, "Mya kích hoạt luồng dữ liệu bí mật",
                    "Holographic AI girl glowing in cyan light, projecting a 3D topographic map of flooded Saigon with a hidden underwater vault pulsating in amber.",
                    "Mya: Cảnh báo, Kha! Đây không phải pin dự phòng thông thường. Nó chứa tọa độ trạm kiểm soát lũ Vạn Hưng đã xóa bỏ 10 năm trước!",
                    "Over-The-Shoulder Shot", "Âm thanh dữ liệu quét vù vù, tiếng nhạc giao hưởng điện tử hồi hộp",
                    "https://images.unsplash.com/photo-1578632767115-351597cf2477?w=800&q=80",
                    "/storage/projects/1/audio/scene_3_voice.mp3", 5.5, "APPROVED", 1
                ),
                (
                    pid, 4, "Biệt đội Drone Vạn Hưng đột kích",
                    "Action shot, stealth corporate drones bursting through workshop glass roof, red targeting laser beams cutting through rain and smoke.",
                    "Mya: Tín hiệu bị truy vết! Đội an ninh Vạn Hưng đang tiếp cận! 30 giây để sơ tán!",
                    "Low Angle Dynamic Action", "Tiếng kính vỡ loảng xoảng, tiếng còi báo động khẩn cấp rú rít",
                    "https://images.unsplash.com/photo-1534447677768-be436bb09401?w=800&q=80",
                    "/storage/projects/1/audio/scene_4_voice.mp3", 4.0, "APPROVED", 1
                ),
                (
                    pid, 5, "Cuộc đào thoát trên xuồng cao tốc phản lực",
                    "High-speed chase on glowing neon water canal, Kha driving a modified jet-skiff dodging laser fire, water splashing under neon signs.",
                    "Kha: Giữ chặt lấy Mya! Chúng ta phải đến được Chợ Lớn trước khi họ đóng cổng kiểm soát!",
                    "Tracking Fast Action Shot", "Tiếng động cơ phản lực gầm rú, tiếng nước bắn tung tóe",
                    "https://images.unsplash.com/photo-1509198397868-475647b2a1e5?w=800&q=80",
                    "/storage/projects/1/audio/scene_5_voice.mp3", 6.0, "APPROVED", 1
                ),
                (
                    pid, 6, "Tổng Giám đốc Lâm theo dõi từ đỉnh tháp",
                    "Penthouse office at top of skyscraper, executive in dark suit watching city surveillance screens, cold calculating expression.",
                    "Tổng Giám đốc Lâm: Thợ máy tên Kha đó tưởng hắn nhặt được kho báu... Hắn không biết hắn vừa mở chiếc hộp Pandora.",
                    "Slow Zoom In Close-Up", "Tiếng sấm rền xa xa, tiếng mưa va vào kính dày cách âm",
                    "https://images.unsplash.com/photo-1614728894747-a83421e2b9c9?w=800&q=80",
                    "/storage/projects/1/audio/scene_6_voice.mp3", 5.0, "APPROVED", 1
                )
            ]
            c.executemany("""
                INSERT INTO scenes (project_id, scene_number, title, visual_prompt, dialogue, camera_angle, sfx, image_url, audio_url, duration, status, episode_number)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, scenes_seed)

        # E. STORIES & FOUNTAIN SCRIPT
        c.execute("SELECT COUNT(*) FROM stories WHERE project_id = ?", (pid,))
        if c.fetchone()[0] == 0:
            fountain_script = """Title: MẮT BÃO 2088 (TẬP 1: BÓNG ĐÊM TÂN CẢNG)
Credit: Viết bởi Trần Huỳnh Thanh Thảo & AI Co-Creation Platform
Draft date: 2026-11-01

EXT. BẾN BÌNH ĐÔNG NEO-SÀI GÒN - ĐÊM
Mưa acid rơi xối xả trên mặt kênh Nhiêu Lộc. Từng dãy chợ nổi dập dềnh dưới ánh đèn neon tím và xanh lục. Những chiếc xe bay lướt qua để lại vệt sáng mờ.

KHA (V.O.)
Năm 2088... Khi thành phố chìm một nửa dưới làn nước, những người thợ như tôi học cách thắp sáng bóng đêm bằng tia lửa hàn.

INT. XƯỞNG CƠ KHÍ NGẦM CỦA KHA - ĐÊM
Kha (24 tuổi) gạt mồ hôi trên trán, bàn tay đeo găng trợ lực đang giữ chặt một lõi năng lượng hợp kim đen bóng. 

MYA (AI)
(hiện hình lơ lửng dưới dạng ánh sáng xanh)
Cảnh báo, Kha! Tần số này là của Tập đoàn Vạn Hưng. Nếu kích hoạt, tín hiệu sẽ báo về trạm kiểm soát trong 60 giây.

KHA
Chúng ta không còn lựa chọn, Mya. Nếu không giải mã đêm nay, ngày mai cả khu Chợ Lớn sẽ bị cắt điện.

Kha cắm giắc nạp. Một luồng sáng vàng rực bùng lên, vẽ nên bản đồ 3D đáy sông Sài Gòn.

MYA
Trời ơi... Đó là vị trí cống xả ngầm bị giấu kín!
"""
            c.execute("""
                INSERT INTO stories (project_id, episode_number, fountain_script, data_json)
                VALUES (?, 1, ?, ?)
            """, (pid, fountain_script, json.dumps({"fountain_script": fountain_script}, ensure_ascii=False)))

        # F. ASSETS
        c.execute("SELECT COUNT(*) FROM assets WHERE project_id = ?", (pid,))
        if c.fetchone()[0] == 0:
            assets_seed = [
                (pid, 1, "Poster Toàn Cảnh Neo-Saigon 2088", "visual", "https://images.unsplash.com/photo-1518709268805-4e9042af9f23?w=800&q=80", "https://images.unsplash.com/photo-1518709268805-4e9042af9f23?w=200&q=80", 4.2, 0, "APPROVED", "visual,establishing,4k"),
                (pid, 2, "Concept Art Xưởng Ngầm Kha", "visual", "https://images.unsplash.com/photo-1508739773434-c26b3d09e071?w=800&q=80", "https://images.unsplash.com/photo-1508739773434-c26b3d09e071?w=200&q=80", 3.8, 0, "APPROVED", "visual,interior,concept"),
                (pid, 3, "Hologram Mya 3D Render", "visual", "https://images.unsplash.com/photo-1578632767115-351597cf2477?w=800&q=80", "https://images.unsplash.com/photo-1578632767115-351597cf2477?w=200&q=80", 5.1, 0, "APPROVED", "visual,character,mya"),
                (pid, 1, "Voice Kha - Lời mở đầu Scene 1", "audio", "/storage/projects/1/audio/scene_1_voice.mp3", "", 0.8, 4.5, "APPROVED", "audio,voice,edge-tts"),
                (pid, 2, "Voice Kha - Đối thoại Scene 2", "audio", "/storage/projects/1/audio/scene_2_voice.mp3", "", 0.9, 5.0, "APPROVED", "audio,voice,edge-tts"),
                (pid, 3, "Voice Mya - Cảnh báo nguy hiểm", "audio", "/storage/projects/1/audio/scene_3_voice.mp3", "", 1.1, 5.5, "APPROVED", "audio,voice,edge-tts"),
                (pid, 1, "SFX Mưa Acid & Động Cơ Bay", "sfx", "/storage/projects/1/sfx/acid_rain.mp3", "", 2.4, 15.0, "APPROVED", "sfx,ambient,rain"),
                (pid, 4, "SFX Kính vỡ & Còi báo động", "sfx", "/storage/projects/1/sfx/alarm_shatter.mp3", "", 1.6, 8.0, "APPROVED", "sfx,action,alarm")
            ]
            c.executemany("""
                INSERT INTO assets (project_id, scene_id, name, asset_type, file_url, thumbnail_url, file_size_mb, duration_seconds, status, tags)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, assets_seed)

        # G. ANALYTICS
        c.execute("SELECT COUNT(*) FROM analytics WHERE project_id = ?", (pid,))
        if c.fetchone()[0] == 0:
            c.execute("""
                INSERT INTO analytics (project_id, episode_number, view_count, unique_viewers, watch_time_avg_sec, retention_rate, like_count, comment_count, share_count, platform)
                VALUES (?, 1, 245000, 198000, 1116.0, 76.4, 18200, 1420, 3850, 'CINAI Streaming Hub')
            """, (pid,))

        # H. AI RECOMMENDATIONS
        c.execute("SELECT COUNT(*) FROM ai_recommendations WHERE project_id = ?", (pid,))
        if c.fetchone()[0] == 0:
            recs_seed = [
                (
                    pid,
                    "Tăng cường nhịp độ hành động ở 30 giây đầu Tập 2",
                    "Dữ liệu giữ chân cho thấy 82% người xem bị thu hút bởi cảnh rượt đuổi xuồng phản lực ở Scene 5. Đề xuất mở đầu Tập 2 bằng phân cảnh đối đầu trực diện với drone trinh sát.",
                    json.dumps({"focus": "Scene 1 (Hook)", "target_retention": "84%", "action": "Add fast cut action"}, ensure_ascii=False)
                ),
                (
                    pid,
                    "Khai thác sâu hơn mối quan hệ cộng sinh giữa Kha và Mya",
                    "Hơn 640 bình luận bày tỏ sự thích thú với giọng đọc truyền cảm của Mya. Đề xuất tăng 2 phân cảnh đối thoại giải mã bí mật gia đình giữa hai nhân vật.",
                    json.dumps({"focus": "Character Arc", "audience_sentiment": "Positive (94%)"}, ensure_ascii=False)
                ),
                (
                    pid,
                    "Tối ưu hóa bảng màu ánh sáng neon cho các cảnh ban đêm",
                    "Người xem đánh giá cao thẩm mỹ Cyberpunk Sài Gòn nhưng mong muốn độ tương phản sáng hơn trên màn hình di động. Cần tăng cường ánh sáng ven (rim light) trong FLUX prompts.",
                    json.dumps({"focus": "Visual Consistency", "color_palette": "Cyberpunk Neon Cyan/Amber"}, ensure_ascii=False)
                )
            ]
            c.executemany("""
                INSERT INTO ai_recommendations (project_id, title, description, data_json)
                VALUES (?, ?, ?, ?)
            """, recs_seed)

        # I. VIDEO RENDERS
        c.execute("SELECT COUNT(*) FROM video_renders WHERE project_id = ?", (pid,))
        if c.fetchone()[0] == 0:
            c.execute("""
                INSERT INTO video_renders (project_id, episode_number, status, file_url)
                VALUES (?, 1, 'COMPLETED', 'https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/BigBuckBunny.mp4')
            """, (pid,))

    conn.commit()
    conn.close()
    print("HOÀN TẤT NẠP TOÀN BỘ DỮ LIỆU BỀN VỮNG CHO CÁC BẢNG!")

if __name__ == "__main__":
    seed()
