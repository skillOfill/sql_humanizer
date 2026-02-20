"""
SQL Humanizer 🤖 — SQL to English Translator
Freemium app with License Key gate. Uses Google Gemini for translation.
"""

import json
import os
import urllib.parse
import streamlit as st
from dotenv import load_dotenv

# Load .env for GEMINI_API_KEY (create .env from .env.example and paste your key)
load_dotenv()

# =============================================================================
# CONFIGURATION — Razorpay payment link; license keys delivered after payment (see LICENSE_DELIVERY.md)
# =============================================================================
RAZORPAY_UPGRADE_URL = os.getenv("RAZORPAY_UPGRADE_URL", "https://your-razorpay-payment-link-or-checkout-url")

# Optional: URL of license server (backend). If set, keys are validated via GET /api/validate?key=...
LICENSE_SERVER_URL = os.getenv("LICENSE_SERVER_URL", "").strip().rstrip("/")

# Google OAuth for "Google Login → Payment → Auto-Unlock"
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "").strip()
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "").strip()
# Must match the redirect URI configured in Google Cloud Console (e.g. https://yourapp.streamlit.app/)
REDIRECT_URI = os.getenv("REDIRECT_URI", "").strip() or None

# Free tier: max queries before upgrade prompt
FREE_TIER_MAX_QUERIES = 1


