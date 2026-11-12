"""Stop on legal/account setup and Android permission screens; only the user may complete them."""

from roguebot.emulator import EmulatorError
from roguebot.vision import Text


def check_manual_setup(texts: list[Text]) -> None:
    phrases = ("privacy policy", "terms of service", "terms of use", "politica de privacidad",
               "terminos de servicio", "sign in with", "iniciar sesion", "log in to",
               "allow rogue legend", "permitir que rogue legend", "while using the app",
               "mientras usas la aplicacion")
    if any(phrase in text.norm for text in texts for phrase in phrases):
        raise EmulatorError("err_manual_setup")
