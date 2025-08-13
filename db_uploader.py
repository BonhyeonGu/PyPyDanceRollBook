import os
import json
import time
import pymysql
from datetime import datetime
from log_analyzer import PyPyDanceLogAnalyzer


def load_config(config_path):
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)


def get_consented_users(db_conf):
    conn = pymysql.connect(
        host=db_conf["host"],
        port=db_conf.get("port", 3306),
        user=db_conf["user"],
        password=db_conf["password"],
        db=db_conf["database"],
        charset="utf8mb4"
    )
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT nickname FROM users")
            result = cursor.fetchall()
            return {row[0] for row in result}
    finally:
        conn.close()


def get_log_files(directory="."):
    files = [f for f in os.listdir(directory) if f.startswith("output_log") and f.endswith(".txt")]
    files.sort(key=lambda f: os.path.getmtime(os.path.join(directory, f)))
    return files


def get_last_processed_line(db_conf, filename):
    conn = pymysql.connect(
        host=db_conf["host"],
        port=db_conf.get("port", 3306),
        user=db_conf["user"],
        password=db_conf["password"],
        db=db_conf["database"],
        charset="utf8mb4"
    )
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT last_line_processed FROM log_process_tracker WHERE log_filename = %s", (filename,))
            result = cursor.fetchone()
            return result[0] if result else 0
    finally:
        conn.close()


def update_last_processed_line(db_conf, filename, line_number):
    conn = pymysql.connect(
        host=db_conf["host"],
        port=db_conf.get("port", 3306),
        user=db_conf["user"],
        password=db_conf["password"],
        db=db_conf["database"],
        charset="utf8mb4"
    )
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                INSERT INTO log_process_tracker (log_filename, last_line_processed)
                VALUES (%s, %s)
                ON DUPLICATE KEY UPDATE last_line_processed = %s
            """, (filename, line_number, line_number))
        conn.commit()
    finally:
        conn.close()


def insert_results_to_db(db_conf, attendance_list, music_list):
    conn = pymysql.connect(
        host=db_conf["host"],
        port=db_conf.get("port", 3306),
        user=db_conf["user"],
        password=db_conf["password"],
        db=db_conf["database"],
        charset="utf8mb4"
    )
    try:
        with conn.cursor() as cursor:
            for a in attendance_list:
                cursor.execute(
                    "SELECT user_id FROM users WHERE nickname = %s",
                    (a["name"],)
                )
                result = cursor.fetchone()
                if result:
                    user_id = result[0]
                    cursor.execute("""
                        INSERT INTO attendance (user_id, enter_time, leave_time, duration_sec)
                        VALUES (%s, %s, %s, %s)
                    """, (user_id, a["start"], a["end"], int(a["duration"].total_seconds())))

                    cursor.execute("""
                        INSERT INTO user_attendance_summary (user_id, total_count, last_attended)
                        VALUES (%s, 1, %s)
                        ON DUPLICATE KEY UPDATE
                            total_count = total_count + 1,
                            last_attended = GREATEST(last_attended, VALUES(last_attended))
                    """, (user_id, a["end"]))

            for m in music_list:
                cursor.execute(
                    "SELECT user_id FROM users WHERE nickname = %s",
                    (m["user"],)
                )
                result = cursor.fetchone()
                if result:
                    user_id = result[0]
                    cursor.execute("""
                        INSERT INTO music_play (user_id, played_at, title, url)
                        VALUES (%s, %s, %s, %s)
                    """, (user_id, m["timestamp"], m["title"], m["url"]))

        conn.commit()
    finally:
        conn.close()


def should_run_now(target_time_str):
    now = datetime.now()
    target_time = datetime.strptime(target_time_str, "%H:%M").time()
    return now.time().hour == target_time.hour and now.time().minute == target_time.minute


def run_analysis(config):
    db_conf = config["db"]
    consented_users = get_consented_users(db_conf)
    log_dir = os.path.dirname(config["log_file_path"]) or "."

    for filename in get_log_files(log_dir):
        filepath = os.path.join(log_dir, filename)
        last_line = get_last_processed_line(db_conf, filename)

        with open(filepath, "r", encoding="utf-8") as f:
            all_lines = f.readlines()

        new_lines = all_lines[last_line:]
        if not new_lines:
            continue

        analyzer = PyPyDanceLogAnalyzer(
            log_file_path=filepath,
            room_name=config.get("room_name", "PyPyDance"),
            min_minutes=config.get("min_minutes", 30),
            youtube_api_key=config.get("youtube_api_key", ""),
            consented_users=consented_users,
            baned_songs=config.get("baned_songs", [])
        )

        analyzer._lines_override = new_lines
        metrics = analyzer.get_metrics()

        print(f"\n[{filename}] 처리 결과:")
        print("[출석자 명단]")
        for a in metrics["attendance"]:
            print(f"- {a['name']} | {a['start']} ~ {a['end']} ({a['duration']})")

        print("\n[재생된 음악 목록]")
        for m in metrics["music"]:
            print(f"- {m['timestamp']} | {m['title']} | {m['user']}")

        insert_results_to_db(db_conf, metrics["attendance"], metrics["music"])
        update_last_processed_line(db_conf, filename, len(all_lines))


def main():
    config = load_config("config.json")
    interval = config.get("check_interval_sec", 60)

    if interval == -1:
        print("[INFO] 설정에 따라 즉시 한 번 실행 후 종료합니다.")
        run_analysis(config)
        return

    last_run_date = None
    while True:
        now = datetime.now()
        if should_run_now(config["run_time"]):
            if last_run_date != now.date():
                print(f"[{now}] 실행 조건 만족. 분석 시작.")
                run_analysis(config)
                last_run_date = now.date()
            #else:
            #    print(f"[{now}] 이미 실행됨. 다음 날 대기 중...")

        time.sleep(interval)


if __name__ == "__main__":
    main()