def email_has_license(email: str) -> bool:
    """True if this email has a license (auto-unlock after Google Login + Payment)."""
    if not email or not LICENSE_SERVER_URL:
        return False
    try:
        import urllib.request
        q = urllib.parse.quote(email.strip())
        req = urllib.request.Request(
            f"{LICENSE_SERVER_URL}/api/validate-by-email?email={q}",
            method="GET",
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            if resp.status != 200:
                return False
            data = json.loads(resp.read().decode())
            return data.get("valid") is True
    except Exception:
        return False


def get_payment_link_for_email(email: str) -> str | None:
    """Get a Razorpay payment link with email pre-filled (from backend). Returns URL or None."""
    if not email or not LICENSE_SERVER_URL:
        return None
    try:
        import urllib.request
        data = json.dumps({"email": email.strip()}).encode()
        req = urllib.request.Request(
            f"{LICENSE_SERVER_URL}/api/create-payment-link",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status != 200:
                return None
            out = json.loads(resp.read().decode())
            return (out.get("url") or "").strip() or None
    except Exception:
        return None


def translate_sql(query: str, api_key: str) -> tuple[str | None, str | None]:
    """
    Use Google Generative AI (Gemini) to explain the SQL query in plain English.
    Returns (result_text, error_message). One of them will be None.
    """
    if not query or not query.strip():
        return None, "Please enter an SQL query."
    if not api_key or not api_key.strip():
        return None, "Gemini API key is missing. Add GEMINI_API_KEY to your .env file."

    try:
        import google.generativeai as genai
        genai.configure(api_key=api_key.strip())
        model = genai.GenerativeModel("gemini-2.5-flash")
        prompt = (
            "Explain this SQL query to a non-technical manager in one simple sentence. "
            "Be clear and concise. Reply with only that sentence, no code or extra formatting.\n\n"
            f"{query.strip()}"
        )
        response = model.generate_content(prompt)
        if response and response.text:
            return response.text.strip(), None
        return None, "The model returned an empty response."
    except Exception as e:
        err = str(e).strip() or "Unknown error"
        if "API_KEY_INVALID" in err or "invalid" in err.lower():
            return None, "Invalid or missing Gemini API key. Check your .env (GEMINI_API_KEY)."
        return None, f"Translation failed: {err}"


def _google_oauth_url() -> str:
    base = "https://accounts.google.com/o/oauth2/v2/auth"
    params = {
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": "openid email profile",
        "access_type": "offline",
        "prompt": "consent",
    }
    return base + "?" + urllib.parse.urlencode(params)


def _exchange_code_for_user(code: str) -> tuple[str | None, str | None]:
    """Exchange OAuth code for user email and name. Returns (email, name) or (None, None)."""
    if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET or not REDIRECT_URI:
        return None, None
    try:
        import requests
        r = requests.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code": code,
                "client_id": GOOGLE_CLIENT_ID,
                "client_secret": GOOGLE_CLIENT_SECRET,
                "redirect_uri": REDIRECT_URI,
                "grant_type": "authorization_code",
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=10,
        )
        if r.status_code != 200:
            return None, None
        tok = r.json().get("access_token")
        if not tok:
            return None, None
        u = requests.get(
            "https://www.googleapis.com/oauth2/v2/userinfo",
            headers={"Authorization": f"Bearer {tok}"},
            timeout=10,
        )
        if u.status_code != 200:
            return None, None
        info = u.json()
        return (info.get("email") or "").strip() or None, (info.get("name") or "").strip() or None
    except Exception:
        return None, None


def main():
    # --- Session state ---
    if "free_queries_used" not in st.session_state:
        st.session_state.free_queries_used = 0
    if "user_email" not in st.session_state:
        st.session_state.user_email = None
    if "user_name" not in st.session_state:
        st.session_state.user_name = None

    # --- Page config and title ---
    st.set_page_config(
        page_title="SQL Humanizer",
        page_icon="🤖",
        layout="centered",
        initial_sidebar_state="expanded",
    )

    # --- Google OAuth: handle callback (code in URL) ---
    q = st.query_params
    code = (q.get("code") or "").strip() if hasattr(q, "get") else ""
    if code and not st.session_state.user_email and GOOGLE_CLIENT_ID and REDIRECT_URI:
        email, name = _exchange_code_for_user(code)
        if email:
            st.session_state.user_email = email
            st.session_state.user_name = name or email
            # Clear code from URL by redirecting to same app without query (optional; avoids re-use)
            st.query_params.clear()
            st.rerun()

    # --- If Google Login is configured but user not logged in: show login screen ---
    use_google_login = bool(GOOGLE_CLIENT_ID and REDIRECT_URI)
    if use_google_login and not st.session_state.user_email:
        st.markdown("## SQL Humanizer 🤖")
        st.markdown("Sign in with Google to use the app and upgrade to Pro.")
        oauth_url = _google_oauth_url()
        st.link_button("Sign in with Google", oauth_url, type="primary")
        st.stop()

    # --- Modern typography and header ---
    st.markdown(
        """
        <style>
        /* Clean, professional look */
        @import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&display=swap');
        html, body, [class*="css"] { font-family: 'DM Sans', sans-serif; }
        .main-header {
            font-size: 2rem;
            font-weight: 700;
            color: #1e293b;
            margin-bottom: 0.5rem;
        }
        .sub-header {
            font-size: 1rem;
            color: #64748b;
            margin-bottom: 2rem;
        }
        .pro-badge {
            background: linear-gradient(135deg, #10b981 0%, #059669 100%);
            color: white;
            padding: 0.35rem 0.75rem;
            border-radius: 9999px;
            font-size: 0.875rem;
            font-weight: 600;
        }
        .upgrade-cta {
            background: linear-gradient(135deg, #6366f1 0%, #4f46e5 100%);
            color: white;
            padding: 1rem 1.5rem;
            border-radius: 0.5rem;
            text-align: center;
            margin: 1rem 0;
            font-weight: 600;
        }
        .limit-warning {
            background: #fef3c7;
            border-left: 4px solid #f59e0b;
            padding: 1rem;
            border-radius: 0 0.5rem 0.5rem 0;
            margin: 1rem 0;
        }
        /* Hide Streamlit dev menu (Deploy, Settings, etc.) — app is for end users only */
        #MainMenu, footer, header [data-testid="stToolbar"] { visibility: hidden; }
        footer { display: none; }
        /* Hide sidebar collapse (<<) so sidebar stays open and never gets stuck; expand tab (>) left visible */
        [data-testid="stSidebar"] > div:first-child button[aria-label*="Collapse"],
        [data-testid="stSidebar"] > div:first-child button[aria-label*="close"],
        [data-testid="stSidebarCollapseButton"] { display: none !important; }
        </style>
        """,
        unsafe_allow_html=True,
    )

    st.markdown('<p class="main-header">SQL Humanizer 🤖</p>', unsafe_allow_html=True)
    st.markdown(
        '<p class="sub-header">Paste your SQL — get a one-sentence explanation for non-technical stakeholders.</p>',
        unsafe_allow_html=True,
    )

    # --- Sidebar: Account, Pro status, Upgrade ---
    user_email = st.session_state.user_email
    with st.sidebar:
        if user_email:
            st.caption(f"Signed in as **{user_email}**")
            if st.button("Sign out"):
                st.session_state.user_email = None
                st.session_state.user_name = None
                st.rerun()
            st.markdown("---")
        st.header("Pro")
        # Pro = this email has paid (backend has a license for this email)
        is_pro = email_has_license(user_email) if user_email else False

        if is_pro:
            st.markdown('<p class="pro-badge">Pro — Unlimited 🚀</p>', unsafe_allow_html=True)
            st.caption("You have unlimited access.")
        else:
            st.caption("Free: 1 query. Pay once for unlimited (same email = auto-unlock).")
            st.markdown("---")
            st.markdown("**Upgrade to Pro**")
            upgrade_url = None
            if user_email and LICENSE_SERVER_URL:
                upgrade_url = get_payment_link_for_email(user_email)
            if not upgrade_url:
                upgrade_url = RAZORPAY_UPGRADE_URL
            st.markdown(
                f'<a href="{upgrade_url}" target="_blank" class="upgrade-cta" '
                'style="display:block;text-decoration:none;color:white;">Upgrade (₹499)</a>',
                unsafe_allow_html=True,
            )
            if user_email:
                st.caption("Use the **same email** when paying so you’re auto-unlocked.")

    # --- Main area: SQL input and translate ---
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    sql_query = st.text_area(
        "SQL Query",
        height=120,
        placeholder="e.g. SELECT name, SUM(amount) FROM orders GROUP BY name HAVING SUM(amount) > 1000",
        label_visibility="collapsed",
    )

    col1, col2, _ = st.columns([1, 1, 3])
    with col1:
        translate_clicked = st.button("Translate to English", type="primary", use_container_width=True)
    with col2:
        if st.button("Clear", use_container_width=True):
            st.session_state.last_result = None
            st.rerun()

    # --- Gatekeeper: enforce free-tier limit when not pro (block further translations) ---
    if (
        not is_pro
        and st.session_state.free_queries_used >= FREE_TIER_MAX_QUERIES
        and translate_clicked
    ):
        st.markdown(
            """
            <div class="limit-warning">
                <strong>Limit reached!</strong> Upgrade to Pro in the sidebar for unlimited access (₹499).
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.stop()

    # --- Run translation on button click ---
    if translate_clicked and sql_query:
        if not is_pro:
            st.session_state.free_queries_used = st.session_state.get("free_queries_used", 0) + 1

        result, error = translate_sql(sql_query, api_key)
        if error:
            st.error(error)
        else:
            st.success("**In plain English:**")
            st.info(result)

        # If we just used the free query and now at limit, show upgrade message
        if not is_pro and st.session_state.free_queries_used >= FREE_TIER_MAX_QUERIES:
            st.markdown(
                """
                <div class="limit-warning">
                    <strong>Limit reached!</strong> Upgrade to Pro in the sidebar for unlimited access.
                </div>
                """,
                unsafe_allow_html=True,
            )

if __name__ == "__main__":
    main()
