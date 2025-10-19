from flask import Flask, render_template, jsonify, request
import pymysql
import os
import json
from datetime import date, datetime, timedelta, timezone
import random
from threading import Lock
from collections import defaultdict
import numpy as np
import pandas as pd
from urllib.parse import quote
from concurrent.futures import ThreadPoolExecutor
import uuid
from og import create_user_card_blueprint, build_all_user_cards
from collections import defaultdict, Counter

app = Flask(__name__)

with open("web_config.json", "r", encoding="utf-8") as f:
    WEB_CONFIG = json.load(f)

DB_CONFIG = WEB_CONFIG["db"]
PROFILE_IMG_DIR = WEB_CONFIG["profile_img_dir"]
PROFILE_FONT_DIR = WEB_CONFIG["profile_font_dir"]
OG_CACHE_DIR = WEB_CONFIG["og_cache_dir"]

PROFILE_DEFAULT_FILENAME = "default.png"

#---------------------------------------------------------------------------------------

cache_store = {
    "ranking_users": {
        "total": [],
        "weekly": [],
        "monthly": []
    },
    "popular_music": [],
    "all_users": [],
    "achievements": [],

    "attendance_interval_summary": {},
    "attendance_daily_count": [],
    "weekday_attendance_summary": {},

    "love_graph": {
        "nodes": [],
        "links": []
    },
    "attendance_correlation": [],
    "user_details_by_nickname": {}
}
cache_lock = Lock()

executor = ThreadPoolExecutor(max_workers=2)
_jobs = {}
_jobs_lock = Lock()


def _compute_and_update_all():
    updated = {}

    # 0) 유저 디테일: 락 밖에서 새 스냅샷 계산 (Top-N 포함)
    try:
        new_user_details = compute_all_user_details()   # dict 반환, 캐시에 직접 쓰지 않음
        new_user_details_error = None
    except Exception as e:
        new_user_details = None
        new_user_details_error = str(e)

    # 1) 가벼운 캐시들은 락 안에서 기존대로 갱신
    with cache_lock:
        for mode in ["total", "weekly", "monthly"]:
            cache_store["ranking_users"][mode] = compute_ranking(mode)
        updated["ranking_users"] = {k: len(v) for k, v in cache_store["ranking_users"].items()}

        cache_store["all_users"] = compute_all_users()
        updated["all_users"] = len(cache_store["all_users"])

        cache_store["achievements"] = compute_achievements()
        updated["achievements"] = len(cache_store["achievements"])

        cache_store["popular_music"] = compute_popular_music()
        updated["popular_music"] = len(cache_store["popular_music"])

        summary = compute_attendance_interval_summary()
        cache_store["attendance_interval_summary"] = summary or {}
        updated["attendance_interval_summary"] = bool(summary)

        cache_store["attendance_daily_count"] = compute_attendance_daily_count()
        updated["attendance_daily_count"] = len(cache_store["attendance_daily_count"])

        summary = compute_weekday_attendance_summary()
        cache_store["weekday_attendance_summary"] = summary or {}
        updated["weekday_attendance_summary"] = bool(summary)

        cache_store["love_graph"] = compute_love_graph()
        updated["love_graph"] = {
            "nodes": len(cache_store["love_graph"]["nodes"]),
            "links": len(cache_store["love_graph"]["links"])
        }

        cache_store["attendance_correlation"] = compute_attendance_correlation(top_n=CORR_TOP_N)
        updated["attendance_correlation"] = len(cache_store["attendance_correlation"])

        # 2) 유저 디테일 핫스왑(성공 시 교체, 실패 시 유지)
        if new_user_details is not None:
            cache_store["user_details_by_nickname"] = new_user_details
            updated["user_details_by_nickname"] = len(new_user_details)
        else:
            updated["user_details_by_nickname"] = len(cache_store["user_details_by_nickname"])
            updated["user_details_error"] = new_user_details_error

    # 3) OG 카드는 락 밖에서 (기존 그대로)
    try:
        with app.app_context():
            og_res = build_all_user_cards(
                db_config=DB_CONFIG,
                profile_img_dir=PROFILE_IMG_DIR,
                profile_default_filename=PROFILE_DEFAULT_FILENAME,
                font_path_bold=os.path.join(PROFILE_FONT_DIR, "NotoSansKR-Bold.ttf"),
                font_path_reg=os.path.join(PROFILE_FONT_DIR, "NotoSansKR-Regular.ttf"),
                brand_watermark="VRChat JustDance Community: 죽지않고돌아온저댄",
                route_prefix="",
                template_user_page="og.html",
                cache_dir=OG_CACHE_DIR,
            )
        updated["og_cards"] = og_res
    except Exception as e:
        updated["og_cards"] = {"error": str(e)}

    return {"status": "refreshed", "updated": updated}



def _start_job():
    job_id = str(uuid.uuid4())
    fut = executor.submit(_compute_and_update_all)
    with _jobs_lock:
        _jobs[job_id] = {"future": fut, "started_at": datetime.utcnow(), "done_at": None}
    def _mark_done(f, jid):
        with _jobs_lock:
            if jid in _jobs:
                _jobs[jid]["done_at"] = datetime.utcnow()
    fut.add_done_callback(lambda f, jid=job_id: _mark_done(f, jid))
    return job_id


def _status_payload(job_id):
    with _jobs_lock:
        entry = _jobs.get(job_id)
    if not entry:
        return jsonify({"error": "job_id not found"}), 404
    fut = entry["future"]
    if not fut.done():
        return jsonify({
            "job_id": job_id,
            "status": "running",
            "started_at": entry["started_at"].isoformat() + "Z"
        }), 200
    try:
        result = fut.result()
        return jsonify({
            "job_id": job_id,
            "status": "done",
            "started_at": entry["started_at"].isoformat() + "Z",
            "done_at": (entry["done_at"].isoformat() + "Z") if entry["done_at"] else None,
            "result": result
        }), 200
    except Exception as e:
        return jsonify({"job_id": job_id, "status": "failed", "error": str(e)}), 500

