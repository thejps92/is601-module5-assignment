import datetime
from pathlib import Path
import pandas as pd
import pytest
import logging
from unittest.mock import Mock, patch, PropertyMock
from decimal import Decimal
from tempfile import TemporaryDirectory
from app.calculator import Calculator
from app.calculator_repl import calculator_repl
from app.calculator_config import CalculatorConfig
from app.exceptions import OperationError, ValidationError
from app.history import LoggingObserver, AutoSaveObserver
from app.operations import OperationFactory

@pytest.fixture
def calculator():
    with TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        config = CalculatorConfig(base_dir=tmp_path)

        with patch.object(CalculatorConfig, 'log_dir', new_callable=PropertyMock) as mock_log_dir, \
             patch.object(CalculatorConfig, 'log_file', new_callable=PropertyMock) as mock_log_file, \
             patch.object(CalculatorConfig, 'history_dir', new_callable=PropertyMock) as mock_history_dir, \
             patch.object(CalculatorConfig, 'history_file', new_callable=PropertyMock) as mock_history_file:

            mock_log_dir.return_value = tmp_path / "logs"
            mock_log_file.return_value = tmp_path / "logs/calculator.log"
            mock_history_dir.return_value = tmp_path / "history"
            mock_history_file.return_value = tmp_path / "history/calculator_history.csv"

            calc = Calculator(config=config)

            # Clear any auto-added calculations or stacks
            calc.history.clear()  # pragma: no cover
            calc.undo_stack.clear()  # pragma: no cover
            calc.redo_stack.clear()  # pragma: no cover

            yield calc

        for handler in logging.root.handlers[:]:  # pragma: no cover
            handler.close()
            logging.root.removeHandler(handler)


def test_calculator_initialization(calculator):
    assert calculator.history == []
    assert calculator.undo_stack == []
    assert calculator.redo_stack == []
    assert calculator.operation_strategy is None

def test_add_observer(calculator):
    observer = LoggingObserver()
    calculator.add_observer(observer)
    assert observer in calculator.observers

def test_remove_observer(calculator):
    observer = LoggingObserver()
    calculator.add_observer(observer)
    calculator.remove_observer(observer)
    assert observer not in calculator.observers

def test_set_operation(calculator):
    operation = OperationFactory.create_operation('add')
    calculator.set_operation(operation)
    assert calculator.operation_strategy == operation

def test_perform_operation_addition(calculator):
    operation = OperationFactory.create_operation('add')
    calculator.set_operation(operation)
    result = calculator.perform_operation(2, 3)
    assert result == Decimal('5')

def test_perform_operation_validation_error(calculator):
    calculator.set_operation(OperationFactory.create_operation('add'))
    with pytest.raises(ValidationError):
        calculator.perform_operation('invalid', 3)

def test_perform_operation_operation_error(calculator):
    with pytest.raises(OperationError, match="No operation set"):
        calculator.perform_operation(2, 3)

def test_undo(calculator):
    operation = OperationFactory.create_operation('add')
    calculator.set_operation(operation)
    calculator.perform_operation(2, 3)
    calculator.undo()
    assert calculator.history == []

def test_redo(calculator):
    operation = OperationFactory.create_operation('add')
    calculator.set_operation(operation)
    calculator.perform_operation(2, 3)
    calculator.undo()
    calculator.redo()
    assert len(calculator.history) == 1

@patch('app.calculator.pd.DataFrame.to_csv')
def test_save_history(mock_to_csv, calculator):
    operation = OperationFactory.create_operation('add')
    calculator.set_operation(operation)
    calculator.perform_operation(2, 3)
    calculator.save_history()
    mock_to_csv.assert_called_once()

