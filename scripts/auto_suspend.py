"""
scripts/auto_suspend.py
Streamlit auto-suspend helper (req 14).

Injects a JavaScript idle-detection timer into the Streamlit page.
After IDLE_TIMEOUT_SECONDS of inactivity the user is shown a warning.
After an additional idle_warning_seconds the page reloads, releasing
the server session and preventing idle compute cost.

Import from app.py in two safe ways:

    # Option A  (recommended - no package required)
    from auto_suspend import inject_idle_timer

    # Option B  (when scripts/ is a proper package with __init__.py)
    from scripts.auto_suspend import inject_idle_timer
"""

from __future__ import annotations

import os
import sys

# Make sure the project root is on sys.path so Config can be found
# regardless of whether this file is imported as a package member or
# executed / imported directly.
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)          # one level up from scripts/
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import streamlit as st
from config import Config


def inject_idle_timer(
    timeout_seconds: int | None = None,
    warning_seconds: int | None = None,
) -> None:
    """
    Inject a JavaScript idle-detection timer into the Streamlit app.

    Call once near the top of app.py, after st.set_page_config().

    Args:
        timeout_seconds: Seconds of inactivity before the warning overlay
                         appears.  Defaults to Config.IDLE_TIMEOUT_SECONDS.
        warning_seconds: Countdown seconds shown in the overlay before the
                         page reloads.  Defaults to
                         app_settings.yaml session.idle_warning_seconds.
    """
    timeout = (
        timeout_seconds
        if timeout_seconds is not None
        else Config.IDLE_TIMEOUT_SECONDS
    )

    warning = warning_seconds
    if warning is None:
        try:
            warning = int(
                Config._settings.get("session", {}).get("idle_warning_seconds", 60)
            )
        except Exception:
            warning = 60

    title = Config.APP_TITLE

    st.markdown(
        f"""
<style>
#idle-overlay {{
    display: none;
    position: fixed;
    inset: 0;
    background: rgba(15,23,42,0.85);
    z-index: 9999999;
    align-items: center;
    justify-content: center;
    flex-direction: column;
    color: #f8fafc;
    font-family: Inter, system-ui, sans-serif;
}}
#idle-overlay.visible {{
    display: flex;
}}
#idle-box {{
    background: #1e293b;
    border-radius: 16px;
    padding: 40px 52px;
    text-align: center;
    box-shadow: 0 24px 60px rgba(0,0,0,0.5);
    max-width: 440px;
}}
#idle-box h2 {{ margin: 0 0 10px; font-size: 22px; font-weight: 700; }}
#idle-box p  {{ margin: 0 0 24px; font-size: 14px; color: #94a3b8; }}
#idle-box button {{
    background: #1d4ed8;
    color: #fff;
    border: none;
    border-radius: 8px;
    padding: 10px 28px;
    font-size: 15px;
    font-weight: 600;
    cursor: pointer;
}}
#idle-box button:hover {{ background: #2563eb; }}
#idle-countdown {{ font-weight: 700; color: #f59e0b; }}
</style>

<div id="idle-overlay">
  <div id="idle-box">
    <h2>Session Idle</h2>
    <p>
      {title} has been inactive.<br>
      The session will be suspended in
      <span id="idle-countdown">{warning}</span> seconds.
    </p>
    <button onclick="window.idleReset()">Resume Session</button>
  </div>
</div>

<script>
(function() {{
    var TIMEOUT  = {timeout} * 1000;
    var WARNING  = {warning} * 1000;
    var timer, warnTimer;
    var overlay   = document.getElementById('idle-overlay');
    var countdown = document.getElementById('idle-countdown');
    var remaining = {warning};

    function freeze() {{
        if (overlay) overlay.classList.add('visible');
        remaining = {warning};
        if (countdown) countdown.textContent = remaining;
        warnTimer = setInterval(function() {{
            remaining -= 1;
            if (countdown) countdown.textContent = remaining;
            if (remaining <= 0) {{
                clearInterval(warnTimer);
                window.location.reload();
            }}
        }}, 1000);
    }}

    window.idleReset = function() {{
        clearTimeout(timer);
        clearInterval(warnTimer);
        if (overlay) overlay.classList.remove('visible');
        resetTimer();
    }};

    function resetTimer() {{
        clearTimeout(timer);
        timer = setTimeout(freeze, TIMEOUT);
    }}

    ['mousemove','keydown','mousedown','touchstart','scroll','click']
        .forEach(function(e) {{
            document.addEventListener(e, window.idleReset, true);
        }});

    resetTimer();
}})();
</script>
        """,
        unsafe_allow_html=True,
    )
