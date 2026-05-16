# config.py — GridWatch AI · DTE Energy · Hack Michigan 2026
"""
Central configuration module.
Import this FIRST in app.py to fix local module resolution and load all env vars.

Usage in app.py:
    from config import config          # access settings
    from config import PROJECT_ROOT    # access project path
"""

import os
import sys
import logging
from pathlib import Path
from dotenv import load_dotenv

# ── Path fix (resolves all Pylance / import errors) ───────────────────────
# Adds this file's parent directory (the project root) to sys.path so that
# dte_config, ml_model, weather_utils, etc. are always importable regardless
# of how or where Python is invoked.
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# ── Load .env ─────────────────────────────────────────────────────────────
_env_path = PROJECT_ROOT / '.env'
load_dotenv(dotenv_path=_env_path, override=False)

# ── Logging ───────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s — %(message)s',
)
_log = logging.getLogger('config')


# ── Settings class ────────────────────────────────────────────────────────
class Config:

    # ----- Flask ----------------------------------------------------------
    SECRET_KEY          = os.getenv('FLASK_SECRET_KEY', 'change-me-in-production')
    DEBUG               = os.getenv('FLASK_DEBUG', 'false').lower() == 'true'
    HOST                = os.getenv('FLASK_HOST', '0.0.0.0')
    PORT                = int(os.getenv('FLASK_PORT', '5000'))
    MAX_CONTENT_LENGTH  = 16 * 1024 * 1024   # 16 MB upload limit
    UPLOAD_FOLDER       = str(PROJECT_ROOT / 'uploads')

    # ----- IBM watsonx.ai -------------------------------------------------
    WATSONX_URL         = os.getenv('WATSONX_URL', 'https://us-south.ml.cloud.ibm.com')
    WATSONX_API_KEY     = os.getenv('WATSONX_API_KEY', '')
    WATSONX_PROJECT_ID  = os.getenv('WATSONX_PROJECT_ID', '')
    WATSONX_MODEL_ID    = os.getenv('WATSONX_MODEL_ID', 'ibm/granite-13b-instruct-v2')

    # ----- Google Earth Engine (optional) ---------------------------------
    GEE_SERVICE_ACCOUNT = os.getenv('GEE_SERVICE_ACCOUNT', '')
    GEE_KEY_FILE        = os.getenv('GEE_KEY_FILE', str(PROJECT_ROOT / 'gee_credentials.json'))

    # ----- Database / model paths -----------------------------------------
    DB_PATH             = str(PROJECT_ROOT / 'pole_history.db')
    RISK_MODEL_PATH     = str(PROJECT_ROOT / 'pole_risk_model.pkl')
    COST_MODEL_PATH     = str(PROJECT_ROOT / 'cost_predictor.pkl')

    # ----- DTE Energy territory -------------------------------------------
    DTE_CENTER_LAT  = 42.3314
    DTE_CENTER_LON  = -83.0458
    DTE_BBOX        = (42.0, -84.0, 43.0, -82.0)   # (south, west, north, east)
    DTE_MAX_POLES   = 250

    # ----- Risk score thresholds ------------------------------------------
    RISK_CRITICAL   = 70    # >= Critical / High
    RISK_HIGH       = 45    # >= Medium
    RISK_LOW        = 25    # >= Low  (below = Very Low)

    # ----- External API timeouts (seconds) --------------------------------
    WEATHER_TIMEOUT = 6
    NOAA_TIMEOUT    = 8
    FEMA_TIMEOUT    = 8
    OSM_TIMEOUT     = 20

    # ----- Feature list (must match ml_model.py FEATURE_NAMES) -----------
    FEATURE_NAMES = [
        'tilt_angle', 'veg_proximity', 'wind_speed',
        'soil_risk',  'age',           'material_code',
    ]

    # ----- Validation -----------------------------------------------------
    @classmethod
    def validate(cls) -> bool:
        """
        Check that all required environment variables are set.
        Logs a warning for each missing variable; returns False if any are absent.
        Call this on startup so problems are caught early.
        """
        required = {
            'WATSONX_API_KEY':    cls.WATSONX_API_KEY,
            'WATSONX_PROJECT_ID': cls.WATSONX_PROJECT_ID,
        }
        missing = [k for k, v in required.items() if not v]
        if missing:
            _log.warning(
                f"Missing environment variables: {', '.join(missing)}. "
                "watsonx.ai features will be disabled. "
                "Set these in your .env file."
            )
            return False
        _log.info("All required environment variables loaded ✓")
        return True

    @classmethod
    def summary(cls) -> dict:
        """Return a safe (no secrets) summary for logging."""
        return {
            'debug':             cls.DEBUG,
            'host':              cls.HOST,
            'port':              cls.PORT,
            'watsonx_url':       cls.WATSONX_URL,
            'watsonx_key_set':   bool(cls.WATSONX_API_KEY),
            'watsonx_proj_set':  bool(cls.WATSONX_PROJECT_ID),
            'gee_key_set':       bool(cls.GEE_SERVICE_ACCOUNT),
            'db_path':           cls.DB_PATH,
            'project_root':      str(PROJECT_ROOT),
        }


# ── Singleton export ──────────────────────────────────────────────────────
config = Config()

# Print summary on import (visible in terminal on startup)
_log.info(f"Config loaded — project root: {PROJECT_ROOT}")
if config.DEBUG:
    _log.info(f"Config summary: {config.summary()}")