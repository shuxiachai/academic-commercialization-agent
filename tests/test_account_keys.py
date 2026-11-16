"""An account's API keys are saved with the account, sealed, and used for its runs.

Until 2026-11-15 an account's keys lived in the browser alone: first in the
open tab, then (#407, #408) optionally in that browser's local storage. Either
way the keys belonged to a browser, not to the account, so a different
browser, a signed-out session or a cleared profile asked for them again, and
the owner's report after both changes was that the form "still pops up every
time". An account is where a person expects their settings to be.

The keys are now saved to the account on the server:

- sealed at rest: the account database holds one opaque token per account
  and nothing readable, not the provider, the model or the last characters;
  the secret that opens it is not in the database and not in its backups;
- used by the server for that account's paid operations when the request
  brings no keys of its own, exactly as if the request had carried them;
- never sent back: the page is told that keys are saved, which provider and
  model, and the last four characters of each key, so a person can tell
  which key it is;
- the account's alone: removed with the account, and by the account at will.

A request that brings its own keys still runs on those, and stores nothing:
that is the "this tab only" choice the key form keeps.
"""

from __future__ import annotations

import os
import sqlite3
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from academic_agent.language import TopicSearchPlan
from fastapi.testclient import TestClient

from api import access, account_keys, accounts, papers, plan_preview, runs
from api.main import app
from tests.test_api_accounts import PASSWORD, _AccountsHttp

LLM_KEY = "sk-fixture-model-key-0123456789abcd"
SEARCH_KEY = "tvly-fixture-search-key-9876wxyz"
OTHER_LLM_KEY = "sk-fixture-second-model-key-55556666"
OTHER_SEARCH_KEY = "fixture-serper-key-000011112222"
KEYS = {"llm_provider": "deepseek", "llm_api_key": LLM_KEY, "llm_model": "deepseek-chat", "tavily_api_key": SEARCH_KEY}
OTHER_KEYS = {"llm_provider": "qwen", "llm_api_key": OTHER_LLM_KEY, "llm_model": "qwen3.8-27b",
              "serper_api_key": OTHER_SEARCH_KEY}
SECRETS = (LLM_KEY, SEARCH_KEY, OTHER_LLM_KEY, OTHER_SEARCH_KEY)
TOPIC = {"topic": "a valid research topic"}
RUN = ("20261115T000000Z-0123456789abcdef0123456789abcdef", Path("."))


class _Keys(_AccountsHttp):
    def setUp(self):
        super().setUp()
        for name in ("ACCOUNT_KEYS_SECRET", "ACCESS_CODE", "ACCESS_CODES"):
            os.environ.pop(name, None)
        account_keys._forget_secret()
        self.addCleanup(account_keys._forget_secret)
        self.session = self._signup()
        self.headers = self._bearer(self.session["token"])
        self.user = accounts.session_user(self.session["token"])

    def _database_text(self) -> bytes:
        """Every byte the account store holds, the journal and the secret's neighbours included."""
        root = Path(os.environ["ACCOUNTS_DB"]).parent
        return b"".join(path.read_bytes() for path in sorted(root.iterdir())
                        if path.is_file() and not path.name.endswith(account_keys.SECRET_SUFFIX))

    def _save(self, keys=KEYS, headers=None):
        response = self.client.put("/api/auth/keys", json=keys, headers=headers or self.headers)
        self.assertEqual(response.status_code, 200, response.text)
        return response


