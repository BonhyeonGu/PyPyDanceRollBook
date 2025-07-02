from flask import Flask, render_template, jsonify, request, send_from_directory
import pymysql
import os
import json
from datetime import date, timedelta

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

@app.route("/api/date/participants")
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

@app.route("/api/date/music")
def music_by_date():
    date_str = request.args.get("date")
    if not date_str:
        return jsonify([])

    conn = pymysql.connect(**DB_CONFIG)
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT m.played_at, m.title, m.url, u.nickname
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
                    "url": r[2],
                    "user": r[3]
                } for r in rows
            ])
    finally:
        conn.close()

@app.route("/api/popular-music")
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

def get_user_info_by_nickname(cursor, nickname):
    cursor.execute("""
        SELECT u.user_id, u.nickname, u.comment, COALESCE(uas.total_count, 0), uas.last_attended
        FROM users u
        LEFT JOIN user_attendance_summary uas ON u.user_id = uas.user_id
        WHERE u.nickname = %s
        LIMIT 1
    """, (nickname,))
    row = cursor.fetchone()
    if not row:
        return None

    user_id, nickname, comment, total_count, last_attended = row

    # 도전과제
    cursor.execute("""
        SELECT a.name, a.description, DATE(ua.achieved_at)
        FROM user_achievements ua
        JOIN achievements a ON ua.achievement_id = a.achievement_id
        WHERE ua.user_id = %s
        ORDER BY ua.achieved_at DESC
    """, (user_id,))
    achievements = [
        {"name": r[0], "description": r[1], "achieved_at": r[2].strftime("%Y-%m-%d")}
        for r in cursor.fetchall()
    ]

    # 프로필 이미지
    img_filename = f"{nickname}.png"
    img_path = os.path.join(PROFILE_IMG_DIR, img_filename)
    if not os.path.exists(img_path):
        img_filename = "default.png"

    return {
        "user_id": user_id,
        "nickname": nickname,
        "comment": comment,
        "total_count": total_count,
        "last_attended": last_attended.strftime("%Y-%m-%d %H:%M") if last_attended else None,
        "img": f"/static/profiles/{img_filename}",
        "achievements": achievements,
    }


@app.route("/api/user-details")
def user_details():
    nickname = request.args.get("nickname")
    if not nickname:
        return jsonify({"error": "닉네임 없음"}), 400

    conn = pymysql.connect(**DB_CONFIG)
    try:
        with conn.cursor() as cursor:
            info = get_user_info_by_nickname(cursor, nickname)
            if not info:
                return jsonify({"error": "사용자 없음"}), 404

            user_id = info["user_id"]

            # ✅ 재생시간, 곡 수
            cursor.execute("""
                SELECT
                    (SELECT COALESCE(SUM(duration_sec), 0) FROM attendance WHERE user_id = %s),
                    (SELECT COUNT(*) FROM music_play WHERE user_id = %s)
            """, (user_id, user_id))
            play_duration_sec, song_play_count = cursor.fetchone()

            # ✅ 최근 30일 활동
            cursor.execute("""
                SELECT DATE(enter_time) AS day, SUM(duration_sec)
                FROM attendance
                WHERE user_id = %s AND enter_time >= CURDATE() - INTERVAL 30 DAY
                GROUP BY day
                ORDER BY day ASC
            """, (user_id,))
            raw = cursor.fetchall()
            activity_map = {r[0]: r[1] for r in raw}

            today = date.today()
            recent_30days = [
                {
                    "date": (today - timedelta(days=29 - i)).strftime("%Y-%m-%d"),
                    "duration_sec": activity_map.get(today - timedelta(days=29 - i), 0)
                }
                for i in range(30)
            ]

            # ✅ 통합 결과
            info["play_duration_sec"] = play_duration_sec
            info["song_play_count"] = song_play_count
            info["recent_30days"] = recent_30days

            return jsonify(info)

    finally:
        conn.close()

@app.route("/api/ranking-users")
def ranking_users():
    conn = pymysql.connect(**DB_CONFIG)
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT u.nickname
                FROM user_attendance_summary uas
                JOIN users u ON u.user_id = uas.user_id
                ORDER BY uas.total_count DESC, uas.last_attended DESC
                LIMIT 10
            """)
            nicknames = [row[0] for row in cursor.fetchall()]

            users = []
            for rank, nickname in enumerate(nicknames, start=1):
                info = get_user_info_by_nickname(cursor, nickname)
                if info:
                    info["rank"] = rank
                    users.append(info)

            return jsonify(users)
    finally:
        conn.close()

@app.route("/api/random-users")
def random_users():
    excluded_ids = request.args.getlist("excluded_ids")  # 예: ?excluded_ids=3&excluded_ids=7
    excluded_nicks = ("아짱나", "미쿠")

    conn = pymysql.connect(**DB_CONFIG)
    try:
        with conn.cursor() as cursor:
            # 1. 무작위 닉네임 6개 선택
            if excluded_ids:
                placeholders = ",".join(["%s"] * len(excluded_ids))
                nick_placeholders = ",".join(["%s"] * len(excluded_nicks))
                query = f"""
                    SELECT u.nickname
                    FROM users u
                    WHERE u.user_id NOT IN ({placeholders})
                    AND u.nickname NOT IN ({nick_placeholders})
                    ORDER BY RAND()
                    LIMIT 6
                """
                cursor.execute(query, excluded_ids + list(excluded_nicks))
            else:
                query = f"""
                    SELECT u.nickname
                    FROM users u
                    WHERE u.nickname NOT IN ({','.join(['%s'] * len(excluded_nicks))})
                    ORDER BY RAND()
                    LIMIT 6
                """
                cursor.execute(query, excluded_nicks)

            nicknames = [row[0] for row in cursor.fetchall()]

            # 2. 닉네임 기반으로 유저 정보 구성
            users = []
            for nickname in nicknames:
                info = get_user_info_by_nickname(cursor, nickname)
                if info:
                    users.append(info)

            return jsonify(users)
    finally:
        conn.close()


@app.route("/api/achievements")
def get_achievements():
    conn = pymysql.connect(**DB_CONFIG)
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT name, description FROM achievements")
            rows = cursor.fetchall()
            return jsonify([{"name": row[0], "description": row[1]} for row in rows])
    finally:
        conn.close()


@app.route("/")
def serve_index():
    return render_template("index.html")


if __name__ == "__main__":
    app.run(host='0.0.0.0', debug=True)