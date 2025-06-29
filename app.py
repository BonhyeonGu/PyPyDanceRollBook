from flask import Flask, render_template, jsonify, request
import pymysql
import os
import json

app = Flask(__name__)

with open("web_config.json", "r", encoding="utf-8") as f:
    WEB_CONFIG = json.load(f)

DB_CONFIG = WEB_CONFIG["db"]
PROFILE_IMG_DIR = WEB_CONFIG["profile_img_dir"]

def get_top_attendees(limit=10):
    conn = pymysql.connect(**DB_CONFIG)
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT u.nickname, u.comment, uas.total_count, uas.last_attended
                FROM user_attendance_summary uas
                JOIN users u ON u.user_id = uas.user_id
                ORDER BY uas.total_count DESC, uas.last_attended DESC
                LIMIT %s
            """, (limit,))
            result = cursor.fetchall()
            return result
    finally:
        conn.close()

@app.route("/participants")
def participants_by_date():
    date_str = request.args.get("date")  # YYYY-MM-DD
    if not date_str:
        return jsonify([])

    conn = pymysql.connect(**DB_CONFIG)
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT u.nickname, u.comment, COALESCE(uas.total_count, 0),
                       MIN(a.enter_time), MAX(a.leave_time)
                FROM attendance a
                JOIN users u ON u.user_id = a.user_id
                LEFT JOIN user_attendance_summary uas ON u.user_id = uas.user_id
                WHERE DATE(a.enter_time) = %s
                GROUP BY u.user_id
                ORDER BY MIN(a.enter_time) ASC
            """, (date_str,))
            result = cursor.fetchall()
    finally:
        conn.close()

    users = []
    for r in result:
        nickname = r[0]
        comment = r[1]
        total_count = r[2]
        enter_time = r[3]
        leave_time = r[4]
        duration_min = int((leave_time - enter_time).total_seconds() // 60)

        img_filename = f"{nickname}.png"
        img_path = os.path.join(PROFILE_IMG_DIR, img_filename)
        if not os.path.exists(img_path):
            img_filename = "default.png"

        users.append({
            "nickname": nickname,
            "comment": comment,
            "total_count": total_count,
            "duration": duration_min,
            "img": f"/static/profiles/{img_filename}"
        })

    return jsonify(users)

@app.route("/music")
def music_by_date():
    date_str = request.args.get("date")
    if not date_str:
        return jsonify([])

    conn = pymysql.connect(**DB_CONFIG)
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT m.played_at, m.title, u.nickname
                FROM music_play m
                JOIN users u ON m.user_id = u.user_id
                WHERE DATE(m.played_at) = %s
                ORDER BY m.played_at ASC
            """, (date_str,))
            rows = cursor.fetchall()
            return jsonify([
                {
                    "played_at": r[0].strftime("%H:%M"),
                    "title": r[1],
                    "user": r[2]
                } for r in rows
            ])
    finally:
        conn.close()

@app.route("/popular-music")
def popular_music():
    conn = pymysql.connect(**DB_CONFIG)
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT title, COUNT(*) AS play_count
                FROM music_play
                WHERE played_at >= NOW() - INTERVAL 7 DAY
                GROUP BY title
                ORDER BY play_count DESC, MAX(played_at) DESC
                LIMIT 10
            """)
            rows = cursor.fetchall()
            return jsonify([
                { "title": r[0], "count": r[1] }
                for r in rows
            ])
    finally:
        conn.close()

@app.route("/user")
def user_profile():
    nickname = request.args.get("nickname")
    if not nickname:
        return jsonify({"error": "닉네임 없음"}), 400

    conn = pymysql.connect(**DB_CONFIG)
    try:
        with conn.cursor() as cursor:
            # 1️⃣ 사용자 기본 정보 가져오기
            cursor.execute("""
                SELECT u.user_id, u.nickname, u.comment, COALESCE(uas.total_count, 0), uas.last_attended
                FROM users u
                LEFT JOIN user_attendance_summary uas ON u.user_id = uas.user_id
                WHERE u.nickname = %s
                LIMIT 1
            """, (nickname,))
            result = cursor.fetchone()
            if not result:
                return jsonify({"error": "사용자 없음"}), 404

            user_id = result[0]
            nickname = result[1]  # 실제 대소문자 포함된 닉네임 재지정

            img_filename = f"{nickname}.png"
            img_path = os.path.join(PROFILE_IMG_DIR, img_filename)
            if not os.path.exists(img_path):
                img_filename = "default.png"

            # 2️⃣ 도전과제 목록 가져오기
            cursor.execute("""
                SELECT a.name, a.description, DATE(ua.achieved_at)
                FROM user_achievements ua
                JOIN achievements a ON ua.achievement_id = a.achievement_id
                WHERE ua.user_id = %s
            """, (user_id,))
            achievements = [
                {"name": row[0], "description": row[1], "achieved_at": row[2].strftime("%Y-%m-%d")}
                for row in cursor.fetchall()
            ]

            cursor.execute("""
                SELECT
                    (SELECT COALESCE(SUM(duration_sec), 0) FROM attendance WHERE user_id = %s),
                    (SELECT COUNT(*) FROM music_play WHERE user_id = %s)
            """, (user_id, user_id))
            play_duration_sec, song_play_count = cursor.fetchone()
            

            # 3️⃣ 응답 JSON
            return jsonify({
                "nickname": nickname,
                "comment": result[2],
                "total_count": result[3],
                "last_attended": result[4].strftime("%Y-%m-%d %H:%M") if result[4] else None,
                "img": f"/static/profiles/{img_filename}",
                "achievements": achievements,
                "play_duration_sec": play_duration_sec,
                "song_play_count": song_play_count
            })

    finally:
        conn.close()

