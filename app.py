import os
import re
import json
import base64
import logging
import requests
from io import BytesIO
import sys

# Fix Colab/Codespaces argument bug
sys.argv = [sys.argv[0]]

from flask import Flask, request, jsonify
from playwright.sync_api import sync_playwright
import pdfplumber
import pandas as pd
from pyngrok import ngrok

logging.basicConfig(level=logging.INFO, format="%(asctime)s [INFO] %(message)s")
logger = logging.getLogger("quiz-server")

app = Flask(__name__)

SECRET = os.environ.get("SECRET")
NGROK_TOKEN = os.environ.get("NGROK_TOKEN")


# ------------ PLAYWRIGHT JS RENDERING ----------------
def render_js(url):
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox"]
        )
        page = browser.new_page()
        page.goto(url, wait_until="networkidle", timeout=60000)
        text = page.inner_text("body")
        html = page.content()
        browser.close()
        return text, html


# ------------ BASE64 atob() DECODER -------------------
def decode_atob(html):
    patterns = [
        r'atob\("([^"]+)"\)',
        r"atob\('([^']+)'\)",
        r"atob\(`([^`]+)`\)"
    ]
    for ptn in patterns:
        m = re.search(ptn, html, re.S)
        if m:
            try:
                return base64.b64decode(m.group(1)).decode("utf-8", "ignore")
            except:
                pass
    return None


# ------------ PDF TABLE SUMMER ------------------------
def pdf_sum(pdf_bytes, col=None, page=None):
    with pdfplumber.open(BytesIO(pdf_bytes)) as pdf:
        pages = [pdf.pages[page - 1]] if page else pdf.pages
        for pg in pages:
            tables = pg.extract_tables()
            for tb in tables:
                df = pd.DataFrame(tb[1:], columns=tb[0])

                if col and col in df.columns:
                    return pd.to_numeric(df[col], errors="coerce").sum()

                for c in df.columns:
                    nums = pd.to_numeric(df[c], errors="coerce")
                    if nums.notna().any():
                        return nums.sum()
    return None


# ------------ HTML TABLE SUMMER -----------------------
def html_sum(html, col=None):
    try:
        dfs = pd.read_html(html)
        for df in dfs:
            if col and col in df.columns:
                return pd.to_numeric(df[col], errors="coerce").sum()

            for c in df.columns:
                nums = pd.to_numeric(df[c], errors="coerce")
                if nums.notna().any():
                    return nums.sum()

    except:
        pass

    return None


# ------------ FIND SUBMIT URL -------------------------
def find_submit(text):
    urls = re.findall(r"https?://[^\s\"'<>]+", text)
    for u in urls:
        if "submit" in u.lower():
            return u
    return urls[0] if urls else None


# ------------ MAIN SOLVER -----------------------------
def solve(visible, html):
    # decode base64 if present
    decoded = decode_atob(html)
    if decoded:
        visible = decoded + "\n" + visible

    # SUM OF COLUMN ON PAGE
    m = re.search(r"sum.*['\"]?(\w+)['\"]?.*page\s*(\d+)", visible, re.I)
    if m:
        col = m.group(1)
        page = int(m.group(2))

        pdf_urls = re.findall(r"https?://[^\s\"'<>]+\.pdf", html)
        if pdf_urls:
            pdf_bytes = requests.get(pdf_urls[0]).content
            return pdf_sum(pdf_bytes, col, page), find_submit(visible + html)

    # HTML TABLE SUM
    v = html_sum(html, "value")
    if v is not None:
        return v, find_submit(visible + html)

    # fallback
    return None, find_submit(visible + html)


# ------------ API ENDPOINT ----------------------------
@app.route("/task", methods=["POST"])
def task():
    try:
        data = request.get_json(force=True)
    except:
        return jsonify({"error": "invalid json"}), 400

    if data.get("secret") != SECRET:
        return jsonify({"error": "invalid secret"}), 403

    url = data.get("url")

    try:
        visible, html = render_js(url)
    except Exception as e:
        return jsonify({"ok": False, "reason": "page load failed", "error": str(e)}), 200

    ans, submit_url = solve(visible, html)

    if ans is None:
        return jsonify({"ok": False, "reason": "could not solve"}), 200

    submit_result = {}
    if submit_url:
        try:
            r = requests.post(submit_url, json={
                "email": data["email"],
                "secret": data["secret"],
                "url": url,
                "answer": ans,
            })
            submit_result = r.json()
        except:
            submit_result = {"error": "submit failed"}

    return jsonify({
        "ok": True,
        "answer": ans,
        "submit_url": submit_url,
        "submit_result": submit_result
    }), 200


# ------------ NGROK STARTER ---------------------------
def start_ngrok(port=5000):
    ngrok.set_auth_token(NGROK_TOKEN)
    t = ngrok.connect(port, "http")
    logger.info(f"PUBLIC URL: {t.public_url}")
    return t.public_url


# ------------ FLASK SERVER ----------------------------
if __name__ == "__main__":
    from werkzeug.serving import run_simple
    run_simple("0.0.0.0", 5000, app, use_reloader=False)