@patch('app.calculator.pd.read_csv')
@patch('app.calculator.Path.exists', return_value=True)
def test_load_history(mock_exists, mock_read_csv, calculator):
    import datetime
    import pandas as pd
    from app.calculation import Calculation

    mock_read_csv.return_value = pd.DataFrame({
        'operation': ['Addition'],
        'operand1': ['2'],
        'operand2': ['3'],
        'result': ['5'],
        'timestamp': [datetime.datetime.now().isoformat()]
    })

    try:
        calculator.load_history()
        assert len(calculator.history) == 1
        assert calculator.history[0].operation == "Addition"
        assert calculator.history[0].operand1 == Decimal("2")
        assert calculator.history[0].operand2 == Decimal("3")
        assert calculator.history[0].result == Decimal("5")
    except OperationError:
        pytest.fail("Loading history failed due to OperationError")

def test_clear_history(calculator):
    operation = OperationFactory.create_operation('add')
    calculator.set_operation(operation)
    calculator.perform_operation(2, 3)
    calculator.clear_history()
    assert calculator.history == []
    assert calculator.undo_stack == []
    assert calculator.redo_stack == []


def test_calculator_initialization_without_explicit_config():
    with patch.object(Calculator, 'load_history', return_value=None):
        calc = Calculator(config=None)
        assert calc.config is not None


def test_calculator_initialization_load_history_warning():
    with patch.object(Calculator, 'load_history', side_effect=Exception("load failed")), \
         patch('app.calculator.logging.warning') as mock_warning:
        Calculator(config=None)
        mock_warning.assert_called_once()


def test_setup_logging_exception_path(calculator):
    with patch('app.calculator.logging.basicConfig', side_effect=Exception("log setup failed")):
        with pytest.raises(Exception, match="log setup failed"):
            calculator._setup_logging()


def test_notify_observers_calls_update(calculator):
    observer = Mock()
    calculation = Mock()
    calculator.add_observer(observer)
    calculator.notify_observers(calculation)
    observer.update.assert_called_once_with(calculation)


def test_perform_operation_trims_history_when_exceeding_max_size(calculator):
    calculator.config.max_history_size = 1
    calculator.set_operation(OperationFactory.create_operation('add'))
    calculator.perform_operation(1, 1)
    calculator.perform_operation(2, 2)
    assert len(calculator.history) == 1
    assert calculator.history[0].operand1 == Decimal('2')


def test_perform_operation_wraps_generic_exception(calculator):
    calculator.set_operation(OperationFactory.create_operation('add'))
    with patch.object(calculator.operation_strategy, 'execute', side_effect=RuntimeError("boom")):
        with pytest.raises(OperationError, match="Operation failed: boom"):
            calculator.perform_operation(2, 3)


def test_save_history_empty(calculator):
    calculator.clear_history()
    calculator.save_history()
    assert calculator.config.history_file.exists()


def test_save_history_error(calculator):
    calculator.set_operation(OperationFactory.create_operation('add'))
    calculator.perform_operation(2, 3)
    with patch('app.calculator.pd.DataFrame.to_csv', side_effect=Exception('write failed')):
        with pytest.raises(OperationError, match='Failed to save history'):
            calculator.save_history()


@patch('app.calculator.pd.read_csv', return_value=pd.DataFrame())
def test_load_history_empty_file(mock_read_csv, calculator):
    calculator.save_history()
    calculator.load_history()
    assert calculator.history == []


def test_load_history_no_file(calculator):
    if calculator.config.history_file.exists():
        calculator.config.history_file.unlink()
    calculator.load_history()
    assert calculator.history == []


@patch('app.calculator.pd.read_csv', side_effect=Exception('read failed'))
def test_load_history_error(mock_read_csv, calculator):
    calculator.save_history()
    with pytest.raises(OperationError, match='Failed to load history'):
        calculator.load_history()


def test_get_history_dataframe_and_show_history(calculator):
    calculator.set_operation(OperationFactory.create_operation('add'))
    calculator.perform_operation(2, 3)
    df = calculator.get_history_dataframe()
    assert list(df.columns) == ['operation', 'operand1', 'operand2', 'result', 'timestamp']
    shown = calculator.show_history()
    assert shown == ['Addition(2, 3) = 5']


def test_undo_when_stack_empty_returns_false(calculator):
    assert calculator.undo() is False


def test_redo_when_stack_empty_returns_false(calculator):
    assert calculator.redo() is False