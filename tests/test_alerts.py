"""The operator is told what needs them, once, and nothing about anyone else.

Three things can go wrong with an alert and each is worse than no alert: it
goes somewhere it should not, it says something it should not, or it says
the same thing until the group mutes it. These tests are about those.
"""
from __future__ import annotations

import asyncio
import contextlib
import io
import json
import os
import re
import threading
import unittest
from unittest.mock import AsyncMock, Mock, patch

from fastapi.testclient import TestClient

from api import alerts, main, runs

KEY = "693a91f6-7c3e-4bc4-97a0-0ec2a1b5c9d7"
ADDRESS = f"https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key={KEY}"
HOUR = 3600.0
FEISHU = f"https://open.feishu.cn/open-apis/bot/v2/hook/{KEY}"
LARK = f"https://open.larksuite.com/open-apis/bot/v2/hook/{KEY}"
SECRET = "demo-signing-secret"
_SETTINGS = ("ALERT_FEISHU_WEBHOOK", "ALERT_FEISHU_SECRET", "ALERT_WECOM_WEBHOOK", "ALERT_REPEAT_HOURS",
             "ALERT_SERVICE_NAME", "RAILWAY_PUBLIC_DOMAIN")


class _Robot:
    """Stands where the vendor's host would, and remembers what it was sent."""

    def __init__(self, status: int = 200, body: bytes = b'{"errcode":0,"errmsg":"ok","code":0,"msg":"success"}',
                 fault: BaseException | None = None):
        self.status, self.body, self.fault = status, body, fault
        self.connections: list[tuple[str, object]] = []
        self.requests: list[tuple[str, str, dict, dict]] = []
        self.closed = 0

    def __call__(self, host, timeout=None):
        self.connections.append((host, timeout))
        return self

    def request(self, method, url, body=None, headers=None):
        if self.fault is not None:
            raise self.fault
        self.requests.append((method, url, json.loads(body.decode("utf-8")), dict(headers or {})))

    def getresponse(self):
        return self

    def read(self, _limit=None):
        return self.body

    def close(self):
        self.closed += 1


class _Case(unittest.TestCase):
    def setUp(self):
        self._saved = {name: os.environ.pop(name, None) for name in _SETTINGS}
        alerts.reset()
        self.said: list[str] = []

    def tearDown(self):
        for name, value in self._saved.items():
            os.environ.pop(name, None)
            if value is not None:
                os.environ[name] = value
        alerts.reset()

    def _on(self, value: str = ADDRESS) -> None:
        os.environ["ALERT_WECOM_WEBHOOK"] = value

    def _on_feishu(self, value: str = FEISHU, secret: str | None = None) -> None:
        os.environ["ALERT_FEISHU_WEBHOOK"] = value
        if secret is not None:
            os.environ["ALERT_FEISHU_SECRET"] = secret

    def _review(self, problems=(), failures=None, *, at: float) -> bool:
        return alerts.review(problems, failures, revision="git:abc1234", now=at, deliver=self.said.append)


