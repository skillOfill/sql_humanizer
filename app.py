"""
SQL Humanizer 🤖 — SQL to English Translator
Freemium app with License Key gate. Uses Google Gemini for translation.
"""

import os
import streamlit as st
from dotenv import load_dotenv

# Load .env for GEMINI_API_KEY (create .env from .env.example and paste your key)
load_dotenv()

# =============================================================================
# CONFIGURATION — Paste your Stripe payment link and valid license key here
# =============================================================================
# [INSERT_STRIPE_LINK_HERE] — Replace with your Stripe payment/checkout link for ₹499
STRIPE_UPGRADE_URL = os.getenv("STRIPE_UPGRADE_URL", "https://buy.stripe.com/[INSERT_STRIPE_LINK_HERE]")

# Hardcoded valid license key for testing. In production, validate against a DB or API.
VALID_LICENSE_KEY = "DEMO-KEY-2026"

# Free tier: max queries before upgrade prompt
FREE_TIER_MAX_QUERIES = 1


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


def main():
    # --- Session state for free-tier usage and license ---
    if "free_queries_used" not in st.session_state:
        st.session_state.free_queries_used = 0
    if "license_key" not in st.session_state:
        st.session_state.license_key = ""

    # --- Page config and title ---
    st.set_page_config(
        page_title="SQL Humanizer",
        page_icon="🤖",
        layout="centered",
        initial_sidebar_state="expanded",
    )

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
        </style>
        """,
        unsafe_allow_html=True,
    )

    st.markdown('<p class="main-header">SQL Humanizer 🤖</p>', unsafe_allow_html=True)
    st.markdown(
        '<p class="sub-header">Paste your SQL — get a one-sentence explanation for non-technical stakeholders.</p>',
        unsafe_allow_html=True,
    )

    # --- Sidebar: License key and upgrade CTA ---
    with st.sidebar:
        st.header("License")
        license_input = st.text_input(
            "License Key",
            value=st.session_state.license_key,
            type="password",
            placeholder="Enter your license key",
        )
        st.session_state.license_key = license_input

        is_pro = license_input.strip() == VALID_LICENSE_KEY

        if is_pro:
            st.markdown('<p class="pro-badge">Pro Mode Activated 🚀</p>', unsafe_allow_html=True)
            st.caption("Unlimited translations.")
        else:
            st.caption("Free: 1 query. Enter a valid key for unlimited.")
            st.markdown("---")
            st.markdown("**Upgrade to Pro**")
            st.markdown(
                f'<a href="{STRIPE_UPGRADE_URL}" target="_blank" class="upgrade-cta" '
                'style="display:block;text-decoration:none;color:white;">Get License Key (₹5)</a>',
                unsafe_allow_html=True,
            )

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
                <strong>Limit reached!</strong> Upgrade to Unlimited — enter a valid license key in the sidebar 
                or click <strong>Get License Key (₹5)</strong>.
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
                    <strong>Limit reached!</strong> Upgrade to Unlimited — get a license key from the sidebar.
                </div>
                """,
                unsafe_allow_html=True,
            )

if __name__ == "__main__":
    main()