class StorageTests(_Keys):
    def test_saved_keys_come_back_whole_and_the_database_holds_nothing_readable(self):
        saved = account_keys.save(self.user, provider="deepseek", model="deepseek-chat", llm_api_key=LLM_KEY,
                                  search="tavily", search_api_key=SEARCH_KEY, now=1_800_000_000)
        loaded = account_keys.load(self.user)
        self.assertEqual(loaded, saved)
        self.assertEqual((loaded.provider, loaded.model, loaded.llm_api_key, loaded.search, loaded.search_api_key,
                          loaded.updated_at),
                         ("deepseek", "deepseek-chat", LLM_KEY, "tavily", SEARCH_KEY, 1_800_000_000))
        self.assertEqual(loaded.request_fields(), KEYS)
        stored = self._database_text()
        for readable in (LLM_KEY, SEARCH_KEY, LLM_KEY[-4:], SEARCH_KEY[-4:], "deepseek-chat", "tavily"):
            self.assertNotIn(readable.encode(), stored, readable)
        with closing(sqlite3.connect(os.environ["ACCOUNTS_DB"])) as db, db:
            columns = [row[1] for row in db.execute("PRAGMA table_info(account_keys)")]
            rows = db.execute("SELECT user_id, sealed, updated_at FROM account_keys").fetchall()
        self.assertEqual(columns, ["user_id", "sealed", "updated_at"])
        self.assertEqual([(row[0], row[2]) for row in rows], [(self.user.id, 1_800_000_000)])

    def test_serper_keys_and_a_second_save_replace_the_first(self):
        account_keys.save(self.user, provider="deepseek", model="deepseek-chat", llm_api_key=LLM_KEY,
                          search="tavily", search_api_key=SEARCH_KEY)
        first = self._database_text()
        account_keys.save(self.user, provider="qwen", model="qwen3.8-27b", llm_api_key=OTHER_LLM_KEY,
                          search="serper", search_api_key=OTHER_SEARCH_KEY)
        self.assertEqual(account_keys.load(self.user).request_fields(), OTHER_KEYS)
        with closing(sqlite3.connect(os.environ["ACCOUNTS_DB"])) as db, db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM account_keys").fetchone()[0], 1)
        # The same keys sealed twice do not look alike: nothing can be told from two rows matching.
        account_keys.save(self.user, provider="qwen", model="qwen3.8-27b", llm_api_key=OTHER_LLM_KEY,
                          search="serper", search_api_key=OTHER_SEARCH_KEY)
        self.assertNotEqual(first, self._database_text())

    def test_each_account_has_its_own_and_removal_is_the_accounts(self):
        bob = accounts.session_user(self._signup("bob@example.com")["token"])
        self.assertIsNone(account_keys.load(bob))
        account_keys.save(self.user, provider="deepseek", model="deepseek-chat", llm_api_key=LLM_KEY,
                          search="tavily", search_api_key=SEARCH_KEY)
        self.assertIsNone(account_keys.load(bob), "One account's keys are not another's")
        self.assertFalse(account_keys.remove(bob), "Nothing to remove")
        self.assertIsNotNone(account_keys.load(self.user))
        self.assertTrue(account_keys.remove(self.user))
        self.assertIsNone(account_keys.load(self.user))

    def test_deleting_the_account_takes_its_keys_with_it(self):
        account_keys.save(self.user, provider="deepseek", model="deepseek-chat", llm_api_key=LLM_KEY,
                          search="tavily", search_api_key=SEARCH_KEY)
        accounts.delete_account(self.user, PASSWORD)
        with closing(sqlite3.connect(os.environ["ACCOUNTS_DB"])) as db, db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM account_keys").fetchone()[0], 0)

    def test_the_secret_is_made_once_beside_the_database_and_is_not_in_it(self):
        secret = Path(os.environ["ACCOUNTS_DB"] + account_keys.SECRET_SUFFIX)
        self.assertFalse(secret.exists(), "No secret until there is something to seal")
        account_keys.save(self.user, provider="deepseek", model="deepseek-chat", llm_api_key=LLM_KEY,
                          search="tavily", search_api_key=SEARCH_KEY)
        made = secret.read_bytes()
        self.assertGreaterEqual(len(made.strip()), 40)
        self.assertNotIn(made.strip(), self._database_text())
        account_keys._forget_secret()        # a restart
        self.assertEqual(account_keys.load(self.user).llm_api_key, LLM_KEY)
        self.assertEqual(secret.read_bytes(), made, "The same secret after a restart")

    def test_a_secret_from_the_environment_is_used_and_nothing_is_written_beside_the_database(self):
        with patch.dict("os.environ", {"ACCOUNT_KEYS_SECRET": "an operator's own secret, kept in the platform's variables"}):
            account_keys._forget_secret()
            account_keys.save(self.user, provider="deepseek", model="deepseek-chat", llm_api_key=LLM_KEY,
                              search="tavily", search_api_key=SEARCH_KEY)
            self.assertFalse(Path(os.environ["ACCOUNTS_DB"] + account_keys.SECRET_SUFFIX).exists())
            self.assertEqual(account_keys.load(self.user).llm_api_key, LLM_KEY)
        # Without that secret the keys cannot be opened: they read as not saved, and nothing breaks.
        account_keys._forget_secret()
        self.assertIsNone(account_keys.load(self.user))
        self.assertFalse(account_keys.saved(self.user))
        # Saving again replaces what could not be read.
        account_keys.save(self.user, provider="qwen", model="qwen3.8-27b", llm_api_key=OTHER_LLM_KEY,
                          search="serper", search_api_key=OTHER_SEARCH_KEY)
        self.assertEqual(account_keys.load(self.user).request_fields(), OTHER_KEYS)

    def test_a_damaged_row_reads_as_not_saved(self):
        account_keys.save(self.user, provider="deepseek", model="deepseek-chat", llm_api_key=LLM_KEY,
                          search="tavily", search_api_key=SEARCH_KEY)
        for damaged in ("", "not a token", "gAAAAAB" + "A" * 60):
            with closing(sqlite3.connect(os.environ["ACCOUNTS_DB"])) as db, db:
                db.execute("UPDATE account_keys SET sealed = ?", (damaged,))
            self.assertIsNone(account_keys.load(self.user), damaged)

    def test_a_backup_holds_only_the_sealed_token_and_a_restore_clears_saved_keys(self):
        """A restore is a picture of the past: keys an account removed or
        replaced since must not come back into use, as ended sessions do not."""
        from api import account_backup

        account_keys.save(self.user, provider="deepseek", model="deepseek-chat", llm_api_key=LLM_KEY,
                          search="tavily", search_api_key=SEARCH_KEY)
        copy = Path(self._tmp.name) / "elsewhere" / "accounts-backup.sqlite3"
        account_backup.backup(copy)
        held = copy.read_bytes()
        for readable in (LLM_KEY, SEARCH_KEY, "deepseek-chat"):
            self.assertNotIn(readable.encode(), held, readable)
        self.assertEqual([path.name for path in copy.parent.iterdir()], [copy.name], "The secret is not backed up")
        self.assertTrue(account_keys.remove(self.user))        # removed after the backup was taken
        account_backup.restore(copy)
        self.assertIsNone(account_keys.load(self.user), "The removed keys did not come back")
        with closing(sqlite3.connect(os.environ["ACCOUNTS_DB"])) as db, db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM account_keys").fetchone()[0], 0)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM users").fetchone()[0], 1, "The account is back")

    def test_a_hint_is_the_last_four_characters_and_never_most_of_a_short_key(self):
        self.assertEqual(account_keys.hint(LLM_KEY), "…abcd")
        self.assertEqual(account_keys.hint("k" * 12), "…kkkk")
        for short in ("", "k", "abcdefgh", "k" * 11):
            self.assertEqual(account_keys.hint(short), "…", short)