class WhereItGoesTests(_Case):
    """The setting supplies a key. It never chooses a destination."""

    def test_the_address_wecom_shows_and_the_key_alone_both_work(self):
        self.assertEqual(alerts.configured(), "off")
        for value in (ADDRESS, f"  {ADDRESS}\n", KEY):
            with self.subTest(value=value):
                self._on(value)
                self.assertEqual(alerts.configured(), "ready")

    def test_anything_that_is_not_wecoms_own_address_is_refused_and_never_contacted(self):
        elsewhere = (
            ADDRESS.replace("https://", "http://"),
            ADDRESS.replace("qyapi.weixin.qq.com", "qyapi.weixin.qq.com.example.org"),
            ADDRESS.replace("qyapi.weixin.qq.com", "qyapi.weixin.qq.com@example.org"),
            ADDRESS.replace("qyapi.weixin.qq.com", "user@qyapi.weixin.qq.com"),
            ADDRESS.replace("qyapi.weixin.qq.com", "qyapi.weixin.qq.com:8443"),
            ADDRESS.replace("/cgi-bin/webhook/send", "/cgi-bin/webhook/upload_media"),
            f"https://hooks.example.org/services?key={KEY}",
            "https://qyapi.weixin.qq.com/cgi-bin/webhook/send",
            ADDRESS + f"&key={KEY}",
            ADDRESS.replace(KEY, "short"),
            ADDRESS.replace(KEY, KEY + "%20x"),
            "https://[not-a-host/cgi-bin/webhook/send?key=" + KEY,
            "too-short",
            KEY + " and more",
        )
        robot = _Robot()
        for value in elsewhere:
            with self.subTest(value=value), patch.object(alerts, "_connect", robot):
                self._on(value)
                self.assertEqual(alerts.configured(), "misconfigured")
                self.assertEqual(alerts.status()["state"], "misconfigured")
                with self.assertRaises(alerts.AlertError) as refused:
                    alerts.send("anything")
                # The value may be most of a real address. It is not repeated.
                self.assertNotIn(KEY, str(refused.exception))
                self.assertFalse(self._review(["maintenance:papers"], at=0))
        self.assertEqual((robot.connections, self.said), ([], []))

    def test_a_message_goes_to_wecoms_host_as_one_text_and_the_connection_is_closed(self):
        robot = _Robot()
        self._on()
        with patch.object(alerts, "_connect", robot):
            alerts.send("备份失败")
        self.assertEqual(robot.connections, [("qyapi.weixin.qq.com", 10)])
        (method, url, body, headers), = robot.requests
        self.assertEqual((method, url), ("POST", f"/cgi-bin/webhook/send?key={KEY}"))
        self.assertEqual(body, {"msgtype": "text", "text": {"content": "备份失败"}})
        self.assertIn("application/json", headers["Content-Type"])
        self.assertEqual(robot.closed, 1)

    def test_only_the_key_is_taken_from_the_setting(self):
        # Whatever else the pasted address carries is not sent on.
        robot = _Robot()
        self._on(ADDRESS + "&debug=1&msgtype=file#fragment")
        with patch.object(alerts, "_connect", robot):
            alerts.send("anything")
        self.assertEqual(robot.requests[0][1], f"/cgi-bin/webhook/send?key={KEY}")

    def test_every_way_delivery_fails_is_said_without_the_key(self):
        failures = (
            (_Robot(status=500), "HTTP 500"),
            (_Robot(status=302), "HTTP 302"),          # a redirect is an answer, not somewhere to go
            (_Robot(body=b'{"errcode":93000,"errmsg":"invalid webhook url ' + KEY.encode() + b'"}'), "errcode 93000"),
            (_Robot(body=b'{"errcode":45009}'), "too often"),
            (_Robot(body=b'{"errcode":"' + KEY.encode() + b'"}'), "unreadable"),
            (_Robot(body=b"<html>" + KEY.encode()), "could not be read"),
            (_Robot(body=b"[]"), "could not be read"),
            (_Robot(fault=OSError(f"no route to /cgi-bin/webhook/send?key={KEY}")), "OSError"),
            (_Robot(fault=TimeoutError()), "TimeoutError"),
        )
        self._on()
        for robot, expected in failures:
            with self.subTest(expected=expected), patch.object(alerts, "_connect", robot):
                with self.assertRaises(alerts.AlertError) as refused:
                    alerts.send("anything")
                self.assertIn(expected, str(refused.exception))
                self.assertNotIn(KEY, str(refused.exception))
                # Nothing chained behind it either: a traceback prints the chain.
                self.assertIsNone(refused.exception.__cause__)
                self.assertTrue(refused.exception.__context__ is None or refused.exception.__suppress_context__)
                self.assertEqual(robot.closed, 1)

    def test_nothing_about_a_delivery_is_logged_or_printed(self):
        self._on()
        out, err = io.StringIO(), io.StringIO()
        with patch.object(alerts, "_connect", _Robot()), self.assertNoLogs(level="DEBUG"), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            alerts.send("anything")
        self.assertEqual((out.getvalue(), err.getvalue()), ("", ""))

    def test_a_long_message_is_cut_to_what_wecom_takes_and_says_so(self):
        robot = _Robot()
        self._on()
        with patch.object(alerts, "_connect", robot):
            alerts.send("告警" * 2000)
        content = robot.requests[0][2]["text"]["content"]
        self.assertLessEqual(len(content.encode("utf-8")), 2048)
        self.assertTrue(content.endswith("已截断）"))
        self.assertNotIn("�", content)


