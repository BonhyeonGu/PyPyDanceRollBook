import pymysql
import json
from datetime import datetime, timedelta

#인싸:        10명이서 저댄
def award_inssa_achievement_from_date(start_date_str, config_path="config.json"):
    """
    start_date_str: 'YYYY-MM-DD' 형식
    config_path: JSON 파일 경로 (기본값: 'config.json')
    """
    # ✅ config.json 불러오기
    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)
    db_conf = config["db"]
    # ✅ pymysql이 요구하는 DB config 키 이름 맞추기
    db_params = {
        "host": db_conf["host"],
        "port": db_conf["port"],
        "user": db_conf["user"],
        "password": db_conf["password"],
        "db": db_conf["database"],
        "charset": "utf8mb4"
    }

    conn = pymysql.connect(**db_params)
    try:
        with conn.cursor() as cursor:
            # 1️⃣ '인싸' 도전과제 ID 조회
            cursor.execute("""
                SELECT achievement_id FROM achievements WHERE name = '인싸'
            """)
            result = cursor.fetchone()
            if not result:
                print("[ERROR] '인싸' 도전과제가 존재하지 않습니다.")
                return
            achievement_id = result[0]

            # 2️⃣ 시작일 ~ 오늘까지 날짜 목록 생성
            start_date = datetime.strptime(start_date_str, "%Y-%m-%d").date()
            today = datetime.today().date()
            current_date = start_date

            while current_date <= today:
                date_str = current_date.strftime("%Y-%m-%d")
                # 3️⃣ 해당 날짜의 10명 이상 참여자 조회
                cursor.execute("""
                    SELECT DISTINCT a.user_id
                    FROM attendance a
                    WHERE DATE(a.enter_time) = %s
                """, (date_str,))
                users = cursor.fetchall()

                if len(users) >= 10:
                    user_ids = [row[0] for row in users]

                    # 4️⃣ 이미 '인싸' 도전과제를 획득한 유저 제외
                    cursor.execute("""
                        SELECT user_id FROM user_achievements
                        WHERE achievement_id = %s
                    """, (achievement_id,))
                    achieved_users = {row[0] for row in cursor.fetchall()}

                    # 5️⃣ 이번 날짜 참여자 중 달성 안 한 유저만 추림
                    new_achievers = [uid for uid in user_ids if uid not in achieved_users]

                    if new_achievers:
                        for uid in new_achievers:
                            cursor.execute("""
                                INSERT INTO user_achievements (user_id, achievement_id, achieved_at)
                                VALUES (%s, %s, %s)
                            """, (uid, achievement_id, date_str))
                        conn.commit()
                        print(f"[INFO] {date_str}: {len(new_achievers)}명에게 '인싸' 도전과제 지급 완료!")
                    else:
                        print(f"[INFO] {date_str}: 이미 모두 달성함.")
                else:
                    print(f"[INFO] {date_str}: 참여자 {len(users)}명으로, 조건 불충족.")

                current_date += timedelta(days=1)
    finally:
        conn.close()

