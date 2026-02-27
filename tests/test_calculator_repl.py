from decimal import Decimal
from unittest.mock import Mock, patch

import pytest

from app.exceptions import OperationError, ValidationError
from app.calculator_repl import calculator_repl


def _run_repl(inputs, calc=None, operation=None):
    calc = calc or Mock()
    operation = operation or Mock()

    with patch("app.calculator_repl.Calculator", return_value=calc), \
         patch("app.calculator_repl.LoggingObserver", return_value=Mock()), \
         patch("app.calculator_repl.AutoSaveObserver", return_value=Mock()), \
         patch("app.calculator_repl.OperationFactory.create_operation", return_value=operation), \
         patch("builtins.input", side_effect=inputs), \
         patch("builtins.print") as mock_print:
        calculator_repl()

    return calc, operation, mock_print


def test_repl_help_and_exit():
    calc, _, mock_print = _run_repl(["help", "exit"])

    calc.save_history.assert_called_once()
    assert any("Available commands" in str(call) for call in mock_print.call_args_list)


def test_repl_exit_when_save_fails():
    calc = Mock()
    calc.save_history.side_effect = Exception("cannot save")

    _, _, mock_print = _run_repl(["exit"], calc=calc)

    assert any("Warning: Could not save history" in str(call) for call in mock_print.call_args_list)


def test_repl_history_empty_and_non_empty():
    calc = Mock()
    calc.show_history.side_effect = [[], ["Addition(2, 3) = 5"]]

    _, _, mock_print = _run_repl(["history", "history", "exit"], calc=calc)

    assert any("No calculations in history" in str(call) for call in mock_print.call_args_list)
    assert any("Calculation History" in str(call) for call in mock_print.call_args_list)


def test_repl_clear_undo_and_redo_paths():
    calc = Mock()
    calc.undo.side_effect = [True, False]
    calc.redo.side_effect = [True, False]

    _, _, mock_print = _run_repl(["clear", "undo", "undo", "redo", "redo", "exit"], calc=calc)

    calc.clear_history.assert_called_once()
    assert any("Operation undone" in str(call) for call in mock_print.call_args_list)
    assert any("Nothing to undo" in str(call) for call in mock_print.call_args_list)
    assert any("Operation redone" in str(call) for call in mock_print.call_args_list)
    assert any("Nothing to redo" in str(call) for call in mock_print.call_args_list)


def test_repl_save_and_load_success_and_failure():
    calc = Mock()
    calc.save_history.side_effect = [None, Exception("save err"), None]
    calc.load_history.side_effect = [None, Exception("load err")]

    _, _, mock_print = _run_repl(["save", "save", "load", "load", "exit"], calc=calc)

    assert any("History saved successfully" in str(call) for call in mock_print.call_args_list)
    assert any("Error saving history" in str(call) for call in mock_print.call_args_list)
    assert any("History loaded successfully" in str(call) for call in mock_print.call_args_list)
    assert any("Error loading history" in str(call) for call in mock_print.call_args_list)


def test_repl_operation_cancel_paths():
    _run_repl(["add", "cancel", "add", "1", "cancel", "exit"])


def test_repl_operation_success_normalizes_decimal():
    calc = Mock()
    calc.perform_operation.return_value = Decimal("2.5000")

    _, operation, mock_print = _run_repl(["add", "2", "4", "exit"], calc=calc)

    calc.set_operation.assert_called_once_with(operation)
    calc.perform_operation.assert_called_once_with("2", "4")
    assert any("Result: 2.5" in str(call) for call in mock_print.call_args_list)


def test_repl_operation_success_non_decimal_result():
    calc = Mock()
    calc.perform_operation.return_value = "done"

    _, operation, mock_print = _run_repl(["add", "2", "4", "exit"], calc=calc)

    calc.set_operation.assert_called_once_with(operation)
    calc.perform_operation.assert_called_once_with("2", "4")
    assert any("Result: done" in str(call) for call in mock_print.call_args_list)


@pytest.mark.parametrize("exc", [ValidationError("bad input"), OperationError("bad op")])
def test_repl_operation_known_errors(exc):
    calc = Mock()
    calc.perform_operation.side_effect = exc

    _, _, mock_print = _run_repl(["add", "2", "4", "exit"], calc=calc)

    assert any("Error:" in str(call) for call in mock_print.call_args_list)


def test_repl_operation_unexpected_error():
    calc = Mock()
    calc.perform_operation.side_effect = RuntimeError("boom")

    _, _, mock_print = _run_repl(["add", "2", "4", "exit"], calc=calc)

    assert any("Unexpected error: boom" in str(call) for call in mock_print.call_args_list)


def test_repl_unknown_command():
    _, _, mock_print = _run_repl(["something", "exit"])
    assert any("Unknown command" in str(call) for call in mock_print.call_args_list)


def test_repl_keyboard_interrupt_recovery():
    _, _, mock_print = _run_repl([KeyboardInterrupt(), "exit"])
    assert any("Operation cancelled" in str(call) for call in mock_print.call_args_list)


def test_repl_eof_exits_loop():
    _, _, mock_print = _run_repl([EOFError()])
    assert any("Input terminated. Exiting" in str(call) for call in mock_print.call_args_list)


def test_repl_inner_generic_exception_recovery():
    _, _, mock_print = _run_repl([Exception("cmd error"), "exit"])
    assert any("Error: cmd error" in str(call) for call in mock_print.call_args_list)


def test_repl_fatal_outer_exception():
    with patch("app.calculator_repl.Calculator", side_effect=Exception("fatal")), \
         patch("app.calculator_repl.logging.error") as mock_log_error, \
         patch("builtins.print") as mock_print:
        with pytest.raises(Exception, match="fatal"):
            calculator_repl()

    mock_log_error.assert_called_once()
    assert any("Fatal error: fatal" in str(call) for call in mock_print.call_args_list)