class FeishuTests(_Case):
    """The same promises for the other vendor, and the two things only it has."""

    def test_feishu_and_lark_addresses_work_and_the_message_goes_to_the_host_named(self):
        for address, host in ((FEISHU, "open.feishu.cn"), (LARK, "open.larksuite.com"),
                              (f"  {FEISHU}?from=copy#x\n", "open.feishu.cn")):
            with self.subTest(address=address):
                robot = _Robot()
                self._on_feishu(address)
                self.assertEqual(alerts.configured(), "ready")
                self.assertEqual(alerts.status()["channel"], "feishu")
                with patch.object(alerts, "_connect", robot):
                    alerts.send("备份失败")
                self.assertEqual(robot.connections, [(host, 10)])
                (method, url, body, headers), = robot.requests
                # Only the key is taken from what was pasted.
                self.assertEqual((method, url), ("POST", f"/open-apis/bot/v2/hook/{KEY}"))
                # No signature is sent for a robot that was not given a secret.
                self.assertEqual(body, {"msg_type": "text", "content": {"text": "备份失败"}})
                self.assertIn("application/json", headers["Content-Type"])
                self.assertEqual(robot.closed, 1)

    def test_anything_that_is_not_the_vendors_own_address_is_refused_and_never_contacted(self):
        elsewhere = (
            FEISHU.replace("https://", "http://"),
            FEISHU.replace("open.feishu.cn", "open.feishu.cn.example.org"),
            FEISHU.replace("open.feishu.cn", "open.feishu.cn@example.org"),
            FEISHU.replace("open.feishu.cn", "user@open.feishu.cn"),
            FEISHU.replace("open.feishu.cn", "open.feishu.cn:8443"),
            FEISHU.replace("open.feishu.cn", "feishu.cn"),
            FEISHU.replace("/bot/v2/hook/", "/bot/v2/hooks/"),
            FEISHU.replace("/open-apis/bot/v2/hook/", "/open-apis/im/v1/messages/"),
            FEISHU + "/more",
            FEISHU.replace(KEY, "short"),
            FEISHU.replace(KEY, ""),
            f"https://hooks.example.org/open-apis/bot/v2/hook/{KEY}",
            KEY,              # by itself a key does not say which of the two hosts it is on
            ADDRESS,          # the other vendor's robot, in this vendor's setting
        )
        robot = _Robot()
        for value in elsewhere:
            with self.subTest(value=value), patch.object(alerts, "_connect", robot):
                self._on_feishu(value)
                self.assertEqual(alerts.configured(), "misconfigured")
                self.assertEqual(alerts.status()["channel"], None)
                with self.assertRaises(alerts.AlertError) as refused:
                    alerts.send("anything")
                self.assertNotIn(KEY, str(refused.exception))
                self.assertFalse(self._review(["maintenance:papers"], at=0))
        os.environ.pop("ALERT_FEISHU_WEBHOOK")
        with patch.object(alerts, "_connect", robot):
            self._on(FEISHU)   # and the other way round
            self.assertEqual(alerts.configured(), "misconfigured")
        self.assertEqual((robot.connections, self.said), ([], []))

    def test_two_robots_set_is_refused_and_neither_is_contacted(self):
        # Which group hears about a failure is not left to an order of precedence.
        robot = _Robot()
        self._on()
        self._on_feishu()
        with patch.object(alerts, "_connect", robot):
            self.assertEqual(alerts.configured(), "misconfigured")
            self.assertEqual(alerts.status()["channel"], None)
            with self.assertRaises(alerts.AlertError) as refused:
                alerts.send("anything")
            self.assertIn("exactly one of ALERT_FEISHU_WEBHOOK and ALERT_WECOM_WEBHOOK", str(refused.exception))
            self.assertFalse(self._review(["maintenance:papers"], at=0))
        self.assertEqual(robot.connections, [])
        # Taking one away is enough.
        os.environ.pop("ALERT_WECOM_WEBHOOK")
        self.assertEqual((alerts.configured(), alerts.status()["channel"]), ("ready", "feishu"))

    def test_a_robot_with_signature_verification_gets_feishus_signature(self):
        # The value was computed with openssl, not with the code under test:
        # an HMAC-SHA256 of nothing, keyed with "<seconds>\n<secret>".
        self.assertEqual(alerts._feishu_signature(1599360473, SECRET),
                         "bnV2U4NV6EaiJh72Hk2WwxeDzah+5+dmIJUJ+18wVCQ=")
        robot = _Robot()
        self._on_feishu(secret=f"  {SECRET}\n")
        with patch.object(alerts, "_connect", robot), patch.object(alerts.time, "time", return_value=1599360473.9):
            alerts.send("备份失败")
        (_method, url, body, headers), = robot.requests
        self.assertEqual(body, {"msg_type": "text", "content": {"text": "备份失败"},
                                "timestamp": "1599360473", "sign": "bnV2U4NV6EaiJh72Hk2WwxeDzah+5+dmIJUJ+18wVCQ="})
        # The secret signs. It is never sent.
        self.assertNotIn(SECRET, url + json.dumps(body) + json.dumps(headers))
        # And it means nothing to the other vendor.
        os.environ.pop("ALERT_FEISHU_WEBHOOK")
        self._on()
        wecom = _Robot()
        with patch.object(alerts, "_connect", wecom):
            alerts.send("备份失败")
        self.assertEqual(wecom.requests[0][2], {"msgtype": "text", "text": {"content": "备份失败"}})

    def test_each_refusal_says_what_to_change_and_repeats_nothing_feishu_said(self):
        said = (KEY + " " + SECRET).encode()
        refusals = (
            (200, 19001, "code 19001", "address is not valid"),
            (400, 19001, "code 19001", "address is not valid"),   # the code explains; the status beside it does not
            (200, 19021, "code 19021", "ALERT_FEISHU_SECRET"),
            (200, 19022, "code 19022", "IP allowlist"),
            (200, 19024, "code 19024", "keyword"),
            (200, 9499, "code 9499", "format"),
            (200, 11232, "code 11232", "too often"),
            (200, 12345, "code 12345", "Feishu refused the message (code 12345)."),   # one with no hint is still named
        )
        self._on_feishu(secret=SECRET)
        for status, code, named, hint in refusals:
            robot = _Robot(status=status, body=b'{"code":%d,"msg":"%s","data":{}}' % (code, said))
            with self.subTest(code=code, status=status), patch.object(alerts, "_connect", robot):
                with self.assertRaises(alerts.AlertError) as refused:
                    alerts.send("anything")
                text = str(refused.exception)
                self.assertIn(named, text)
                self.assertIn(hint, text)
                self.assertNotIn(KEY, text)
                self.assertNotIn(SECRET, text)
        for robot, expected in ((_Robot(status=502, body=b"bad gateway"), "Feishu answered HTTP 502."),
                                (_Robot(body=b'{"errcode":0}'), "Feishu's answer could not be read."),
                                (_Robot(body=b'{"code":"' + said + b'"}'), "code unreadable"),
                                (_Robot(body=b'{"code":true}'), "code unreadable"),
                                (_Robot(fault=ConnectionResetError(SECRET)), "Feishu could not be reached (ConnectionResetError).")):
            with self.subTest(expected=expected), patch.object(alerts, "_connect", robot):
                with self.assertRaises(alerts.AlertError) as refused:
                    alerts.send("anything")
                self.assertIn(expected, str(refused.exception))
                self.assertNotIn(KEY, str(refused.exception))
                self.assertNotIn(SECRET, str(refused.exception))

    def test_every_message_contains_the_keywords_the_guide_tells_the_operator_to_use(self):
        # A robot with a keyword check drops a message that lacks the keyword.
        self._on_feishu()
        robot = _Robot()
        with patch.object(alerts, "_connect", robot):
            alerts.review(["maintenance:papers"], now=0)
            alerts.review([], now=30)
            alerts.review([], {"provider_auth": 1}, now=60)
            alerts.review([alerts.LOOP_STOPPED], now=90)
            alerts.main(["test"])
        texts = [request[2]["content"]["text"] for request in robot.requests]
        self.assertEqual(len(texts), 5)
        for text in texts:
            self.assertIn("告警", text)
            self.assertIn("ACA", text)

    def test_a_long_message_is_cut_to_what_feishu_takes(self):
        robot = _Robot()
        self._on_feishu()
        with patch.object(alerts, "_connect", robot):
            alerts.send("告警" * 9000)
        content = robot.requests[0][2]["content"]["text"]
        self.assertLessEqual(len(content.encode("utf-8")), 8000)
        self.assertGreater(len(content.encode("utf-8")), 7900)
        self.assertTrue(content.endswith("已截断）"))


