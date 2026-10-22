"""One invention under several publication numbers reads as one; distinct inventions stay apart."""

from __future__ import annotations

import pytest

from academic_agent.patent_family import publication_number, same_invention, title_key, titles_match

G = "https://patents.google.com/patent/{}/en"


@pytest.mark.parametrize("url,expected", [
    ("https://patents.google.com/patent/US9422922B2/en", "US9422922B2"),
    ("https://patents.google.com/patent/AU2022387053A1/enAug", "AU2022387053A1"),
    ("https://patents.google.com/patent/CN202710634U", "CN202710634U"),
    ("https://patentscope.wipo.int/search/en/WO2011032127", "WO2011032127"),
    ("https://patentscope.wipo.int/search/en/detail.jsf?docId=WO2023064214&_cid=P1", "WO2023064214"),
    ("https://patentscope.wipo.int/search/en/detail.jsf?docId=CN370180949", None),
    ("https://patents.justia.com/patent/20100224696", "US20100224696"),
    ("https://patents.justia.com/assignee/azur-space-solar-power-gmbh", None),
    ("https://patents.google.com/?q=fusion", None),
    (None, None),
])
def test_publication_numbers_come_from_the_url(url, expected):
    assert publication_number(url) == expected


def test_title_keys_drop_numbers_and_the_site_name_even_when_cut_off():
    assert title_key("US9422922B2 - Systems for production of electricity - Google Patents") == (
        "systems for production of electricity", False)
    assert title_key("AU2022387053A1 - Treatment of depression with psilocybin - G")[0] == (
        "treatment of depression with psilocybin")
    assert title_key("High-voltage dc voltage divider - CN202710634U")[0] == "high voltage dc voltage divider"
    assert title_key("Underground modular high-voltage direct current electric ...") == (
        "underground modular high voltage direct current electric", True)


def test_a_cut_off_title_matches_the_start_of_the_full_one_only_when_long_enough():
    assert titles_match("Underground modular high-voltage direct current electric ...",
                        "underground modular high-voltage direct current electric power ...")
    assert not titles_match("Vertical farming systems ...", "Vertical farming systems and methods")
    assert not titles_match("Underground modular high-voltage direct current electric",
                            "Underground modular high-voltage direct current electric power")


def test_one_invention_across_offices_and_from_application_to_grant_is_one():
    title = "{} - Treatment of treatment resistant depression with psilocybin - Google Patents"
    for other in ("EP4429671A1", "US20250000881A1", "CA3237885A1"):
        assert same_invention(title.format("AU2022387053A1"), G.format("AU2022387053A1"),
                              title.format(other), G.format(other))
    assert same_invention("US20190307077A1 - Automated vertical farming system using mobile robots",
                          G.format("US20190307077A1"),
                          "US11778956B2 - Automated vertical farming system using mobile robots",
                          G.format("US11778956B2"))


def test_the_same_publication_on_two_hosts_is_one_whatever_the_titles():
    assert same_invention("WO2020041762A1 - Mobile and modular cultivation systems - Google Patents",
                          G.format("WO2020041762A1"), "MOBILE AND MODULAR CULTIVATION SYSTEMS FOR VERTICAL ...",
                          "https://patentscope.wipo.int/search/en/WO2020041762")
    assert same_invention("Weather management using space based power system", G.format("US20100224696A1"),
                          "Patent US20100224696: weather management", "https://patents.justia.com/patent/20100224696")


def test_same_kind_publications_from_one_office_stay_apart_even_with_one_title():
    title = "{} - A centralized quantum key relay network and key distribution method - Google Patents"
    assert not same_invention(title.format("CN120811600B"), G.format("CN120811600B"),
                              title.format("CN119766443B"), G.format("CN119766443B"))
    assert not same_invention("US20220400623A1 - Vertical farming systems and methods", G.format("US20220400623A1"),
                              "US20190159415A1 - Vertical farming systems and methods", G.format("US20190159415A1"))


def test_different_titles_or_unknown_numbers_are_never_merged():
    assert not same_invention("US9511881B1 - Dispersed space based laser weapon", G.format("US9511881B1"),
                              "EP1234567A1 - Solar powered space weapon", G.format("EP1234567A1"))
    assert not same_invention("Vertical farming systems and methods", "https://patents.justia.com/assignee/x",
                              "Vertical farming systems and methods", G.format("EP4104673A1"))