@app.route("/")
def index():
    conn = pymysql.connect(**DB_CONFIG)
    try:
        with conn.cursor() as cursor:
            # 1️⃣ 누적 출석 상위 10명
            cursor.execute("""
                SELECT u.user_id, u.nickname, u.comment, COALESCE(uas.total_count, 0), uas.last_attended
                FROM user_attendance_summary uas
                JOIN users u ON u.user_id = uas.user_id
                ORDER BY uas.total_count DESC, uas.last_attended DESC
                LIMIT 10
            """)
            rows = cursor.fetchall()

            users = []
            ranking_user_ids = set()
            for rank, row in enumerate(rows, start=1):
                user_id, nickname, comment, total_count, last_attended = row
                ranking_user_ids.add(user_id)

                # 도전과제
                cursor.execute("""
                    SELECT a.name, a.description, DATE(ua.achieved_at)
                    FROM user_achievements ua
                    JOIN achievements a ON ua.achievement_id = a.achievement_id
                    WHERE ua.user_id = %s
                """, (user_id,))
                achievements = [
                    {"name": a[0], "description": a[1], "achieved_at": a[2].strftime("%Y-%m-%d")}
                    for a in cursor.fetchall()
                ]

                # 이미지
                img_filename = f"{nickname}.png"
                img_path = os.path.join(PROFILE_IMG_DIR, img_filename)
                if not os.path.exists(img_path):
                    img_filename = "default.png"

                users.append({
                    "rank": rank,
                    "nickname": nickname,
                    "comment": comment,
                    "total_count": total_count,
                    "last_attended": last_attended,
                    "img": f"/static/profiles/{img_filename}",
                    "achievements": achievements
                })

            # 2️⃣ 랭킹에 없는 유저 6명 랜덤으로 뽑되, '아짱나'는 제외
            placeholders = ",".join(str(uid) for uid in ranking_user_ids)
            cursor.execute(f"""
                SELECT u.user_id, u.nickname, u.comment, COALESCE(uas.total_count, 0), uas.last_attended
                FROM users u
                LEFT JOIN user_attendance_summary uas ON u.user_id = uas.user_id
                WHERE u.user_id NOT IN ({placeholders})
                AND u.nickname != %s
                ORDER BY RAND()
                LIMIT 6
            """, ("아짱나",))
            random_users = cursor.fetchall()
            
            thanks_users = []
            for row in random_users:
                user_id, nickname, comment, total_count, last_attended = row

                # 도전과제 조회
                cursor.execute("""
                    SELECT a.name, a.description, DATE(ua.achieved_at)
                    FROM user_achievements ua
                    JOIN achievements a ON ua.achievement_id = a.achievement_id
                    WHERE ua.user_id = %s
                """, (user_id,))
                achievements = [
                    {"name": a[0], "description": a[1], "achieved_at": a[2].strftime("%Y-%m-%d")}
                    for a in cursor.fetchall()
                ]

                img_filename = f"{nickname}.png"
                img_path = os.path.join(PROFILE_IMG_DIR, img_filename)
                if not os.path.exists(img_path):
                    img_filename = "default.png"

                thanks_users.append({
                    "nickname": nickname,
                    "comment": comment,
                    "total_count": total_count,
                    "last_attended": last_attended,
                    "img": f"/static/profiles/{img_filename}",
                    "achievements": achievements
                })

            return render_template("index.html", users=users, thanks_users=thanks_users)
    finally:
        conn.close()


if __name__ == "__main__":
    app.run(host='0.0.0.0', debug=True)