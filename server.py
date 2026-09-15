#!/usr/bin/env python3
"""Diagram-Studio: Web-UI zum Erstellen von diagram-design Diagrammen.
Stdlib-only. Settings (OmniRoute/OpenRouter) via /api/settings.
"""
import html as _html
import json
import os
import re
import time
import urllib.request
import urllib.error
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, unquote, parse_qs

BASE = os.path.dirname(os.path.abspath(__file__))
SETTINGS_FILE = os.path.join(BASE, "settings.json")
GEN_DIR = os.path.join(BASE, "generated")
os.makedirs(GEN_DIR, exist_ok=True)

MAX_BODY = 1_000_000  # 1 MB Limit für POST-Bodys (DoS-Schutz)
MAX_HTML = 5_000_000  # 5 MB Limit für generiertes HTML

DEFAULTS = {
    "provider": "omniroute",
    "base_url": "http://192.168.178.127:20128/v1",
    "api_key": "",
    "model": "auto/best-free",
    "keys": {},
}
PROVIDER_URLS = {
    "omniroute": "http://192.168.178.127:20128/v1",
    "openrouter": "https://openrouter.ai/api/v1",
}

TYPES = [
    ("architecture", "Architektur (Komponenten + Verbindungen)"),
    ("flowchart", "Flowchart (Entscheidungslogik)"),
    ("sequence", "Sequenz (Nachrichten über Zeit)"),
    ("state", "State Machine (Zustände + Übergänge)"),
    ("er", "ER / Datenmodell"),
    ("timeline", "Timeline"),
    ("swimlane", "Swimlane"),
    ("quadrant", "Quadrant (2-Achsen-Positionierung)"),
    ("radar", "Radar / Spider"),
    ("polar", "Polar-Chart"),
    ("loop", "Loop / Flywheel"),
    ("nested", "Nested (Hierarchie durch Enthaltensein)"),
    ("tree", "Tree (Eltern → Kinder)"),
    ("org-chart", "Org-Chart"),
    ("layers", "Layer-Stack"),
    ("venn", "Venn"),
    ("pyramid", "Pyramide / Funnel"),
    ("bar", "Balkendiagramm"),
    ("waterfall", "Waterfall"),
    ("treemap", "Treemap"),
    ("line", "Linien-Chart"),
    ("gantt", "Gantt"),
    ("scatter", "Scatter / Bubble / Beeswarm"),
    ("high-level", "High-Level (End-to-End-Stack)"),
    ("process", "Process (Multi-Akteur-Workflow)"),
    ("medallion", "Medallion (Data-Tiers)"),
    ("data-flow", "Data Flow (rollenbasiert)"),
    ("dp-integration", "DP-Integration (Quellen → Kern → Verbraucher)"),
    ("dp-security-matrix", "DP-Security-Matrix"),
    ("sankey", "Sankey"),
    ("fishbone", "Fishbone (Ursache → Wirkung)"),
    ("wardley", "Wardley-Map"),
    ("kanban", "Kanban"),
    ("journey", "User Journey"),
    ("deployment", "Deployment (Zonen, Hosts, Artefakte)"),
    ("dependency", "Dependency-Graph"),
    ("uml-class", "UML-Klasse"),
    ("story-map", "Story-Map"),
    ("db-schema", "Datenbank-Schema"),
    ("it-state", "IT-Current-State"),
]

CORE_RULES = """Du erzeugst EIN eigenständiges Diagramm als komplettes HTML-Dokument mit inline-SVG und eingebettetem CSS.
Pflicht-Regeln (editorial design system):
- Farben: paper #f5f5f5, ink #2d3142, muted #4f5d75, soft #7a8399, accent #eb6c36 (NUR 1-2 fokale Elemente!), link #2e5aa8.
- Fonts: Titel Instrument Serif; Node-Namen Geist sans 12px/600; technische Sublabels Geist Mono 9px; Eyebrow/Tags Geist Mono 7-8px uppercase.
- Google-Fonts-Link einbetten: Instrument Serif + Geist + Geist Mono.
- KEINE Schatten, KEIN rounded-2xl (max rx 6-10), KEIN Dark-Mode-Glow.
- Verbinder: orthogonale Pfade mit abgerundeten Ecken (r=8), NIEMALS diagonale Linien. Pfeil-Labels (<=14 Zeichen, CAPS) mit deckendem Masken-Rechteck und 6-10px Abstand zur Linie.
- Max 9 Knoten, max 12 Pfeile. Überzählige Inhalte in die Summary-Cards auslagern.
- SVG braucht role="img", aria-labelledby, sowie <title> als erstes Kind und <desc> mit IDs <slug>-title / <slug>-desc.
- Legende als horizontaler Streifen UNTEN, nicht schwebend im Diagramm.
- Alle Koordinaten/Größen durch 4 teilbar.
- Ausgabe: NUR das HTML, keine Markdown-Fences, keine Erklärungen.
Vom Nutzer gewählter Diagrammtyp und Stil-Referenz folgen unten. Baue darauf das Diagramm zum Nutzer-Wunsch."""