class EndpointTests(_Keys):
    def test_saving_reading_and_removing(self):
        self.assertEqual(self.client.get("/api/auth/keys", headers=self.headers).json(),
                         {"saved": False})
        saved = self._save()
        expected = {"saved": True, "llm_provider": "deepseek", "llm_model": "deepseek-chat",
                    "llm_key_hint": "…abcd", "search": "tavily", "search_key_hint": "…wxyz"}
        body = saved.json()
        self.assertRegex(body.pop("saved_at"), r"^20\d\d-\d\d-\d\dT\d\d:\d\d:\d\d(Z|\+00:00)$")
        self.assertEqual(body, expected)
        read = self.client.get("/api/auth/keys", headers=self.headers)
        self.assertEqual({key: value for key, value in read.json().items() if key != "saved_at"}, expected)
        self.assertEqual(read.headers["Cache-Control"], "no-store")
        self.assertEqual(self.client.delete("/api/auth/keys", headers=self.headers).status_code, 204)
        self.assertEqual(self.client.get("/api/auth/keys", headers=self.headers).json(), {"saved": False})
        self.assertEqual(self.client.delete("/api/auth/keys", headers=self.headers).status_code, 204, "Idempotent")

    def test_no_reply_ever_carries_a_key(self):
        replies = [self._save(), self.client.get("/api/auth/keys", headers=self.headers),
                   self.client.get("/api/auth/me", headers=self.headers),
                   self.client.get("/api/access/check", headers=self.headers),
                   self.client.post("/api/auth/login", json={"email": "alice@example.com", "password": PASSWORD}),
                   self._save(OTHER_KEYS)]
        for reply in replies:
            for secret in SECRETS:
                self.assertNotIn(secret, reply.text)
                self.assertNotIn(secret[:12], reply.text)

    def test_a_malformed_key_set_is_refused_without_quoting_it(self):
        for body in ({**KEYS, "llm_model": "not a model name"}, {**KEYS, "serper_api_key": OTHER_SEARCH_KEY},
                     {key: value for key, value in KEYS.items() if key != "tavily_api_key"},
                     {**KEYS, "llm_provider": "elsewhere"}):
            response = self.client.put("/api/auth/keys", json=body, headers=self.headers)
            self.assertEqual(response.status_code, 422, body)
            for secret in SECRETS:
                self.assertNotIn(secret, response.text)
        self.assertEqual(self.client.put("/api/auth/keys", content=b"not json", headers=self.headers).status_code, 422)
        self.assertEqual(self.client.put("/api/auth/keys", content=b"x" * 20_000, headers=self.headers).status_code, 413)
        self.assertFalse(account_keys.saved(self.user), "Nothing malformed was saved")

    def test_only_an_account_has_keys_to_save(self):
        for method in ("get", "put", "delete"):
            anonymous = getattr(self.client, method)("/api/auth/keys", **({"json": KEYS} if method == "put" else {}))
            self.assertEqual(anonymous.status_code, 401, method)
        with patch.object(access, "ACCESS_CODE", "an-access-code"):
            code = {"X-Access-Code": "an-access-code"}
            self.assertEqual(self.client.get("/api/auth/keys", headers=code).status_code, 404)
            self.assertEqual(self.client.put("/api/auth/keys", json=KEYS, headers=code).status_code, 404)

    def test_the_page_is_told_at_sign_in_whether_keys_are_saved(self):
        def told():
            me = self.client.get("/api/auth/me", headers=self.headers).json()["keys_saved"]
            boot = self.client.get("/api/access/check", headers=self.headers).json()["account"]["keys_saved"]
            login = self.client.post("/api/auth/login", json={"email": "alice@example.com", "password": PASSWORD})
            self.assertEqual({me, boot, login.json()["keys_saved"]}, {me}, "Every answer about the account agrees")
            return me

        self.assertIs(self.session["keys_saved"], False)
        self.assertIs(told(), False)
        self._save()
        self.assertIs(told(), True)
        self.client.delete("/api/auth/keys", headers=self.headers)
        self.assertIs(told(), False)

    def test_the_endpoints_are_declared(self):
        paths = app.openapi()["paths"]["/api/auth/keys"]
        self.assertEqual(set(paths), {"get", "put", "patch", "delete"})
        schemas = app.openapi()["components"]["schemas"]
        for model in ("AuthMe", "AuthSession"):
            self.assertIn("keys_saved", schemas[model]["properties"], model)
        self.assertNotIn("llm_api_key", schemas["SavedKeys"]["properties"])


