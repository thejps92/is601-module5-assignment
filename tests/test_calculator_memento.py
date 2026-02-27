from datetime import datetime
from decimal import Decimal

from app.calculation import Calculation
from app.calculator_memento import CalculatorMemento


def test_memento_to_dict():
    calc = Calculation(operation="Addition", operand1=Decimal("2"), operand2=Decimal("3"))
    memento = CalculatorMemento(history=[calc], timestamp=datetime.now())

    data = memento.to_dict()

    assert "history" in data
    assert "timestamp" in data
    assert len(data["history"]) == 1
    assert data["history"][0]["operation"] == "Addition"


def test_memento_from_dict():
    timestamp = datetime.now().isoformat()
    data = {
        "history": [
            {
                "operation": "Addition",
                "operand1": "2",
                "operand2": "3",
                "result": "5",
                "timestamp": timestamp,
            }
        ],
        "timestamp": timestamp,
    }

    memento = CalculatorMemento.from_dict(data)

    assert len(memento.history) == 1
    assert memento.history[0].operation == "Addition"
    assert memento.history[0].result == Decimal("5")