#칠가이:        7일 연속 저댄
def award_chill_guy_achievement(config_path="config.json"):
    # ✅ config.json 불러오기
    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)
    db_conf = config["db"]
    db_params = {
        "host": db_conf["host"],
        "port": db_conf["port"],
        "user": db_conf["user"],
        "password": db_conf["password"],
        "db": db_conf["database"],
        "charset": "utf8mb4"
    }

    conn = pymysql.connect(**db_params)
    try:
        with conn.cursor() as cursor:
            # 1️⃣ 'Chill guy' 도전과제 ID 조회
            cursor.execute("""
                SELECT achievement_id FROM achievements WHERE name = 'Chill guy'
            """)
            result = cursor.fetchone()
            if not result:
                print("[ERROR] 'Chill guy' 도전과제가 존재하지 않습니다.")
                return
            achievement_id = result[0]

            # 2️⃣ 이미 'Chill guy' 달성한 유저 목록 조회
            cursor.execute("""
                SELECT user_id FROM user_achievements
                WHERE achievement_id = %s
            """, (achievement_id,))
            achieved_users = {row[0] for row in cursor.fetchall()}

            # 3️⃣ 전체 유저 목록 조회 (도전과제 없는 유저만)
            cursor.execute("""
                SELECT DISTINCT user_id FROM attendance
            """)
            all_users = [row[0] for row in cursor.fetchall()]
            target_users = [uid for uid in all_users if uid not in achieved_users]

            # 4️⃣ 각 유저의 출석 기록 확인
            for uid in target_users:
                cursor.execute("""
                    SELECT DISTINCT DATE(enter_time) as day
                    FROM attendance
                    WHERE user_id = %s
                    ORDER BY day
                """, (uid,))
                dates = [row[0] for row in cursor.fetchall()]
                if len(dates) < 7:
                    continue  # 최소 7일 이상 출석한 적이 없으면 스킵

                # 5️⃣ 7일 연속 출석 확인
                dates_set = set(dates)
                for i in range(len(dates)):
                    start_date = dates[i]
                    success = True
                    for j in range(7):
                        day = start_date + timedelta(days=j)
                        if day not in dates_set:
                            success = False
                            break
                    if success:
                        # 7일 연속 출석 성공!
                        cursor.execute("""
                            INSERT INTO user_achievements (user_id, achievement_id, achieved_at)
                            VALUES (%s, %s, %s)
                        """, (uid, achievement_id, start_date.strftime("%Y-%m-%d")))
                        conn.commit()
                        print(f"[INFO] 유저 {uid} - 7일 연속 출석으로 'Chill guy' 달성!")
                        break  # 이 유저는 조건 충족했으니 더 확인할 필요 없음

    finally:
        conn.close()

#과몰입:        단 둘이서
def award_over_immersed_achievement_from_date(start_date_str, config_path="config.json"):
    """
    도전과제 '과몰입'을 해당하지 않는 유저들 중, 특정 날짜 이후로 딱 두 명만 접속한 기록이 있으면 부여합니다.
    """
    # ✅ config.json 불러오기
    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)
    db_conf = config["db"]
    db_params = {
        "host": db_conf["host"],
        "port": db_conf["port"],
        "user": db_conf["user"],
        "password": db_conf["password"],
        "db": db_conf["database"],
        "charset": "utf8mb4"
    }

    conn = pymysql.connect(**db_params)
    try:
        with conn.cursor() as cursor:
            # 1️⃣ '과몰입' 도전과제 ID 조회
            cursor.execute("""
                SELECT achievement_id FROM achievements WHERE name = '과몰입'
            """)
            result = cursor.fetchone()
            if not result:
                print("[ERROR] '과몰입' 도전과제가 존재하지 않습니다.")
                return
            achievement_id = result[0]

            # 2️⃣ 이미 '과몰입' 달성한 유저 목록 조회
            cursor.execute("""
                SELECT user_id FROM user_achievements
                WHERE achievement_id = %s
            """, (achievement_id,))
            achieved_users = {row[0] for row in cursor.fetchall()}

            # 3️⃣ 시작일 ~ 오늘까지 날짜 순회
            start_date = datetime.strptime(start_date_str, "%Y-%m-%d").date()
            today = datetime.today().date()
            current_date = start_date

            while current_date <= today:
                date_str = current_date.strftime("%Y-%m-%d")
                # 4️⃣ 해당 날짜의 참여자 조회
                cursor.execute("""
                    SELECT DISTINCT a.user_id
                    FROM attendance a
                    WHERE DATE(a.enter_time) = %s
                """, (date_str,))
                users = [row[0] for row in cursor.fetchall()]

                if len(users) == 2:
                    # 5️⃣ 두명 중 이미 도전과제 달성자 제외
                    new_achievers = [uid for uid in users if uid not in achieved_users]

                    if new_achievers:
                        for uid in new_achievers:
                            cursor.execute("""
                                INSERT INTO user_achievements (user_id, achievement_id, achieved_at)
                                VALUES (%s, %s, %s)
                            """, (uid, achievement_id, date_str))
                        conn.commit()
                        print(f"[INFO] {date_str}: {len(new_achievers)}명에게 '과몰입' 도전과제 지급 완료!")
                    else:
                        print(f"[INFO] {date_str}: 이미 모두 달성함.")
                else:
                    print(f"[INFO] {date_str}: 참여자 수 {len(users)}명 → 조건 불충족.")

                current_date += timedelta(days=1)

    finally:
        conn.close()

