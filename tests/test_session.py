import unittest

from runtime.session import Participant, Session, SessionError, SessionState


PROFILE = {"game_id": "GMPE01", "region": "USA"}


class SessionTests(unittest.TestCase):
    def make_session(self):
        session = Session(
            host_id="host",
            game_id="GMPE01",
            region="USA",
            adapter_id="dolphin",
            game_pack_id="mario_party_4",
        )
        session.participants["host"].profile = dict(PROFILE)
        session.add_participant(Participant("peer", profile=dict(PROFILE)))
        return session

    def test_ready_barrier_activates_only_when_everyone_is_ready(self):
        session = self.make_session()
        session.begin_validation()
        session.set_ready("host")
        with self.assertRaises(SessionError):
            session.activate()
        session.set_ready("peer")
        session.activate()
        self.assertEqual(SessionState.ACTIVE, session.state)

    def test_incompatible_profile_fails_explicitly(self):
        session = self.make_session()
        session.participants["peer"].profile["region"] = "EUR"
        with self.assertRaisesRegex(SessionError, "incompatible region"):
            session.begin_validation()
        self.assertEqual(SessionState.FAILED, session.state)


if __name__ == "__main__":
    unittest.main()
