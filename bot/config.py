from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

from dotenv import load_dotenv


def _s(name: str, default: str = "") -> str:
    v = os.getenv(name)
    return default if v is None else v.strip()


def _b(name: str, default: bool) -> bool:
    v = os.getenv(name)
    if v is None or v.strip() == "":
        return default
    return v.strip().lower() in ("1", "true", "yes", "sim", "on")


def _f(name: str, default: float) -> float:
    v = os.getenv(name)
    if v is None or v.strip() == "":
        return default
    return float(v.strip().replace(",", "."))


def _i(name: str, default: int) -> int:
    v = os.getenv(name)
    if v is None or v.strip() == "":
        return default
    return int(v.strip())


@dataclass(frozen=True)
class Config:
    tg_api_id: int
    tg_api_hash: str
    tg_session: str
    tg_channel: str
    tg_notify: str

    casa: str
    pinnacle_user: str
    pinnacle_pass: str
    gmail_user: str
    gmail_app_password: str

    unit_value: float
    extra_tip_units: float
    max_stake: float
    daily_max_total: float
    # True = UNIT_VALUE/MAX_STAKE/DAILY_MAX_TOTAL vieram de <CASA>_UNIT_VALUE etc. (valores na moeda da casa).
    # Casa com moeda diferente de R$ exige isso, para nunca usar por engano o UNIT_VALUE em reais.
    money_from_casa: bool

    dry_run: bool

    max_tip_age_s: int
    give_up_minute: int
    monitor_timeout_s: int
    cancel_window_s: int
    require_score_check: bool
    match_threshold: float

    chrome_channel: str
    headless: bool
    profile_dir: str
    fresh_session: bool
    viewport_w: int
    viewport_h: int
    manual_intervention_timeout_s: int
    line_gone_s: int
    idle_close_min: int
    poll_min_s: float
    poll_max_s: float

    state_db: str
    log_level: str

    @staticmethod
    def load(env_file: Optional[str] = None) -> "Config":
        load_dotenv(env_file or ".env")
        casa = _s("CASA", "pinnacle")
        prefixo = casa.strip().upper() + "_"

        def da_casa(nome: str) -> str:
            """'<CASA>_<NOME>' se estiver preenchido no .env, senão '<NOME>' (valor geral)."""
            v = os.getenv(prefixo + nome)
            return prefixo + nome if v is not None and v.strip() != "" else nome

        dinheiro = ("UNIT_VALUE", "MAX_STAKE", "DAILY_MAX_TOTAL")
        return Config(
            tg_api_id=_i("TG_API_ID", 0),
            tg_api_hash=_s("TG_API_HASH"),
            tg_session=_s("TG_SESSION", "tg_session"),
            tg_channel=_s("TG_CHANNEL"),
            tg_notify=_s("TG_NOTIFY", "me"),
            casa=casa,
            pinnacle_user=_s("PINNACLE_USER"),
            pinnacle_pass=_s("PINNACLE_PASS"),
            gmail_user=_s("GMAIL_USER"),
            gmail_app_password=_s("GMAIL_APP_PASSWORD").replace(" ", ""),
            unit_value=_f(da_casa("UNIT_VALUE"), 350.0),
            extra_tip_units=_f("EXTRA_TIP_UNITS", 0.25),
            max_stake=_f(da_casa("MAX_STAKE"), 500.0),
            daily_max_total=_f(da_casa("DAILY_MAX_TOTAL"), 2000.0),
            money_from_casa=all(da_casa(n) != n for n in dinheiro),
            dry_run=_b("DRY_RUN", True),
            max_tip_age_s=_i("MAX_TIP_AGE_S", 600),
            give_up_minute=_i("GIVE_UP_MINUTE", 88),
            monitor_timeout_s=_i("MONITOR_TIMEOUT_S", 2700),
            cancel_window_s=_i("CANCEL_WINDOW_S", 180),
            require_score_check=_b("REQUIRE_SCORE_CHECK", True),
            match_threshold=_f("MATCH_THRESHOLD", 0.70),
            chrome_channel=_s("CHROME_CHANNEL", "chrome"),
            headless=_b("HEADLESS", False),
            profile_dir=_s(da_casa("PROFILE_DIR"), "browser_profile"),
            fresh_session=_b(da_casa("FRESH_SESSION"), True),
            viewport_w=_i("VIEWPORT_W", 440),
            viewport_h=_i("VIEWPORT_H", 940),
            manual_intervention_timeout_s=_i("MANUAL_INTERVENTION_TIMEOUT_S", 600),
            line_gone_s=_i("LINE_GONE_S", 60),
            idle_close_min=_i("IDLE_CLOSE_MIN", 20),
            poll_min_s=_f("POLL_MIN_S", 2.0),
            poll_max_s=_f("POLL_MAX_S", 4.5),
            state_db=_s("STATE_DB", "state.sqlite3"),
            log_level=_s("LOG_LEVEL", "INFO"),
        )