# ---- 생성(POST/GET 둘 다 허용) ----
@app.route("/api/refresh-stats", methods=["GET", "POST"])
@app.route("/api/refresh-stats/", methods=["GET", "POST"])  # 슬래시 호환
def refresh_stats_async():
    # GET으로 들어와도 바로 잡 생성(하위호환)
    job_id = _start_job()
    return jsonify({"job_id": job_id, "status": "accepted"}), 202

# ---- 상태조회: path 파라미터 버전 ----
@app.route("/api/refresh-stats/<job_id>", methods=["GET"])
def refresh_stats_status(job_id):
    return _status_payload(job_id)

# ---- 상태조회: 쿼리스트링 버전 (?job_id=...) ----
@app.route("/api/refresh-stats/status", methods=["GET"])
def refresh_stats_status_qs():
    job_id = request.args.get("job_id")
    if not job_id:
        return jsonify({"error": "missing job_id"}), 400
    return _status_payload(job_id)


def safe_filename(nickname):
    return nickname.replace("/", "_SLASH_").replace("⁄", "_SLASH_")


#---------------------------------------------------------------------------------------
'''
def compute_ranking(mode: str):
    conn = pymysql.connect(**DB_CONFIG)
    try:
        with conn.cursor() as cursor:
            today = datetime.today()

            if mode == "weekly":
                start_of_week = today - timedelta(days=today.weekday())  # 월요일
                start_str = start_of_week.strftime("%Y-%m-%d 00:00:00")
                end_str = today.strftime("%Y-%m-%d 23:59:59")

                cursor.execute("""
                    SELECT u.nickname, COUNT(*) AS count
                    FROM attendance a
                    JOIN users u ON u.user_id = a.user_id
                    WHERE a.enter_time BETWEEN %s AND %s
                    GROUP BY u.user_id
                    ORDER BY count DESC
                    LIMIT 10
                """, (start_str, end_str))

            elif mode == "monthly":
                start_of_month = today.replace(day=1)
                start_str = start_of_month.strftime("%Y-%m-%d 00:00:00")
                end_str = today.strftime("%Y-%m-%d 23:59:59")

                cursor.execute("""
                    SELECT u.nickname, COUNT(*) AS count
                    FROM attendance a
                    JOIN users u ON u.user_id = a.user_id
                    WHERE a.enter_time BETWEEN %s AND %s
                    GROUP BY u.user_id
                    ORDER BY count DESC
                    LIMIT 10
                """, (start_str, end_str))

            else:  # total
                cursor.execute("""
                    SELECT u.nickname, uas.total_count
                    FROM user_attendance_summary uas
                    JOIN users u ON u.user_id = uas.user_id
                    ORDER BY uas.total_count DESC, uas.last_attended DESC
                    LIMIT 10
                """)

            rows = cursor.fetchall()

            users = []
            for rank, row in enumerate(rows, start=1):
                nickname = row[0]
                count = row[1] if len(row) > 1 else None
                info = get_user_info_by_nickname(cursor, nickname)
                if info:
                    info["rank"] = rank
                    if count is not None:
                        info["total_count"] = count
                    users.append(info)

            return users
    finally:
        conn.close()

@app.route("/api/ranking-users")
def ranking_users():
    mode = request.args.get("mode", "total")
    with cache_lock:
        return jsonify(cache_store["ranking_users"].get(mode, []))


def update_ranking_users_cache():
    with cache_lock:
        for mode in ["total", "weekly", "monthly"]:
            cache_store["ranking_users"][mode] = compute_ranking(mode)

'''

def compute_ranking(mode: str, offset: int = 0):
    conn = pymysql.connect(**DB_CONFIG)
    try:
        with conn.cursor() as cursor:
            today = datetime.today()
            start_str = ""
            end_str = ""

            if mode == "weekly":
                start_of_week = today - timedelta(days=today.weekday(), weeks=offset)
                end_of_week = start_of_week + timedelta(days=6)

                start_str = start_of_week.strftime("%Y-%m-%d 00:00:00")
                end_str = end_of_week.strftime("%Y-%m-%d 23:59:59")

                cursor.execute("""
                    SELECT u.nickname, COUNT(*) AS count
                    FROM attendance a
                    JOIN users u ON u.user_id = a.user_id
                    WHERE a.enter_time BETWEEN %s AND %s
                    GROUP BY u.user_id
                    ORDER BY count DESC
                    LIMIT 10
                """, (start_str, end_str))

            elif mode == "monthly":
                target_month = today.month - offset
                target_year = today.year
                while target_month <= 0:
                    target_month += 12
                    target_year -= 1

                start_of_month = datetime(target_year, target_month, 1)
                if target_month == 12:
                    next_month = datetime(target_year + 1, 1, 1)
                else:
                    next_month = datetime(target_year, target_month + 1, 1)

                start_str = start_of_month.strftime("%Y-%m-%d 00:00:00")
                end_str = (next_month - timedelta(days=1)).strftime("%Y-%m-%d 23:59:59")

                cursor.execute("""
                    SELECT u.nickname, COUNT(*) AS count
                    FROM attendance a
                    JOIN users u ON u.user_id = a.user_id
                    WHERE a.enter_time BETWEEN %s AND %s
                    GROUP BY u.user_id
                    ORDER BY count DESC
                    LIMIT 10
                """, (start_str, end_str))

            else:  # total
                cursor.execute("""
                    SELECT u.nickname, uas.total_count
                    FROM user_attendance_summary uas
                    JOIN users u ON u.user_id = uas.user_id
                    ORDER BY uas.total_count DESC, uas.last_attended DESC
                    LIMIT 10
                """)

            rows = cursor.fetchall()
            users = []
            for rank, row in enumerate(rows, start=1):
                nickname = row[0]
                count = row[1] if len(row) > 1 else None
                info = get_user_info_by_nickname(cursor, nickname)
                if info:
                    info["rank"] = rank
                    if count is not None:
                        info["total_count"] = count
                    users.append(info)

            # ✅ 날짜 범위는 date만 잘라서 반환 (프론트가 포맷 꾸미기 편하게)
            return {
                "users": users,
                "start_date": start_str.split(" ")[0] if start_str else "",
                "end_date": end_str.split(" ")[0] if end_str else ""
            }
    finally:
        conn.close()


