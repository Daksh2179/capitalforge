"""Integration tests for the strategy API: create, retrieve, and version."""

import uuid

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.strategy import StrategyVersion


def _valid_config_payload() -> dict:
    return {
        "schema_version": 1,
        "symbol": "AAPL",
        "conditions": {
            "operator": "AND",
            "rules": [
                {"indicator": "RSI", "period": 14, "operator": "less_than", "value": 30},
                {"indicator": "SMA", "period": 200, "operator": "price_above"},
            ],
        },
        "position_sizing": {"type": "fixed_allocation", "value_pct": 5},
        "exit": {"stop_loss_pct": 3, "take_profit_pct": None},
    }


def test_create_strategy_returns_created_strategy(client: TestClient):
    user_id = str(uuid.uuid4())

    response = client.post(
        "/strategies",
        json={
            "user_id": user_id,
            "config": _valid_config_payload(),
            "source": "manual",
        },
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
        json={
            "user_id": user_id,
            "config": _valid_config_payload(),
            "source": "manual",
        },
    )
    strategy_id = response.json()["id"]

    version = (
        db_session.query(StrategyVersion)
        .filter(StrategyVersion.strategy_id == uuid.UUID(strategy_id))
        .one()
    )
    assert version.version_number == 1
    assert version.config_json["symbol"] == "AAPL"


def test_get_strategy_returns_existing_strategy(client: TestClient):
    user_id = str(uuid.uuid4())
    create_response = client.post(
        "/strategies",
        json={
            "user_id": user_id,
            "config": _valid_config_payload(),
            "source": "manual",
        },
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
        json={
            "user_id": user_id,
            "config": _valid_config_payload(),
            "source": "manual",
        },
    )
    strategy_id = create_response.json()["id"]
    first_version_id = create_response.json()["current_version_id"]

    new_config = _valid_config_payload()
    new_config["position_sizing"]["value_pct"] = 10  # a real change from version 1

    version_response = client.post(
        f"/strategies/{strategy_id}/versions",
        json={"config": new_config, "source": "manual"},
    )

    assert version_response.status_code == 201
    new_version_body = version_response.json()
    assert new_version_body["version_number"] == 2
    assert new_version_body["id"] != first_version_id

    # The strategy's current_version_id must now point at the new version.
    strategy_response = client.get(f"/strategies/{strategy_id}")
    assert strategy_response.json()["current_version_id"] == new_version_body["id"]

    # The original version row must be completely untouched.
    old_version = db_session.get(StrategyVersion, uuid.UUID(first_version_id))
    assert old_version is not None
    assert old_version.version_number == 1
    assert old_version.config_json["position_sizing"]["value_pct"] == 5


def test_create_version_for_unknown_strategy_returns_404(client: TestClient):
    response = client.post(
        f"/strategies/{uuid.uuid4()}/versions",
        json={"config": _valid_config_payload(), "source": "manual"},
    )

    assert response.status_code == 404