class WhatIsSaidAndHowOftenTests(_Case):
    def test_a_problem_is_said_when_it_starts_again_while_it_lasts_and_once_when_it_ends(self):
        self._on()
        backup = "maintenance:account_backup"
        self.assertTrue(self._review([backup], at=0))
        self.assertIn("新出现的问题", self.said[-1])
        self.assertIn("维护任务 account_backup 失败（账号数据库自动备份）", self.said[-1])
        # The loop asks every half minute. For six hours the answer is nothing.
        for later in (30, HOUR, 6 * HOUR - 1):
            self.assertFalse(self._review([backup], at=later), later)
        self.assertEqual(len(self.said), 1)
        self.assertTrue(self._review([backup], at=6 * HOUR))
        self.assertIn("仍未恢复", self.said[-1])
        self.assertNotIn("新出现的问题", self.said[-1])
        self.assertFalse(self._review([backup], at=6 * HOUR + 30))
        self.assertTrue(self._review([], at=7 * HOUR))
        self.assertIn("已恢复：\n· account_backup", self.said[-1])
        self.assertFalse(self._review([], at=8 * HOUR))
        self.assertEqual(len(self.said), 3)
        # Failing again later is new again.
        self.assertTrue(self._review([backup], at=9 * HOUR))
        self.assertIn("新出现的问题", self.said[-1])

    def test_one_message_carries_everything_that_changed_in_a_cycle(self):
        self._on()
        self._review(["maintenance:papers"], at=0)
        self.assertTrue(self._review(["maintenance:timeouts", "maintenance:somewhere_new"],
                                     {"provider_free_quota": 2}, at=30))
        text = self.said[-1]
        self.assertEqual(len(self.said), 2)
        self.assertIn("维护任务 timeouts 失败（超时看门狗", text)
        self.assertIn("· 维护任务 somewhere_new 失败\n", text)   # a stage with no wording still gets named
        self.assertIn("已恢复：\n· papers", text)
        self.assertIn("· provider_free_quota ×2：部署方所用模型的免费额度已用完", text)
        self.assertIn("版本 git:abc1234", text)
        self.assertTrue(text.startswith("【ACA 告警】\n"))

    def test_the_period_is_a_setting_and_nonsense_is_the_default(self):
        self.assertEqual(alerts.repeat_seconds(), 6 * HOUR)
        for value, seconds in (("1", HOUR), ("0.5", 1800.0), ("48", 48 * HOUR)):
            with patch.dict("os.environ", {"ALERT_REPEAT_HOURS": value}):
                self.assertEqual(alerts.repeat_seconds(), seconds)
        # Never "every cycle": a robot that repeats itself is muted by the people it is for.
        for bad in ("0", "0.01", "-2", "soon", "nan", "inf", ""):
            with self.subTest(bad=bad), patch.dict("os.environ", {"ALERT_REPEAT_HOURS": bad}):
                self.assertEqual(alerts.repeat_seconds(), 6 * HOUR)

    def test_run_failures_are_counted_by_cause_and_each_cause_is_limited(self):
        self._on()
        self.assertTrue(self._review([], {"provider_free_quota": 1}, at=0))
        self.assertIn("provider_free_quota ×1", self.said[-1])
        self.assertIn("运行 ID 在服务日志里", self.said[-1])
        # Every visitor's run fails the same way until the operator acts. One message, not one each.
        for later in range(30, 3000, 30):
            self.assertFalse(self._review([], {"provider_free_quota": 1}, at=later))
        # A different cause is news at once.
        self.assertTrue(self._review([], {"provider_auth": 1}, at=3000))
        self.assertIn("provider_auth ×1：模型服务商拒绝了部署方的密钥", self.said[-1])
        self.assertNotIn("provider_free_quota", self.said[-1])
        # When the period is over, the first cause is said again with what was held back.
        self.assertTrue(self._review([], None, at=6 * HOUR))
        self.assertIn("provider_free_quota ×99", self.said[-1])
        self.assertFalse(self._review([], None, at=13 * HOUR), "nothing new to count is nothing to say")

    def test_nothing_is_marked_said_until_it_was_delivered(self):
        self._on()
        down = Mock(side_effect=alerts.AlertError("WeCom answered HTTP 502."))
        backup, papers = "maintenance:account_backup", "maintenance:papers"
        with self.assertLogs("api.alerts", level="WARNING") as logged:
            for at in (0, 30, 60):
                self.assertFalse(alerts.review([backup, papers], {"provider_auth": 1}, now=at, deliver=down))
        self.assertEqual(down.call_count, 3, "tried again every cycle")
        self.assertEqual(len(logged.records), 1, "and said in the log once, not every half minute")
        self.assertEqual(alerts.status()["state"], "failing")
        self.assertIsNotNone(alerts.status()["last_failed_at"])
        self.assertIsNone(alerts.status()["last_sent_at"])
        # The robot is back. What goes out is what is true now: papers came and went unannounced.
        with self.assertLogs("api.alerts", level="INFO"):
            self.assertTrue(self._review([backup], at=90))
        text = self.said[-1]
        self.assertIn("account_backup", text)
        self.assertNotIn("papers", text)
        self.assertIn("provider_auth ×3", text, "the runs that failed meanwhile were still counted")
        self.assertEqual(alerts.status()["state"], "ready")
        self.assertIsNotNone(alerts.status()["last_sent_at"])

    def test_off_says_nothing_and_remembers_nothing(self):
        self.assertFalse(self._review(["maintenance:timeouts"], {"provider_auth": 4}, at=0))
        self.assertEqual(self.said, [])
        self.assertEqual(alerts.status(),
                         {"state": "off", "channel": None, "last_sent_at": None, "last_failed_at": None})
        # Turned on later in the same process, it starts from nothing held back.
        self._on()
        self.assertFalse(self._review([], None, at=30))

    def test_a_group_that_hears_from_more_than_one_deployment_is_told_which(self):
        self._on()
        with patch.dict("os.environ", {"RAILWAY_PUBLIC_DOMAIN": "aca.example.org"}):
            self._review(["maintenance:papers"], at=0)
            self.assertTrue(self.said[-1].startswith("【ACA 告警】aca.example.org\n"))
            with patch.dict("os.environ", {"ALERT_SERVICE_NAME": "  staging\n copy  "}):
                self._review([], at=30)
                self.assertTrue(self.said[-1].startswith("【ACA 告警】staging copy\n"))

    def test_the_revision_is_short_enough_to_read(self):
        self._on()
        for revision, shown in (("git:7b544ab", "版本 git:7b544ab ·"), ("source:" + "1288ef30f51b" + "d" * 52, "版本 source:1288ef30f51b ·"),
                                ("", "版本 未知 ·"), ("x" * 90, "版本 " + "x" * 20 + " ·")):
            with self.subTest(revision=revision):
                alerts.reset()
                alerts.review(["maintenance:papers"], revision=revision, now=0, deliver=self.said.append)
                self.assertIn(shown, self.said[-1])
                # The whole line, spaces included: it is the one every message ends with.
                self.assertRegex(self.said[-1].splitlines()[-1],
                                 r"^版本 \S+ · \d{4}-\d\d-\d\d \d\d:\d\d UTC · 详情见 /health$")

    def test_every_cause_and_every_fixed_stage_has_its_wording(self):
        # A cause added to the API with no line here would reach the group as a bare code.
        self.assertEqual(set(alerts._FAILURES), set(runs.OPERATOR_FAILURE_CODES))
        self.assertEqual(runs.OPERATOR_FAILURE_CODES, {
            "provider_auth", "provider_free_quota", "provider_billing",
            "provider_model_unavailable", "provider_request_rejected", "provider_output_limit"})
        with TestClient(main.app) as client:
            stages = {name for name in client.get("/health").json()["maintenance"]["checks"]
                      if not name.startswith("source_locator")}
        self.assertEqual(stages, set(alerts._STAGES))

    def test_every_path_a_message_names_is_one_the_service_serves(self):
        # A message sends its reader to a path. One that is not there costs
        # them the minute they have least of.
        served = {route.path for route in main.app.routes}
        said = " ".join([*alerts._STAGES.values(), alerts._named(alerts.LOOP_STOPPED),
                         alerts._compose(["maintenance:papers"], [], [], {"provider_auth": 1}, "git:abc")])
        named = set(re.findall(r"(?<![\w/])/[a-z][a-z/_-]*", said))
        self.assertEqual(named, {"/health", "/health/ready"})
        self.assertLessEqual(named, served)