@app.route("/api/ranking-users")
def ranking_users():
    mode = request.args.get("mode", "total")
    try:
        offset = int(request.args.get("offset", "0"))
    except ValueError:
        offset = 0

    return jsonify(compute_ranking(mode, offset))


#---------------------------------------------------------------------------------------

def compute_popular_music():
    conn = pymysql.connect(**DB_CONFIG)
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT title, COUNT(*) AS play_count
                FROM music_play
                WHERE played_at >= CURDATE() - INTERVAL 30 DAY
                    AND played_at < CURDATE()
                GROUP BY title
                ORDER BY play_count DESC, MAX(played_at) DESC
                LIMIT 10
            """)
            rows = cursor.fetchall()
            return [
                { "title": r[0], "count": r[1] }
                for r in rows
            ]
    finally:
        conn.close()

@app.route("/api/popular-music")
def popular_music():
    with cache_lock:
        return jsonify(cache_store["popular_music"])


#---------------------------------------------------------------------------------------


def compute_all_users():
    exclude_list = ["아짱나", "미쿠"]
    conn = pymysql.connect(**DB_CONFIG)
    try:
        with conn.cursor() as cursor:
            placeholders = ', '.join(['%s'] * len(exclude_list))
            query = f"SELECT nickname FROM users WHERE nickname NOT IN ({placeholders}) ORDER BY user_id ASC"
            cursor.execute(query, exclude_list)

            nicknames = [row[0] for row in cursor.fetchall()]

            users = []
            for nickname in nicknames:
                info = get_user_info_by_nickname(cursor, nickname)
                if info:
                    users.append(info)
            return users
    finally:
        conn.close()

#Page All Users
@app.route("/api/all-users")
def all_users():
    with cache_lock:
        cached_users = cache_store["all_users"][:]
    random.shuffle(cached_users)
    return jsonify(cached_users)

#---------------------------------------------------------------------------------------

def compute_achievements():
    conn = pymysql.connect(**DB_CONFIG)
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT a.name, a.description,
                       COUNT(ua.user_id) AS achieved_count,
                       (SELECT COUNT(*) FROM users) AS total_users
                FROM achievements a
                LEFT JOIN user_achievements ua ON ua.achievement_id = a.achievement_id
                GROUP BY a.achievement_id, a.name, a.description
                ORDER BY a.name ASC
            """)
            rows = cursor.fetchall()
            return [
                {
                    "name": row[0],
                    "description": row[1],
                    "achieved_count": row[2],
                    "total_users": row[3],
                    "percentage": round(row[2] / row[3] * 100, 1) if row[3] else 0
                }
                for row in rows
            ]
    finally:
        conn.close()

@app.route("/api/achievements")
def get_achievements():
    with cache_lock:
        return jsonify(cache_store["achievements"])

#---------------------------------------------------------------------------------------

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

        img_filename = safe_filename(nickname) + ".png"
        img_path = os.path.join(PROFILE_IMG_DIR, img_filename)
        if not os.path.exists(img_path):
            img_filename = PROFILE_DEFAULT_FILENAME

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

# ------------------------------------------------------------
# 전역에 기간 상수 추가 (오늘 제외, 최근 N일)
DAYRANGE = 90
# ------------------------------------------------------------

def compute_attendance_interval_summary():
    conn = pymysql.connect(**DB_CONFIG)
    try:
        with conn.cursor() as cursor:
            end_date = datetime.now().date() - timedelta(days=1)  # 오늘 제외
            date_list = [end_date - timedelta(days=i) for i in range(DAYRANGE)]

            segment_ratio_sums = [0.0] * 6
            valid_days = 0

            for d in date_list:
                date_str = d.strftime("%Y-%m-%d")
                cursor.execute("""
                    SELECT enter_time
                    FROM attendance
                    WHERE DATE(enter_time) = %s
                    ORDER BY enter_time ASC
                """, (date_str,))
                entries = cursor.fetchall()
                if not entries:
                    continue

                # 첫 입장 시각 기준으로 1시간 창 설정 (분 단위 0/30으로 정렬)
                first_entry = entries[0][0]
                minute = first_entry.minute
                rounded_min = 0 if minute < 15 else 30 if minute < 45 else 60
                start_hour = first_entry.hour + (1 if rounded_min == 60 else 0)
                start_min = 0 if rounded_min == 60 else rounded_min
                start_time = datetime(d.year, d.month, d.day, start_hour, start_min)
                end_time = start_time + timedelta(hours=1)

                # 10분 간격 경계(7점 → 6구간)
                segments = [start_time + timedelta(minutes=10*i) for i in range(7)]
                counts = [0] * 6

                for (enter_time,) in entries:
                    if not (start_time <= enter_time < end_time):
                        continue
                    for i in range(6):
                        if segments[i] <= enter_time < segments[i+1]:
                            counts[i] += 1
                            break

                total = sum(counts)
                if total == 0:
                    continue

                ratios = [c / total for c in counts]
                segment_ratio_sums = [s + r for s, r in zip(segment_ratio_sums, ratios)]
                valid_days += 1

            if valid_days == 0:
                return None

            averages = [round(s / valid_days * 100, 2) for s in segment_ratio_sums]
            return {
                "labels": ["0~10분", "10~20분", "20~30분", "30~40분", "40~50분", "50~60분"],
                "averages": averages
            }
    finally:
        conn.close()

@app.route("/api/attendance-interval-summary")
def attendance_interval_summary():
    with cache_lock:
        summary = cache_store["attendance_interval_summary"]
    if not summary:
        return jsonify({"error": f"No data found for last {DAYRANGE} days"}), 404
    return jsonify(summary)


# ------------------------------------------------------------

def compute_attendance_daily_count():
    conn = pymysql.connect(**DB_CONFIG)
    try:
        with conn.cursor() as cursor:
            end_date = datetime.now().date() - timedelta(days=1)       # 오늘 제외
            start_date = end_date - timedelta(days=(DAYRANGE - 1))     # 최근 DAYRANGE일 범위

            cursor.execute("""
                SELECT DATE(a.enter_time) AS date, COUNT(DISTINCT a.user_id) AS user_count
                FROM attendance a
                WHERE DATE(a.enter_time) BETWEEN %s AND %s
                GROUP BY DATE(a.enter_time)
                ORDER BY date ASC
            """, (start_date, end_date))

            rows = cursor.fetchall()
            return [
                {"date": row[0].strftime("%Y-%m-%d"), "count": row[1]}
                for row in rows
            ]
    finally:
        conn.close()

