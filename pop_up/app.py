#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Moodle Desktop Assistant (Dark Theme) - Backend & Real Moodle Connector
Ubicación: pop_up/app.py
Soporta:
  1. Autenticación CAS EDEA Junta de Andalucía ("Acceso Único Educación" - Usuario IdEA / Pasen / Séneca)
     en https://educacionadistancia.juntadeandalucia.es/centros/sevilla/my/ (y sevilla25, FP, Adultos)
  2. Autenticación local Moodle ("Otro tipo de acceso" con logintoken / ?authCAS=NOCAS)
  3. API móvil de Moodle (/login/token.php) y sincronización por .ics o Cookie MoodleSession.
"""

import datetime
import html as html_lib
import http.cookiejar
import http.server
import json
import os
import re
import shutil
import socket
import ssl
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid
import webbrowser
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
STATIC_DIR = BASE_DIR / "static"
DATA_FILE = DATA_DIR / "assistant_data.json"
COOKIES_JSON_FILE = DATA_DIR / "moodle_cookies.json"

DATA_DIR.mkdir(parents=True, exist_ok=True)
STATIC_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_MOODLE_ENTRY_URL = "https://educacionadistancia.juntadeandalucia.es/centros/sevilla/my/"

COURSE_COLORS = [
    "#6366f1", "#10b981", "#f59e0b", "#ec4899",
    "#06b6d4", "#8b5cf6", "#3b82f6", "#f43f5e"
]


def pick_color_for_course(course_name: str) -> str:
    if not course_name:
        return "#6366f1"
    idx = sum(ord(c) for c in course_name) % len(COURSE_COLORS)
    return COURSE_COLORS[idx]


def create_ssl_context():
    ctx = ssl._create_unverified_context()
    return ctx


def normalize_moodle_base_url(raw_url: str) -> str:
    url = (raw_url or DEFAULT_MOODLE_ENTRY_URL).strip()
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    url = url.split("?", 1)[0].split("#", 1)[0].rstrip("/")
    suffixes = [
        "/my/index.php",
        "/my/courses.php",
        "/my",
        "/login/index.php",
        "/login",
        "/calendar/view.php",
        "/calendar",
        "/user/profile.php",
        "/user/preferences.php",
        "/index.php"
    ]
    lower_url = url.lower()
    for s in suffixes:
        if lower_url.endswith(s):
            url = url[: len(url) - len(s)].rstrip("/")
            break
    return url


def get_default_data():
    """Estado inicial limpio, sin ningún dato falso o de ejemplo."""
    return {
        "profile": {
            "linked": False,
            "studentName": "",
            "username": "",
            "authType": "auto",  # "auto" (CAS IdEA + Local), "cas" (Acceso Único Educación), "local" (Otro tipo de acceso)
            "university": "Moodle Centros - Junta de Andalucía (Sevilla)",
            "degree": "",
            "moodleEntryUrl": DEFAULT_MOODLE_ENTRY_URL,
            "moodleBaseUrl": normalize_moodle_base_url(DEFAULT_MOODLE_ENTRY_URL),
            "moodleProfileUrl": "https://educacionadistancia.juntadeandalucia.es/centros/sevilla/user/profile.php",
            "icsUrl": "",
            "apiToken": "",
            "sessionCookie": "",
            "userid": None,
            "userPictureUrl": "",
            "lastSync": "Sin sincronizar",
            "openMode": "both",
            "avatarInitials": "MD"
        },
        "courses": [],
        "moodleTasks": [],
        "personalEvents": [],
        "schedule": [],
        "grades": [],
        "notes": [],
        "pomodoroStats": {
            "completedSessions": 0,
            "totalMinutes": 0
        }
    }


def load_data():
    if not DATA_FILE.exists():
        data = get_default_data()
        save_data(data)
        return data
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if "courses" not in data:
            data["courses"] = []
        if "authType" not in data.get("profile", {}):
            data.setdefault("profile", {})["authType"] = "auto"
        return data
    except Exception:
        data = get_default_data()
        save_data(data)
        return data


def save_data(data):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# PARSER DE CALENDARIO MOODLE (.ICS)
# ---------------------------------------------------------------------------
def parse_ics_datetime(dt_raw: str):
    clean = dt_raw.strip()
    if ":" in clean:
        clean = clean.split(":", 1)[1].strip()
    m = re.match(r"^(\d{4})(\d{2})(\d{2})(?:T(\d{2})(\d{2})(\d{2})Z?)?", clean)
    if not m:
        today = datetime.date.today().isoformat()
        return today, "23:55"
    y, mo, d, hh, mm, _ss = m.groups()
    if dt_raw.endswith("Z") and hh and mm:
        try:
            dt_utc = datetime.datetime(int(y), int(mo), int(d), int(hh), int(mm), tzinfo=datetime.timezone.utc)
            dt_local = dt_utc.astimezone()
            return dt_local.strftime("%Y-%m-%d"), dt_local.strftime("%H:%M")
        except Exception:
            pass
    date_str = f"{y}-{mo}-{d}"
    time_str = f"{hh}:{mm}" if hh and mm else "23:55"
    return date_str, time_str


def parse_ics_content(ics_text: str, moodle_base_url: str = ""):
    unfolded = re.sub(r"\r?\n[ \t]", "", ics_text)
    blocks = re.findall(r"BEGIN:VEVENT(.*?)END:VEVENT", unfolded, flags=re.DOTALL)
    tasks = []
    base = normalize_moodle_base_url(moodle_base_url) if moodle_base_url else ""

    for idx, block in enumerate(blocks):
        fields = {}
        for line in block.splitlines():
            line = line.strip()
            if not line or ":" not in line:
                continue
            key_part, val_part = line.split(":", 1)
            key_name = key_part.split(";")[0].upper()
            fields[key_name] = val_part.strip()

        summary = fields.get("SUMMARY", "Evento de Moodle")
        summary = summary.replace("\\,", ",").replace("\\;", ";").replace("\\n", " ").strip()

        description = fields.get("DESCRIPTION", "")
        description = description.replace("\\n", "\n").replace("\\,", ",").replace("\\;", ";").strip()

        categories = fields.get("CATEGORIES", "").replace("\\,", ", ").strip()
        course = categories if categories else "Moodle"

        dt_raw = fields.get("DTEND") or fields.get("DTSTART") or ""
        due_date, due_time = parse_ics_datetime(dt_raw)

        url = fields.get("URL", "").strip()
        if not url and description:
            m_url = re.search(r"https?://[^\s<>\"']+", description)
            if m_url:
                url = m_url.group(0)
        if not url:
            if base:
                url = f"{base}/my/"
            else:
                q = urllib.parse.quote_plus(f"Moodle {course} {summary}")
                url = f"https://www.google.com/search?q={q}"

        uid = fields.get("UID", f"ics-{idx}-{uuid.uuid4().hex[:6]}")
        task_id = "moodle-" + re.sub(r"[^a-zA-Z0-9_-]", "", uid)[:32]

        tasks.append({
            "id": task_id,
            "title": summary,
            "course": course,
            "courseCode": course[:10].upper(),
            "dueDate": due_date,
            "dueTime": due_time,
            "status": "pending",
            "priority": "high",
            "description": description or "Evento sincronizado desde el calendario de Moodle.",
            "moodleUrl": url,
            "source": "moodle",
            "color": pick_color_for_course(course)
        })

    return tasks


# ---------------------------------------------------------------------------
# CLIENTE DE CONEXIÓN REAL CON MOODLE SEVILLA (CAS EDEA + LOCAL + API)
# ---------------------------------------------------------------------------
def clean_html_text(raw_html: str) -> str:
    if not raw_html:
        return ""
    txt = re.sub(r"<br\s*/?>", "\n", raw_html, flags=re.I)
    txt = re.sub(r"<[^>]+>", "", txt)
    txt = html_lib.unescape(txt)
    return re.sub(r"\n{3,}", "\n\n", txt).strip()


class MoodleSessionConnector:
    """
    Conector especializado en Moodle Centros Junta de Andalucía (Sevilla) y Moodle estándar:
      - Soporta el Servicio de Autenticación Centralizado (CAS EDEA: edea.juntadeandalucia.es/cas/login)
        usado por el botón "Acceso Único Educación" (?authCAS=CAS) con Usuario IdEA (Pasen / Séneca).
      - Soporta el acceso local de Moodle ("Otro tipo de acceso" -> ?authCAS=NOCAS) con logintoken.
      - Soporta salto automático entre /centros/sevilla (26-27) y /centros/sevilla25 (25-26) usando el ticket SSO CAS.
    """

    def __init__(self, entry_url: str):
        self.entry_url = (entry_url or DEFAULT_MOODLE_ENTRY_URL).strip()
        self.base_url = normalize_moodle_base_url(self.entry_url)
        self.ssl_ctx = create_ssl_context()
        self.cookie_jar = http.cookiejar.CookieJar()
        self._load_cookies_json()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.cookie_jar),
            urllib.request.HTTPSHandler(context=self.ssl_ctx)
        )
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,application/json,*/*;q=0.8",
            "Accept-Language": "es-ES,es;q=0.9"
        }
        self.sesskey = None
        self.userid = None
        self.student_name = ""
        self.site_name = ""
        self.user_picture = ""
        self.wstoken = ""

    def _save_cookies_json(self):
        try:
            items = []
            for c in self.cookie_jar:
                items.append({
                    "name": c.name,
                    "value": c.value,
                    "domain": c.domain,
                    "path": c.path,
                    "secure": c.secure
                })
            with open(COOKIES_JSON_FILE, "w", encoding="utf-8") as f:
                json.dump(items, f)
        except Exception:
            pass

    def _load_cookies_json(self):
        if not COOKIES_JSON_FILE.exists():
            return
        try:
            with open(COOKIES_JSON_FILE, "r", encoding="utf-8") as f:
                items = json.load(f)
            for it in items:
                cookie = http.cookiejar.Cookie(
                    version=0,
                    name=it["name"],
                    value=it["value"],
                    port=None,
                    port_specified=False,
                    domain=it["domain"],
                    domain_specified=True,
                    domain_initial_dot=it["domain"].startswith("."),
                    path=it.get("path", "/"),
                    path_specified=True,
                    secure=bool(it.get("secure", True)),
                    expires=None,
                    discard=False,
                    comment=None,
                    comment_url=None,
                    rest={}
                )
                self.cookie_jar.set_cookie(cookie)
        except Exception:
            pass

    def _request(self, url: str, data=None, extra_headers=None, timeout=20):
        hdrs = dict(self.headers)
        if extra_headers:
            hdrs.update(extra_headers)
        req = urllib.request.Request(url, data=data, headers=hdrs)
        resp = self.opener.open(req, timeout=timeout)
        raw = resp.read().decode("utf-8", errors="replace")
        return resp.geturl(), raw

    def set_manual_session_cookie(self, moodle_session_val: str):
        if not moodle_session_val:
            return
        parsed = urllib.parse.urlparse(self.base_url)
        cookie = http.cookiejar.Cookie(
            version=0,
            name="MoodleSession",
            value=moodle_session_val.strip(),
            port=None,
            port_specified=False,
            domain=parsed.hostname,
            domain_specified=True,
            domain_initial_dot=False,
            path="/",
            path_specified=True,
            secure=parsed.scheme == "https",
            expires=None,
            discard=False,
            comment=None,
            comment_url=None,
            rest={}
        )
        self.cookie_jar.set_cookie(cookie)
        self._save_cookies_json()

    def try_obtain_mobile_token(self, username: str, password: str):
        for service_slug in ("moodle_mobile_app", "local_mobile"):
            try:
                token_url = f"{self.base_url}/login/token.php"
                form = urllib.parse.urlencode({
                    "username": username,
                    "password": password,
                    "service": service_slug
                }).encode("utf-8")
                _, body = self._request(token_url, data=form)
                info = json.loads(body)
                if isinstance(info, dict) and info.get("token"):
                    self.wstoken = info["token"]
                    return self.wstoken
            except Exception:
                continue
        return ""

    def _login_via_junta_cas(self, username: str, password: str) -> str:
        """
        Inicia sesión a través del botón "Acceso Único Educación" (?authCAS=CAS),
        que redirige al servidor CAS centralizado de la Junta de Andalucía:
        https://edea.juntadeandalucia.es/cas/login?service=...
        """
        cas_trigger_url = f"{self.base_url}/login/index.php?authCAS=CAS"
        final_url, html_page = self._request(cas_trigger_url)

        # Si ya tenía sesión CAS activa y entró directo a Moodle
        if "educacionadistancia.juntadeandalucia.es" in final_url and "/login/" not in final_url:
            self._extract_page_metadata(html_page)
            if self.sesskey and self.userid:
                self._save_cookies_json()
                return html_page

        # Extraer token 'execution' del formulario CAS (#fm1)
        m_exec = re.search(r'name=["\']execution["\']\s+value=["\']([^"\']+)["\']', html_page)
        if not m_exec:
            m_exec = re.search(r'value=["\']([^"\']+)["\']\s+name=["\']execution["\']', html_page)

        if not m_exec:
            raise ValueError("El servidor no mostró el formulario CAS de la Junta de Andalucía.")

        execution_val = m_exec.group(1)

        cas_payload = urllib.parse.urlencode({
            "username": username,
            "password": password,
            "execution": execution_val,
            "_eventId": "submit",
            "geolocation": ""
        }).encode("utf-8")

        parsed_cas = urllib.parse.urlparse(final_url)
        cas_origin = f"{parsed_cas.scheme}://{parsed_cas.netloc}"

        try:
            post_url, post_html = self._request(
                final_url,
                data=cas_payload,
                extra_headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Origin": cas_origin,
                    "Referer": final_url
                }
            )
        except urllib.error.HTTPError as http_err:
            err_body = ""
            try:
                err_body = http_err.read().decode("utf-8", errors="replace")
            except Exception:
                pass
            alerts = [
                clean_html_text(a)
                for a in re.findall(r'<div[^>]+class=["\'][^"\']*alert[^"\']*["\'][^>]*>(.*?)</div>', err_body, re.S)
            ]
            alerts = [a for a in alerts if a and "contraseñas de las cuentas idea" not in a.lower()]
            detail = alerts[0] if alerts else "Usuario IdEA o contraseña incorrectos en el Acceso Único de Educación (Séneca/Pasen)."
            raise ValueError(detail)

        # Comprobar si CAS nos devolvió a Moodle o se quedó en edea.juntadeandalucia.es
        if "edea.juntadeandalucia.es/cas" in post_url:
            alerts = [
                clean_html_text(a)
                for a in re.findall(r'<div[^>]+class=["\'][^"\']*alert[^"\']*["\'][^>]*>(.*?)</div>', post_html, re.S)
            ]
            alerts = [a for a in alerts if a and "contraseñas de las cuentas idea" not in a.lower()]
            detail = alerts[0] if alerts else "No se pudo completar el acceso en CAS Junta de Andalucía. Revisa tu usuario IdEA y contraseña."
            raise ValueError(detail)

        # Asegurar que cargamos /my/ para extraer M.cfg (sesskey, userid)
        _, my_html = self._request(f"{self.base_url}/my/")
        self._extract_page_metadata(my_html)
        self._save_cookies_json()
        return my_html

    def _login_via_moodle_local_form(self, username: str, password: str) -> str:
        """
        Inicia sesión mediante el formulario estándar de Moodle ("Otro tipo de acceso": ?authCAS=NOCAS o /login/index.php).
        """
        login_url = f"{self.base_url}/login/index.php?authCAS=NOCAS"
        final_url, login_html = self._request(login_url)
        if "logintoken" not in login_html:
            login_url = f"{self.base_url}/login/index.php"
            final_url, login_html = self._request(login_url)

        m_token = re.search(r'name=["\']logintoken["\']\s+value=["\']([^"\']+)["\']', login_html)
        if not m_token:
            m_token = re.search(r'value=["\']([^"\']+)["\']\s+name=["\']logintoken["\']', login_html)
        logintoken = m_token.group(1) if m_token else ""

        m_action = re.search(r'<form[^>]+action=["\']([^"\']*login/index\.php[^"\']*)["\']', login_html, flags=re.I)
        post_url = m_action.group(1) if m_action else f"{self.base_url}/login/index.php"

        payload = {
            "anchor": "",
            "username": username,
            "password": password
        }
        if logintoken:
            payload["logintoken"] = logintoken

        encoded = urllib.parse.urlencode(payload).encode("utf-8")
        post_final_url, post_html = self._request(
            post_url,
            data=encoded,
            extra_headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Referer": login_url
            }
        )

        if "loginerrormessage" in post_html or "datos erróneos" in post_html.lower() or "acceso inválido" in post_html.lower():
            raise ValueError("Credenciales rechazadas en el formulario local de Moodle.")

        _, my_html = self._request(f"{self.base_url}/my/")
        self._extract_page_metadata(my_html)
        if not self.sesskey or not self.userid:
            raise ValueError("No se pudo iniciar sesión con cuenta local de Moodle.")

        self._save_cookies_json()
        return my_html

    def login_web_session(self, username: str, password: str, auth_type: str = "auto") -> str:
        """
        Prueba automáticamente el método de autenticación adecuado:
          1. Si es Moodle de la Junta de Andalucía (o auth_type in ('auto', 'cas')), prueba primero
             CAS EDEA ("Acceso Único Educación" con Usuario IdEA / Pasen / Séneca).
          2. Si el usuario eligió 'local' o su cuenta no es IdEA, prueba el formulario local de Moodle.
        """
        self. cookie_jar.clear()
        is_junta = "juntadeandalucia.es" in self.base_url.lower()
        errors = []

        if auth_type in ("auto", "cas") and is_junta:
            try:
                return self._login_via_junta_cas(username, password)
            except Exception as cas_err:
                errors.append(f"Acceso Único IdEA (CAS): {cas_err}")
                if auth_type == "cas":
                    raise ValueError(errors[-1])

        if auth_type in ("auto", "local"):
            try:
                return self._login_via_moodle_local_form(username, password)
            except Exception as loc_err:
                errors.append(f"Acceso local Moodle: {loc_err}")

        if auth_type == "cas" and not is_junta:
            try:
                return self._login_via_junta_cas(username, password)
            except Exception as e:
                errors.append(str(e))

        raise ValueError(" | ".join(errors) if errors else "No se pudo iniciar sesión en Moodle.")

    def _extract_page_metadata(self, html_text: str):
        m_cfg = re.search(r"M\.cfg\s*=\s*(\{.*?\});", html_text, flags=re.DOTALL)
        if m_cfg:
            try:
                cfg = json.loads(m_cfg.group(1))
                self.sesskey = cfg.get("sesskey") or self.sesskey
                uid = cfg.get("userId") if "userId" in cfg else cfg.get("userid")
                if uid and int(uid) > 0:
                    self.userid = int(uid)
            except Exception:
                pass

        if not self.userid:
            m_uid = re.search(r'data-userid=["\'](\d+)["\']', html_text)
            if not m_uid:
                m_uid = re.search(r'/user/profile\.php\?id=(\d+)', html_text)
            if m_uid and int(m_uid.group(1)) > 0:
                self.userid = int(m_uid.group(1))

        name_patterns = [
            r'<span class="usertext[^"]*">([^<]+)</span>',
            r'class="userbutton"[^>]*>.*?<span[^>]*>([^<]+)</span>',
            r'title="Ver perfil"[^>]*>([^<]+)</a>',
            r'<div class="user-info"[^>]*>.*?<span[^>]*>([^<]+)</span>',
        ]
        for pat in name_patterns:
            m_name = re.search(pat, html_text, flags=re.DOTALL | re.I)
            if m_name:
                candidate = clean_html_text(m_name.group(1))
                if candidate and len(candidate) > 1 and "área personal" not in candidate.lower() and "entrar" not in candidate.lower():
                    self.student_name = candidate
                    break

        m_title = re.search(r"<title>(.*?)</title>", html_text, flags=re.DOTALL | re.I)
        if m_title:
            raw_t = clean_html_text(m_title.group(1))
            if "|" in raw_t:
                self.site_name = raw_t.split("|")[-1].strip()
            elif ":" in raw_t:
                self.site_name = raw_t.split(":", 1)[0].strip()
            elif raw_t:
                self.site_name = raw_t

    def call_moodle_ajax(self, methodname: str, args: dict):
        if not self.sesskey:
            return None
        ajax_url = f"{self.base_url}/lib/ajax/service.php?sesskey={self.sesskey}&info={methodname}"
        payload = json.dumps([{"index": 0, "methodname": methodname, "args": args}]).encode("utf-8")
        _, resp_text = self._request(
            ajax_url,
            data=payload,
            extra_headers={"Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest"}
        )
        parsed = json.loads(resp_text)
        if isinstance(parsed, list) and len(parsed) > 0:
            item = parsed[0]
            if not item.get("error"):
                return item.get("data")
        return None

    def fetch_all_from_web_session(self, my_html: str = ""):
        if not my_html:
            _, my_html = self._request(f"{self.base_url}/my/")
            self._extract_page_metadata(my_html)

        courses = []
        tasks = []
        seen_task_ids = set()

        # 1. Obtener todos los cursos matriculados vía AJAX interno de Moodle
        for classification in ("all", "inprogress", "future", "past"):
            try:
                data = self.call_moodle_ajax(
                    "core_course_get_enrolled_courses_by_timeline_classification",
                    {"offset": 0, "limit": 0, "classification": classification, "sort": "fullname"}
                )
                if data and isinstance(data.get("courses"), list):
                    for c in data["courses"]:
                        cid = c.get("id")
                        if cid and not any(x["id"] == cid for x in courses):
                            fullname = clean_html_text(c.get("fullname") or c.get("shortname") or "Asignatura Moodle")
                            shortname = clean_html_text(c.get("shortname") or fullname[:12])
                            courses.append({
                                "id": cid,
                                "fullname": fullname,
                                "shortname": shortname,
                                "viewurl": c.get("viewurl") or f"{self.base_url}/course/view.php?id={cid}",
                                "color": pick_color_for_course(fullname),
                                "progress": c.get("progress")
                            })
            except Exception:
                continue

        # 2. Fallback HTML en /my/ y /my/courses.php por si el tema de Moodle Centros oculta algún curso
        for page_path in ("", "/my/courses.php"):
            try:
                html_to_scan = my_html if not page_path else self._request(f"{self.base_url}{page_path}")[1]
                for m in re.finditer(r'href=["\']([^"\']*?/course/view\.php\?id=(\d+))["\'][^>]*>(.*?)</a>', html_to_scan, flags=re.DOTALL | re.I):
                    c_url, cid_str, c_inner = m.groups()
                    cid = int(cid_str)
                    if cid == 1 or any(x["id"] == cid for x in courses):
                        continue
                    c_title = clean_html_text(c_inner)
                    if c_title and len(c_title) > 2 and "curso" not in c_title.lower()[:5]:
                        courses.append({
                            "id": cid,
                            "fullname": c_title,
                            "shortname": c_title[:12].upper(),
                            "viewurl": c_url if c_url.startswith("http") else f"{self.base_url}/course/view.php?id={cid}",
                            "color": pick_color_for_course(c_title),
                            "progress": None
                        })
            except Exception:
                pass

        course_map = {c["id"]: c["fullname"] for c in courses}

        # 3. Obtener entregas de la Línea de Tiempo (Timeline) vía AJAX
        now_ts = int(datetime.datetime.now().timestamp())
        start_ts = now_ts - (45 * 86400)
        try:
            ev_data = self.call_moodle_ajax(
                "core_calendar_get_action_events_by_timesort",
                {"limitnum": 50, "timesortfrom": start_ts}
            )
            if ev_data and isinstance(ev_data.get("events"), list):
                for ev in ev_data["events"]:
                    t_obj = self._convert_moodle_event_dict(ev, course_map)
                    if t_obj and t_obj["id"] not in seen_task_ids:
                        seen_task_ids.add(t_obj["id"])
                        tasks.append(t_obj)
        except Exception:
            pass

        # 4. Obtener próximos eventos del calendario vía AJAX
        try:
            up_data = self.call_moodle_ajax("core_calendar_get_calendar_upcoming_view", {"courseid": 1, "categoryid": 0})
            if up_data and isinstance(up_data.get("events"), list):
                for ev in up_data["events"]:
                    t_obj = self._convert_moodle_event_dict(ev, course_map)
                    if t_obj and t_obj["id"] not in seen_task_ids:
                        seen_task_ids.add(t_obj["id"])
                        tasks.append(t_obj)
        except Exception:
            pass

        # 5. Obtener vista mensual del calendario de Moodle (mes anterior, actual y siguientes 2 meses)
        today = datetime.date.today()
        for month_offset in (-1, 0, 1, 2):
            total_m = (today.year * 12 + (today.month - 1)) + month_offset
            y = total_m // 12
            m = (total_m % 12) + 1
            try:
                m_data = self.call_moodle_ajax(
                    "core_calendar_get_calendar_monthly_view",
                    {"year": y, "month": m, "courseid": 1, "categoryid": 0, "includenavigation": False}
                )
                if m_data and isinstance(m_data.get("weeks"), list):
                    for week in m_data["weeks"]:
                        for day_obj in week.get("days", []):
                            for ev in day_obj.get("events", []):
                                t_obj = self._convert_moodle_event_dict(ev, course_map)
                                if t_obj and t_obj["id"] not in seen_task_ids:
                                    seen_task_ids.add(t_obj["id"])
                                    tasks.append(t_obj)
            except Exception:
                pass

        # 6. Scraping directo de /calendar/view.php?view=upcoming
        try:
            _, cal_html = self._request(f"{self.base_url}/calendar/view.php?view=upcoming")
            html_tasks = self._parse_calendar_upcoming_html(cal_html)
            for ht in html_tasks:
                if ht["id"] not in seen_task_ids:
                    seen_task_ids.add(ht["id"])
                    tasks.append(ht)
        except Exception:
            pass

        # 7. Si aún hay pocos eventos, escanear actividades evaluables (tareas y cuestionarios) dentro de los cursos matriculados
        if courses and len(tasks) < 3:
            for c in courses[:8]:
                try:
                    _, c_html = self._request(c["viewurl"])
                    for m_act in re.finditer(
                        r'href=["\'](https?://[^"\']*?/mod/(assign|quiz)/view\.php\?id=(\d+))["\'][^>]*>(.*?)</a>',
                        c_html,
                        flags=re.DOTALL | re.I
                    ):
                        act_url, mod_type, cmid, raw_label = m_act.groups()
                        tid = f"moodle-{mod_type}-cm-{cmid}"
                        if tid in seen_task_ids:
                            continue
                        clean_label = clean_html_text(raw_label)
                        clean_label = re.sub(r"\s+(Tarea|Cuestionario)$", "", clean_label, flags=re.I).strip()
                        if not clean_label or len(clean_label) < 2:
                            continue
                        seen_task_ids.add(tid)
                        tasks.append({
                            "id": tid,
                            "title": clean_label,
                            "course": c["fullname"],
                            "courseCode": c["shortname"],
                            "dueDate": today.isoformat(),
                            "dueTime": "23:55",
                            "status": "pending",
                            "priority": "medium",
                            "description": f"{'Tarea' if mod_type == 'assign' else 'Cuestionario'} en el curso {c['fullname']}.",
                            "moodleUrl": html_lib.unescape(act_url),
                            "source": "moodle",
                            "color": c["color"]
                        })
                except Exception:
                    continue

        return {
            "courses": courses,
            "tasks": tasks
        }

    def _convert_moodle_event_dict(self, ev: dict, course_map: dict):
        ev_id = ev.get("id") or uuid.uuid4().hex[:8]
        title = clean_html_text(ev.get("name") or ev.get("activityname") or "Tarea de Moodle")
        course_info = ev.get("course") or {}
        course_name = clean_html_text(
            course_info.get("fullname")
            or course_info.get("shortname")
            or course_map.get(ev.get("courseid"), "")
            or "Moodle"
        )
        ts = ev.get("timesort") or ev.get("timestart") or 0
        if ts:
            dt = datetime.datetime.fromtimestamp(int(ts))
            due_date = dt.strftime("%Y-%m-%d")
            due_time = dt.strftime("%H:%M")
        else:
            due_date = datetime.date.today().isoformat()
            due_time = "23:55"

        action_obj = ev.get("action") or {}
        url = (
            action_obj.get("url")
            or ev.get("url")
            or ev.get("viewurl")
            or f"{self.base_url}/calendar/view.php?view=day&time={ts}"
        )
        desc = clean_html_text(ev.get("description") or ev.get("activitystr") or "")

        return {
            "id": f"moodle-ev-{ev_id}",
            "title": title,
            "course": course_name,
            "courseCode": course_name[:10].upper(),
            "dueDate": due_date,
            "dueTime": due_time,
            "status": "pending",
            "priority": "high",
            "description": desc or f"Evento oficial del calendario de Moodle ({course_name}).",
            "moodleUrl": url,
            "source": "moodle",
            "color": pick_color_for_course(course_name)
        }

    def _parse_calendar_upcoming_html(self, cal_html: str):
        results = []
        blocks = re.findall(
            r'<div[^>]+data-type=["\']event["\'][^>]*>(.*?)<!--\s*/event\s*-->|<div[^>]+class=["\'][^"\']*event[^"\']*["\'][^>]+data-event-id=["\'](\d+)["\'][^>]*>(.*?)</div>\s*</div>\s*</div>',
            cal_html,
            flags=re.DOTALL | re.I
        )
        for idx, match_tuple in enumerate(blocks):
            raw_block = " ".join(match_tuple)
            m_id = re.search(r'data-event-id=["\'](\d+)["\']', raw_block)
            ev_id = m_id.group(1) if m_id else f"html-{idx}"

            m_title = re.search(r'<h3[^>]+class=["\'][^"\']*name[^"\']*["\'][^>]*>(.*?)</h3>', raw_block, flags=re.DOTALL | re.I)
            title = clean_html_text(m_title.group(1)) if m_title else "Evento Moodle"

            m_course = re.search(r'/course/view\.php\?id=\d+["\'][^>]*>(.*?)</a>', raw_block, flags=re.DOTALL | re.I)
            course = clean_html_text(m_course.group(1)) if m_course else "Moodle"

            m_time = re.search(r'time=(\d+)', raw_block)
            if m_time:
                dt = datetime.datetime.fromtimestamp(int(m_time.group(1)))
                d_str, t_str = dt.strftime("%Y-%m-%d"), dt.strftime("%H:%M")
            else:
                d_str, t_str = datetime.date.today().isoformat(), "23:55"

            m_link = re.search(r'href=["\'](https?://[^"\']*/mod/[^"\']+)["\']', raw_block, flags=re.I)
            if not m_link:
                m_link = re.search(r'href=["\'](https?://[^"\']*/calendar/view\.php[^"\']+)["\']', raw_block, flags=re.I)
            url = html_lib.unescape(m_link.group(1)) if m_link else f"{self.base_url}/my/"

            results.append({
                "id": f"moodle-ev-{ev_id}",
                "title": title,
                "course": course,
                "courseCode": course[:10].upper(),
                "dueDate": d_str,
                "dueTime": t_str,
                "status": "pending",
                "priority": "high",
                "description": f"Evento extraído del calendario de Moodle ({course}).",
                "moodleUrl": url,
                "source": "moodle",
                "color": pick_color_for_course(course)
            })
        return results

    def fetch_all_from_ws_api(self, token: str):
        endpoint = f"{self.base_url}/webservice/rest/server.php"

        def call_ws(wsfunction, extra_params=None):
            params = {
                "wstoken": token,
                "wsfunction": wsfunction,
                "moodlewsrestformat": "json"
            }
            if extra_params:
                params.update(extra_params)
            url = f"{endpoint}?{urllib.parse.urlencode(params)}"
            _, raw = self._request(url)
            return json.loads(raw)

        site_info = call_ws("core_webservice_get_site_info")
        if isinstance(site_info, dict) and site_info.get("exception"):
            raise ValueError(site_info.get("message", "Token de Moodle inválido"))

        self.student_name = site_info.get("fullname") or self.student_name
        self.site_name = site_info.get("sitename") or self.site_name
        self.userid = site_info.get("userid") or self.userid
        self.user_picture = site_info.get("userpictureurl") or self.user_picture

        courses = []
        course_map = {}
        if self.userid:
            try:
                raw_courses = call_ws("core_enrol_get_users_courses", {"userid": self.userid})
                if isinstance(raw_courses, list):
                    for c in raw_courses:
                        cid = c.get("id")
                        cname = clean_html_text(c.get("fullname") or c.get("shortname") or "Curso Moodle")
                        cshort = clean_html_text(c.get("shortname") or cname[:10])
                        course_map[cid] = cname
                        courses.append({
                            "id": cid,
                            "fullname": cname,
                            "shortname": cshort,
                            "viewurl": f"{self.base_url}/course/view.php?id={cid}",
                            "color": pick_color_for_course(cname),
                            "progress": c.get("progress")
                        })
            except Exception:
                pass

        tasks = []
        seen_ids = set()

        try:
            assign_data = call_ws("mod_assign_get_assignments")
            for course in assign_data.get("courses", []):
                cid = course.get("id")
                c_name = clean_html_text(course.get("fullname") or course_map.get(cid) or "Moodle")
                c_short = clean_html_text(course.get("shortname") or c_name[:10])
                for a in course.get("assignments", []):
                    duedate_ts = a.get("duedate") or a.get("cutoffdate") or 0
                    if duedate_ts:
                        dt = datetime.datetime.fromtimestamp(int(duedate_ts))
                        d_str, t_str = dt.strftime("%Y-%m-%d"), dt.strftime("%H:%M")
                    else:
                        d_str, t_str = datetime.date.today().isoformat(), "23:55"
                    cmid = a.get("cmid")
                    direct_url = f"{self.base_url}/mod/assign/view.php?id={cmid}" if cmid else f"{self.base_url}/course/view.php?id={cid}"
                    tid = f"moodle-assign-{a.get('id')}"
                    seen_ids.add(tid)
                    tasks.append({
                        "id": tid,
                        "title": clean_html_text(a.get("name", "Tarea Moodle")),
                        "course": c_name,
                        "courseCode": c_short,
                        "dueDate": d_str,
                        "dueTime": t_str,
                        "status": "pending",
                        "priority": "high",
                        "description": clean_html_text(a.get("intro", "")) or f"Entrega de {c_name}",
                        "moodleUrl": direct_url,
                        "source": "moodle",
                        "color": pick_color_for_course(c_name)
                    })
        except Exception:
            pass

        try:
            now_ts = int(datetime.datetime.now().timestamp()) - (30 * 86400)
            ev_resp = call_ws("core_calendar_get_action_events_by_timesort", {"timesortfrom": now_ts, "limitnum": 50})
            for ev in ev_resp.get("events", []):
                t_obj = self._convert_moodle_event_dict(ev, course_map)
                if t_obj and t_obj["id"] not in seen_ids:
                    seen_ids.add(t_obj["id"])
                    tasks.append(t_obj)
        except Exception:
            pass

        grades_list = []
        if self.userid and courses:
            for c in courses[:12]:
                cid = c["id"]
                items = []
                try:
                    g_resp = call_ws("gradereport_user_get_grade_items", {"courseid": cid, "userid": self.userid})
                    usergrades = g_resp.get("usergrades", [])
                    if usergrades:
                        for gi in usergrades[0].get("gradeitems", []):
                            if gi.get("itemtype") == "course":
                                continue
                            iname = clean_html_text(gi.get("itemname") or "Actividad evaluable")
                            weight = gi.get("weightraw")
                            weight_val = round(float(weight) * 100, 1) if weight is not None else 20
                            grademax = float(gi.get("grademax") or 10.0)
                            graderaw = gi.get("graderaw")
                            score_10 = None
                            if graderaw is not None and grademax > 0:
                                score_10 = round((float(graderaw) / grademax) * 10.0, 2)
                            items.append({
                                "name": iname,
                                "weight": weight_val,
                                "score": score_10
                            })
                except Exception:
                    pass

                if not items:
                    items = [
                        {"name": "Actividades / Tareas Moodle", "weight": 40, "score": None},
                        {"name": "Examen / Prueba Final", "weight": 60, "score": None}
                    ]

                grades_list.append({
                    "id": f"grd-course-{cid}",
                    "subject": c["fullname"],
                    "color": c["color"],
                    "targetGrade": 7.0,
                    "items": items
                })

        return {
            "courses": courses,
            "tasks": tasks,
            "grades": grades_list
        }


# ---------------------------------------------------------------------------
# LANZADOR DE NAVEGADOR GOOGLE CHROME Y MINI POP-UP FLOTANTE
# ---------------------------------------------------------------------------
def find_chrome_executable():
    candidates = [
        shutil.which("chrome"),
        shutil.which("google-chrome"),
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
    ]
    for c in candidates:
        if c and os.path.exists(c):
            return c
    return None


def find_app_browser_executable():
    chrome = find_chrome_executable()
    if chrome:
        return chrome
    edge_candidates = [
        shutil.which("msedge"),
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    ]
    for e in edge_candidates:
        if e and os.path.exists(e):
            return e
    return None


def open_url_in_google(target_url: str, search_query: str = "", mode: str = "direct"):
    final_url = (target_url or "").strip()
    if mode == "google_search" or not final_url.startswith(("http://", "https://")):
        q = search_query or final_url or "Moodle"
        final_url = f"https://www.google.com/search?q={urllib.parse.quote_plus(q)}"

    chrome_exe = find_chrome_executable()
    if chrome_exe:
        try:
            subprocess.Popen([chrome_exe, final_url], close_fds=True)
            return {"ok": True, "browser": "Google Chrome", "url": final_url}
        except Exception:
            pass

    webbrowser.open(final_url)
    return {"ok": True, "browser": "Navegador predeterminado", "url": final_url}


# ---------------------------------------------------------------------------
# SERVIDOR HTTP LOCAL PARA LA APLICACIÓN DE ESCRITORIO
# ---------------------------------------------------------------------------
class AssistantRequestHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(STATIC_DIR), **kwargs)

    def log_message(self, format, *args):
        pass

    def _send_json(self, payload, status=200):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _read_json_body(self):
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0:
            return {}
        raw = self.rfile.read(length).decode("utf-8", errors="replace")
        return json.loads(raw)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/api/state":
            data = load_data()
            self._send_json({"ok": True, "data": data})
            return
        if parsed.path == "/api/ping":
            self._send_json({"ok": True, "service": "MoodleDesktopAssistant"})
            return
        return super().do_GET()

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)

        if parsed.path == "/api/state":
            try:
                body = self._read_json_body()
                new_data = body.get("data")
                if not isinstance(new_data, dict):
                    self._send_json({"ok": False, "error": "Formato de datos inválido"}, status=400)
                    return
                save_data(new_data)
                self._send_json({"ok": True, "data": new_data})
            except Exception as e:
                self._send_json({"ok": False, "error": str(e)}, status=500)
            return

        if parsed.path == "/api/clear-all":
            data = get_default_data()
            if COOKIES_JSON_FILE.exists():
                try:
                    COOKIES_JSON_FILE.unlink()
                except Exception:
                    pass
            save_data(data)
            self._send_json({"ok": True, "data": data})
            return

        if parsed.path == "/api/open-google":
            try:
                body = self._read_json_body()
                url = body.get("url", "")
                query = body.get("query", "")
                mode = body.get("mode", "direct")
                res = open_url_in_google(url, query, mode)
                self._send_json(res)
            except Exception as e:
                self._send_json({"ok": False, "error": str(e)}, status=500)
            return

        if parsed.path in ("/api/login-moodle", "/api/sync-moodle"):
            try:
                body = self._read_json_body()
                data = load_data()
                profile = data.get("profile", {})

                entry_url = (body.get("moodleEntryUrl") or body.get("moodleBaseUrl") or profile.get("moodleEntryUrl") or DEFAULT_MOODLE_ENTRY_URL).strip()
                base_url = normalize_moodle_base_url(entry_url)
                profile["moodleEntryUrl"] = entry_url
                profile["moodleBaseUrl"] = base_url

                for k in ("studentName", "username", "authType", "university", "degree", "moodleProfileUrl", "icsUrl", "apiToken", "sessionCookie", "openMode"):
                    if k in body and body[k] is not None:
                        profile[k] = str(body[k]).strip()

                username = (body.get("username") or profile.get("username") or "").strip()
                password = (body.get("password") or "").strip()
                auth_type = (body.get("authType") or profile.get("authType") or "auto").strip()
                api_token = profile.get("apiToken", "").strip()
                session_cookie = profile.get("sessionCookie", "").strip()
                ics_url = profile.get("icsUrl", "").strip()
                ics_raw_content = (body.get("icsContent") or "").strip()

                connector = MoodleSessionConnector(entry_url)
                imported_tasks = []
                imported_courses = []
                imported_grades = []
                sync_messages = []

                # 1. Inicio de sesión con Usuario IdEA / Moodle y Contraseña
                if username and password:
                    token = connector.try_obtain_mobile_token(username, password)
                    if token:
                        profile["apiToken"] = token
                        api_token = token

                    try:
                        my_html = connector.login_web_session(username, password, auth_type=auth_type)
                        web_res = connector.fetch_all_from_web_session(my_html if isinstance(my_html, str) else "")
                        imported_courses.extend(web_res.get("courses", []))
                        imported_tasks.extend(web_res.get("tasks", []))

                        # Si el estudiante entró en /centros/sevilla (26-27) pero sus cursos están en /centros/sevilla25 (25-26),
                        # aprovechamos el ticket SSO CAS ya activo para comprobar automáticamente sevilla25 también:
                        if not imported_courses and "/centros/sevilla" in base_url and "/centros/sevilla25" not in base_url:
                            try:
                                alt_base = base_url.replace("/centros/sevilla", "/centros/sevilla25")
                                connector.base_url = alt_base
                                _, alt_html = connector._request(f"{alt_base}/login/index.php?authCAS=CAS")
                                connector._extract_page_metadata(alt_html)
                                if connector.sesskey and connector.userid:
                                    alt_res = connector.fetch_all_from_web_session(alt_html)
                                    if alt_res.get("courses") or alt_res.get("tasks"):
                                        imported_courses.extend(alt_res.get("courses", []))
                                        imported_tasks.extend(alt_res.get("tasks", []))
                                        base_url = alt_base
                                        profile["moodleBaseUrl"] = alt_base
                                        profile["moodleEntryUrl"] = f"{alt_base}/my/"
                            except Exception:
                                connector.base_url = base_url

                        sync_messages.append(
                            f"Conectado a Moodle ({len(imported_courses)} asignaturas, {len(imported_tasks)} tareas/eventos)"
                        )
                    except Exception as web_err:
                        if not api_token:
                            raise web_err

                # 2. Si hay cookie de sesión previa o manual
                elif session_cookie or COOKIES_JSON_FILE.exists():
                    if session_cookie:
                        connector.set_manual_session_cookie(session_cookie)
                    try:
                        web_res = connector.fetch_all_from_web_session()
                        if connector.sesskey and connector.userid:
                            imported_courses.extend(web_res.get("courses", []))
                            imported_tasks.extend(web_res.get("tasks", []))
                            sync_messages.append(
                                f"Sincronizado desde sesión activa ({len(imported_courses)} asignaturas, {len(imported_tasks)} tareas)"
                            )
                    except Exception:
                        pass

                # 3. Si hay Token WebService (wstoken)
                if api_token:
                    try:
                        ws_res = connector.fetch_all_from_ws_api(api_token)
                        for c in ws_res.get("courses", []):
                            if not any(x["id"] == c["id"] for x in imported_courses):
                                imported_courses.append(c)
                        imported_tasks.extend(ws_res.get("tasks", []))
                        imported_grades.extend(ws_res.get("grades", []))
                        sync_messages.append(
                            f"API de Moodle sincronizada ({len(ws_res.get('tasks', []))} entregas)"
                        )
                    except Exception as ws_err:
                        if not sync_messages:
                            raise ws_err

                # 4. Si hay URL de calendario .ics
                if ics_url and ics_url.startswith(("http://", "https://")):
                    _, remote_ics = connector._request(ics_url)
                    parsed_remote = parse_ics_content(remote_ics, base_url)
                    imported_tasks.extend(parsed_remote)
                    sync_messages.append(f"{len(parsed_remote)} tareas desde URL iCal (.ics)")

                # 5. Si subió un archivo .ics
                if ics_raw_content:
                    parsed_ics = parse_ics_content(ics_raw_content, base_url)
                    imported_tasks.extend(parsed_ics)
                    sync_messages.append(f"{len(parsed_ics)} tareas desde archivo .ics")

                if not sync_messages and not (ics_url or ics_raw_content or api_token or session_cookie or (username and password)):
                    raise ValueError("Introduce tu Usuario IdEA y Contraseña (o pega tu URL de calendario .ics) para conectar con Moodle.")

                if connector.student_name:
                    profile["studentName"] = connector.student_name
                elif not profile.get("studentName") and username:
                    profile["studentName"] = username

                if connector.site_name:
                    profile["university"] = connector.site_name
                if connector.userid:
                    profile["userid"] = connector.userid
                    profile["moodleProfileUrl"] = f"{base_url}/user/profile.php?id={connector.userid}"
                elif not profile.get("moodleProfileUrl"):
                    profile["moodleProfileUrl"] = f"{base_url}/user/profile.php"

                if connector.user_picture:
                    profile["userPictureUrl"] = connector.user_picture

                name_for_initials = profile.get("studentName") or username or "MD"
                name_parts = [p[0].upper() for p in name_for_initials.split() if p]
                profile["avatarInitials"] = "".join(name_parts[:2]) or "MD"
                profile["linked"] = True
                profile["lastSync"] = datetime.datetime.now().strftime("%d/%m/%Y %H:%M")

                if imported_courses:
                    data["courses"] = imported_courses
                    if not data.get("grades") and not imported_grades:
                        for c in imported_courses:
                            imported_grades.append({
                                "id": f"grd-course-{c['id']}",
                                "subject": c["fullname"],
                                "color": c["color"],
                                "targetGrade": 7.0,
                                "items": [
                                    {"name": "Tareas y Prácticas Moodle", "weight": 40, "score": None},
                                    {"name": "Examen / Prueba Final", "weight": 60, "score": None}
                                ]
                            })

                if imported_grades:
                    existing_grades_by_id = {g["id"]: g for g in data.get("grades", [])}
                    for ng in imported_grades:
                        if ng["id"] not in existing_grades_by_id:
                            existing_grades_by_id[ng["id"]] = ng
                    data["grades"] = list(existing_grades_by_id.values())

                if imported_tasks:
                    existing_by_id = {t["id"]: t for t in data.get("moodleTasks", [])}
                    for nt in imported_tasks:
                        if nt["id"] in existing_by_id:
                            nt["status"] = existing_by_id[nt["id"]].get("status", "pending")
                        existing_by_id[nt["id"]] = nt
                    data["moodleTasks"] = list(existing_by_id.values())

                data["profile"] = profile
                save_data(data)

                msg = " | ".join(sync_messages) if sync_messages else "Perfil de Moodle sincronizado."
                self._send_json({"ok": True, "message": msg, "data": data})
            except Exception as e:
                self._send_json({"ok": False, "error": str(e)}, status=400)
            return

        if parsed.path == "/api/launch-popup":
            try:
                popup_script = BASE_DIR / "popup_widget.py"
                if popup_script.exists():
                    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
                    subprocess.Popen(
                        [sys.executable, str(popup_script), "--port", str(self.server.server_port)],
                        cwd=str(BASE_DIR),
                        creationflags=creationflags
                    )
                    self._send_json({"ok": True, "message": "Mini Pop-up Flotante iniciado en el escritorio."})
                else:
                    self._send_json({"ok": False, "error": "No se encontró popup_widget.py"}, status=404)
            except Exception as e:
                self._send_json({"ok": False, "error": str(e)}, status=500)
            return

        self._send_json({"ok": False, "error": "Ruta no encontrada"}, status=404)


def find_free_port(preferred=8765):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        if s.connect_ex(("127.0.0.1", preferred)) != 0:
            return preferred
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def start_server(port: int):
    server = http.server.ThreadingHTTPServer(("127.0.0.1", port), AssistantRequestHandler)
    return server


def launch_desktop_window(url: str):
    browser_exe = find_app_browser_executable()
    if browser_exe:
        user_data_dir = DATA_DIR / "desktop_window_profile"
        user_data_dir.mkdir(parents=True, exist_ok=True)
        args = [
            browser_exe,
            f"--app={url}",
            f"--user-data-dir={user_data_dir}",
            "--window-size=1380,870",
            "--disable-extensions",
            "--no-first-run",
            "--no-default-browser-check",
        ]
        try:
            return subprocess.Popen(args, close_fds=True)
        except Exception:
            pass
    webbrowser.open(url)
    return None


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Asistente de Escritorio Moodle (Tema Oscuro)")
    parser.add_argument("--no-browser", action="store_true", help="Inicia solo el servidor local sin abrir ventana")
    parser.add_argument("--popup-only", action="store_true", help="Inicia el servidor y el widget pop-up flotante")
    parser.add_argument("--port", type=int, default=0, help="Puerto local opcional")
    args = parser.parse_args()

    data = load_data()
    save_data(data)

    port = args.port or find_free_port(8765)
    server = start_server(port)
    url = f"http://127.0.0.1:{port}"

    print("=" * 64)
    print("  ASISTENTE DE ESCRITORIO MOODLE (CAS EDEA SEVILLA + DARK UI)")
    print(f"  Servidor activo en: {url}")
    print("=" * 64)

    if args.popup_only:
        popup_script = BASE_DIR / "popup_widget.py"
        subprocess.Popen([sys.executable, str(popup_script), "--port", str(port)], cwd=str(BASE_DIR))
    elif not args.no_browser:
        launch_desktop_window(url)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nCerrando Asistente de Moodle...")
        server.server_close()


if __name__ == "__main__":
    main()
