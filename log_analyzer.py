import re
from datetime import datetime, timedelta
from collections import defaultdict, deque
import requests
import json
import os


class PyPyDanceLogAnalyzer:
    def __init__(self, log_file_path: str, room_name: str = "PyPyDance", min_minutes: int = 30,
                 youtube_api_key: str = "", consented_users: list[str] = None):
        self.log_file_path = log_file_path
        self.room_name = room_name
        self.min_duration = timedelta(minutes=min_minutes)
        self.youtube_api_key = youtube_api_key
        self.consented_users = set(consented_users) if consented_users else set()

        # 정규식 패턴
        self.enter_room_pattern = re.compile(r"\d{4}\.\d{2}\.\d{2} \d{2}:\d{2}:\d{2} .*?Entering Room: " + re.escape(self.room_name))
        self.leave_room_pattern = re.compile(r"\d{4}\.\d{2}\.\d{2} \d{2}:\d{2}:\d{2} .*?(Successfully left room|Safe handle has been closed)")
        self.join_pattern = re.compile(r"(\d{4}\.\d{2}\.\d{2} \d{2}:\d{2}:\d{2}) .*?OnPlayerJoinComplete (.+)")
        self.left_pattern = re.compile(r"(\d{4}\.\d{2}\.\d{2} \d{2}:\d{2}:\d{2}) .*?OnPlayerLeft ([^(]+)")
        self.video_play_pattern = re.compile(
            r"(\d{4}\.\d{2}\.\d{2} \d{2}:\d{2}:\d{2}) .*?\[VRCX\] VideoPlay\(" + re.escape(self.room_name) + r"\) \"([^\"]+)\",.*?,\"([^\"]+)\""
        )

    def parse_time(self, line_or_ts: str):
        return datetime.strptime(line_or_ts[:19], "%Y.%m.%d %H:%M:%S")


    def get_youtube_title(self, video_id: str, cache_path="youtube_title_cache.json"):
        # 캐시 파일 불러오기
        if os.path.exists(cache_path):
            try:
                with open(cache_path, "r", encoding="utf-8") as f:
                    cache = json.load(f)
            except Exception as e:
                print(f"[WARN] 캐시 파일 읽기 실패: {e}")
                cache = {}
        else:
            cache = {}

        # 캐시에 있으면 반환
        if video_id in cache:
            return cache[video_id]

        # API 키 없으면 ID 반환
        if not self.youtube_api_key:
            return video_id

        # API 요청
        try:
            url = f"https://www.googleapis.com/youtube/v3/videos?part=snippet&id={video_id}&key={self.youtube_api_key}"
            resp = requests.get(url)
            data = resp.json()
            title = data["items"][0]["snippet"]["title"] if data.get("items") else video_id
        except Exception as e:
            print(f"[WARN] 유튜브 제목 조회 실패: {video_id}: {e}")
            return video_id

        # 캐시에 저장하고 반환
        cache[video_id] = title
        try:
            with open(cache_path, "w", encoding="utf-8") as f:
                json.dump(cache, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[WARN] 캐시 파일 저장 실패: {e}")

        return title

    def extract_valid_ranges(self, lines):
        ranges = []
        current = None
        for i, line in enumerate(lines):
            if self.enter_room_pattern.search(line):
                current = {"start_index": i}
            elif current and self.leave_room_pattern.search(line):
                current["end_index"] = i
                ranges.append(current)
                current = None
        return ranges

    def analyze_range(self, lines, start_idx, end_idx):
        join_times = {}
        left_times = {}
        range_end_time = self.parse_time(lines[end_idx][:19])

        for i in range(start_idx, end_idx + 1):
            line = lines[i]
            jm = self.join_pattern.search(line)
            if jm:
                ts = self.parse_time(jm.group(1))
                name = jm.group(2).strip() 
                if name not in join_times:
                    join_times[name] = ts

            lm = self.left_pattern.search(line)
            if lm:
                ts = self.parse_time(lm.group(1))
                name = lm.group(2).strip() 
                left_times[name] = ts

        for name, join_time in join_times.items():
            if self.consented_users and name not in self.consented_users:
                continue  # 동의하지 않은 사람은 무시
            leave_time = left_times.get(name, range_end_time)
            duration = leave_time - join_time
            if duration > timedelta(seconds=0):
                yield {
                    "type": "attendance",
                    "name": name,
                    "start": join_time,
                    "end": leave_time,
                    "duration": duration
                }

    def extract_music_logs(self, lines):
        last_entries = deque(maxlen=5)
        for line in lines:
            m = self.video_play_pattern.search(line)
            if not m:
                continue

            ts = self.parse_time(m.group(1))
            url = m.group(2)
            meta = m.group(3)

            title = None
            user = "Unknown"

            # 메타 정보 파싱
            if " : " in meta and "(" in meta:
                try:
                    title_part = meta.split(" : ", 1)[1]
                    title, user = title_part.rsplit("(", 1)
                except ValueError:
                    continue
            elif "(" in meta:
                try:
                    title, user = meta.rsplit("(", 1)
                except ValueError:
                    continue
            else:
                title = meta.strip()

            title = title.strip()
            user = user.strip(")")

            # 동의 사용자 검사
            if self.consented_users and user not in self.consented_users:
                continue

            # 유튜브 제목 보정
            if "youtu.be" in url or "youtube.com" in url:
                vid_match = re.search(r"(?:v=|be/)([\w\-]+)", url)
                if vid_match:
                    video_id = vid_match.group(1)
                    title = self.get_youtube_title(video_id)

            entry = (ts, title, user)
            if not any(prev[1] == title and prev[2] == user for prev in last_entries):
                last_entries.append(entry)
                yield {
                    "type": "music",
                    "timestamp": ts,
                    "title": title,
                    "user": user,
                    "url": url  # 추가
                }


    def analyze(self):
        with open(self.log_file_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        # 출석
        ranges = self.extract_valid_ranges(lines)
        attendance_total = defaultdict(timedelta)
        attendance_logs = []

        for r in ranges:
            for entry in self.analyze_range(lines, r["start_index"], r["end_index"]):
                attendance_total[entry["name"]] += entry["duration"]
                attendance_logs.append(entry)

        valid_attendance = [a for a in attendance_logs if attendance_total[a["name"]] >= self.min_duration]

        # 음악
        music_logs = list(self.extract_music_logs(lines))

        # 출력
        print(f"\n[출석자 명단] ({self.room_name} 방, {self.min_duration} 이상)")
        for entry in sorted(valid_attendance, key=lambda e: e["start"]):
            print(f" - {entry['name']} | {entry['start']} ~ {entry['end']} ({entry['duration']})")

        print(f"\n[재생된 음악 목록] ({self.room_name} 방)")
        for entry in sorted(music_logs, key=lambda e: e["timestamp"]):
            print(f" - {entry['timestamp']} | {entry['title']} | {entry['user']}")

    def get_metrics(self):
        with open(self.log_file_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        ranges = self.extract_valid_ranges(lines)
        attendance_total = defaultdict(timedelta)
        attendance_logs = []

        for r in ranges:
            for entry in self.analyze_range(lines, r["start_index"], r["end_index"]):
                attendance_total[entry["name"]] += entry["duration"]
                attendance_logs.append(entry)

        valid_attendance = [a for a in attendance_logs if attendance_total[a["name"]] >= self.min_duration]
        music_logs = list(self.extract_music_logs(lines))

        return {
            "attendance": sorted(valid_attendance, key=lambda e: e["start"]),
            "music": sorted(music_logs, key=lambda e: e["timestamp"])
        }

if __name__ == "__main__":
    consented_list = ["!"]
    analyzer = PyPyDanceLogAnalyzer(
        log_file_path="!",
        room_name="PyPyDance",
        min_minutes=30,
        youtube_api_key="!",
        consented_users=consented_list
    )
    analyzer.analyze()