def _exited(run_id: str, *, byok: bool) -> runs._Handle:
    return runs._Handle(run_id=run_id, topic="a private topic", proc=Mock(poll=Mock(return_value=1)), byok=byok)


class WhichRunsCountTests(_Case):
    """Only the deployment's own trouble is the operator's news."""

    def setUp(self):
        super().setUp()
        self._registry = dict(runs._registry)
        runs._registry.clear()
        runs._settled.clear()

    def tearDown(self):
        runs._registry.clear()
        runs._registry.update(self._registry)
        runs._settled.clear()
        super().tearDown()

    def test_only_deployment_funded_runs_with_an_operators_cause_are_counted(self):
        outcome = {
            "quota-1": {"state": "failed", "error_code": "provider_free_quota"},
            "quota-2": {"state": "failed", "error_code": "provider_free_quota"},
            "auth": {"state": "failed", "error_code": "provider_auth"},
            "fine": {"state": "completed", "error_code": None},
            "thin": {"state": "failed", "error_code": "insufficient_evidence"},   # nobody's key is at fault
            "odd": {"state": "failed", "error_code": "unknown"},
            "theirs": {"state": "failed", "error_code": "provider_auth"},         # their key, their page
        }
        for run_id in outcome:
            runs._registry[run_id] = _exited(run_id, byok=run_id == "theirs")
        runs._registry["gone"] = _exited("gone", byok=False)
        runs._registry["live"] = runs._Handle(run_id="live", topic="t", proc=Mock(poll=Mock(return_value=None)))

        def state(run_id):
            if run_id not in outcome:
                raise runs.RunNotFound(run_id)
            return outcome[run_id]

        asked = Mock(side_effect=state)
        err = io.StringIO()
        with patch.object(runs, "get_state", asked), contextlib.redirect_stderr(err):
            self.assertEqual(runs.drain_operator_failures(), {"provider_free_quota": 2, "provider_auth": 1})
            # Each exit is counted once.
            self.assertEqual(runs.drain_operator_failures(), {})
        self.assertNotIn("theirs", [call.args[0] for call in asked.call_args_list])
        self.assertEqual(list(runs._registry), ["live"])
        # The IDs are for the operator's log. The count that goes to the group has none.
        logged = err.getvalue()
        self.assertEqual(logged.count("on the deployment's keys failed"), 3)
        self.assertIn("run quota-1 on the deployment's keys failed: provider_free_quota", logged)
        self.assertNotIn("a private topic", logged)

    def test_what_is_held_is_bounded_when_nothing_reads_it(self):
        for number in range(400):
            runs._registry[f"r{number}"] = _exited(f"r{number}", byok=False)
            runs.active_count()
        self.assertEqual(len(runs._settled), 256)


