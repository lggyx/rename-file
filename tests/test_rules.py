"""规则引擎测试：四类规则 + 大小写敏感 + 边界。"""

import pytest

from rename_file.core.rules import (
    RULE_PREFIX,
    RULE_REGEX,
    RULE_REPLACE,
    RULE_SUFFIX,
    apply_rule,
    normalize_rule,
)


def make_rule(rtype, case_sensitive=True, **params):
    return normalize_rule(rtype, params, case_sensitive)


def test_prefix():
    assert apply_rule("a.txt", make_rule(RULE_PREFIX, text="[2026] ")) == "[2026] a.txt"


def test_suffix_inserts_before_ext():
    assert apply_rule("a.txt", make_rule(RULE_SUFFIX, text="_new")) == "a_new.txt"
    assert apply_rule("noext", make_rule(RULE_SUFFIX, text="_new")) == "noext_new"


def test_replace_case_sensitive():
    rule = make_rule(RULE_REPLACE, find="IMG", replace="PIC")
    assert apply_rule("IMG_01.jpg", rule) == "PIC_01.jpg"
    assert apply_rule("img_01.jpg", rule) == "img_01.jpg"


def test_replace_case_insensitive():
    rule = make_rule(RULE_REPLACE, find="img", replace="PIC", case_sensitive=False)
    assert apply_rule("IMG_01.jpg", rule) == "PIC_01.jpg"
    # 字面量替换，不解释正则元字符："." 只匹配点号本身，不匹配任意字符
    dot_rule = make_rule(RULE_REPLACE, find="a.b", replace="X", case_sensitive=False)
    assert apply_rule("axb.txt", dot_rule) == "axb.txt"  # 通配符语义会误伤 axb
    assert apply_rule("a.B.txt", dot_rule) == "X.txt"


def test_replace_empty_find_returns_original():
    assert apply_rule("a.txt", make_rule(RULE_REPLACE, find="", replace="x")) == "a.txt"


def test_regex_with_groups():
    rule = make_rule(RULE_REGEX, find=r"^IMG_(\d+)", replace=r"2023_\1")
    assert apply_rule("IMG_0001.jpg", rule) == "2023_0001.jpg"


def test_regex_case_insensitive():
    rule = make_rule(RULE_REGEX, find=r"^img", replace="pic", case_sensitive=False)
    assert apply_rule("IMG_01.jpg", rule) == "pic_01.jpg"


def test_regex_invalid_returns_original():
    rule = make_rule(RULE_REGEX, find="([", replace="x")
    assert apply_rule("a.txt", rule) == "a.txt"


def test_normalize_rule_rejects_unknown_type():
    with pytest.raises(ValueError):
        normalize_rule("nope")
