# user_card.py
import os
from io import BytesIO
import pymysql
from flask import Blueprint, render_template, url_for, send_file, abort, request
from PIL import Image, ImageDraw, ImageFont, ImageOps


class UserCardService:
    """
    - DB 조회(유저/출석/도전과제 요약)
    - OG 이미지(1200x630) 동적 생성
    - Flask 라우트(페이지 + 이미지) 제공
    - 디자인: 상단 좌측 가로형(상/하 크롭) 이미지 배너, 우측에 이름/설명,
             하단(이미지 아래) 전체 폭에 3개 통계 카드,
             최하단 얇은 푸터(워터마크 고정)
    """
    def __init__(
        self,
        db_config: dict,
        profile_img_dir: str,
        profile_default_filename: str,
        font_path_bold: str,
        font_path_reg: str,
        brand_watermark: str = "저댄로그 · community",
        route_prefix: str = "",
        template_user_page: str = "user_page.html",
        cache_dir: str = "./og_cache",
    ):
        self.DB_CONFIG = db_config
        self.PROFILE_IMG_DIR = profile_img_dir
        self.PROFILE_DEFAULT_FILENAME = profile_default_filename
        self.FONT_PATH_BOLD = font_path_bold
        self.FONT_PATH_REG = font_path_reg
        self.BRAND_WATERMARK = brand_watermark
        self.ROUTE_PREFIX = route_prefix.rstrip("/")
        self.TEMPLATE_USER_PAGE = template_user_page

        self.bp = Blueprint("user_card", __name__)
        self._register_routes()

        self.CACHE_DIR = cache_dir
        os.makedirs(self.CACHE_DIR, exist_ok=True)

    # ---------- utils ----------
    @staticmethod
    def safe_filename(nickname: str) -> str:
        return nickname.replace("/", "_SLASH_").replace("⁄", "_SLASH_")

    @staticmethod
    def sec_to_hms_str(total_sec) -> str:
        # None/Decimal/float 모두 방어
        total_sec = int(total_sec or 0)
        h = total_sec // 3600
        m = (total_sec % 3600) // 60
        return f"{h:02d}:{m:02d}"

    def try_font(self, path: str, size: int):
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            return ImageFont.load_default()

    def fit_font(self, text: str, font_path: str, base_size: int, max_width: int, min_size: int = 20):
        """텍스트가 max_width를 넘지 않도록 폰트 크기를 자동 축소"""
        size = base_size
        # PIL 기본 폰트는 크기 제어가 어려우니 TrueType 기준
        while size >= min_size and os.path.exists(font_path):
            try:
                f = ImageFont.truetype(font_path, size)
            except Exception:
                break
            w = ImageDraw.Draw(Image.new("RGB", (10, 10))).textbbox((0, 0), text, font=f)[2]
            if w <= max_width:
                return f
            size -= 2
        # fallback
        try:
            return ImageFont.truetype(font_path, min_size)
        except Exception:
            return ImageFont.load_default()

    def resolve_profile_image(self, nickname: str) -> str:
        img_filename = self.safe_filename(nickname) + ".png"
        img_path = os.path.join(self.PROFILE_IMG_DIR, img_filename)
        if not os.path.exists(img_path):
            img_path = os.path.join(self.PROFILE_IMG_DIR, self.PROFILE_DEFAULT_FILENAME)
        return img_path

    # ---------- DB ----------
    def fetch_user_stats(self, nickname: str):
        """
        반환:
        {
            "user_id": int, "nickname": str, "comment": str,
            "total_count": int, "total_duration_sec": int,
            "achv_count": int, "last_attended": datetime|None
        } or None
        """
        conn = pymysql.connect(**self.DB_CONFIG)
        try:
            with conn.cursor() as cur:
                # 1) 유저
                cur.execute(
                    """
                    SELECT user_id, nickname, COALESCE(comment, '')
                    FROM users
                    WHERE nickname = %s
                    """,
                    (nickname,),
                )
                row = cur.fetchone()
                if not row:
                    return None
                user_id, nickname_db, comment = row

                # 2) 참여 횟수 요약
                cur.execute(
                    """
                    SELECT total_count, last_attended
                    FROM user_attendance_summary
                    WHERE user_id = %s
                    """,
                    (user_id,),
                )
                summary = cur.fetchone()
                if summary:
                    total_count, last_attended = summary
                else:
                    cur.execute("SELECT COUNT(*) FROM attendance WHERE user_id = %s", (user_id,))
                    total_count = (cur.fetchone() or [0])[0]
                    last_attended = None

                # 3) 총 참여 시간
                cur.execute(
                    """
                    SELECT COALESCE(SUM(duration_sec), 0)
                    FROM attendance
                    WHERE user_id = %s
                    """,
                    (user_id,),
                )
                total_duration_sec = (cur.fetchone() or [0])[0] or 0

                # 4) 도전과제 수
                cur.execute(
                    """
                    SELECT COUNT(*)
                    FROM user_achievements
                    WHERE user_id = %s
                    """,
                    (user_id,),
                )
                achv_count = (cur.fetchone() or [0])[0] or 0
                
                # 5) 최초 참가일
                cur.execute("SELECT MIN(enter_time) FROM attendance WHERE user_id = %s", (user_id,))
                first_attended = (cur.fetchone() or [None])[0]

                return {
                    "user_id": user_id,
                    "nickname": nickname_db,
                    "comment": comment,
                    "total_count": int(total_count or 0),
                    "total_duration_sec": int(total_duration_sec or 0),
                    "achv_count": int(achv_count or 0),
                    "last_attended": last_attended,
                    "first_attended": first_attended,
                }
        finally:
            conn.close()

    def compute_popular_music(self):
        conn = pymysql.connect(**self.DB_CONFIG)
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT title, COUNT(*) AS play_count
                    FROM music_play
                    WHERE played_at >= CURDATE() - INTERVAL 30 DAY
                      AND played_at < CURDATE()
                    GROUP BY title
                    ORDER BY play_count DESC, MAX(played_at) DESC
                    LIMIT 10
                    """
                )
                rows = cursor.fetchall()
                return [{"title": r[0], "count": r[1]} for r in rows]
        finally:
            conn.close()

    # ---------- Render OG Image ----------


    def render_user_card_image(self, stats: dict) -> Image.Image:
        """
        - 왼쪽 전체(푸터 포함)를 프로필 이미지가 가득 채우는 레이아웃
        - 오른쪽에 이름/소개 + 통계 2x2 + 우측 하단 푸터
        """
        # ===== 캔버스 & 여백 =====
        W, H = 1200, 630
        pad = 60
        gap = 28
        FOOTER_H = 48
        SAFE_MARGIN = 14

        # ===== 왼쪽 이미지 폭 (전체 높이 H 를 채움) =====
        LEFT_IMG_W = 512  # 필요하면 420, 450 등으로 조정 가능

        # ===== 우측 패널 상단(이름/소개) 고정 높이 =====
        RIGHT_PANEL_FIXED_H = 280  # 소개 길어도 이 높이까지만 사용

        # ===== 통계 그리드(2×2, 텍스트만) =====
        GRID_COLS = 2
        GRID_ROWS = 2
        COL_GAP   = 42
        ROW_GAP   = 18
        BLOCK_H   = 112

        # ===== 텍스트 간격 =====
        LABEL_VALUE_GAP    = 10
        VALUE_CENTER_SHIFT = 8
        NAME_SUB_GAP       = 30

        # ===== '소개 아래' 구분선 & 여백 =====
        PRE_STATS_GAP   = -10   # 선 '위' 여백
        LINE_AFTER_GAP  = 24    # 선 '아래' 기본 여백
        GRID_TOP_EXTRA  = 16    # ⬅ 선과 첫 번째 값/라벨이 겹치지 않도록 추가 여백
        LINE_COLOR      = (52, 56, 63)
        LINE_WIDTH      = 2

        # ===== 워터마크 우측 여백 =====
        WM_RIGHT_PAD = 16

        # ===== 배경 & Draw =====
        from PIL import ImageOps, Image, ImageDraw
        bg = Image.new("RGB", (W, H), (22, 24, 28))
        draw = ImageDraw.Draw(bg)

        # ===== 폰트 =====
        font_title = self.try_font(self.FONT_PATH_BOLD, 68)
        font_sub   = self.try_font(self.FONT_PATH_REG, 30)
        font_label = self.try_font(self.FONT_PATH_REG, 26)
        base_num_sz = 50
        font_num   = self.try_font(self.FONT_PATH_BOLD, base_num_sz)
        font_wm    = self.try_font(self.FONT_PATH_REG, 22)

        # ===== 유틸 =====
        def text_size(text, font):
            bbox = draw.textbbox((0, 0), text, font=font)
            return bbox[2] - bbox[0], bbox[3] - bbox[1]

        def text_w(text, font): return text_size(text, font)[0]
        def text_h(text, font): return text_size(text, font)[1]

        def wrap_text_clamped(text: str, font, max_width: int, max_height: int, line_spacing: int = 6):
            """우측 고정 영역 내 줄바꿈, 높이 초과 시 마지막 줄 말줄임표."""
            t = (text or "").strip()
            if not t:
                return [], 0
            words = t.split()
            lines, cur = [], ""

            def fits(s): return text_w(s, font) <= max_width or not s
            def can_push(line, cur_h):
                h = text_h(line, font)
                new_h = h if cur_h == 0 else cur_h + line_spacing + h
                return new_h <= max_height, h

            cur_h = 0
            if len(words) > 1:
                for w in words:
                    trial = (cur + " " + w).strip()
                    if fits(trial):
                        cur = trial
                    else:
                        if not cur:
                            break
                        ok, h = can_push(cur, cur_h)
                        if ok:
                            lines.append(cur)
                            cur_h = h if cur_h == 0 else cur_h + line_spacing + h
                            cur = w
                        else:
                            cur = ""
                            break
                if cur:
                    ok, h = can_push(cur, cur_h)
                    if ok:
                        lines.append(cur)
            if not lines and t:
                # 글자 단위 폴백
                cur, cur_h = "", 0
                for ch in t:
                    trial = cur + ch
                    if fits(trial):
                        cur = trial
                    else:
                        ok, h = can_push(cur, cur_h)
                        if ok:
                            lines.append(cur)
                            cur_h = h if cur_h == 0 else cur_h + line_spacing + h
                            cur = ch
                        else:
                            cur = ""
                            break
                if cur:
                    ok, h = can_push(cur, cur_h)
                    if ok:
                        lines.append(cur)

            # 말줄임표
            if lines:
                original = t
                rendered = " ".join(lines)
                if len(rendered) < len(original):
                    last = lines[-1]
                    if text_w(last + "…", font) <= max_width:
                        lines[-1] = last + "…"
                    else:
                        while last and text_w(last + "…", font) > max_width:
                            last = last[:-1]
                        lines[-1] = (last + "…") if last else "…"
            # 총 높이 계산
            total_h = 0
            for i, line in enumerate(lines):
                h = text_h(line, font)
                total_h += h if i == 0 else (6 + h)
            return lines, total_h

        def fmt_first(dt):
            if not dt: return "-"
            try:
                import datetime as _dt
                if isinstance(dt, (_dt.date, _dt.datetime)):
                    return dt.strftime("%Y.%m.%d")
                from dateutil import parser
                return parser.parse(str(dt)).strftime("%Y.%m.%d")
            except Exception:
                return str(dt)

        def fmt_duration(seconds: int) -> str:
            if not seconds or seconds <= 0:
                return "0m"
            h = seconds // 3600
            m = (seconds % 3600) // 60
            return (f"{h}h " if h > 0 else "") + f"{m}m"

        # ===== 왼쪽 전체 이미지(푸터 포함) =====
        img_x, img_y = 0, 0
        avatar_path = self.resolve_profile_image(stats["nickname"])
        try:
            src = Image.open(avatar_path).convert("RGB")
        except Exception:
            src = Image.new("RGB", (LEFT_IMG_W, H), (60, 65, 72))

        # 높이 H 전체를 채우도록 크롭/리사이즈
        banner = ImageOps.fit(src, (LEFT_IMG_W, H), centering=(0.5, 0.5))
        bg.paste(banner, (img_x, img_y))

        # ===== 우측 이름/소개 (고정 상단 영역) =====
        right_x0 = LEFT_IMG_W + pad
        right_x1 = W - pad
        RIGHT_W  = right_x1 - right_x0
        right_y0 = pad

        # 이름
        name_text = f"{stats['nickname']}"
        draw.text((right_x0, right_y0), name_text, fill=(240, 240, 245), font=font_title)
        _, name_h = text_size(name_text, font_title)

        # 소개(고정 영역 내)
        sub_area_top    = right_y0 + name_h + NAME_SUB_GAP
        sub_area_height = max(0, RIGHT_PANEL_FIXED_H - (name_h + NAME_SUB_GAP))
        subtitle        = (stats.get("comment") or "").strip()
        if subtitle and sub_area_height > 0:
            lines, _ = wrap_text_clamped(subtitle, font_sub, RIGHT_W, sub_area_height, line_spacing=6)
            y = sub_area_top
            for i, line in enumerate(lines):
                draw.text((right_x0, y), line, fill=(180, 183, 190), font=font_sub)
                y += text_h(line, font_sub) + (6 if i < len(lines)-1 else 0)

        # ===== 소개 아래: 선 & 여백 (고정) =====
        grid_left  = right_x0
        grid_right = right_x1
        sep_y = right_y0 + RIGHT_PANEL_FIXED_H + PRE_STATS_GAP
        draw.line((grid_left, sep_y, grid_right, sep_y), fill=LINE_COLOR, width=LINE_WIDTH)

        # 선 아래 충분한 여백을 확보해 겹침 방지
        grid_top   = sep_y + LINE_AFTER_GAP + GRID_TOP_EXTRA
        grid_width = grid_right - grid_left

        # 푸터와 겹치지 않게 보정(그리드만 위로 이동)
        total_grid_h = GRID_ROWS * BLOCK_H + (GRID_ROWS - 1) * ROW_GAP
        footer_top = H - FOOTER_H
        max_bottom = footer_top - SAFE_MARGIN
        if grid_top + total_grid_h > max_bottom:
            grid_top = max(pad, max_bottom - total_grid_h)

        # 오른쪽 영역 폭 기준 칼럼 폭
        col_w = (grid_width - (GRID_COLS - 1) * COL_GAP) // GRID_COLS

        # 통계 순서
        cards = [
            ("First joined",   fmt_first(stats.get("first_attended"))),
            ("Participations", f"{int(stats['total_count'])}"),
            ("Total time",     fmt_duration(stats['total_duration_sec'])),
            ("Achievements",   f"{int(stats['achv_count'])}"),
        ]

        for idx, (label_en, value) in enumerate(cards):
            row = idx // GRID_COLS
            col = idx % GRID_COLS

            x0 = grid_left + col * (col_w + COL_GAP)
            y0 = grid_top + row * (BLOCK_H + ROW_GAP)
            x1 = x0 + col_w
            y1 = y0 + BLOCK_H
            cx = (x0 + x1) // 2
            cy = (y0 + y1) // 2

            # 값 폭이 넓으면 축소
            max_value_w = col_w - 40
            if hasattr(self, "fit_font"):
                font_num_use = self.fit_font(value, self.FONT_PATH_BOLD, base_num_sz, max_value_w, min_size=24)
            else:
                font_num_use = font_num

            lbl_w, lbl_h = text_size(label_en, font_label)
            val_w, val_h = text_size(value, font_num_use)

            # 값: 중앙
            val_x = cx - val_w // 2
            val_y = cy - val_h // 2 + VALUE_CENTER_SHIFT
            draw.text((val_x, val_y), value, font=font_num_use, fill=(245, 247, 250))

            # 라벨: 값 위
            lbl_x = cx - lbl_w // 2
            lbl_y = val_y - lbl_h - LABEL_VALUE_GAP
            draw.text((lbl_x, lbl_y), label_en, font=font_label, fill=(170, 175, 182))

        # ===== 푸터 (오른쪽 영역에만) =====
        # 왼쪽은 이미지 그대로, 오른쪽만 푸터 바 생성
        draw.rectangle([LEFT_IMG_W, H - FOOTER_H, W, H], fill=(26, 28, 34))
        wm = self.BRAND_WATERMARK
        wm_w, wm_h = text_size(wm, font_wm)
        wm_x = W - WM_RIGHT_PAD - wm_w
        wm_y = H - FOOTER_H + (FOOTER_H - wm_h) // 2
        draw.text((wm_x, wm_y), wm, fill=(120, 125, 132), font=font_wm)

        return bg


    # ---------- Caching ---------
    def _cached_path(self, nickname: str) -> str:
        """닉네임 기준 캐시 파일 경로(.png)"""
        fname = self.safe_filename(nickname) + ".png"
        return os.path.join(self.CACHE_DIR, fname)

    def build_all_user_cards(self, overwrite: bool = True) -> dict:
        """
        모든 users.nickname에 대해 OG 이미지를 미리 생성해 캐시에 저장.
        overwrite=False 이면 이미 있는 파일은 건너뜀.
        반환: {'total': N, 'built': k, 'skipped': s, 'errors': [(nickname, errstr), ...]}
        """
        result = {"total": 0, "built": 0, "skipped": 0, "errors": []}
        conn = pymysql.connect(**self.DB_CONFIG)
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT nickname FROM users")
                rows = cur.fetchall()
                result["total"] = len(rows)
                print(rows)                

                for (nickname,) in rows:
                    try:
                        cache_path = self._cached_path(nickname)
                        if (not overwrite) and os.path.exists(cache_path):
                            result["skipped"] += 1
                            continue

                        stats = self.fetch_user_stats(nickname)
                        if not stats:
                            result["errors"].append((nickname, "stats_not_found"))
                            continue

                        img = self.render_user_card_image(stats)
                        img.save(cache_path, format="PNG")
                        result["built"] += 1
                    except Exception as e:
                        result["errors"].append((nickname, str(e)))
        finally:
            conn.close()
        return result


    def get_or_build_user_card(self, nickname: str, force_rebuild: bool = False) -> BytesIO:
        """
        캐시에 미리 생성된 이미지를 읽어 반환.
        - 없거나 force_rebuild=True 이면 바로 생성해서 캐시에 쓰고 반환.
        반환: PNG 바이너리(메모리 버퍼)
        """
        cache_path = self._cached_path(nickname)

        # 캐시 사용
        if (not force_rebuild) and os.path.exists(cache_path):
            with open(cache_path, "rb") as f:
                buf = BytesIO(f.read())
                buf.seek(0)
                return buf

        # 캐시에 없으면 생성
        stats = self.fetch_user_stats(nickname)
        if not stats:
            raise FileNotFoundError("user stats not found")

        img = self.render_user_card_image(stats)
        os.makedirs(self.CACHE_DIR, exist_ok=True)
        img.save(cache_path, format="PNG")

        buf = BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)
        return buf


    # ---------- Routes ----------
    def _register_routes(self):
        page_rule = (self.ROUTE_PREFIX + "/u/<nickname>") or "/u/<nickname>"
        og_rule = (self.ROUTE_PREFIX + "/og/u/<nickname>.png") or "/og/u/<nickname>.png"

        @self.bp.route(page_rule)
        def user_page(nickname):
            stats = self.fetch_user_stats(nickname)
            if not stats:
                abort(404)
            og_image_url = url_for("user_card.user_og_image", nickname=nickname, _external=True)
            return render_template(self.TEMPLATE_USER_PAGE, stats=stats, og_image_url=og_image_url)

        # @self.bp.route(og_rule)
        # def user_og_image(nickname):
        #     stats = self.fetch_user_stats(nickname)
        #     if not stats:
        #         abort(404)
        #     img = self.render_user_card_image(stats)
        #     buf = BytesIO()
        #     img.save(buf, format="PNG")
        #     buf.seek(0)
        #     return send_file(buf, mimetype="image/png")
        @self.bp.route(og_rule)
        def user_og_image(nickname):
            stats = self.fetch_user_stats(nickname)
            if not stats:
                abort(404)
            # 캐시 우선 반환 (쿼리로 강제 재생성 가능: ?rebuild=1)
            force = request.args.get("rebuild") in ("1", "true", "yes")
            try:
                buf = self.get_or_build_user_card(stats["nickname"], force_rebuild=force)
            except FileNotFoundError:
                abort(404)
            return send_file(buf, mimetype="image/png")



def create_user_card_blueprint(**kwargs) -> Blueprint:
    svc = UserCardService(**kwargs)
    return svc.bp

def build_all_user_cards(**kwargs) -> dict:
    svc = UserCardService(**kwargs)
    return svc.build_all_user_cards()