def is_http_url(u):
    """Nur http(s)-URLs erlauben (SSRF-Schutz für LLM-Proxy)."""
    try:
        p = urlparse((u or "").strip())
        return p.scheme in ("http", "https") and bool(p.hostname)
    except Exception:
        return False


def load_settings():
    s = dict(DEFAULTS)
    s["keys"] = dict(DEFAULTS.get("keys") or {})
    try:
        with open(SETTINGS_FILE, encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                s.update(data)
                if not isinstance(s.get("keys"), dict):
                    s["keys"] = {}
    except (OSError, ValueError):
        pass
    return s


def save_settings(s):
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(s, f, indent=2)


def slugify(t):
    t = re.sub(r"[^a-zA-Z0-9]+", "-", t.lower()).strip("-")
    return (t or "diagramm")[:40]


def gen_path(name):
    """Pfad zu einer generierten Datei oder None bei ungültigem Namen."""
    name = unquote(name)
    if not name or "/" in name or "\\" in name or ".." in name \
            or not name.endswith(".html") or name in (".html",) \
            or name.startswith(".") or "\x00" in name:
        return None
    return os.path.join(GEN_DIR, name)


def fetch_models(base_url, api_key):
    """Modelliste von einem OpenAI-kompatiblen /models-Endpunkt holen."""
    if not is_http_url(base_url):
        raise RuntimeError("Ungültige API-Basis-URL (nur http/https erlaubt).")
    req = urllib.request.Request(base_url.rstrip("/") + "/models")
    if api_key:
        req.add_header("Authorization", "Bearer " + api_key)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Modelle-HTTP {e.code}: {e.read().decode()[:300]}")
    except Exception as e:
        raise RuntimeError(f"Modelliste nicht erreichbar: {e}")
    items = data.get("data") if isinstance(data, dict) else None
    if not isinstance(items, list):
        raise RuntimeError("Unerwartetes /models-Format.")
    out = []
    for m in items:
        mid = m.get("id") if isinstance(m, dict) else None
        if mid:
            out.append(mid)
    return sorted(set(out))


def type_reference(dtype):
    for cand in (f"type-{dtype}.md",):
        p = os.path.join(BASE, "skill", "references", cand)
        if os.path.exists(p):
            with open(p, encoding="utf-8") as f:
                return f.read()
    return ""


def post_chat(settings, payload):
    """POST an einen OpenAI-kompatiblen /chat/completions-Endpunkt."""
    base = (settings.get("base_url") or "").strip()
    if not is_http_url(base):
        raise RuntimeError("Ungültige API-Basis-URL (nur http/https erlaubt).")
    body = json.dumps(payload).encode()
    req = urllib.request.Request(
        base.rstrip("/") + "/chat/completions", data=body,
        headers={"Content-Type": "application/json",
                 "HTTP-Referer": "https://github.com/HatchetMan111/DiagrammDesign",
                 "X-Title": "Diagram-Studio"})
    if settings.get("api_key"):
        req.add_header("Authorization", "Bearer " + settings["api_key"])
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        raw = e.read().decode()[:1000]
        msg = raw
        try:
            ej = json.loads(raw)
            em = ej.get("error") if isinstance(ej, dict) else None
            if isinstance(em, dict) and em.get("message"):
                msg = em["message"]
            elif isinstance(em, str):
                msg = em
        except ValueError:
            pass
        raise RuntimeError(f"LLM-HTTP {e.code}: {msg}")
    except Exception as e:
        raise RuntimeError(f"LLM-Verbindung fehlgeschlagen: {e}")


def check_data(data):
    if isinstance(data, dict) and data.get("error"):
        em = data["error"]
        msg = em.get("message") if isinstance(em, dict) else em
        raise RuntimeError(f"LLM-Fehler: {msg}")
    return data


def _message_text(msg):
    """Text aus einer OpenAI-kompatiblen Message holen.
    content kann str, Liste von Content-Parts oder None sein
    (Reasoning-Modelle via OpenRouter liefern oft content=null + reasoning)."""
    if not isinstance(msg, dict):
        return ""
    c = msg.get("content")
    if isinstance(c, str) and c.strip():
        return c.strip()
    if isinstance(c, list):
        parts = []
        for p in c:
            if isinstance(p, dict):
                t = p.get("text")
                if isinstance(t, str) and t.strip():
                    parts.append(t)
        if parts:
            return "".join(parts).strip()
    return ""


def _empty_reply_error(choice, msg, data):
    """Hilfreiche Fehlermeldung, wenn die LLM-Antwort keinen Text enthält."""
    fr = choice.get("finish_reason") if isinstance(choice, dict) else None
    if isinstance(msg, dict) and msg.get("refusal"):
        return f"Modell verweigert die Antwort: {str(msg['refusal'])[:200]}"
    if isinstance(msg, dict) and (msg.get("reasoning") or msg.get("reasoning_details")):
        return ("Modell liefert nur internes Reasoning, keinen Antwort-Text "
                f"(finish: {fr}). Tipp: Non-Reasoning-Modell wählen "
                "(z. B. ohne 'thinking'/'reasoning' im Namen).")
    if fr == "length":
        return ("Antwort abgeschnitten (Token-Limit erreicht, kein Text). "
                "Tipp: anderes Modell wählen oder Prompt kürzen.")
    return "Unerwartete LLM-Antwort (leerer Content): " + json.dumps(data)[:500]


def llm_test(settings):
    data = check_data(post_chat(settings, {
        "model": settings.get("model") or "auto/best-free",
        "messages": [{"role": "user", "content": "Antworte mit genau einem Wort: OK"}],
        # Absichtlich großzügig: Reasoning-Modelle verbrauchen Tokens für
        # internes Denken — mit max_tokens=10 käme nur content=null zurück.
        "max_tokens": 500,
        "temperature": 0,
    }))
    try:
        choice = data["choices"][0]
        msg = choice.get("message", {})
    except (KeyError, IndexError, TypeError):
        raise RuntimeError("Unerwartete LLM-Antwort: " + json.dumps(data)[:500])
    text = _message_text(msg)
    if text:
        return text[:200]
    raise RuntimeError(_empty_reply_error(choice, msg, data))


def llm_generate(settings, dtype, variant, prompt):
    ref = type_reference(dtype)
    system = CORE_RULES + "\n\n--- TYP-REFERENZ (" + dtype + ") ---\n" + ref
    try:
        if variant == "full":
            with open(os.path.join(BASE, "skill", "template-full.html"), encoding="utf-8") as f:
                tpl = f.read()
            system += "\n\n--- TEMPLATE (Full-Editorial, als Gerüst nutzen, IDs/Slug ersetzen) ---\n" + tpl[:12000]
        else:
            with open(os.path.join(BASE, "skill", "template.html"), encoding="utf-8") as f:
                tpl = f.read()
            system += "\n\n--- TEMPLATE (minimal, als Gerüst nutzen, IDs/Slug ersetzen) ---\n" + tpl[:6000]
    except OSError as e:
        raise RuntimeError(f"Template fehlt: {e.filename or e}")
    user = f"Diagrammtyp: {dtype}\nWunsch:\n{prompt}"
    data = check_data(post_chat(settings, {
        "model": settings.get("model") or "auto/best-free",
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0.4,
    }))
    try:
        choice = data["choices"][0]
        msg = choice.get("message", {})
    except (KeyError, IndexError, TypeError):
        raise RuntimeError("Unerwartete LLM-Antwort: " + json.dumps(data)[:500])
    content = _message_text(msg)
    if not content:
        raise RuntimeError(_empty_reply_error(choice, msg, data))
    if isinstance(choice, dict) and choice.get("finish_reason") == "length":
        raise RuntimeError("LLM-Antwort abgeschnitten (Token-Limit). "
                           "Tipp: kürzeren Prompt, Variante 'Minimal' oder anderes Modell versuchen.")
    m = re.search(r"```html\s*(.*?)```", content, re.S)
    html = (m.group(1) if m else content).strip()
    if len(html) > MAX_HTML:
        raise RuntimeError("LLM-Antwort zu groß (>5 MB), verworfen.")
    if "<svg" not in html.lower() or "<html" not in html.lower():
        raise RuntimeError("LLM hat kein gültiges HTML+SVG geliefert.")
    return html


def draft_generate(prompt, dtype):
    try:
        with open(os.path.join(BASE, "skill", "template.html"), encoding="utf-8") as f:
            tpl = f.read()
    except OSError as e:
        raise RuntimeError(f"Template fehlt: {e.filename or e}")
    raw_title = (prompt.strip().split("\n")[0] or "Mein Diagramm")[:80]
    title = _html.escape(raw_title)
    slug = slugify(raw_title)
    dtype_safe = _html.escape(dtype)
    nodes = [
        (140, 240, "Start", "Input"),
        (420, 240, "Kern", "Logik"),
        (700, 240, "Ergebnis", "Output"),
    ]
    boxes = ""
    for x, y, name, sub in nodes:
        cx = x + 80
        boxes += f"""
        <rect x="{x}" y="{y}" width="160" height="64" rx="6" fill="#f5f5f5"/>
        <rect x="{x}" y="{y}" width="160" height="64" rx="6" fill="#ffffff" stroke="#2d3142" stroke-width="1"/>
        <text x="{cx}" y="{y + 36}" fill="#2d3142" font-size="12" font-weight="600" font-family="'Geist', sans-serif" text-anchor="middle">{name}</text>
        <text x="{cx}" y="{y + 52}" fill="#4f5d75" font-size="9" font-family="'Geist Mono', monospace" text-anchor="middle">{sub}</text>"""
    arrows = """
        <line x1="300" y1="272" x2="412" y2="272" stroke="#4f5d75" stroke-width="1.2" marker-end="url(#arrow)"/>
        <line x1="580" y1="272" x2="692" y2="272" stroke="#4f5d75" stroke-width="1.2" marker-end="url(#arrow)"/>"""
    body = arrows + boxes + f"""
        <line x1="40" y1="380" x2="960" y2="380" stroke="rgba(45,49,66,0.10)" stroke-width="0.8"/>
        <text x="40" y="396" fill="#4f5d75" font-size="8" font-family="'Geist Mono', monospace" letter-spacing="0.18em">LEGEND</text>
        <rect x="40" y="404" width="14" height="10" rx="2" fill="#ffffff" stroke="#2d3142" stroke-width="1"/>
        <text x="60" y="412" fill="#4f5d75" font-size="8" font-family="'Geist', sans-serif">Entwurf — per KI verfeinern</text>"""
    html = tpl.replace("[Diagram title]", title).replace("[Type]", dtype_safe)
    html = html.replace("[diagram-slug]", slug)
    html = html.replace("[One sentence describing what the diagram shows]",
                        f"Schnell-Entwurf zum Thema {title} als {dtype_safe}-Diagramm.")
    html = html.replace("<title>Diagram</title>", f"<title>{title}</title>")
    html = html.replace("<!-- Draw arrows first, then nodes. Replace with your content. -->", body)
    return html, slug


class Handler(BaseHTTPRequestHandler):
    server_version = "DiagramStudio/1.0"

    def _sec_headers(self):
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")

    def _json(self, obj, code=200):
        b = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self._sec_headers()
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(b)

    def _send_file(self, path, ctype, download_name=None, sandbox=False):
        try:
            with open(path, "rb") as f:
                b = f.read()
        except OSError:
            self.send_error(404)
            return
        # Sichere Download-Dateinamen (keine Quotes/Newlines → Header-Injection)
        if download_name:
            download_name = re.sub(r'[^A-Za-z0-9._-]', '_', download_name)[:120]
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self._sec_headers()
        if sandbox:
            # Generierte LLM-Diagramme isolieren: kein Zugriff auf /api/* (Key-Klau via iframe-JS)
            self.send_header("Content-Security-Policy", "sandbox allow-scripts")
        if download_name:
            self.send_header("Content-Disposition", f'attachment; filename="{download_name}"')
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(b)

    def _read_json(self):
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = 0
        if length > MAX_BODY:
            return None, "Body zu groß (Limit 1 MB)."
        if length < 0:
            return None, "Ungültige Content-Length."
        try:
            raw = self.rfile.read(length).decode() if length else "{}"
            return json.loads(raw or "{}"), None
        except ValueError:
            return None, "Ungültiges JSON"

    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        u = urlparse(self.path)
        if u.path in ("/", "/index.html"):
            self._send_file(os.path.join(BASE, "index.html"), "text/html; charset=utf-8")
        elif u.path == "/favicon.svg":
            self._send_file(os.path.join(BASE, "favicon.svg"), "image/svg+xml")
        elif u.path == "/api/settings":
            self._json(load_settings())
        elif u.path == "/api/types":
            self._json([{"id": t, "label": l} for t, l in TYPES])
        elif u.path == "/api/models":
            q = parse_qs(u.query, keep_blank_values=True)
            s = load_settings()
            base = (q.get("base_url", [s.get("base_url", "")])[0] or "").strip()
            key = q.get("api_key", [s.get("api_key", "")])[0] or ""
            if not base:
                self._json({"ok": False, "error": "Keine API-Basis-URL gesetzt."}, 400)
                return
            if not is_http_url(base):
                self._json({"ok": False, "error": "Ungültige Basis-URL (nur http/https)."}, 400)
                return
            try:
                self._json({"ok": True, "models": fetch_models(base, key)})
            except RuntimeError as e:
                self._json({"ok": False, "error": str(e)}, 502)
        elif u.path == "/api/diagrams":
            rows = []
            try:
                names = sorted(os.listdir(GEN_DIR), reverse=True)
            except OSError:
                names = []
            for n in names:
                if not n.endswith(".html"):
                    continue
                p = os.path.join(GEN_DIR, n)
                try:
                    st = os.stat(p)
                except OSError:
                    continue
                tail = n.rsplit("-", 1)[-1]
                if tail.endswith(".html"):
                    tail = tail[:-5]
                dtype = tail if any(t == tail for t, _ in TYPES) else ""
                rows.append({"file": n, "dtype": dtype,
                             "size": st.st_size, "mtime": int(st.st_mtime),
                             "created": time.strftime("%d.%m.%Y %H:%M", time.localtime(st.st_mtime))})
            self._json({"ok": True, "diagrams": rows})
        elif u.path.startswith("/generated/"):
            path = gen_path(u.path[len("/generated/"):])
            if not path:
                self.send_error(400)
                return
            dl = "download" in parse_qs(u.query, keep_blank_values=True)
            name = os.path.basename(path)
            self._send_file(path, "text/html; charset=utf-8",
                            download_name=name if dl else None, sandbox=True)
        else:
            self.send_error(404)

    def do_DELETE(self):
        u = urlparse(self.path)
        if u.path.startswith("/api/diagrams/"):
            path = gen_path(u.path[len("/api/diagrams/"):])
            if not path:
                self._json({"ok": False, "error": "Ungültiger Dateiname."}, 400)
                return
            try:
                os.remove(path)
                self._json({"ok": True})
            except FileNotFoundError:
                self._json({"ok": False, "error": "Datei nicht gefunden."}, 404)
            except OSError as e:
                self._json({"ok": False, "error": str(e)}, 500)
        else:
            self.send_error(404)

    def do_POST(self):
        u = urlparse(self.path)
        payload, err = self._read_json()
        if err:
            code = 413 if "zu groß" in err else 400
            self._json({"ok": False, "error": err}, code)
            return
        if u.path == "/api/models":
            # POST-Variante (empfohlen): Key nicht in URL/Logs, statt GET /api/models?api_key=...
            s = load_settings()
            base = str(payload.get("base_url", s.get("base_url", "")) or "").strip()
            key = payload.get("api_key", s.get("api_key", ""))
            if not isinstance(key, str):
                key = ""
            if not base:
                self._json({"ok": False, "error": "Keine API-Basis-URL gesetzt."}, 400)
                return
            if not is_http_url(base):
                self._json({"ok": False, "error": "Ungültige Basis-URL (nur http/https)."}, 400)
                return
            try:
                self._json({"ok": True, "models": fetch_models(base, key)})
            except RuntimeError as e:
                self._json({"ok": False, "error": str(e)}, 502)
            return
        if u.path == "/api/settings":
            s = load_settings()
            for k in ("provider", "base_url", "api_key", "model"):
                if k in payload and isinstance(payload[k], str):
                    s[k] = payload[k].strip() if k != "api_key" else payload[k]
            if "keys" in payload and isinstance(payload["keys"], dict):
                if not isinstance(s.get("keys"), dict):
                    s["keys"] = {}
                for pk, pv in payload["keys"].items():
                    if isinstance(pv, str):
                        s["keys"][pk] = pv
            if s["provider"] in PROVIDER_URLS and "base_url" not in payload:
                s["base_url"] = PROVIDER_URLS[s["provider"]]
            if s.get("base_url") and not is_http_url(s["base_url"]):
                self._json({"ok": False, "error": "Ungültige Basis-URL (nur http/https)."}, 400)
                return
            if len(s.get("model", "")) > 200:
                self._json({"ok": False, "error": "Modell-ID zu lang."}, 400)
                return
            save_settings(s)
            self._json({"ok": True})
        elif u.path == "/api/test":
            s = load_settings()
            for k in ("provider", "base_url", "api_key", "model"):
                if k in payload and isinstance(payload[k], str):
                    s[k] = payload[k].strip() if k != "api_key" else payload[k]
            if not s.get("base_url"):
                self._json({"ok": False, "error": "Keine API-Basis-URL gesetzt."}, 400)
                return
            if not is_http_url(s.get("base_url")):
                self._json({"ok": False, "error": "Ungültige Basis-URL (nur http/https)."}, 400)
                return
            try:
                reply = llm_test(s)
                self._json({"ok": True, "model": s.get("model"), "reply": reply})
            except RuntimeError as e:
                self._json({"ok": False, "error": str(e)}, 502)
            except Exception:
                self._json({"ok": False, "error": "Unerwarteter Test-Fehler."}, 500)
        elif u.path == "/api/generate":
            prompt = str(payload.get("prompt") or "")[:4000].strip()
            dtype = str(payload.get("dtype") or "architecture").strip()
            variant = payload.get("variant") if payload.get("variant") in ("minimal", "full") else "minimal"
            mode = payload.get("mode") if payload.get("mode") in ("ai", "draft") else "ai"
            if not prompt and mode == "ai":
                self._json({"ok": False, "error": "Bitte eine Beschreibung eingeben."}, 400)
                return
            if not any(t == dtype for t, _ in TYPES):
                dtype = "architecture"
            try:
                if mode == "draft":
                    html, slug = draft_generate(prompt or "Mein Diagramm", dtype)
                else:
                    settings = load_settings()
                    if not settings.get("base_url"):
                        raise RuntimeError("Keine API-Basis-URL konfiguriert (Einstellungen).")
                    html = llm_generate(settings, dtype, variant, prompt)
                    slug = slugify(prompt[:60])
                fname = f"{time.strftime('%Y%m%d-%H%M%S')}-{slug}-{dtype}.html"
                with open(os.path.join(GEN_DIR, fname), "w", encoding="utf-8") as f:
                    f.write(html)
                self._json({"ok": True, "file": fname})
            except RuntimeError as e:
                self._json({"ok": False, "error": str(e)}, 502)
            except Exception:
                self._json({"ok": False, "error": "Unerwarteter Generierungs-Fehler."}, 500)
        else:
            self.send_error(404)

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    import sys
    try:
        port = int(sys.argv[1]) if len(sys.argv) > 1 else 8123
    except ValueError:
        print("Fehler: Port muss eine Zahl sein.", flush=True)
        sys.exit(2)
    if not 1 <= port <= 65535:
        print("Fehler: Port muss 1-65535 sein.", flush=True)
        sys.exit(2)
    print(f"Diagram-Studio auf Port {port}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()