import pymysql
import json
import os
from datetime import datetime, timedelta
from collections import defaultdict

START_DAY = '2025-05-12'
DEFAULT_CACHE_PATH = "achievement_cache.json"
CONFIG_PATH = "config.json"

def load_achievement_cache(cache_path=DEFAULT_CACHE_PATH):
    """
    캐시 파일을 불러옵니다. 없으면 빈 딕셔너리 반환.
    """
    if os.path.exists(cache_path):
        with open(cache_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_achievement_cache(cache_data, cache_path=DEFAULT_CACHE_PATH):
    """
    캐시 데이터를 파일에 저장합니다.
    """
    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(cache_data, f, ensure_ascii=False, indent=2)

def ensure_achievement_key(cache_data, achievement_name):
    """
    주어진 캐시에 해당 도전과제 키가 없으면 빈 딕셔너리로 초기화합니다.
    """
    if achievement_name not in cache_data:
        cache_data[achievement_name] = {}
    return cache_data[achievement_name]

def sync_cache_to_db(cache_data, achievement_name, conn):
    """
    캐시에 저장된 user_id → 날짜 정보를 DB에 반영합니다.
    이미 DB에 있는 경우는 무시됩니다.
    """
    with conn.cursor() as cursor:
        # 도전과제 ID 조회
        cursor.execute("""
            SELECT achievement_id FROM achievements WHERE name = %s
        """, (achievement_name,))
        result = cursor.fetchone()
        if not result:
            raise ValueError(f"[ERROR] 도전과제 '{achievement_name}'이 존재하지 않습니다.")
        achievement_id = result[0]

        # 이미 존재하는 (user_id, date) 쌍 조회
        cursor.execute("""
            SELECT user_id, DATE(achieved_at) FROM user_achievements
            WHERE achievement_id = %s
        """, (achievement_id,))
        already_in_db = {(uid, date.strftime("%Y-%m-%d")) for uid, date in cursor.fetchall()}

        inserted = 0
        for uid_str, date in cache_data.get(achievement_name, {}).items():
            uid = int(uid_str)  # 👈 명시적으로 int 변환
            if (uid, date) not in already_in_db:
                cursor.execute("""
                    INSERT IGNORE INTO user_achievements (user_id, achievement_id, achieved_at)
                    VALUES (%s, %s, %s)
                """, (uid, achievement_id, date))  # 👈 uid는 이제 int형
                inserted += 1

        if inserted:
            conn.commit()
            print(f"[SYNC] 캐시에서 DB로 {inserted}건 삽입 완료.")


#인싸:        10명이서 저댄
def award_inssa_achievement_from_date(start_date_str: str, conn):
    """
    '인싸' 도전과제: 하루에 10명 이상이 참여한 날, 그날 참석한 모든 유저에게 도전과제 부여
    - 캐시: 기록용
    - 중복 방지: DB 기준으로 판단
    - conn: 외부에서 주입된 pymysql 커넥션
    """
    # 📌 캐시 로딩 및 키 보장
    cache = load_achievement_cache()
    inssa_cache = ensure_achievement_key(cache, "인싸")

    # 📌 캐시 → DB 동기화
    sync_cache_to_db(cache, "인싸", conn)

    try:
        with conn.cursor() as cursor:
            # 1️⃣ 도전과제 ID 조회
            cursor.execute("SELECT achievement_id FROM achievements WHERE name = '인싸'")
            result = cursor.fetchone()
            if not result:
                print("[ERROR] '인싸' 도전과제가 존재하지 않습니다.")
                return
            achievement_id = result[0]

            # 2️⃣ 날짜 루프
            start_date = datetime.strptime(start_date_str, "%Y-%m-%d").date()
            today = datetime.today().date()
            current_date = start_date
            new_awards = {}

            while current_date <= today:
                date_str = current_date.strftime("%Y-%m-%d")

                # 3️⃣ 해당 날짜 참여 유저 조회
                cursor.execute("""
                    SELECT DISTINCT user_id
                    FROM attendance
                    WHERE DATE(enter_time) = %s
                """, (date_str,))
                user_ids = [row[0] for row in cursor.fetchall()]

                if len(user_ids) >= 10:
                    # 4️⃣ DB 기준 중복 제거
                    cursor.execute("""
                        SELECT user_id FROM user_achievements
                        WHERE achievement_id = %s
                    """, (achievement_id,))
                    already_awarded = {row[0] for row in cursor.fetchall()}

                    to_award = [uid for uid in user_ids if uid not in already_awarded]

                    # 5️⃣ INSERT & 캐시에 기록
                    for uid in to_award:
                        cursor.execute("""
                            INSERT INTO user_achievements (user_id, achievement_id, achieved_at)
                            VALUES (%s, %s, %s)
                        """, (uid, achievement_id, date_str))
                        new_awards[str(uid)] = date_str

                    if to_award:
                        conn.commit()
                        print(f"[INFO] {date_str}: {len(to_award)}명에게 '인싸' 도전과제 지급 완료!")
                    else:
                        print(f"[INFO] {date_str}: 이미 모두 달성함.")
                else:
                    print(f"[INFO] {date_str}: 참여자 {len(user_ids)}명으로 조건 불충족.")

                current_date += timedelta(days=1)

        # 6️⃣ 캐시 갱신 및 저장
        inssa_cache.update(new_awards)
        save_achievement_cache(cache)

    except Exception as e:
        print(f"[FATAL] 실행 중 예외 발생: {e}")

#칠가이:        7일 연속 저댄
def award_chill_guy_achievement(conn):
    cache = load_achievement_cache()
    chill_cache = ensure_achievement_key(cache, "ChillGuy")

    try:
        sync_cache_to_db(cache, "ChillGuy", conn)

        with conn.cursor() as cursor:
            # 1️⃣ 도전과제 ID 조회
            cursor.execute("SELECT achievement_id FROM achievements WHERE name = 'ChillGuy'")
            result = cursor.fetchone()
            if not result:
                print("[ERROR] 'ChillGuy' 도전과제가 존재하지 않습니다.")
                return
            achievement_id = result[0]

            # 2️⃣ 전체 유저 조회
            cursor.execute("SELECT DISTINCT user_id FROM attendance")
            all_users = [row[0] for row in cursor.fetchall()]

            # 2-1️⃣ DB에 이미 달성한 유저 확인
            cursor.execute("""
                SELECT user_id FROM user_achievements
                WHERE achievement_id = %s
            """, (achievement_id,))
            already_awarded = {row[0] for row in cursor.fetchall()}

            # 2-2️⃣ 캐시 + DB 모두에 없는 유저만 대상
            target_users = [
                uid for uid in all_users
                if str(uid) not in chill_cache and uid not in already_awarded
            ]

            new_awards = {}

            # 3️⃣ 7일 연속 출석 검사
            for uid in target_users:
                cursor.execute("""
                    SELECT DISTINCT DATE(enter_time) as day
                    FROM attendance
                    WHERE user_id = %s
                    ORDER BY day
                """, (uid,))
                dates = [row[0] for row in cursor.fetchall()]
                if len(dates) < 7:
                    continue

                dates_set = set(dates)
                for i in range(len(dates)):
                    start_date = dates[i]
                    if all((start_date + timedelta(days=j)) in dates_set for j in range(7)):
                        achieved_at = (start_date + timedelta(days=6)).strftime("%Y-%m-%d")
                        cursor.execute("""
                            INSERT INTO user_achievements (user_id, achievement_id, achieved_at)
                            VALUES (%s, %s, %s)
                        """, (uid, achievement_id, achieved_at))
                        conn.commit()
                        new_awards[str(uid)] = achieved_at
                        print(f"[INFO] 유저 {uid} - 7일 연속 출석으로 'ChillGuy' 달성!")
                        break

            # 5️⃣ 캐시 갱신
            chill_cache.update(new_awards)
            save_achievement_cache(cache)

    except Exception as e:
        print(f"[ERROR] 처리 중 오류 발생: {e}")

#과몰입:        단 둘이서
def award_over_immersed_achievement_from_date(start_date_str, conn):
    """
    도전과제 '과몰입' 부여:
    특정 날짜 이후, 딱 두 명만 출석한 날에 한하여,
    그 두 명 중 아직 해당 도전과제를 획득하지 않은 사람에게 부여.
    """

    cache = load_achievement_cache()
    over_cache = ensure_achievement_key(cache, "과몰입")

    try:
        sync_cache_to_db(cache, "과몰입", conn)

        with conn.cursor() as cursor:
            # 1️⃣ '과몰입' 도전과제 ID 조회
            cursor.execute("SELECT achievement_id FROM achievements WHERE name = '과몰입'")
            result = cursor.fetchone()
            if not result:
                print("[ERROR] '과몰입' 도전과제가 존재하지 않습니다.")
                return
            achievement_id = result[0]

            # 2️⃣ 시작일부터 오늘까지 순회
            start_date = datetime.strptime(start_date_str, "%Y-%m-%d").date()
            today = datetime.today().date()
            current_date = start_date

            new_awards = {}

            while current_date <= today:
                date_str = current_date.strftime("%Y-%m-%d")

                cursor.execute("""
                    SELECT DISTINCT user_id
                    FROM attendance
                    WHERE DATE(enter_time) = %s
                """, (date_str,))
                users = [row[0] for row in cursor.fetchall()]

                if len(users) == 2:
                    new_achievers = [uid for uid in users if str(uid) not in over_cache]

                    for uid in new_achievers:
                        cursor.execute("""
                            INSERT INTO user_achievements (user_id, achievement_id, achieved_at)
                            VALUES (%s, %s, %s)
                        """, (uid, achievement_id, date_str))
                        new_awards[str(uid)] = date_str

                    if new_achievers:
                        conn.commit()
                        print(f"[INFO] {date_str}: {len(new_achievers)}명에게 '과몰입' 도전과제 지급 완료!")
                    else:
                        print(f"[INFO] {date_str}: 캐시에 의해 모두 달성된 상태입니다.")
                else:
                    print(f"[INFO] {date_str}: 참여자 수 {len(users)}명 → 조건 불충족.")

                current_date += timedelta(days=1)

            over_cache.update(new_awards)
            save_achievement_cache(cache)

    except Exception as e:
        print(f"[ERROR] 처리 중 예외 발생: {e}")

#완장:         나없을때 저댄
def award_captain_achievement_from_date(start_date_str, conn):
    """
    '완장' 도전과제 부여 함수.
    Nine_Bones가 참여하지 않은 날의 출석자 중 아직 도전과제를 획득하지 않은 사람에게 부여.
    """

    cache = load_achievement_cache()
    captain_cache = ensure_achievement_key(cache, "완장")

    try:
        sync_cache_to_db(cache, "완장", conn)

        with conn.cursor() as cursor:
            # 1️⃣ '완장' 도전과제 ID 조회
            cursor.execute("SELECT achievement_id FROM achievements WHERE name = '완장'")
            result = cursor.fetchone()
            if not result:
                print("[ERROR] '완장' 도전과제가 존재하지 않습니다.")
                return
            achievement_id = result[0]

            # 2️⃣ 날짜 순회
            start_date = datetime.strptime(start_date_str, "%Y-%m-%d").date()
            today = datetime.today().date()
            current_date = start_date

            new_awards = {}

            while current_date <= today:
                date_str = current_date.strftime("%Y-%m-%d")
                cursor.execute("""
                    SELECT DISTINCT a.user_id, u.nickname
                    FROM attendance a
                    JOIN users u ON a.user_id = u.user_id
                    WHERE DATE(a.enter_time) = %s
                """, (date_str,))
                rows = cursor.fetchall()

                nicknames = [row[1] for row in rows]
                if "Nine_Bones" in nicknames:
                    print(f"[INFO] {date_str}: Nine_Bones가 참여 → 조건 불충족.")
                elif rows:
                    # 캐시에 없는 사람만 추출
                    new_achievers = [row[0] for row in rows if str(row[0]) not in captain_cache]

                    for uid in new_achievers:
                        cursor.execute("""
                            INSERT INTO user_achievements (user_id, achievement_id, achieved_at)
                            VALUES (%s, %s, %s)
                        """, (uid, achievement_id, date_str))
                        new_awards[str(uid)] = date_str

                    if new_achievers:
                        conn.commit()
                        print(f"[INFO] {date_str}: {len(new_achievers)}명에게 '완장' 도전과제 지급 완료!")
                    else:
                        print(f"[INFO] {date_str}: 캐시에 의해 모두 달성함.")
                else:
                    print(f"[INFO] {date_str}: 참여자가 없습니다.")

                current_date += timedelta(days=1)

            # 캐시 저장
            captain_cache.update(new_awards)
            save_achievement_cache(cache)

    except Exception as e:
        print(f"[ERROR] 처리 중 오류 발생: {e}")

#최애숭배:      한 곡 30번
def award_favorite_song_achievement(conn):
    """
    '최애숭배' 도전과제 부여:
    같은 곡을 30일 이상 튼 유저에게, 30번째 날짜를 달성일로 기록.
    하루에 여러 번 재생해도 1일 1회로 계산.
    """

    cache = load_achievement_cache()
    favorite_cache = ensure_achievement_key(cache, "최애숭배")

    try:
        sync_cache_to_db(cache, "최애숭배", conn)

        with conn.cursor() as cursor:
            # 1️⃣ 도전과제 ID 조회
            cursor.execute("SELECT achievement_id FROM achievements WHERE name = '최애숭배'")
            result = cursor.fetchone()
            if not result:
                print("[ERROR] '최애숭배' 도전과제가 존재하지 않습니다.")
                return
            achievement_id = result[0]

            # 2️⃣ music_play 기록이 있는 유저 중 캐시에 없는 유저만 추림
            cursor.execute("SELECT DISTINCT user_id FROM music_play")
            all_users = [row[0] for row in cursor.fetchall()]
            target_users = [uid for uid in all_users if str(uid) not in favorite_cache]

            new_awards = {}

            for uid in target_users:
                # 곡별로 재생 날짜 수집 (중복 날짜 제거용 GROUP BY)
                cursor.execute("""
                    SELECT title, DATE(played_at) as play_day
                    FROM music_play
                    WHERE user_id = %s
                    GROUP BY title, play_day
                    ORDER BY title, play_day
                """, (uid,))
                rows = cursor.fetchall()

                song_days = defaultdict(list)
                for title, play_day in rows:
                    song_days[title].append(play_day)

                for title, days in song_days.items():
                    if len(days) >= 30:
                        achieved_at = days[29]  # 0-indexed 30번째 날짜
                        cursor.execute("""
                            INSERT INTO user_achievements (user_id, achievement_id, achieved_at)
                            VALUES (%s, %s, %s)
                        """, (uid, achievement_id, achieved_at.strftime('%Y-%m-%d')))
                        conn.commit()
                        new_awards[str(uid)] = achieved_at.strftime('%Y-%m-%d')
                        print(f"[INFO] 유저 {uid} - '{title}'을 {len(days)}일간 재생 → '최애숭배' 달성일: {achieved_at}")
                        break  # 한 곡으로 만족하면 다음 유저로

            favorite_cache.update(new_awards)
            save_achievement_cache(cache)

    except Exception as e:
        print(f"[ERROR] 처리 중 예외 발생: {e}")

#39:           39가지의 곡
def award_39_achievement(conn):
    """
    '39' 도전과제 부여:
    서로 다른 곡 39개 이상 플레이한 유저에게,
    39번째 곡의 최초 재생일을 기준으로 달성 처리.
    """
    try:
        cache = load_achievement_cache()
        a39_cache = ensure_achievement_key(cache, "39")

        sync_cache_to_db(cache, "39", conn)

        with conn.cursor() as cursor:
            # 1️⃣ 도전과제 ID 조회
            cursor.execute("SELECT achievement_id FROM achievements WHERE name = '39'")
            result = cursor.fetchone()
            if not result:
                print("[ERROR] '39' 도전과제가 존재하지 않습니다.")
                return
            achievement_id = result[0]

            # 2️⃣ music_play 기록 있는 유저 중 캐시에 없는 유저만 추림
            cursor.execute("SELECT DISTINCT user_id FROM music_play")
            all_users = [row[0] for row in cursor.fetchall()]
            target_users = [uid for uid in all_users if str(uid) not in a39_cache]

            new_awards = {}

            # 3️⃣ 각 유저별 서로 다른 곡의 최초 재생일 정렬
            for uid in target_users:
                cursor.execute("""
                    SELECT MIN(played_at) as first_played
                    FROM music_play
                    WHERE user_id = %s
                    GROUP BY title
                    ORDER BY first_played ASC
                    LIMIT 39
                """, (uid,))
                rows = cursor.fetchall()

                if len(rows) < 39:
                    print(f"[INFO] 유저 {uid}: 조건 미충족 (서로 다른 곡 {len(rows)}개).")
                    continue

                achieved_at = rows[-1][0].date()
                cursor.execute("""
                    INSERT INTO user_achievements (user_id, achievement_id, achieved_at)
                    VALUES (%s, %s, %s)
                """, (uid, achievement_id, achieved_at.strftime('%Y-%m-%d')))
                conn.commit()

                new_awards[str(uid)] = achieved_at.strftime('%Y-%m-%d')
                print(f"[INFO] 유저 {uid} - 최초 39곡 달성일: {achieved_at} → '39' 달성!")

            a39_cache.update(new_awards)
            save_achievement_cache(cache)

    except Exception as e:
        print(f"[ERROR] 처리 중 예외 발생: {e}")

#파인튜닝:    30일동안 평균 55분
def award_finetuning_achievement(conn, verbose: bool = False):
    """
    유저의 각 출석일 기준, 해당 날짜 포함 이전 출석일 최대 30개에 대해
    평균 플레이 시간이 55분 이상이면 도전과제 '파인튜닝'을 달성합니다.

    ✅ 도전과제 등록 시 해당 유저는 더 이상 평가하지 않음
    ✅ 모든 평가 구간은 verbose=True일 때만 로그 출력
    ✅ 각 날짜의 참여 시간도 함께 로그에 출력
    """

    cache = load_achievement_cache()
    fine_cache = ensure_achievement_key(cache, "finet파인튜닝uning")

    try:
        sync_cache_to_db(cache, "파인튜닝", conn)

        with conn.cursor() as cursor:
            # 1️⃣ 도전과제 ID 조회
            cursor.execute("""
                SELECT achievement_id FROM achievements WHERE name = '파인튜닝'
            """)
            result = cursor.fetchone()
            if not result:
                print("[ERROR] '파인튜닝' 도전과제가 존재하지 않습니다.")
                return
            achievement_id = result[0]

            # 2️⃣ 출석 기록 있는 유저 중 캐시에 없는 유저만 대상
            cursor.execute("SELECT DISTINCT user_id FROM attendance")
            all_users = [row[0] for row in cursor.fetchall()]
            target_users = [uid for uid in all_users if str(uid) not in fine_cache]

            new_awards = {}

            for uid in target_users:
                # 출석일 목록 (오름차순)
                cursor.execute("""
                    SELECT DISTINCT DATE(enter_time) as day
                    FROM attendance
                    WHERE user_id = %s
                    ORDER BY day
                """, (uid,))
                attendance_days = [row[0] for row in cursor.fetchall()]
                total_attendances = len(attendance_days)

                if total_attendances == 0:
                    if verbose:
                        print(f"[유저 {uid}] ▶ 출석일 없음 → 평가 불가\n")
                    continue

                for idx in range(total_attendances):
                    current_day = attendance_days[idx]
                    window_days = attendance_days[max(0, idx - 29):idx + 1]
                    start_day = window_days[0]
                    end_day = window_days[-1]

                    # 전체 총 시간 계산
                    cursor.execute("""
                        SELECT SUM(duration_sec)
                        FROM attendance
                        WHERE user_id = %s AND DATE(enter_time) BETWEEN %s AND %s
                    """, (uid, start_day, end_day))
                    total_seconds = cursor.fetchone()[0] or 0
                    avg_minutes = (total_seconds / 60) / len(window_days)

                    # 각 날짜별 duration도 조회
                    cursor.execute("""
                        SELECT DATE(enter_time), SUM(duration_sec)
                        FROM attendance
                        WHERE user_id = %s AND DATE(enter_time) BETWEEN %s AND %s
                        GROUP BY DATE(enter_time)
                    """, (uid, start_day, end_day))
                    per_day_durations = {row[0]: row[1] for row in cursor.fetchall()}

                    if verbose:
                        day_str_list = [
                            f"{d.strftime('%m-%d')} ({(per_day_durations.get(d, 0))/60:.1f}분)"
                            for d in window_days
                        ]
                        status = "✅" if len(window_days) == 30 and avg_minutes >= 55 else "❌"
                        print(f"[유저 {uid}] ▶ 기준일: {current_day.strftime('%m-%d')} | 출석일 수: {len(window_days)} | 평균: {avg_minutes:.2f}분 {status}")
                        print(f"       ↳ 날짜들: [{', '.join(day_str_list)}]")

                    # 조건 만족 → 등록 및 종료
                    if len(window_days) == 30 and avg_minutes >= 55:
                        cursor.execute("""
                            INSERT INTO user_achievements (user_id, achievement_id, achieved_at)
                            VALUES (%s, %s, %s)
                        """, (uid, achievement_id, current_day.strftime("%Y-%m-%d")))
                        conn.commit()
                        new_awards[str(uid)] = current_day.strftime("%Y-%m-%d")
                        if verbose:
                            print(f"[유저 {uid}] ▶ 도전과제 '파인튜닝' 달성 후 평가 종료\n")
                        break  # 유저 평가 중단

                if verbose:
                    print()

            fine_cache.update(new_awards)
            save_achievement_cache(cache)

    except Exception as e:
        print(f"[ERROR] 처리 중 예외 발생: {e}")

#엣지오브투머로우: 3일 연속 동일한 5곡
def award_edge_of_tomorrow(conn):
    """
    '엣지오브투머로우' 도전과제:
    3일 연속, 동일한 5곡을 동일한 순서로 플레이하면 달성.
    단, 각 날짜 내 어디든 연속으로 등장하면 인정.
    """

    def extract_sequences(title_list, length=5):
        return [tuple(title_list[i:i+length]) for i in range(len(title_list) - length + 1)]

    cache = load_achievement_cache()
    edge_cache = ensure_achievement_key(cache, "엣지오브투머로우")

    try:
        sync_cache_to_db(cache, "엣지오브투머로우", conn)

        with conn.cursor() as cursor:
            # 1️⃣ 도전과제 ID 조회
            cursor.execute("SELECT achievement_id FROM achievements WHERE name = '엣지오브투머로우'")
            result = cursor.fetchone()
            if not result:
                print("[ERROR] '엣지오브투머로우' 도전과제가 존재하지 않습니다.")
                return
            achievement_id = result[0]

            # 2️⃣ music_play 기록 있는 유저 중 캐시에 없는 유저만 추림
            cursor.execute("SELECT DISTINCT user_id FROM music_play")
            all_users = [row[0] for row in cursor.fetchall()]
            target_users = [uid for uid in all_users if str(uid) not in edge_cache]

            new_awards = {}

            for uid in target_users:
                cursor.execute("""
                    SELECT DATE(played_at), title
                    FROM music_play
                    WHERE user_id = %s
                    ORDER BY played_at
                """, (uid,))
                rows = cursor.fetchall()

                if not rows:
                    continue

                daily_titles = defaultdict(list)
                for date, title in rows:
                    daily_titles[date].append(title)

                sorted_days = sorted(daily_titles.keys())
                if len(sorted_days) < 3:
                    continue

                for i in range(len(sorted_days) - 2):
                    d1, d2, d3 = sorted_days[i:i+3]
                    if d2 != d1 + timedelta(days=1) or d3 != d2 + timedelta(days=1):
                        continue

                    l1, l2, l3 = daily_titles[d1], daily_titles[d2], daily_titles[d3]
                    if len(l1) < 5 or len(l2) < 5 or len(l3) < 5:
                        continue

                    s1 = set(extract_sequences(l1))
                    s2 = set(extract_sequences(l2))
                    s3 = set(extract_sequences(l3))

                    common = s1 & s2 & s3
                    if common:
                        achieved_at = d3.strftime("%Y-%m-%d")
                        cursor.execute("""
                            INSERT INTO user_achievements (user_id, achievement_id, achieved_at)
                            VALUES (%s, %s, %s)
                        """, (uid, achievement_id, achieved_at))
                        conn.commit()

                        edge_cache[str(uid)] = achieved_at
                        print(f"[유저 {uid}] ▶ '엣지오브투머로우' 달성! (공통 시퀀스: {common.pop()} | 날짜: {achieved_at})")
                        break  # 한 번 달성 시 평가 종료

            save_achievement_cache(cache)

    except Exception as e:
        print(f"[ERROR] 처리 중 예외 발생: {e}")

#도원결의: 전달 플레이 3개 동일하게
def award_dowon_pledge(conn):
    """
    '도원결의' 도전과제:
    전날 누군가가 연속으로 재생한 3곡과 동일한 3곡을,
    다음날 누군가가 동일 순서로 연속 재생하면 달성.
    """

    cache = load_achievement_cache()
    dowon_cache = ensure_achievement_key(cache, "도원결의")

    try:
        sync_cache_to_db(cache, "도원결의", conn)

        with conn.cursor() as cursor:
            # 1️⃣ 도전과제 ID 조회
            cursor.execute("SELECT achievement_id FROM achievements WHERE name = '도원결의'")
            result = cursor.fetchone()
            if not result:
                print("[ERROR] '도원결의' 도전과제가 존재하지 않습니다.")
                return
            achievement_id = result[0]

            # 2️⃣ 이미 달성한 유저는 캐시 기준으로 필터링
            achieved_users = set(dowon_cache.keys())

            # 3️⃣ 날짜 리스트 조회
            cursor.execute("SELECT DISTINCT DATE(played_at) AS day FROM music_play ORDER BY day")
            all_days = [row[0] for row in cursor.fetchall()]

            new_awards = {}

            for i in range(1, len(all_days)):
                prev_day = all_days[i - 1]
                curr_day = all_days[i]

                # 전날 연속 3곡 시퀀스 수집
                cursor.execute("""
                    SELECT user_id, played_at, title
                    FROM music_play
                    WHERE DATE(played_at) = %s
                    ORDER BY user_id, played_at
                """, (prev_day,))
                rows = cursor.fetchall()

                prev_sequences = set()
                user_tracks = defaultdict(list)
                for uid, _, title in rows:
                    user_tracks[uid].append(title)
                for track_list in user_tracks.values():
                    for j in range(len(track_list) - 2):
                        prev_sequences.add(tuple(track_list[j:j+3]))
                if not prev_sequences:
                    continue

                # 당일 유저의 시퀀스 검사
                cursor.execute("""
                    SELECT user_id, played_at, title
                    FROM music_play
                    WHERE DATE(played_at) = %s
                    ORDER BY user_id, played_at
                """, (curr_day,))
                rows = cursor.fetchall()

                today_tracks = defaultdict(list)
                for uid, _, title in rows:
                    today_tracks[uid].append(title)

                for uid, track_list in today_tracks.items():
                    if str(uid) in dowon_cache or len(track_list) < 3:
                        continue

                    for j in range(len(track_list) - 2):
                        seq = tuple(track_list[j:j+3])
                        if seq in prev_sequences:
                            achieved_at = curr_day.strftime("%Y-%m-%d")
                            cursor.execute("""
                                INSERT INTO user_achievements (user_id, achievement_id, achieved_at)
                                VALUES (%s, %s, %s)
                            """, (uid, achievement_id, achieved_at))
                            conn.commit()
                            dowon_cache[str(uid)] = achieved_at
                            print(f"[유저 {uid}] ▶ '도원결의' 달성! ({achieved_at})")
                            break

            save_achievement_cache(cache)

    except Exception as e:
        print(f"[ERROR] 처리 중 예외 발생: {e}")

#마이웨이: 3-9명 6번
def award_myway_achievement(conn):
    cache = load_achievement_cache()
    myway_cache = ensure_achievement_key(cache, "마이웨이")

    try:
        sync_cache_to_db(cache, "마이웨이", conn)

        with conn.cursor() as cursor:
            # 1️⃣ 도전과제 ID 조회
            cursor.execute("SELECT achievement_id FROM achievements WHERE name = '마이웨이'")
            result = cursor.fetchone()
            if not result:
                print("[ERROR] '마이웨이' 도전과제가 존재하지 않습니다.")
                return
            achievement_id = result[0]

            # 2️⃣ 전체 유저 조회
            cursor.execute("SELECT DISTINCT user_id FROM attendance")
            all_users = [row[0] for row in cursor.fetchall()]

            # 3️⃣ DB에서 이미 달성한 유저
            cursor.execute("""
                SELECT user_id FROM user_achievements
                WHERE achievement_id = %s
            """, (achievement_id,))
            already_awarded = {row[0] for row in cursor.fetchall()}

            # 4️⃣ 캐시 + DB 모두에 없는 유저만 필터링
            target_users = [
                uid for uid in all_users
                if str(uid) not in myway_cache and uid not in already_awarded
            ]

            new_awards = {}

            # 5️⃣ 유저별로 조사
            for uid in target_users:
                cursor.execute("""
                    SELECT DATE(a.enter_time) AS day, COUNT(DISTINCT a.user_id) AS attendee_count
                    FROM attendance a
                    WHERE DATE(a.enter_time) IN (
                        SELECT DISTINCT DATE(enter_time)
                        FROM attendance
                        WHERE user_id = %s
                    )
                    GROUP BY day
                    HAVING attendee_count BETWEEN 3 AND 9
                    ORDER BY day
                """, (uid,))
                rows = cursor.fetchall()

                # 참석한 날 중 인원 수를 기준으로 다양한 날 개수 확인
                distinct_attendee_counts = set()
                valid_days_log = []  # (day, attendee_count) 저장
                latest_date = None

                for day, count in rows:
                    if count not in distinct_attendee_counts:
                        distinct_attendee_counts.add(count)
                        valid_days_log.append((day.strftime("%Y-%m-%d"), count))
                        latest_date = day

                if len(distinct_attendee_counts) >= 6:
                    achieved_at = latest_date.strftime("%Y-%m-%d")
                    cursor.execute("""
                        INSERT INTO user_achievements (user_id, achievement_id, achieved_at)
                        VALUES (%s, %s, %s)
                    """, (uid, achievement_id, achieved_at))
                    conn.commit()
                    new_awards[str(uid)] = achieved_at

                    print(f"[INFO] 유저 {uid} - '마이웨이' 도전과제 달성! (최종날짜: {achieved_at})")
                    print("        조건 만족 날짜 및 인원 수:")
                    for day_str, cnt in valid_days_log:
                        print(f"         - {day_str} ({cnt}명)")
                else:
                    print(f"[INFO] 유저 {uid} - 조건 불충족 ({len(distinct_attendee_counts)}종 인원 수)")

            # 6️⃣ 캐시 저장
            myway_cache.update(new_awards)
            save_achievement_cache(cache)

    except Exception as e:
        print(f"[ERROR] 처리 중 오류 발생: {e}")


# 조별과제: 6명 이상 출석 && 6명 이상 2곡 이상 플레이
def award_team_project_achievement(start_date_str: str, conn):
    cache = load_achievement_cache()
    team_cache = ensure_achievement_key(cache, "조별과제")

    sync_cache_to_db(cache, "조별과제", conn)

    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT achievement_id FROM achievements WHERE name = '조별과제'")
            result = cursor.fetchone()
            if not result:
                print("[ERROR] '조별과제' 도전과제가 존재하지 않습니다.")
                return
            achievement_id = result[0]

            start_date = datetime.strptime(start_date_str, "%Y-%m-%d").date()
            today = datetime.today().date()
            current_date = start_date
            new_awards = {}

            while current_date <= today:
                date_str = current_date.strftime("%Y-%m-%d")

                # 1️⃣ 출석자 목록
                cursor.execute("""
                    SELECT DISTINCT user_id
                    FROM attendance
                    WHERE DATE(enter_time) = %s
                """, (date_str,))
                user_ids = [row[0] for row in cursor.fetchall()]

                if len(user_ids) < 6:
                    print(f"[INFO] {date_str}: 출석자 {len(user_ids)}명 → 조건 불충족")
                    current_date += timedelta(days=1)
                    continue

                # 2️⃣ 2곡 이상 플레이한 유저 수 확인 (music_play 기준)
                cursor.execute("""
                    SELECT user_id
                    FROM music_play
                    WHERE DATE(played_at) = %s
                    GROUP BY user_id
                    HAVING COUNT(*) >= 2
                """, (date_str,))
                qualified_users = [row[0] for row in cursor.fetchall()]
                qualified_count = len(qualified_users)

                if qualified_count < 6:
                    print(f"[INFO] {date_str}: 2곡 이상 유저 {qualified_count}명 → 조건 불충족")
                    current_date += timedelta(days=1)
                    continue

                # 3️⃣ 이미 도전과제 받은 유저 필터링
                cursor.execute("""
                    SELECT user_id FROM user_achievements
                    WHERE achievement_id = %s
                """, (achievement_id,))
                already_awarded = {row[0] for row in cursor.fetchall()}

                to_award = [uid for uid in user_ids if uid not in already_awarded]

                for uid in to_award:
                    cursor.execute("""
                        INSERT INTO user_achievements (user_id, achievement_id, achieved_at)
                        VALUES (%s, %s, %s)
                    """, (uid, achievement_id, date_str))
                    new_awards[str(uid)] = date_str

                if to_award:
                    conn.commit()
                    print(f"[INFO] {date_str}: 조별과제 달성자 {len(to_award)}명 기록 완료!")
                else:
                    print(f"[INFO] {date_str}: 이미 모든 유저가 조별과제 달성함.")

                current_date += timedelta(days=1)

            team_cache.update(new_awards)
            save_achievement_cache(cache)

    except Exception as e:
        print(f"[FATAL] 실행 중 예외 발생: {e}")


#월말평가: 3달 랭킹 누적




# 📌 DB 연결
with open(CONFIG_PATH, "r", encoding="utf-8") as f:
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
        print("확인: 인싸")
        award_inssa_achievement_from_date(START_DAY, conn)
        print("확인: 칠가이")
        award_chill_guy_achievement(conn)
        print("확인: 과몰입")
        award_over_immersed_achievement_from_date(START_DAY, conn)
        print("확인: 완장")
        award_captain_achievement_from_date(START_DAY, conn)
        print("확인: 최애숭배")
        award_favorite_song_achievement(conn)
        print("확인: 39")
        award_39_achievement(conn)
        print("확인: 파인튜닝")
        award_finetuning_achievement(conn)
        print("확인: 엣지오브투머로우")
        award_edge_of_tomorrow(conn)
        print("확인: 도원결의")
        award_dowon_pledge(conn)
        print("확인: 마이웨이")
        award_myway_achievement(conn)
        print("확인: 조별과제")
        award_team_project_achievement(START_DAY, conn)
except Exception as e:
    import traceback
    print(f"[FATAL] 실행 중 예외 발생: {e}")
    traceback.print_exc()
finally:
    try:
        if conn and conn.open:
            conn.close()
    except Exception:
        pass