class InTheServiceTests(_Case):
    def setUp(self):
        super().setUp()
        saved = (main._maintenance_task, main._maintenance_checks, main._maintenance_timings)
        self.addCleanup(lambda: (setattr(main, "_maintenance_task", saved[0]),
                                 setattr(main, "_maintenance_checks", saved[1]),
                                 setattr(main, "_maintenance_timings", saved[2])))
        main._maintenance_task, main._maintenance_checks, main._maintenance_timings = None, {}, {}

    def _cycles(self, count: int, **replaced):
        """Run the maintenance loop for `count` cycles with every stage stubbed."""
        stages = {"reap": Mock(return_value=[]), "papers": Mock(return_value=[]), **replaced}

        async def exercise():
            with (
                patch.object(main.asyncio, "sleep", AsyncMock(side_effect=[None] * count + [asyncio.CancelledError()])),
                patch.object(runs, "reap_timeouts", stages["reap"]),
                patch.object(main.papers, "prune_old", stages["papers"]),
                patch.object(runs, "prune_expired_runs", return_value=[]),
                patch.object(main, "_prune_receipts", return_value=0),
                patch.object(main.auxiliary_usage, "prune", return_value=0),
                patch.object(main.account_backup, "run_schedule", return_value=0),
                patch.object(main, "_source_locator_stages", return_value=()),
            ):
                with self.assertRaises(asyncio.CancelledError):
                    await main._reaper()
        asyncio.run(exercise())
        return stages

    def test_the_loop_says_what_a_cycle_found_and_says_it_once(self):
        self._on()
        with patch.object(alerts, "send", self.said.append), \
                patch.object(runs, "drain_operator_failures", side_effect=[{"provider_billing": 1}, {}, {}]), \
                self.assertLogs("api.main", level="ERROR"):
            self._cycles(3, papers=Mock(side_effect=PermissionError("/srv/private/path")))
        self.assertEqual(len(self.said), 1, "three cycles, one message")
        text = self.said[0]
        self.assertIn("维护任务 papers 失败（清理过期的上传论文）", text)
        self.assertIn("provider_billing ×1", text)
        self.assertIn(f"版本 {alerts._short(main._PIPELINE_REVISION)} ·", text)
        self.assertNotIn("/srv/private/path", text)

    def test_an_alert_that_goes_wrong_never_costs_the_watchdog_its_loop(self):
        self._on()
        with patch.object(alerts, "review", side_effect=RuntimeError("defect")), \
                patch.object(runs, "drain_operator_failures", return_value={}), \
                self.assertLogs("api.main", level="ERROR") as logged:
            stages = self._cycles(3)
        self.assertEqual(stages["reap"].call_count, 3)
        self.assertEqual(sum("Operator alert review failed" in record.getMessage() for record in logged.records), 3)
        self.assertEqual(main._maintenance_checks["timeouts"], "ok")

    def test_with_no_robot_set_the_loop_does_nothing_new(self):
        with patch.object(alerts, "review") as review, patch.object(runs, "drain_operator_failures") as drain:
            stages = self._cycles(2)
        self.assertEqual((review.call_count, drain.call_count, stages["reap"].call_count), (0, 0, 2))

    def test_the_loop_ending_is_reported_for_it_and_shutdown_is_not(self):
        delivered = threading.Event()

        def take(text):
            self.said.append(text)
            delivered.set()

        async def broken():
            raise RuntimeError("supervisor defect")

        async def forever():
            await asyncio.Event().wait()

        async def lifetime(reaper):
            with patch.object(main, "_reaper", reaper), patch.object(runs, "shutdown_all"):
                async with main._lifespan(main.app):
                    # A stage is failing and the operator has already been told.
                    main._maintenance_checks["papers"] = "failed"
                    alerts.review(["maintenance:papers"], deliver=lambda _text: None)
                    await asyncio.sleep(0.01)

        self._on()
        with patch.object(alerts, "send", take):
            with self.assertLogs("api.main", level="ERROR"):
                asyncio.run(lifetime(broken))
            self.assertTrue(delivered.wait(5))
            self.assertEqual(len(self.said), 1)
            self.assertIn("维护循环已停止", self.said[0])
            self.assertIn("需要重启服务", self.said[0])
            # What was already wrong is not announced as recovered by the loop dying.
            self.assertNotIn("已恢复", self.said[0])
            delivered.clear()
            asyncio.run(lifetime(forever))
            self.assertFalse(delivered.wait(0.3), "an ordinary shutdown is nobody's news")

    def test_health_says_whether_alerts_can_be_sent_and_never_the_address(self):
        with TestClient(main.app) as client:
            self.assertEqual(client.get("/health").json()["alerts"],
                             {"state": "off", "channel": None, "last_sent_at": None, "last_failed_at": None})
            self._on()
            self.assertEqual(client.get("/health").json()["alerts"]["state"], "ready")
            self.assertEqual(client.get("/health").json()["alerts"]["channel"], "wecom")
            self._review(["maintenance:papers"], at=0)
            body = client.get("/health")
            self.assertIsNotNone(body.json()["alerts"]["last_sent_at"])
            self.assertNotIn(KEY, body.text)
            self._on("https://example.org/hook?key=" + KEY)
            with self.assertLogs("api.main", level="WARNING") as logged, TestClient(main.app) as again:
                body = again.get("/health")
            self.assertEqual(body.json()["alerts"]["state"], "misconfigured")
            self.assertIsNone(body.json()["alerts"]["channel"])
            self.assertNotIn(KEY, body.text)
            self.assertNotIn(KEY, " ".join(record.getMessage() for record in logged.records))
            # Advisory: never a reason to be unready. The route is checked to
            # exist, because a path that is not there also has no `alerts` in it.
            ready = client.get("/health/ready")
            self.assertIn("checks", ready.json())
            self.assertNotIn("alerts", ready.json())
            self.assertNotIn(KEY, ready.text)


