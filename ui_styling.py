"""
Professional UI styling module for ProcureIQ Analytics Dashboard.

Provides:
  - Modern CSS styling with professional color scheme
  - Responsive layouts
  - Professional components and cards
  - Theme management
  - Color utilities
"""

import streamlit as st
from config import Config
from typing import Optional


def apply_professional_styling() -> None:
    """
    Apply professional styling to Streamlit dashboard.
    Should be called early in the app initialization.
    """
    
    # Define color variables
    primary_color = Config.PRIMARY_COLOR
    secondary_color = Config.SECONDARY_COLOR
    success_color = Config.SUCCESS_COLOR
    warning_color = Config.WARNING_COLOR
    danger_color = Config.DANGER_COLOR
    info_color = Config.INFO_COLOR
    light_bg = Config.LIGHT_BG_COLOR
    
    # CSS styling
    css = f"""
    <style>
    /* Root Variables */
    :root {{
        --primary-color: {primary_color};
        --secondary-color: {secondary_color};
        --success-color: {success_color};
        --warning-color: {warning_color};
        --danger-color: {danger_color};
        --info-color: {info_color};
        --light-bg: {light_bg};
        --text-primary: #2d3748;
        --text-secondary: #718096;
        --border-color: #e2e8f0;
    }}
    
    /* Main Container */
    .main {{
        background-color: var(--light-bg);
    }}
    
    /* Header Container */
    .header-container {{
        background: linear-gradient(135deg, var(--primary-color) 0%, var(--secondary-color) 100%);
        padding: 2.5rem;
        border-radius: 12px;
        color: white;
        margin-bottom: 2rem;
        box-shadow: 0 4px 15px rgba(102, 126, 234, 0.2);
    }}
    
    .header-title {{
        font-size: 2.5rem;
        font-weight: 700;
        margin: 0;
        color: white;
    }}
    
    .header-subtitle {{
        font-size: 1.1rem;
        opacity: 0.95;
        margin-top: 0.75rem;
        color: rgba(255, 255, 255, 0.9);
    }}
    
    /* Section Headers */
    .section-header {{
        font-size: 1.5rem;
        font-weight: 600;
        color: var(--text-primary);
        margin-top: 2rem;
        margin-bottom: 1rem;
        border-bottom: 2px solid var(--border-color);
        padding-bottom: 0.75rem;
    }}
    
    /* Metric Cards */
    .metric-card {{
        background: white;
        padding: 1.5rem;
        border-radius: 10px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.08);
        border-left: 4px solid var(--primary-color);
        transition: transform 0.2s, box-shadow 0.2s;
    }}
    
    .metric-card:hover {{
        transform: translateY(-2px);
        box-shadow: 0 4px 12px rgba(0,0,0,0.12);
    }}
    
    .metric-label {{
        color: var(--text-secondary);
        font-size: 0.85rem;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }}
    
    .metric-value {{
        font-size: 1.8rem;
        font-weight: 700;
        color: var(--text-primary);
        margin-top: 0.5rem;
    }}
    
    /* Card Component */
    .card {{
        background: white;
        padding: 1.5rem;
        border-radius: 10px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.08);
        margin-bottom: 1rem;
    }}
    
    .card-header {{
        font-size: 1.1rem;
        font-weight: 600;
        color: var(--text-primary);
        margin-bottom: 1rem;
        border-bottom: 1px solid var(--border-color);
        padding-bottom: 0.75rem;
    }}
    
    /* Alerts */
    .alert {{
        padding: 1rem;
        border-radius: 8px;
        border-left: 4px solid;
        margin-bottom: 1rem;
    }}
    
    .alert-success {{
        background-color: #d4edda;
        border-color: var(--success-color);
        color: #155724;
    }}
    
    .alert-warning {{
        background-color: #fff3cd;
        border-color: var(--warning-color);
        color: #856404;
    }}
    
    .alert-danger {{
        background-color: #f8d7da;
        border-color: var(--danger-color);
        color: #721c24;
    }}
    
    .alert-info {{
        background-color: #d1ecf1;
        border-color: var(--info-color);
        color: #0c5460;
    }}
    
    /* Badges */
    .badge {{
        display: inline-block;
        padding: 0.25rem 0.75rem;
        border-radius: 20px;
        font-size: 0.85rem;
        font-weight: 600;
        margin: 0.25rem;
    }}
    
    .badge-success {{
        background-color: #d4edda;
        color: #155724;
    }}
    
    .badge-warning {{
        background-color: #fff3cd;
        color: #856404;
    }}
    
    .badge-danger {{
        background-color: #f8d7da;
        color: #721c24;
    }}
    
    .badge-info {{
        background-color: #d1ecf1;
        color: #0c5460;
    }}
    
    /* Buttons */
    .stButton>button {{
        border-radius: 8px;
        font-weight: 600;
        padding: 0.5rem 1.5rem;
        border: none;
        transition: all 0.3s;
    }}
    
    .stButton>button:hover {{
        transform: translateY(-2px);
        box-shadow: 0 4px 12px rgba(102, 126, 234, 0.3);
    }}
    
    /* Tables */
    .stDataFrame {{
        border-radius: 8px;
        overflow: hidden;
        box-shadow: 0 2px 8px rgba(0,0,0,0.08);
    }}
    
    /* Tabs */
    .stTabs [data-baseweb="tab-list"] button {{
        border-radius: 8px 8px 0 0;
        font-weight: 600;
    }}
    
    /* Sidebar */
    .sidebar .sidebar-content {{
        background-color: white;
    }}
    
    .sidebar-header {{
        font-size: 1.1rem;
        font-weight: 700;
        color: var(--primary-color);
        margin-top: 1.5rem;
        margin-bottom: 1rem;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }}
    
    /* Status Indicators */
    .status-online {{
        display: inline-block;
        width: 12px;
        height: 12px;
        border-radius: 50%;
        background-color: var(--success-color);
        margin-right: 0.5rem;
        animation: pulse 2s infinite;
    }}
    
    .status-offline {{
        display: inline-block;
        width: 12px;
        height: 12px;
        border-radius: 50%;
        background-color: var(--danger-color);
        margin-right: 0.5rem;
    }}
    
    .status-warning {{
        display: inline-block;
        width: 12px;
        height: 12px;
        border-radius: 50%;
        background-color: var(--warning-color);
        margin-right: 0.5rem;
    }}
    
    @keyframes pulse {{
        0%, 100% {{ opacity: 1; }}
        50% {{ opacity: 0.7; }}
    }}
    
    /* Responsive Typography */
    h1 {{
        color: var(--text-primary);
        font-weight: 700;
        margin-bottom: 1rem;
    }}
    
    h2 {{
        color: var(--text-primary);
        font-weight: 600;
        margin-top: 1.5rem;
        margin-bottom: 0.75rem;
    }}
    
    h3, h4, h5, h6 {{
        color: var(--text-primary);
        font-weight: 600;
        margin-top: 1rem;
        margin-bottom: 0.5rem;
    }}
    
    /* Spinner */
    .spinner {{
        border: 4px solid var(--light-bg);
        border-top: 4px solid var(--primary-color);
        border-radius: 50%;
        width: 40px;
        height: 40px;
        animation: spin 1s linear infinite;
    }}
    
    @keyframes spin {{
        0% {{ transform: rotate(0deg); }}
        100% {{ transform: rotate(360deg); }}
    }}
    
    /* Divider */
    .divider {{
        border: 0;
        height: 1px;
        background: var(--border-color);
        margin: 1.5rem 0;
    }}
    </style>
    """
    
    st.markdown(css, unsafe_allow_html=True)


