"""Tests for parameter expansion."""

from torcpy.client.parameter_expansion import (
    ParameterValue,
    expand_parameters,
    substitute_template,
)


def test_parse_integer_range():
    pv = ParameterValue.parse("i", "1:5")
    assert pv.values == [1, 2, 3, 4, 5]


def test_parse_integer_range_with_step():
    pv = ParameterValue.parse("i", "0:10:3")
    assert pv.values == [0, 3, 6, 9]


def test_parse_float_range():
    pv = ParameterValue.parse("lr", "0.0:0.3:0.1")
    assert len(pv.values) == 4
    assert abs(pv.values[0] - 0.0) < 0.001
    assert abs(pv.values[1] - 0.1) < 0.001


def test_parse_list_integers():
    pv = ParameterValue.parse("batch", "[1,5,10]")
    assert pv.values == [1, 5, 10]


def test_parse_list_strings():
    pv = ParameterValue.parse("split", "['train','test','val']")
    assert pv.values == ["train", "test", "val"]


def test_substitute_simple():
    result = substitute_template("job_{i}", {"i": 5})
    assert result == "job_5"


def test_substitute_with_format():
    result = substitute_template("job_{i:03d}", {"i": 5})
    assert result == "job_005"


def test_substitute_float_format():
    result = substitute_template("lr_{lr:.4f}", {"lr": 0.001})
    assert result == "lr_0.0010"


def test_expand_cartesian():
    params = {"x": "[1,2]", "y": "[a,b]"}
    combos = expand_parameters(params)
    assert len(combos) == 4


def test_expand_zip():
    params = {"x": "[1,2,3]", "y": "[a,b,c]"}
    combos = expand_parameters(params, mode="zip")
    assert len(combos) == 3
    assert combos[0] == {"x": 1, "y": "a"}


def test_expand_empty():
    assert expand_parameters({}) == [{}]