class ChangeModelTests(_Keys):
    """The saved set is two keys and the model they are used with. A model
    turns out wrong far more often than a key does (the live account that
    prompted this had saved an OCR model), and the only way to change it was
    to type both keys again."""

    def _change(self, model, headers=None):
        return self.client.patch("/api/auth/keys", json={"llm_model": model}, headers=headers or self.headers)

    def test_the_model_changes_and_the_keys_stay(self):
        account_keys.save(self.user, provider="deepseek", model="deepseek-chat", llm_api_key=LLM_KEY,
                          search="tavily", search_api_key=SEARCH_KEY, now=1_700_000_000)
        reply = self._change("deepseek-reasoner")
        self.assertEqual(reply.status_code, 200, reply.text)
        body = reply.json()
        self.assertEqual((body["saved"], body["llm_provider"], body["llm_model"], body["search"]),
                         (True, "deepseek", "deepseek-reasoner", "tavily"))
        self.assertEqual((body["llm_key_hint"], body["search_key_hint"]), ("…" + LLM_KEY[-4:], "…" + SEARCH_KEY[-4:]))
        self.assertEqual(reply.headers["Cache-Control"], "no-store")
        for secret in SECRETS:
            self.assertNotIn(secret, reply.text)
        kept = account_keys.load(self.user)
        self.assertEqual((kept.provider, kept.model, kept.llm_api_key, kept.search, kept.search_api_key),
                         ("deepseek", "deepseek-reasoner", LLM_KEY, "tavily", SEARCH_KEY))
        self.assertGreater(kept.updated_at, 1_700_000_000, "When the set last changed")
        # Sealed as before: the new model is no more readable in the store than the old one was.
        for readable in (LLM_KEY, SEARCH_KEY, "deepseek-reasoner", "deepseek-chat"):
            self.assertNotIn(readable.encode(), self._database_text(), readable)
        self.assertEqual(self.client.get("/api/auth/keys", headers=self.headers).json()["llm_model"], "deepseek-reasoner")

    def test_the_next_paid_request_runs_on_the_new_model(self):
        self._save()
        self.assertEqual(self._change("deepseek-reasoner").status_code, 200)
        with patch.object(runs, "start_run", return_value=RUN) as started:
            response = self.client.post("/api/runs", json=TOPIC, headers=self.headers)
        self.assertEqual(response.status_code, 202, response.text)
        byok = started.call_args.kwargs["byok"]
        self.assertEqual((byok.llm_provider, byok.llm_api_key, byok.llm_model, byok.tavily_api_key),
                         ("deepseek", LLM_KEY, "deepseek-reasoner", SEARCH_KEY))

    def test_with_nothing_saved_there_is_nothing_to_change(self):
        reply = self._change("deepseek-reasoner")
        self.assertEqual((reply.status_code, reply.headers["X-Error-Code"]), (409, "no_saved_keys"))
        self.assertFalse(account_keys.saved(self.user), "A model alone is not a key set")
        # One account's change does not reach another's keys.
        self._save()
        bob = self._bearer(self._signup("bob@example.com")["token"])
        other = self._change("deepseek-reasoner", headers=bob)
        self.assertEqual((other.status_code, other.headers["X-Error-Code"]), (409, "no_saved_keys"))
        self.assertEqual(account_keys.load(self.user).model, "deepseek-chat")

    def test_only_a_plain_model_name_and_nothing_else_is_taken(self):
        self._save()
        for body in ({"llm_model": "not a model name"}, {"llm_model": ""}, {"llm_model": "x" * 101}, {},
                     {"llm_model": 7}, {"llm_model": "deepseek-reasoner", "llm_provider": "qwen"},
                     # Keys do not belong here: a set is replaced whole, with PUT, or not at all.
                     {"llm_model": "deepseek-reasoner", "llm_api_key": OTHER_LLM_KEY},
                     {"llm_model": "deepseek-reasoner", "tavily_api_key": OTHER_SEARCH_KEY}):
            reply = self.client.patch("/api/auth/keys", json=body, headers=self.headers)
            self.assertEqual(reply.status_code, 422, body)
            for secret in SECRETS:
                self.assertNotIn(secret, reply.text)
            self.assertNotIn("not a model name", reply.text, "A refusal names the field, never the value")
        self.assertEqual(self.client.patch("/api/auth/keys", content=b"not json", headers=self.headers).status_code, 422)
        self.assertEqual(self.client.patch("/api/auth/keys", content=b"[]", headers=self.headers).status_code, 422)
        self.assertEqual(self.client.patch("/api/auth/keys", content=b"x" * 20_000, headers=self.headers).status_code, 413)
        kept = account_keys.load(self.user)
        self.assertEqual((kept.model, kept.llm_api_key, kept.search_api_key), ("deepseek-chat", LLM_KEY, SEARCH_KEY))

    def test_only_an_account_can_change_it(self):
        self._save()
        self.assertEqual(self.client.patch("/api/auth/keys", json={"llm_model": "deepseek-reasoner"}).status_code, 401)
        with patch.object(access, "ACCESS_CODE", "an-access-code"):
            coded = self.client.patch("/api/auth/keys", json={"llm_model": "deepseek-reasoner"},
                                      headers={"X-Access-Code": "an-access-code"})
        self.assertEqual(coded.status_code, 404)
        self.assertEqual(account_keys.load(self.user).model, "deepseek-chat")

    def test_a_set_replaced_meanwhile_is_not_overwritten_with_the_old_keys(self):
        """The change reads the sealed record, opens it, and writes it back
        with another model. A whole new set saved between the read and the
        write must win: writing back would put the old keys over the new."""
        self._save()
        real = account_keys._sealed

        def replaced_while_reading(db, user):
            row = real(db, user)
            account_keys.save(user, provider="qwen", model="qwen3.8-27b", llm_api_key=OTHER_LLM_KEY,
                              search="serper", search_api_key=OTHER_SEARCH_KEY)
            return row

        with patch.object(account_keys, "_sealed", side_effect=replaced_while_reading) as read:
            reply = self._change("deepseek-reasoner")
        self.assertGreaterEqual(read.call_count, 2, "It looked again")
        self.assertEqual((reply.status_code, reply.headers["X-Error-Code"]), (409, "keys_changed"))
        kept = account_keys.load(self.user)
        self.assertEqual((kept.provider, kept.model, kept.llm_api_key, kept.search_api_key),
                         ("qwen", "qwen3.8-27b", OTHER_LLM_KEY, OTHER_SEARCH_KEY))

    def test_a_set_replaced_once_meanwhile_gets_the_new_model_on_the_new_keys(self):
        self._save()
        real = account_keys._sealed
        calls = []

        def replaced_once(db, user):
            row = real(db, user)
            if not calls:
                calls.append(1)
                account_keys.save(user, provider="qwen", model="qwen3.8-27b", llm_api_key=OTHER_LLM_KEY,
                                  search="serper", search_api_key=OTHER_SEARCH_KEY)
            return row

        with patch.object(account_keys, "_sealed", side_effect=replaced_once):
            reply = self._change("qwen3.8-max")
        self.assertEqual(reply.status_code, 200, reply.text)
        kept = account_keys.load(self.user)
        self.assertEqual((kept.provider, kept.model, kept.llm_api_key, kept.search_api_key),
                         ("qwen", "qwen3.8-max", OTHER_LLM_KEY, OTHER_SEARCH_KEY))

    def test_a_record_that_cannot_be_opened_is_not_a_set_to_change(self):
        self._save()
        with closing(sqlite3.connect(os.environ["ACCOUNTS_DB"])) as db, db:
            db.execute("UPDATE account_keys SET sealed = 'damaged'")
        reply = self._change("deepseek-reasoner")
        self.assertEqual((reply.status_code, reply.headers["X-Error-Code"]), (409, "no_saved_keys"))