def render_header(
    title: str = "ProcureIQ Analytics",
    subtitle: str = "Intelligent Procurement & Spend Management Dashboard"
) -> None:
    """
    Render professional header for dashboard.
    
    Args:
        title: Header title
        subtitle: Header subtitle
    """
    st.markdown(f"""
        <div class="header-container">
            <div class="header-title">{title}</div>
            <div class="header-subtitle">{subtitle}</div>
        </div>
    """, unsafe_allow_html=True)


def render_metric_card(
    label: str,
    value: str,
    change: Optional[str] = None,
    color: str = "primary"
) -> None:
    """
    Render a styled metric card.
    
    Args:
        label: Metric label
        value: Metric value
        change: Optional change indicator
        color: Color scheme (primary, success, warning, danger, info)
    """
    color_map = {
        "primary": "--primary-color",
        "success": "--success-color",
        "warning": "--warning-color",
        "danger": "--danger-color",
        "info": "--info-color",
    }
    
    color_var = color_map.get(color, "--primary-color")
    
    html_content = f"""
    <div class="metric-card" style="border-left-color: var({color_var});">
        <div class="metric-label">{label}</div>
        <div class="metric-value">{value}</div>
    """
    
    if change:
        html_content += f'<div style="margin-top: 0.5rem; color: var({color_var}); font-size: 0.9rem;">{change}</div>'
    
    html_content += "</div>"
    
    st.markdown(html_content, unsafe_allow_html=True)