#완장:         나없을때 저댄
def award_captain_achievement_from_date(start_date_str, config_path="config.json"):
    """
    '완장' 도전과제 부여 함수.
    Nine_Bones가 없는 날 접속한 모든 유저에게 도전과제를 부여합니다.
    """
    # ✅ config.json 불러오기
    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)
    db_conf = config["db"]
    db_params = {
        "host": db_conf["host"],
        "port": db_conf["port"],
        "user": db_conf["user"],
        "password": db_conf["password"],
        "db": db_conf["database"],
        "charset": "utf8mb4"
    }

    conn = pymysql.connect(**db_params)
    try:
        with conn.cursor() as cursor:
            # 1️⃣ '완장' 도전과제 ID 조회
            cursor.execute("""
                SELECT achievement_id FROM achievements WHERE name = '완장'
            """)
            result = cursor.fetchone()
            if not result:
                print("[ERROR] '완장' 도전과제가 존재하지 않습니다.")
                return
            achievement_id = result[0]

            # 2️⃣ 이미 '완장' 달성한 유저 목록 조회
            cursor.execute("""
                SELECT user_id FROM user_achievements
                WHERE achievement_id = %s
            """, (achievement_id,))
            achieved_users = {row[0] for row in cursor.fetchall()}

            # 3️⃣ 시작일 ~ 오늘까지 날짜 순회
            start_date = datetime.strptime(start_date_str, "%Y-%m-%d").date()
            today = datetime.today().date()
            current_date = start_date

            while current_date <= today:
                date_str = current_date.strftime("%Y-%m-%d")
                # 4️⃣ 해당 날짜 참여자 조회
                cursor.execute("""
                    SELECT DISTINCT a.user_id, u.nickname
                    FROM attendance a
                    JOIN users u ON a.user_id = u.user_id
                    WHERE DATE(a.enter_time) = %s
                """, (date_str,))
                rows = cursor.fetchall()

                # 5️⃣ Nine_Bones가 있으면 스킵
                nicknames = [row[1] for row in rows]
                if "Nine_Bones" in nicknames:
                    print(f"[INFO] {date_str}: Nine_Bones가 참여 → 조건 불충족.")
                elif rows:  # Nine_Bones가 없고, 참여자가 있으면
                    new_achievers = [row[0] for row in rows if row[0] not in achieved_users]
                    if new_achievers:
                        for uid in new_achievers:
                            cursor.execute("""
                                INSERT INTO user_achievements (user_id, achievement_id, achieved_at)
                                VALUES (%s, %s, %s)
                            """, (uid, achievement_id, date_str))
                        conn.commit()
                        print(f"[INFO] {date_str}: {len(new_achievers)}명에게 '완장' 도전과제 지급 완료!")
                    else:
                        print(f"[INFO] {date_str}: 이미 모두 달성함.")
                else:
                    print(f"[INFO] {date_str}: 참여자가 없습니다.")
                current_date += timedelta(days=1)

    finally:
        conn.close()

#최애숭배:      한 곡 30번
def award_favorite_song_achievement(config_path="config.json"):
    """
    '최애숭배' 도전과제를 아직 받지 않은 유저를 대상으로,
    같은 곡을 30일 이상 튼 기록이 있으면 달성 처리합니다.
    """
    # ✅ config.json 불러오기
    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)
    db_conf = config["db"]
    db_params = {
        "host": db_conf["host"],
        "port": db_conf["port"],
        "user": db_conf["user"],
        "password": db_conf["password"],
        "db": db_conf["database"],
        "charset": "utf8mb4"
    }

    conn = pymysql.connect(**db_params)
    try:
        with conn.cursor() as cursor:
            # 1️⃣ '최애숭배' 도전과제 ID 조회
            cursor.execute("""
                SELECT achievement_id FROM achievements WHERE name = '최애숭배'
            """)
            result = cursor.fetchone()
            if not result:
                print("[ERROR] '최애숭배' 도전과제가 존재하지 않습니다.")
                return
            achievement_id = result[0]

            # 2️⃣ 이미 달성한 유저 제외
            cursor.execute("""
                SELECT user_id FROM user_achievements
                WHERE achievement_id = %s
            """, (achievement_id,))
            achieved_users = {row[0] for row in cursor.fetchall()}

            # 3️⃣ 달성 안 한 유저 중 음악 기록 있는 유저만 추림
            cursor.execute("""
                SELECT DISTINCT user_id FROM music_play
            """)
            all_users = [row[0] for row in cursor.fetchall()]
            target_users = [uid for uid in all_users if uid not in achieved_users]

            # 4️⃣ 각 유저별 동일 곡의 "하루 1번만 카운트" 기록 확인
            for uid in target_users:
                cursor.execute("""
                    SELECT title, COUNT(DISTINCT DATE(played_at)) as days, MAX(played_at)
                    FROM music_play
                    WHERE user_id = %s
                    GROUP BY title
                    HAVING days >= 30
                    ORDER BY days DESC
                    LIMIT 1
                """, (uid,))
                row = cursor.fetchone()
                if row:
                    title, days, last_played = row
                    cursor.execute("""
                        INSERT INTO user_achievements (user_id, achievement_id, achieved_at)
                        VALUES (%s, %s, %s)
                    """, (uid, achievement_id, last_played.date()))
                    conn.commit()
                    print(f"[INFO] 유저 {uid} - '{title}'을 {days}일간 재생 → '최애숭배' 달성!")
                else:
                    print(f"[INFO] 유저 {uid}: 조건 미충족 (30일 이상 기록 없음).")

    finally:
        conn.close()