@app.route("/api/attendance-daily-count")
def attendance_daily_count():
    with cache_lock:
        return jsonify(cache_store["attendance_daily_count"])


# ------------------------------------------------------------

def compute_weekday_attendance_summary():
    conn = pymysql.connect(**DB_CONFIG)
    try:
        with conn.cursor() as cursor:
            end_date = datetime.now().date() - timedelta(days=1)  # 오늘 제외
            date_list = [end_date - timedelta(days=i) for i in range(DAYRANGE)]

            weekday_counts = [0] * 7  # 월(0) ~ 일(6)
            weekday_days = [0] * 7

            for d in date_list:
                weekday = d.weekday()
                date_str = d.strftime("%Y-%m-%d")

                cursor.execute("""
                    SELECT COUNT(*) FROM attendance
                    WHERE DATE(enter_time) = %s
                """, (date_str,))
                count = cursor.fetchone()[0]

                weekday_counts[weekday] += count
                weekday_days[weekday] += 1

            averages = [
                round(count / days, 2) if days > 0 else 0.0
                for count, days in zip(weekday_counts, weekday_days)
            ]

            return {
                "labels": ["월", "화", "수", "목", "금", "토", "일"],
                "averages": averages
            }
    finally:
        conn.close()

@app.route("/api/weekday-attendance-summary")
def weekday_attendance_summary():
    with cache_lock:
        summary = cache_store["weekday_attendance_summary"]
    if not summary:
        return jsonify({"error": f"No data available for last {DAYRANGE} days"}), 404
    return jsonify(summary)

# --- 하이퍼파라미터 (원하는 대로 조절) -----------------------------------
SLOT_MINUTES            = 5
USE_OFFSET_SLOT         = True     # True면 반슬롯(offset)도 포함(=하루*2 벡터)
GAUSS_SIGMA_MINUTES     = 7.5      # 가우시안 커널 표준편차(분). 예: 7.5분(=1.5 슬롯)
RECENCY_HALF_LIFE_DAYS  = 7        # 최근성 가중의 반감기(일). 작을수록 최근 며칠에 민감
USE_SLOT_IDF            = True     # 특정 시간대(모두가 나오는 피크타임) 페널티
IDF_SMOOTHING           = 1.0      # idf = log(1 + (U+IDF_SMOOTHING)/(df+IDF_SMOOTHING))
MIN_EDGE_WEIGHT         = 0.5      # 엣지 최소 유사도
TOP_K_NEIGHBORS         = 4        # 각 닉네임이 유지할 최대 상위 이웃 수(다양성 ↑)
HIGHLIGHT_EPS           = 1e-6     # 부동소수 오차 허용
LOVE_HIGHLIGHT_MAX      = 5        # 닉당 하이라이트 최대 개수
EXCLUDED_NICKNAMES      = {"아짱나", "미쿠"}
# -------------------------------------------------------------------------

