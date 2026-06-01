from config.settings import ACCOUNT_DB_PATH, DB_PATH
from dashboard.account_store import AccountStore


def test_account_store_default_db_is_separate_from_market_data_db():
    assert ACCOUNT_DB_PATH.name == "accounts.db"
    assert ACCOUNT_DB_PATH != DB_PATH
    assert AccountStore.__init__.__defaults__[0] == ACCOUNT_DB_PATH
