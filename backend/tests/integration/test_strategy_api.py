"""Integration tests for the strategy API: create, retrieve, and version."""

import uuid

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.strategy import StrategyVersion


def _valid_config_payload() -> dict:
    return {
        "schema_version": 2,
        "portfolio_rules": {"cash_reserve_pct": 10, "max_allocation_pct": 25, "max_open_positions": 5},
        "asset_rules": [{
            "symbol": "AAPL",
            "buy_conditions": {
                "operator": "AND",
                "rules": [{"indicator": "RSI", "period": 14, "operator": "less_than", "value": 30}],
            },
            "sell_conditions": {
                "operator": "AND",
                "rules": [{"indicator": "PRICE", "period": 1, "operator": "greater_than", "value": 195}],
            },
            "capital_allocation": {"type": "percentage_of_portfolio", "percentage": 5},
            "exit": {"stop_loss_pct": 3, "take_profit_pct": None},
        }],
    }


def test_create_strategy_returns_created_strategy(client: TestClient):
    user_id = str(uuid.uuid4())

    response = client.post(
        "/strategies",
        json={"user_id": user_id, "config": _valid_config_payload(), "source": "manual"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["user_id"] == user_id
    assert body["state"] == "draft"
    assert body["current_version_id"] is not None


def test_create_strategy_persists_first_version(client: TestClient, db_session: Session):
    user_id = str(uuid.uuid4())

    response = client.post(
        "/strategies",
        json={"user_id": user_id, "config": _valid_config_payload(), "source": "manual"},
    )
    strategy_id = response.json()["id"]

    version = (
        db_session.query(StrategyVersion)
        .filter(StrategyVersion.strategy_id == uuid.UUID(strategy_id))
        .one()
    )
    assert version.version_number == 1
    assert version.config_json["asset_rules"][0]["symbol"] == "AAPL"


def test_get_strategy_returns_existing_strategy(client: TestClient):
    user_id = str(uuid.uuid4())
    create_response = client.post(
        "/strategies",
        json={"user_id": user_id, "config": _valid_config_payload(), "source": "manual"},
    )
    strategy_id = create_response.json()["id"]

    response = client.get(f"/strategies/{strategy_id}")

    assert response.status_code == 200
    assert response.json()["id"] == strategy_id


def test_get_strategy_returns_404_for_unknown_id(client: TestClient):
    response = client.get(f"/strategies/{uuid.uuid4()}")

    assert response.status_code == 404


def test_create_new_version_advances_current_version_without_mutating_old_one(
    client: TestClient, db_session: Session
):
    user_id = str(uuid.uuid4())
    create_response = client.post(
        "/strategies",
        json={"user_id": user_id, "config": _valid_config_payload(), "source": "manual"},
    )
    strategy_id = create_response.json()["id"]
    first_version_id = create_response.json()["current_version_id"]

    new_config = _valid_config_payload()
    new_config["asset_rules"][0]["capital_allocation"]["percentage"] = 10

    version_response = client.post(
        f"/strategies/{strategy_id}/versions",
        json={"config": new_config, "source": "manual"},
    )

    assert version_response.status_code == 201
    new_version_body = version_response.json()
    assert new_version_body["version_number"] == 2
    assert new_version_body["id"] != first_version_id

    strategy_response = client.get(f"/strategies/{strategy_id}")
    assert strategy_response.json()["current_version_id"] == new_version_body["id"]

    old_version = db_session.get(StrategyVersion, uuid.UUID(first_version_id))
    assert old_version is not None
    assert old_version.version_number == 1
    assert old_version.config_json["asset_rules"][0]["capital_allocation"]["percentage"] == 5


def test_create_version_for_unknown_strategy_returns_404(client: TestClient):
    response = client.post(
        f"/strategies/{uuid.uuid4()}/versions",
        json={"config": _valid_config_payload(), "source": "manual"},
    )

    assert response.status_code == 404