class CheckSavedTests(_Keys):
    """The page shows which keys are saved and never has them again, so it
    cannot ask the providers about them itself; the server asks."""

    def _asked(self):
        from unittest.mock import AsyncMock

        from api import key_check

        return patch.object(key_check, "check", AsyncMock(return_value=key_check.KeyCheck(
            llm="accepted", model="listed", search="rejected")))

    def test_the_saved_set_is_what_the_providers_are_asked_about(self):
        self._save()
        with patch.dict("os.environ", {"KEY_CHECK": "on"}), patch("api.main._key_check_times", {}), self._asked() as asked:
            reply = self.client.post("/api/auth/keys/check", headers=self.headers)
        self.assertEqual(reply.status_code, 200, reply.text)
        self.assertEqual(reply.json(), {"checked": True, "llm": "accepted", "model": "listed", "search": "rejected"})
        self.assertEqual(asked.await_args.kwargs, {"provider": "deepseek", "llm_api_key": LLM_KEY, "model": "deepseek-chat",
                                                   "search": "tavily", "search_api_key": SEARCH_KEY})
        self.assertEqual(reply.headers["Cache-Control"], "no-store")
        for secret in SECRETS:
            self.assertNotIn(secret, reply.text)
        # Asking changes nothing: a key a provider refuses stays saved until the account acts.
        self.assertEqual(account_keys.load(self.user).search_api_key, SEARCH_KEY)

    def test_with_nothing_saved_nobody_is_asked(self):
        with patch.dict("os.environ", {"KEY_CHECK": "on"}), self._asked() as asked:
            reply = self.client.post("/api/auth/keys/check", headers=self.headers)
            self.assertEqual((reply.status_code, reply.headers["X-Error-Code"]), (409, "no_saved_keys"))
            # One account's saved keys are not another's to ask about.
            self._save()
            bob = self._bearer(self._signup("bob@example.com")["token"])
            other = self.client.post("/api/auth/keys/check", headers=bob)
            self.assertEqual((other.status_code, other.headers["X-Error-Code"]), (409, "no_saved_keys"))
        asked.assert_not_awaited()

    def test_only_an_account_can_ask_and_only_so_often(self):
        self._save()
        with patch.dict("os.environ", {"KEY_CHECK": "on"}), self._asked() as asked:
            self.assertEqual(self.client.post("/api/auth/keys/check").status_code, 401)
            # A code holder passes the gate and has no account: told this is for accounts,
            # not that "no keys are saved", which would be an answer about an account.
            with patch.object(access, "ACCESS_CODE", "an-access-code"):
                coded = self.client.post("/api/auth/keys/check", headers={"X-Access-Code": "an-access-code"})
            self.assertEqual(coded.status_code, 404)
            self.assertNotEqual(coded.headers.get("X-Error-Code"), "no_saved_keys")
            with patch("api.main._key_check_times", {}), patch("api.main._key_check_exceeded", return_value=True):
                limited = self.client.post("/api/auth/keys/check", headers=self.headers)
            self.assertEqual((limited.status_code, limited.headers["X-Error-Code"]), (429, "rate_limited"))
        asked.assert_not_awaited()

    def test_a_deployment_that_checks_no_keys_says_so_and_asks_nobody(self):
        self._save()
        with patch.dict("os.environ", {"KEY_CHECK": "off"}), self._asked() as asked:
            reply = self.client.post("/api/auth/keys/check", headers=self.headers)
        self.assertEqual(reply.json(), {"checked": False, "llm": "unverified", "model": "unknown", "search": "unverified"})
        asked.assert_not_awaited()

    def test_the_two_checks_share_one_limit_per_account(self):
        """Typed keys and saved keys are the same account asking the same providers."""
        self._save()
        with patch.dict("os.environ", {"KEY_CHECK": "on"}), patch("api.main._key_check_times", {}) as times, self._asked():
            self.client.post("/api/auth/keys/check", headers=self.headers)
            self.client.post("/api/keys/check", json=KEYS, headers=self.headers)
            self.assertEqual({owner: len(seen) for owner, seen in times.items()}, {self.user.owner: 2})