def compute_love_graph():
    SLOTS_PER_DAY = (60 * 24) // SLOT_MINUTES
    MULT = 2 if USE_OFFSET_SLOT else 1
    TOTAL_SLOTS = SLOTS_PER_DAY * DAYRANGE * MULT

    end_date = datetime.now().date() - timedelta(days=1)        # 어제까지
    start_date = end_date - timedelta(days=DAYRANGE - 1)
    window_start_dt = datetime.combine(start_date, datetime.min.time())
    window_end_dt   = datetime.combine(end_date + timedelta(days=1), datetime.min.time())

    conn = pymysql.connect(**DB_CONFIG)
    try:
        with conn.cursor() as cursor:
            # 닉/유저 로딩(제외 닉 제거)
            cursor.execute("SELECT user_id, nickname FROM users")
            users = cursor.fetchall()
            id_to_nick = {uid: nick for uid, nick in users if nick not in EXCLUDED_NICKNAMES}
            valid_user_ids = list(id_to_nick.keys())
            if not valid_user_ids:
                return {"nodes": [], "links": []}

            # 윈도우 전체와 겹치는 세션만 가져오기(기간 시작 전에 입장/기간 끝 이후 퇴장 세션 포함)
            in_clause = ",".join(["%s"] * len(valid_user_ids))
            cursor.execute(f"""
                SELECT user_id, enter_time, leave_time
                FROM attendance
                WHERE enter_time < %s
                  AND leave_time > %s
                  AND user_id IN ({in_clause})
            """, [window_end_dt, window_start_dt] + valid_user_ids)
            all_rows = cursor.fetchall()

        # 유저별 세션
        user_sessions = defaultdict(list)
        for uid, ent, lev in all_rows:
            # DB가 tz-aware/naive 혼재일 경우 정규화 필요(여기선 그대로 사용)
            user_sessions[uid].append((ent, lev))

        # 빈 벡터 구성
        user_vectors = {uid: np.zeros(TOTAL_SLOTS, dtype=np.float32) for uid in valid_user_ids}

        # 슬롯 경계 미리 계산
        # index: d(0~DAYRANGE-1), slot(0~SLOTS_PER_DAY-1), [offset0, offset1]
        def slot_bounds(d, slot, is_offset):
            base_start = datetime.combine(start_date + timedelta(days=d), datetime.min.time()) \
                         + timedelta(minutes=slot * SLOT_MINUTES)
            start = base_start + (timedelta(minutes=SLOT_MINUTES//2) if is_offset else timedelta(0))
            end   = start + timedelta(minutes=SLOT_MINUTES)
            return start, end

        # 세션을 슬롯 인덱스 구간으로 바로 매핑해 벡터를 채움(빠름)
        def slot_index_from_dt(dt, is_offset):
            # 윈도우 밖은 클램프
            if dt <= window_start_dt:
                total_index = 0
            elif dt >= window_end_dt:
                total_index = TOTAL_SLOTS
            else:
                delta = dt - window_start_dt
                minutes = delta.total_seconds() // 60
                # base 슬롯 기준
                slot_idx = int(minutes // SLOT_MINUTES)
                if is_offset:
                    # offset 시작점은 슬롯 중간이므로 반슬롯 보정
                    # 시간을 SLOT_MINUTES/2 이동한 효과와 같음
                    minutes_adj = minutes - (SLOT_MINUTES / 2)
                    slot_idx = int(max(0, minutes_adj) // SLOT_MINUTES)
                # 하루 경계를 고려한 전체 인덱스 계산은 아래에서 일괄 보정
                total_index = slot_idx
            return int(total_index)

        for uid in valid_user_ids:
            sessions = user_sessions[uid]
            if not sessions:
                continue
            # base와 offset 각각 채우기
            for is_offset in ([False, True] if USE_OFFSET_SLOT else [False]):
                # 일단 윈도우 전체 기준 연속 인덱스로 처리
                start_idx = slot_index_from_dt(window_start_dt, is_offset)
                # 각 세션을 [s_idx, e_idx)로 변환해 1로 채움
                vec = user_vectors[uid]
                for ent, lev in sessions:
                    s_dt = max(ent, window_start_dt)
                    e_dt = min(lev, window_end_dt)
                    if s_dt >= e_dt:
                        continue
                    s_idx = slot_index_from_dt(s_dt, is_offset)
                    e_idx = slot_index_from_dt(e_dt, is_offset)
                    # base/offset 전체 인덱스에 대해 하루/반슬롯 배치 고려
                    # base: 0,2,4,... / offset: 1,3,5,...
                    if USE_OFFSET_SLOT:
                        # base/offset을 interleave 하도록 2배 인덱스로 매핑
                        # 먼저 base-only 인덱스(0..DAY*slots-1)를 얻었으니,
                        # 실제 TOTAL_SLOTS 인덱스는 (idx*2 + (1 if offset else 0))
                        b = 1 if is_offset else 0
                        # 슬라이스 채우기(간헐적 세션은 반복)
                        vec[(s_idx*2 + b):(e_idx*2 + b):2] = 1
                    else:
                        vec[s_idx:e_idx] = 1

        # --- 슬롯 IDF(희소 시간대 강조: 모두 출근하는 피크시간 가중↓) -----------------
        if USE_SLOT_IDF:
            # df: 슬롯마다 몇 명이 1인지(스무딩 전 이진 기준)
            stacked = np.stack([user_vectors[uid] for uid in valid_user_ids], axis=0)
            df = (stacked > 0).sum(axis=0).astype(np.float32)  # shape=(TOTAL_SLOTS,)
            U = float(len(valid_user_ids))
            idf = np.log(1.0 + (U + IDF_SMOOTHING) / (df + IDF_SMOOTHING)).astype(np.float32)
            # 사용자 벡터에 슬롯별 idf 곱
            for uid in valid_user_ids:
                user_vectors[uid] *= idf

        # --- 최근성 가중(최근일수록 큰 가중) -------------------------------------------
        # day 0 = start_date, day (DAYRANGE-1)=end_date
        half_life = float(RECENCY_HALF_LIFE_DAYS)
        if half_life > 0:
            day_weights = np.array(
                [2 ** (-(DAYRANGE - 1 - d) / half_life) for d in range(DAYRANGE)],
                dtype=np.float32
            )  # end_date(가장 최근 d=DAYRANGE-1)가 weight=1
            # 슬롯 단위로 확장
            w = np.repeat(day_weights, SLOTS_PER_DAY * MULT)
            for uid in valid_user_ids:
                user_vectors[uid] *= w

        # --- 가우시안 스무딩(1D 컨볼루션) ----------------------------------------------
        # sigma(슬롯 단위)로 변환
        sigma_slots = max(1e-6, GAUSS_SIGMA_MINUTES / SLOT_MINUTES)
        # 커널 길이: ±3σ 정도(홀수)
        radius = max(1, int(round(3 * sigma_slots)))
        xs = np.arange(-radius, radius + 1, dtype=np.float32)
        kernel = np.exp(-0.5 * (xs / sigma_slots) ** 2)
        kernel = (kernel / kernel.sum()).astype(np.float32)

        smoothed = {}
        for uid in valid_user_ids:
            # mode='same'으로 길이 유지
            smoothed_vec = np.convolve(user_vectors[uid], kernel, mode='same')
            smoothed[uid] = smoothed_vec.astype(np.float32)

        # --- 코사인 유사도 -------------------------------------------------------------
        uid_list = valid_user_ids
        norms = {uid: float(np.linalg.norm(smoothed[uid])) for uid in uid_list}
        scores = {}  # ((uid1, uid2) -> score)
        for i in range(len(uid_list)):
            uid1 = uid_list[i]
            v1 = smoothed[uid1]
            n1 = norms[uid1]
            if n1 == 0.0:
                continue
            for j in range(i + 1, len(uid_list)):
                uid2 = uid_list[j]
                n2 = norms[uid2]
                if n2 == 0.0:
                    continue
                s = float(np.dot(v1, smoothed[uid2]) / (n1 * n2))
                if s >= MIN_EDGE_WEIGHT:
                    scores[(uid1, uid2)] = s

        # --- 닉 기반 정리 + Top-K per node로 다양성 확보 -------------------------------
        # 각 닉이 높은 이웃 TOP_K만 유지(양방향 보장 위해 그리디 머지)
        nick_scores = []  # (nick1, nick2, score)
        for (u1, u2), w in scores.items():
            n1, n2 = id_to_nick.get(u1), id_to_nick.get(u2)
            if not n1 or not n2 or n1 == n2:
                continue
            a, b = (n1, n2) if n1 < n2 else (n2, n1)
            nick_scores.append((a, b, w))
        # 점수 내림차순
        nick_scores.sort(key=lambda x: x[2], reverse=True)

        kept = []
        deg = defaultdict(int)
        for a, b, w in nick_scores:
            if deg[a] < TOP_K_NEIGHBORS and deg[b] < TOP_K_NEIGHBORS:
                kept.append((a, b, w))
                deg[a] += 1
                deg[b] += 1

        # 닉별 최대 가중치 계산(하이라이트)
        max_edge_per_nick = defaultdict(float)
        for a, b, w in kept:
            if w > max_edge_per_nick[a]:
                max_edge_per_nick[a] = w
            if w > max_edge_per_nick[b]:
                max_edge_per_nick[b] = w

        # 링크 생성(닉별 하이라이트 개수 제한)
        highlight_count = defaultdict(int)
        links = []
        connected_nicks = set()
        for a, b, w in kept:
            ha = abs(w - max_edge_per_nick[a]) <= HIGHLIGHT_EPS
            hb = abs(w - max_edge_per_nick[b]) <= HIGHLIGHT_EPS
            highlight = ha and hb and (highlight_count[a] < LOVE_HIGHLIGHT_MAX) and (highlight_count[b] < LOVE_HIGHLIGHT_MAX)
            links.append({
                "source": a,
                "target": b,
                "weight": w,
                "highlight": highlight
            })
            if highlight:
                highlight_count[a] += 1
                highlight_count[b] += 1
            connected_nicks.update([a, b])

        # 노드 생성
        nodes = []
        for nick in sorted(connected_nicks):
            img_filename = safe_filename(nick) + ".png"
            img_path = os.path.join(PROFILE_IMG_DIR, img_filename)
            if not os.path.exists(img_path):
                img_filename = PROFILE_DEFAULT_FILENAME
            nodes.append({
                "id": nick,
                "nickname": nick,
                "img": f"/static/profiles/{quote(img_filename)}"
            })

        return {"nodes": nodes, "links": links}
    finally:
        conn.close()



@app.route("/api/love-graph")
def love_graph():
    with cache_lock:
        return jsonify(cache_store["love_graph"])

#---------------------------------------------------------------------------------------
# 하이퍼파라미터 (원하면 바꾸세요)
CORR_TOP_N = 10  # 응답에 담을 상위 N명

#---------------------------------------------------------------------------------------
PRESENT_THRESHOLD_SEC = 600
KST = timezone(timedelta(hours=9))

EXCLUDED_NICKNAMES_CORR = {'아짱나', '미쿠', 'Nine_Bones'}
def compute_attendance_correlation(top_n: int | None = None,
                                   excluded_nicks: set[str] | None = None):
    """
    오늘(KST) 제외 최근 DAYRANGE일 동안
      - 하루 총 체류시간 >= 600초 => 출석(1)
      - 각 사용자 vs (자기 제외) 전체 출석율 Pearson r
    하이퍼파라미터:
      - top_n: 상위 N명만 반환 (None이면 전체)
      - excluded_nicks: 제외할 닉네임 집합 (None이면 글로벌 EXCLUDED_NICKNAMES_CORR 사용)
    반환: 리스트[dict] (Top-N + 각 항목에 img URL 포함)
    """
    top_n = top_n or CORR_TOP_N

    # 글로벌 set 기본값 사용 (EXCLUDED_NICKNAMES_CORR)
    effective_excluded = set()
    try:
        if excluded_nicks is not None:
            effective_excluded = set(excluded_nicks)
        elif 'EXCLUDED_NICKNAMES_CORR' in globals() and isinstance(EXCLUDED_NICKNAMES_CORR, set):
            effective_excluded = set(EXCLUDED_NICKNAMES_CORR)
    except Exception:
        effective_excluded = set()

    today_kst = datetime.now(KST).date()
    end_date = today_kst
    start_date = today_kst - timedelta(days=DAYRANGE)

    # 날짜 인덱스 (start ~ end-1)
    date_index = pd.date_range(start=start_date, end=end_date - timedelta(days=1), freq="D")
    if len(date_index) == 0:
        return []

    # 이 함수에서만 DictCursor 지정
    conn = pymysql.connect(**DB_CONFIG, cursorclass=pymysql.cursors.DictCursor)
    try:
        with conn.cursor() as cur:
            # 유저 맵
            cur.execute("SELECT user_id, nickname FROM users;")
            user_rows = cur.fetchall()
            user_map = {r["user_id"]: r["nickname"] for r in user_rows}

            # 제외할 user_id 집합 산출 (닉네임 매칭)
            excluded_user_ids = {uid for uid, nick in user_map.items() if nick in effective_excluded}

            # user_map에서도 제외
            for _uid in excluded_user_ids:
                user_map.pop(_uid, None)

            # 날짜별(user_id, day) 체류시간 합
            sql = """
                SELECT
                    a.user_id,
                    DATE(a.enter_time) AS day,
                    SUM(a.duration_sec) AS total_sec
                FROM attendance a
                WHERE a.enter_time >= %s
                  AND a.enter_time < %s
                GROUP BY a.user_id, DATE(a.enter_time);
            """
            cur.execute(sql, (start_date, end_date))
            att_rows = cur.fetchall()
    finally:
        conn.close()

    if not att_rows:
        return []

    att_df = pd.DataFrame(att_rows)

    # 닉네임 제외 반영 (user_id 기준)
    if not att_df.empty and effective_excluded:
        # 먼저 user_id -> nickname 매핑을 써서 제외할 id 집합 생성
        to_exclude_ids = {uid for uid, nick in user_map.items() if nick in effective_excluded}
        # 위에서 user_map에서 pop 했기 때문에, att_df 기준으로 다시 계산
        if not to_exclude_ids:
            # 혹시 user_map pop 이전의 excluded_user_ids를 재활용 (안전망)
            to_exclude_ids = excluded_user_ids if 'excluded_user_ids' in locals() else set()
        if to_exclude_ids:
            att_df = att_df[~att_df["user_id"].isin(to_exclude_ids)]

    if att_df.empty:
        return []

    att_df["day"] = pd.to_datetime(att_df["day"]).dt.date
    att_df["present"] = (att_df["total_sec"] >= PRESENT_THRESHOLD_SEC).astype(int)

    pivot = att_df.pivot_table(index="day", columns="user_id", values="present",
                               aggfunc="max", fill_value=0)
    pivot = pivot.reindex(date_index.date, fill_value=0)
    pivot.index.name = "day"

    # 윈도우 동안 한 번이라도 출석한 유저만
    active_users = [uid for uid in pivot.columns if pivot[uid].sum() > 0]
    if len(active_users) <= 1:
        return []

    pivot_active = pivot[active_users]
    total_present_per_day = pivot_active.sum(axis=1)  # 일자별 출석자 수
    N = len(active_users)

    rows = []
    for uid in active_users:
        user_vec = pivot_active[uid].astype(float).values
        others_present = (total_present_per_day - pivot_active[uid]).values
        denom = N - 1

        if denom <= 0:
            corr = np.nan
            group_mean_excl = np.nan
        else:
            group_rate_excl = others_present / denom
            if np.std(user_vec) == 0 or np.std(group_rate_excl) == 0:
                corr = np.nan
            else:
                corr = float(np.corrcoef(user_vec, group_rate_excl)[0, 1])
            group_mean_excl = float(np.mean(group_rate_excl))

        rows.append({
            "user_id": int(uid),
            "nickname": user_map.get(uid, str(uid)),
            "corr_with_group_excl_self": None if np.isnan(corr) else round(corr, 4),
            "days_present": int(np.sum(user_vec)),
            "days_total": int(len(pivot_active.index)),
            "user_daily_mean": round(float(np.mean(user_vec)), 4),
            "group_daily_mean_excl_self": None if np.isnan(group_mean_excl) else round(group_mean_excl, 4),
        })

    # 상관계수 내림차순 (None은 뒤로)
    rows.sort(key=lambda r: (-r["corr_with_group_excl_self"]
                             if r["corr_with_group_excl_self"] is not None else float("inf")))

    # Top-N만 선택
    top_rows = rows[:top_n] if (top_n and top_n > 0) else rows

    # 이미지 URL 부여: safe_filename(nickname).png가 있으면 사용, 없으면 기본 이미지
    for r in top_rows:
        nick = r["nickname"]
        img_filename = f"{safe_filename(nick)}.png"
        img_path = os.path.join(PROFILE_IMG_DIR, img_filename)
        if not os.path.exists(img_path):
            img_filename = PROFILE_DEFAULT_FILENAME
        r["img"] = f"/static/profiles/{quote(img_filename)}"

    return top_rows



@app.route("/api/attendance_correlation")
def get_attendance_correlation():
    with cache_lock:
        return jsonify(cache_store["attendance_correlation"])
#---------------------------------------------------------------------------------------




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
    img_filename = img_filename = safe_filename(nickname) + ".png"
    img_path = os.path.join(PROFILE_IMG_DIR, img_filename)
    if not os.path.exists(img_path):
        img_filename = PROFILE_DEFAULT_FILENAME

    return {
        "user_id": user_id,
        "nickname": nickname,
        "comment": comment,
        "total_count": total_count,
        "last_attended": last_attended.strftime("%Y-%m-%d %H:%M") if last_attended else None,
        "img": f"/static/profiles/{img_filename}",
        "achievements": achievements,
    }

TOP_N_RANK = 5

def compute_topn_threshold_counts(n=TOP_N_RANK, limit_months: int | None = None):
    """
    DB에서 (user_id, enter_day)만 일괄로 읽고 파이썬에서 월/주 Top-N 횟수 계산.
    - 이번 달/이번 주 제외
    - 참가자 수 < n 이면 임계값 = 그 기간의 '최소값'
    반환: { user_id: {"monthly": X, "weekly": Y} }
    """
    q = "SELECT DISTINCT user_id, enter_day FROM attendance"
    params = ()
    if limit_months and limit_months > 0:
        q += " WHERE enter_day >= CURDATE() - INTERVAL %s MONTH"
        params = (limit_months,)

    conn = pymysql.connect(**DB_CONFIG)
    try:
        with conn.cursor() as cursor:
            cursor.execute(q, params)
            rows = cursor.fetchall()  # [(user_id:int, enter_day:date), ...]
    finally:
        conn.close()

    today = date.today()
    cur_month_key = (today.year, today.month)
    iy, iw, _ = today.isocalendar()
    cur_week_key = (iy, iw)

    by_month = defaultdict(Counter)  # {(y,m): Counter({uid: days})}
    by_week  = defaultdict(Counter)  # {(ISOy,ISOw): Counter({uid: days})}

    for uid, d in rows:
        by_month[(d.year, d.month)][uid] += 1
        y, w, _ = d.isocalendar()
        by_week[(y, w)][uid] += 1

    def nth_threshold(counter: Counter, n_: int):
        if not counter:
            return None
        vals = sorted(counter.values(), reverse=True)
        return vals[n_-1] if len(vals) >= n_ else vals[-1]

    monthly_counts = defaultdict(int)
    for mk, cnt in by_month.items():
        if mk == cur_month_key:
            continue
        thr = nth_threshold(cnt, n)
        if thr is None:
            continue
        for uid, days in cnt.items():
            if days >= thr:
                monthly_counts[uid] += 1

    weekly_counts = defaultdict(int)
    for wk, cnt in by_week.items():
        if wk == cur_week_key:
            continue
        thr = nth_threshold(cnt, n)
        if thr is None:
            continue
        for uid, days in cnt.items():
            if days >= thr:
                weekly_counts[uid] += 1

    topn = {}
    for uid in set(monthly_counts) | set(weekly_counts):
        topn[uid] = {
            "monthly": int(monthly_counts.get(uid, 0)),
            "weekly":  int(weekly_counts.get(uid, 0)),
        }
    return topn


def compute_all_user_details():
    """
    모든 유저 상세 정보를 계산해 dict으로 반환(캐시에 직접 쓰지 않음).
    - Top-N은 compute_topn_threshold_counts() 결과 포함
    반환: { nickname: {...details...} }
    """
    topn_counts = compute_topn_threshold_counts(n=TOP_N_RANK)  # 필요시 limit_months=12/24 등

    today = date.today()
    conn = pymysql.connect(**DB_CONFIG)
    try:
        with conn.cursor() as cursor:
            # 기본 정보
            cursor.execute("""
                SELECT u.user_id, u.nickname, u.comment,
                       COALESCE(uas.total_count, 0) AS total_count,
                       uas.last_attended
                FROM users u
                LEFT JOIN user_attendance_summary uas ON u.user_id = uas.user_id
            """)
            base_rows = cursor.fetchall()

            # 업적
            cursor.execute("""
                SELECT ua.user_id, a.name, a.description, DATE(ua.achieved_at) AS d
                FROM user_achievements ua
                JOIN achievements a ON ua.achievement_id = a.achievement_id
                ORDER BY ua.achieved_at DESC
            """)
            ach_map = {}
            for uid, name, desc, d in cursor.fetchall():
                ach_map.setdefault(uid, []).append({
                    "name": name,
                    "description": desc,
                    "achieved_at": d.strftime("%Y-%m-%d")
                })

            # 총 재생시간
            cursor.execute("""
                SELECT user_id, COALESCE(SUM(duration_sec), 0) AS total_sec
                FROM attendance
                GROUP BY user_id
            """)
            total_sec_map = {uid: sec for uid, sec in cursor.fetchall()}

            # 곡 수
            cursor.execute("""
                SELECT user_id, COUNT(*) AS cnt
                FROM music_play
                GROUP BY user_id
            """)
            song_cnt_map = {uid: cnt for uid, cnt in cursor.fetchall()}

            # 최근 30일
            cursor.execute("""
                SELECT user_id, enter_day AS day, SUM(duration_sec) AS sec
                FROM attendance
                WHERE enter_day >= CURDATE() - INTERVAL 29 DAY
                GROUP BY user_id, day
                ORDER BY day ASC
            """)
            recent_map = {}
            for uid, d, sec in cursor.fetchall():
                recent_map.setdefault(uid, {})[d] = sec
    finally:
        conn.close()

    details_by_nick = {}
    for user_id, nickname, comment, total_count, last_attended in base_rows:
        img_filename = safe_filename(nickname) + ".png"
        img_path = os.path.join(PROFILE_IMG_DIR, img_filename)
        if not os.path.exists(img_path):
            img_filename = PROFILE_DEFAULT_FILENAME

        per = recent_map.get(user_id, {})
        recent_30days = []
        for i in range(30):
            d = today - timedelta(days=29 - i)
            recent_30days.append({
                "date": d.strftime("%Y-%m-%d"),
                "duration_sec": per.get(d, 0)
            })

        cnts = topn_counts.get(user_id, {"monthly": 0, "weekly": 0})

        details_by_nick[nickname] = {
            "user_id": user_id,
            "nickname": nickname,
            "comment": comment,
            "total_count": total_count,
            "last_attended": last_attended.strftime("%Y-%m-%d %H:%M") if last_attended else None,
            "img": f"/static/profiles/{img_filename}",
            "achievements": ach_map.get(user_id, []),

            "play_duration_sec": total_sec_map.get(user_id, 0),
            "song_play_count":   song_cnt_map.get(user_id, 0),
            "recent_30days":     recent_30days,

            "topn_monthly_count_excl_current": cnts.get("monthly", 0),
            "topn_weekly_count_excl_current":  cnts.get("weekly", 0),
        }

    return details_by_nick


@app.route("/api/user-details")
def user_details():
    nickname = request.args.get("nickname")
    if not nickname:
        return jsonify({"error": "닉네임 없음"}), 400

    # 캐시에서 바로 조회 (락으로 보호)
    with cache_lock:
        info = cache_store["user_details_by_nickname"].get(nickname)

    if not info:
        return jsonify({"error": "사용자 없음 또는 캐시 미구축"}), 404

    return jsonify(info)


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


    conn = pymysql.connect(**DB_CONFIG)
    try:
        with conn.cursor() as cursor:
            # 1️⃣ 최근 30일 날짜 리스트 (어제까지)
            end_date = datetime.now().date() - timedelta(days=1)
            date_list = [end_date - timedelta(days=i) for i in range(30)]

            # 2️⃣ 날짜별 분석 결과 누적용
            segment_ratio_sums = [0.0] * 6
            valid_days = 0

            for d in date_list:
                date_str = d.strftime("%Y-%m-%d")
                cursor.execute("""
                    SELECT enter_time FROM attendance
                    WHERE DATE(enter_time) = %s
                    ORDER BY enter_time ASC
                """, (date_str,))
                entries = cursor.fetchall()
                if not entries:
                    continue

                # 3️⃣ 정규 시작시간 추정
                first_entry = entries[0][0]
                minute = first_entry.minute
                rounded_min = 0 if minute < 15 else 30 if minute < 45 else 60
                start_hour = first_entry.hour + (1 if rounded_min == 60 else 0)
                start_min = 0 if rounded_min == 60 else rounded_min
                start_time = datetime(d.year, d.month, d.day, start_hour, start_min)
                end_time = start_time + timedelta(hours=1)

                # 4️⃣ 6구간 정의 (10분 간격)
                segments = [start_time + timedelta(minutes=10*i) for i in range(7)]
                counts = [0] * 6

                for row in entries:
                    enter_time = row[0]
                    if not (start_time <= enter_time < end_time):
                        continue
                    for i in range(6):
                        if segments[i] <= enter_time < segments[i+1]:
                            counts[i] += 1
                            break

                total = sum(counts)
                if total == 0:
                    continue

                ratios = [c / total for c in counts]
                segment_ratio_sums = [s + r for s, r in zip(segment_ratio_sums, ratios)]
                valid_days += 1

            if valid_days == 0:
                return jsonify({"error": "No data found for last 30 days"}), 404

            # 평균 비율 (%)로 환산
            averages = [round(s / valid_days * 100, 2) for s in segment_ratio_sums]

            return jsonify({
                "labels": ["0~10분", "10~20분", "20~30분", "30~40분", "40~50분", "50~60분"],
                "averages": averages  # 퍼센트 단위
            })

    finally:
        conn.close()


@app.route("/")
def serve_index():
    return render_template("index.html")



app.register_blueprint(create_user_card_blueprint(
    db_config=DB_CONFIG,
    profile_img_dir=PROFILE_IMG_DIR,
    profile_default_filename=PROFILE_DEFAULT_FILENAME,
    font_path_bold=os.path.join(PROFILE_FONT_DIR, "NotoSansKR-Bold.ttf"),
    font_path_reg=os.path.join(PROFILE_FONT_DIR, "NotoSansKR-Regular.ttf"),
    brand_watermark="VRChat JustDance Community: 죽지않고돌아온저댄",
    route_prefix="",  # 필요 시 "/community"
    template_user_page="og.html",
    cache_dir=OG_CACHE_DIR,   # e.g. "./og_cache"
))

if __name__ == "__main__":
    app.run(host='0.0.0.0', debug=True)
    #app.run(debug=True, port=5001)