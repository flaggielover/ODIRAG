from __future__ import annotations

import pytest
from bs4 import BeautifulSoup, Tag

from app.services.source_discovery import (
    _classify_topic_relevance,
    _is_jxt_detail_url,
    _is_jxt_list_url,
    _tag_text_value,
    _topic_matches,
)

SOFTWARE_TOPIC = "四川省软件产业政策"


@pytest.mark.parametrize(
    ("title", "body", "expected"),
    [
        ("软件企业税收优惠政策核查结果公示", "软件与信息服务业处组织核查。", "DIRECT"),
        ("关于组织申报工业软件研发项目的通知", "支持工业软件创新发展。", "DIRECT"),
        ("软件首版次推广应用指导目录公示", "目录支持软件首版次推广。", "DIRECT"),
        ("产业发展说明", "我省软件和信息技术服务业发展规划提出支持措施。", "RELATED"),
        ("数字经济新闻发布会", "介绍数字化转型和工业互联网进展。", "WEAK"),
        ("移动通信基站许可系统支撑服务采购公告", "四川省经济和信息化厅采购服务。", "UNRELATED"),
        ("政务软件服务采购项目公告", "供应商应提交投标材料。", "UNRELATED"),
        ("四川省软件产业政策新闻发布会", "会议介绍政策背景。", "WEAK"),
        ("厅工作动态：召开专题会议", "会议学习四川省软件产业政策。", "WEAK"),
        ("四川省绿色制造政策", "推进绿色工厂和节能降碳。", "UNRELATED"),
    ],
)
def test_software_topic_relevance_levels(title: str, body: str, expected: str) -> None:
    assert _classify_topic_relevance(title, body, SOFTWARE_TOPIC).level == expected


def test_software_topic_accepts_only_direct_or_related() -> None:
    assert _topic_matches(
        "软件和信息技术服务业发展规划提出支持措施。",
        SOFTWARE_TOPIC,
        title="产业发展说明",
    )
    assert not _topic_matches(
        "介绍数字经济和数字化转型进展。",
        SOFTWARE_TOPIC,
        title="新闻发布会",
    )


@pytest.mark.parametrize(
    "url",
    [
        "https://jxt.sc.gov.cn/scjxt/wjfb/common_list.shtml",
        "https://jxt.sc.gov.cn/scjxt/xwzx/news.shtml",
        "https://jxt.sc.gov.cn/scjxt/xzgfxwj/zcgfxwj_list.shtml",
        "https://jxt.sc.gov.cn/scjxt/zcjdn/common_listnb.shtml",
        "https://jxt.sc.gov.cn/scjxt/ggtz/common_list.shtml",
    ],
)
def test_jxt_list_url_patterns(url: str) -> None:
    assert _is_jxt_list_url(url)
    assert not _is_jxt_detail_url(url)


def test_jxt_detail_and_homepage_are_not_columns() -> None:
    detail = "https://jxt.sc.gov.cn/scjxt/ggtz/2026/8/10/fc4f8fb462504ef883ec09a03fba5916.shtml"
    assert _is_jxt_detail_url(detail)
    assert not _is_jxt_list_url(detail)
    assert not _is_jxt_list_url("https://jxt.sc.gov.cn/scjxt/index.shtml")


def test_generic_topic_matching_contract_is_preserved() -> None:
    assert _topic_matches("Official support policy details", "support")
    assert not _topic_matches("Office contact directory", "support")


def test_jxt_meta_title_uses_content_attribute() -> None:
    soup = BeautifulSoup(
        '<meta name="ArticleTitle" content="软件首版次推广应用目录公示">',
        "lxml",
    )
    node = soup.select_one("meta[name='ArticleTitle']")
    assert isinstance(node, Tag)
    assert _tag_text_value(node) == "软件首版次推广应用目录公示"