class PaidOperationTests(_Keys):
    """A request with no keys from an account that saved some runs on them."""

    def _started(self, body=TOPIC, headers=None):
        with patch.object(runs, "start_run", return_value=RUN) as started:
            response = self.client.post("/api/runs", json=body, headers=headers or self.headers)
        return response, started

    def test_a_run_without_keys_uses_the_saved_ones(self):
        refused, started = self._started()
        self.assertEqual((refused.status_code, refused.headers["X-Error-Code"]), (401, "byok_required"))
        started.assert_not_called()
        self._save()
        response, started = self._started()
        self.assertEqual(response.status_code, 202, response.text)
        byok = started.call_args.kwargs["byok"]
        self.assertEqual((byok.llm_provider, byok.llm_api_key, byok.llm_model, byok.tavily_api_key, byok.serper_api_key),
                         ("deepseek", LLM_KEY, "deepseek-chat", SEARCH_KEY, None))
        self.assertEqual(started.call_args.kwargs["owner"], self.user.owner, "Tagged to the account, as its runs are")
        for secret in SECRETS:
            self.assertNotIn(secret, response.text)

    def test_keys_in_the_request_win_and_are_not_saved(self):
        self._save()
        response, started = self._started({**TOPIC, **OTHER_KEYS})
        self.assertEqual(response.status_code, 202, response.text)
        self.assertEqual(started.call_args.kwargs["byok"].llm_api_key, OTHER_LLM_KEY)
        self.assertEqual(account_keys.load(self.user).llm_api_key, LLM_KEY, "What was saved is untouched")
        # ...and an account that saved none stores none by running with keys.
        bob = self._bearer(self._signup("bob@example.com")["token"])
        response, started = self._started({**TOPIC, **OTHER_KEYS}, bob)
        self.assertEqual(response.status_code, 202, response.text)
        self.assertEqual(self.client.get("/api/auth/keys", headers=bob).json(), {"saved": False})

    def test_another_account_does_not_run_on_them(self):
        self._save()
        bob = self._bearer(self._signup("bob@example.com")["token"])
        response, started = self._started(headers=bob)
        self.assertEqual((response.status_code, response.headers["X-Error-Code"]), (401, "byok_required"))
        started.assert_not_called()

    def test_removed_keys_are_not_used(self):
        self._save()
        self.client.delete("/api/auth/keys", headers=self.headers)
        response, started = self._started()
        self.assertEqual((response.status_code, response.headers["X-Error-Code"]), (401, "byok_required"))

    def test_an_unverified_account_is_still_asked_to_verify_first(self):
        self._save()
        with patch.object(accounts, "verification_required", return_value=True):
            carol = self._bearer(self._signup("carol@example.com")["token"])
            self.assertEqual(self.client.put("/api/auth/keys", json=KEYS, headers=carol).status_code, 200,
                             "Keys may be saved before the address is proven, as they could be typed before")
            response, started = self._started(headers=carol)
        self.assertEqual((response.status_code, response.headers["X-Error-Code"]), (403, "email_unverified"))
        started.assert_not_called()

    def test_a_preview_runs_on_the_saved_model_key(self):
        used = []

        def planner(topic, n=2, *, credentials=None):
            used.append(credentials)
            return TopicSearchPlan(search_topic="a valid research topic")

        with patch.object(plan_preview, "_counts", {}), patch.object(plan_preview, "plan_topic_search", planner):
            bare = self.client.post("/api/plan", json=TOPIC, headers=self.headers)
            self.assertEqual((bare.status_code, bare.headers["X-Error-Code"]), (401, "byok_required"))
            self._save()
            own = self.client.post("/api/plan", json=TOPIC, headers=self.headers)
            self.assertEqual(own.status_code, 200, own.text)
            self.assertEqual(used, [{"provider": "deepseek", "api_key": LLM_KEY, "model": "deepseek-chat"}])
            self.assertNotIn(LLM_KEY, own.text)

    def test_an_upload_is_extracted_on_the_saved_model_key(self):
        self._save()
        seen = {}

        async def extracted(paper_id, pdf_path, **credentials):
            seen.update(credentials)
            raise papers.PaperTooLarge("stop here: the credentials are what this test is about")

        root = Path(self._tmp.name) / "outputs"
        root.mkdir()
        with patch.object(runs, "DEFAULT_OUTPUT_ROOT", root), patch.object(papers, "PAPERS_ROOT", root / "_papers"), \
                patch("api.main._process_uploaded_paper", extracted):
            self.client.post("/api/papers", files={"file": ("paper.pdf", b"%PDF-1.4 fixture", "application/pdf")},
                             headers=self.headers)
        self.assertEqual((seen.get("llm_provider"), seen.get("llm_api_key"), seen.get("llm_model")),
                         ("deepseek", LLM_KEY, "deepseek-chat"))

    def test_a_resume_runs_on_the_saved_keys(self):
        self._save()
        root = Path(self._tmp.name) / "outputs"
        parent = root / "20261115T010203Z-0123456789abcdef0123456789abcdef"
        parent.mkdir(parents=True)
        (parent / ".owner").write_text(self.user.owner, encoding="utf-8")
        # What happens after the child is created is not this test's subject, and the
        # stand-in child has no files: the client must not re-raise what the server then meets.
        with patch.object(runs, "DEFAULT_OUTPUT_ROOT", root), \
                patch.object(runs, "resume_run", return_value=("child", root / "child")) as resumed, \
                TestClient(app, raise_server_exceptions=False) as client:
            client.post(f"/api/runs/{parent.name}/resume", json={}, headers=self.headers)
        self.assertTrue(resumed.called, "Admitted without keys in the request")
        self.assertEqual(resumed.call_args.kwargs["byok"].llm_api_key, LLM_KEY)

    def test_a_repeated_request_is_answered_from_its_receipt_after_the_keys_changed(self):
        """The receipt binds what was asked for, not which keys paid for it."""
        self._save()
        root = Path(self._tmp.name) / "outputs"
        root.mkdir()
        key = "v1." + str(int(__import__("time").time())) + "." + "a" * 64
        headers = {**self.headers, "Idempotency-Key": key}
        with patch.object(runs, "DEFAULT_OUTPUT_ROOT", root), patch.object(runs, "start_run", return_value=RUN) as started:
            first = self.client.post("/api/runs", json=TOPIC, headers=headers)
            self._save(OTHER_KEYS)
            again = self.client.post("/api/runs", json=TOPIC, headers=headers)
        self.assertEqual(first.status_code, 202, first.text)
        # The repeat is recognised as the same request. With different input or
        # credentials it would be refused as a conflict; here it reaches the
        # saved receipt (which this test's stand-in run cannot fill in).
        self.assertNotEqual(again.headers.get("X-Error-Code"), "receipt_conflict", again.text)
        self.assertEqual(again.headers.get("X-Error-Code"), "receipt_unavailable", again.text)
        self.assertEqual(started.call_count, 1, "Started once, on the keys saved at the time")
        # Different input under the same key is still a conflict.
        with patch.object(runs, "DEFAULT_OUTPUT_ROOT", root), patch.object(runs, "start_run", return_value=RUN):
            other = self.client.post("/api/runs", json={"topic": "another valid research topic"}, headers=headers)
        self.assertEqual(other.headers.get("X-Error-Code"), "receipt_conflict", other.text)
        self.assertEqual(started.call_args.kwargs["byok"].llm_api_key, LLM_KEY)
        for path in root.rglob("*"):
            if path.is_file():
                for secret in SECRETS:
                    self.assertNotIn(secret.encode(), path.read_bytes(), path.name)
