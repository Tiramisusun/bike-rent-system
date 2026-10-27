import pytest

from src.agent.evaluation import cost_usd, results_match


def test_identical_results_match():
    assert results_match([[115]], [[115]])


def test_extra_columns_are_allowed():
    assert results_match([["GOLDEN LANE"]], [["GOLDEN LANE", 0.7065]])


def test_column_order_does_not_matter():
    assert results_match([["inner", 72], ["outer", 9]], [[9, "outer"], [72, "inner"]])


def test_row_order_ignored_unless_ranked():
    gold = [["A"], ["B"], ["C"]]
    assert results_match(gold, [["C"], ["A"], ["B"]])
    assert not results_match(gold, [["C"], ["A"], ["B"]], order_matters=True)
    assert results_match(gold, [["A"], ["B"], ["C"]], order_matters=True)


def test_numbers_match_within_one_percent():
    assert results_match([[31.973913]], [[31.97]])
    assert results_match([[31.973913]], [["32.0"]])          # numeric string, rounded
    assert not results_match([[31.97]], [[35.0]])


def test_ratio_may_be_given_as_percentage():
    assert results_match([[0.1426]], [[14.26]])
    assert results_match([[66.90]], [[0.669]])


def test_wrong_row_count_fails():
    assert not results_match([["GOLDEN LANE"]], [["GOLDEN LANE"], ["HERBERT STREET"]])
    assert not results_match([[1]], [])


def test_missing_or_wrong_gold_column_fails():
    assert not results_match([["inner", 72]], [["inner"]])
    assert not results_match([["inner", 72]], [["inner", 71]])


def test_case_and_whitespace_insensitive_strings():
    assert results_match([["SMITHFIELD NORTH"]], [[" smithfield north "]])


def test_booleans_and_nulls():
    assert results_match([[True, 5.2], [False, 7.1]], [[1, 5.2], [0, 7.1]])
    assert results_match([[None]], [[None]])


def test_empty_results_match():
    assert results_match([], [])


# ── Cost per question ─────────────────────────────────────────────────────────


def test_cost_charges_cached_tokens_at_the_cache_price():
    price = {"input": 1.0, "cached_input": 0.1, "output": 5.0}
    # 1,000 uncached + 3,000 cached prompt tokens, 200 output tokens
    assert cost_usd(4000, 3000, 200, price) == pytest.approx((1000 * 1.0 + 3000 * 0.1 + 200 * 5.0) / 1e6)


def test_unpublished_cache_price_falls_back_to_full_input_price():
    price = {"input": 1.0, "cached_input": None, "output": 5.0}
    assert cost_usd(4000, 3000, 0, price) == pytest.approx(4000 / 1e6)