def _command(*arguments: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = alerts.main(list(arguments))
    return code, out.getvalue(), err.getvalue()


class TestCommandTests(_Case):
    def test_it_sends_one_message_and_says_what_happened(self):
        code, out, err = _command("test")
        self.assertEqual((code, out), (1, ""))
        self.assertIn("neither ALERT_FEISHU_WEBHOOK nor ALERT_WECOM_WEBHOOK is set", err)

        self._on()
        robot = _Robot()
        with patch.object(alerts, "_connect", robot), patch.dict("os.environ", {"ALERT_SERVICE_NAME": "aca"}):
            code, out, err = _command("test")
        self.assertEqual((code, err), (0, ""))
        self.assertIn("Delivered", out)
        self.assertEqual(len(robot.requests), 1)
        self.assertIn("这是一条测试消息", robot.requests[0][2]["text"]["content"])
        self.assertTrue(robot.requests[0][2]["text"]["content"].startswith("【ACA 告警】aca\n"))

        with patch.object(alerts, "_connect", _Robot(body=b'{"errcode":93000}')):
            code, out, err = _command("test")
        self.assertEqual((code, out), (1, ""))
        self.assertIn("Not delivered. WeCom refused the message (errcode 93000).", err)
        self.assertNotIn(KEY, out + err)

        self._on("https://example.org/hook?key=" + KEY)
        code, out, err = _command("test")
        self.assertEqual(code, 1)
        self.assertIn("Set exactly one of ALERT_FEISHU_WEBHOOK and ALERT_WECOM_WEBHOOK", err)
        self.assertNotIn(KEY, out + err)


if __name__ == "__main__":
    unittest.main()