def render_alert(
    message: str,
    alert_type: str = "info",
    dismissible: bool = True
) -> None:
    """
    Render a styled alert.
    
    Args:
        message: Alert message
        alert_type: Alert type (success, warning, danger, info)
        dismissible: Whether alert can be dismissed
    """
    st.markdown(f"""
        <div class="alert alert-{alert_type}">
            {message}
        </div>
    """, unsafe_allow_html=True)


def render_badge(
    text: str,
    badge_type: str = "info"
) -> str:
    """
    Render a styled badge.
    
    Args:
        text: Badge text
        badge_type: Badge type (success, warning, danger, info)
        
    Returns:
        HTML string for badge
    """
    return f'<span class="badge badge-{badge_type}">{text}</span>'


def render_status_indicator(
    status: str = "online"
) -> str:
    """
    Render a status indicator.
    
    Args:
        status: Status (online, offline, warning)
        
    Returns:
        HTML string for status indicator
    """
    return f'<span class="status-{status}"></span>'


def create_two_column_layout(
    col1_content: callable,
    col2_content: callable,
    gap: str = "medium"
) -> None:
    """
    Create a professional two-column layout.
    
    Args:
        col1_content: Function to render left column content
        col2_content: Function to render right column content
        gap: Gap between columns (small, medium, large)
    """
    col1, col2 = st.columns(2, gap=gap)
    
    with col1:
        col1_content()
    
    with col2:
        col2_content()


def create_three_column_layout(
    col1_content: callable,
    col2_content: callable,
    col3_content: callable,
    gap: str = "medium"
) -> None:
    """
    Create a professional three-column layout.
    
    Args:
        col1_content: Function to render left column content
        col2_content: Function to render middle column content
        col3_content: Function to render right column content
        gap: Gap between columns (small, medium, large)
    """
    col1, col2, col3 = st.columns(3, gap=gap)
    
    with col1:
        col1_content()
    
    with col2:
        col2_content()
    
    with col3:
        col3_content()


def set_page_config(
    app_title: Optional[str] = None,
    layout: str = "wide",
    initial_sidebar_state: str = "expanded"
) -> None:
    """
    Configure page settings with professional defaults.
    
    Args:
        app_title: Page title (uses Config if not provided)
        layout: Layout mode (wide or centered)
        initial_sidebar_state: Initial sidebar state
    """
    title = app_title or Config.APP_TITLE
    
    st.set_page_config(
        page_title=title,
        layout=layout,
        initial_sidebar_state=initial_sidebar_state,
        menu_items={
            'Get Help': 'https://docs.procureiq.local',
            'Report a bug': 'https://github.com/procureiq/issues',
            'About': f'{title} - Intelligent Procurement & Spend Analytics v2.0'
        }
    )