def award_39_achievement(config_path="config.json"):
    """
    '39' 도전과제를 아직 받지 않은 유저를 대상으로,
    서로 다른 곡을 39개 이상 플레이했으면 달성 처리합니다.
    """
    # ✅ config.json 불러오기
    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)
    db_conf = config["db"]
    db_params = {
        "host": db_conf["host"],
        "port": db_conf["port"],
        "user": db_conf["user"],
        "password": db_conf["password"],
        "db": db_conf["database"],
        "charset": "utf8mb4"
    }

    conn = pymysql.connect(**db_params)
    try:
        with conn.cursor() as cursor:
            # 1️⃣ '39' 도전과제 ID 조회
            cursor.execute("""
                SELECT achievement_id FROM achievements WHERE name = '39'
            """)
            result = cursor.fetchone()
            if not result:
                print("[ERROR] '39' 도전과제가 존재하지 않습니다.")
                return
            achievement_id = result[0]

            # 2️⃣ 이미 달성한 유저 제외
            cursor.execute("""
                SELECT user_id FROM user_achievements
                WHERE achievement_id = %s
            """, (achievement_id,))
            achieved_users = {row[0] for row in cursor.fetchall()}

            # 3️⃣ 달성 안 한 유저 중 음악 기록 있는 유저만 추림
            cursor.execute("""
                SELECT DISTINCT user_id FROM music_play
            """)
            all_users = [row[0] for row in cursor.fetchall()]
            target_users = [uid for uid in all_users if uid not in achieved_users]

            # 4️⃣ 각 유저별 서로 다른 곡 개수와 마지막 재생일 확인
            for uid in target_users:
                cursor.execute("""
                    SELECT COUNT(DISTINCT title) as distinct_count, MAX(played_at)
                    FROM music_play
                    WHERE user_id = %s
                """, (uid,))
                row = cursor.fetchone()
                if row and row[0] >= 39:
                    distinct_count, last_played = row
                    cursor.execute("""
                        INSERT INTO user_achievements (user_id, achievement_id, achieved_at)
                        VALUES (%s, %s, %s)
                    """, (uid, achievement_id, last_played.date()))
                    conn.commit()
                    print(f"[INFO] 유저 {uid} - 서로 다른 곡 {distinct_count}개 플레이 → '39' 달성!")
                else:
                    print(f"[INFO] 유저 {uid}: 조건 미충족 (서로 다른 곡 {row[0]}개).")

    finally:
        conn.close()

START_DAY = '2025-05-12'
print("확인: 인싸")
award_inssa_achievement_from_date(START_DAY, config_path="config.json")
print("확인: 칠가이")
award_chill_guy_achievement("config.json")
print("확인: 과몰입")
award_over_immersed_achievement_from_date(START_DAY, config_path="config.json")
print("확인: 완장")
award_captain_achievement_from_date(START_DAY, config_path="config.json")
print("확인: 최애숭배")
award_favorite_song_achievement("config.json")
print("확인: 39")
award_39_achievement("config.json")
