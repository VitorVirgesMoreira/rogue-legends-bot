import pytest

from roguebot.emulator import EmulatorError, PERMANENT_ERRORS
from roguebot.setup_guard import check_manual_setup
from roguebot.vision import Text


@pytest.mark.parametrize("text", ["Privacy Policy", "Terms of Service", "Sign in with Google",
                                  "Allow Rogue Legend to send notifications?", "Política de privacidad"])
def test_manual_setup_is_never_automated(text):
    with pytest.raises(EmulatorError) as err:
        check_manual_setup([Text(text, 0, 0, 400, 80)])
    assert err.value.key == "err_manual_setup" and err.value.key in PERMANENT_ERRORS


def test_regular_lobby_passes():
    check_manual_setup([Text("Adventure", 0, 0, 400, 80)])
