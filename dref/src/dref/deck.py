import threading

from PIL import Image
from StreamDeck.DeviceManager import DeviceManager
from StreamDeck.ImageHelpers import PILHelper
from StreamDeck.Transport.Transport import TransportError


class Deck:
    def __init__(self, deck_id: int = None):
        self._decks = DeviceManager().enumerate()
        self._deck = None
        self._key_change_callback = None

        for index, deck in enumerate(self._decks):
            # if (deck_id is None and index != 0) or index != deck_id:
            #     continue

            if not deck.is_visual():
                continue

            deck.open()
            deck.reset()
            deck.set_brightness(30)
            deck.set_key_callback(self._on_key_change_callback)
            print(
                "Opened '{}' device (serial number: '{}', fw: '{}')".format(
                    deck.deck_type(),
                    deck.get_serial_number(),
                    deck.get_firmware_version(),
                )
            )
            self._deck = deck
            break

    def reset(self):
        self._deck.reset()

    @property
    def key_count(self):
        return self._deck.key_count()

    @property
    def key_change_callback(self):
        return self._key_change_callback

    @key_change_callback.setter
    def key_change_callback(self, value):
        self._key_change_callback = value

    def _on_key_change_callback(self, deck, key: int, state: str):
        print(f"Deck {deck.id()} Key {key} = {state}")
        if self._key_change_callback is not None:
            self._key_change_callback(key, state)

    def update_key(self, key: int, image: Image):
        deck_image = PILHelper.to_native_key_format(self._deck, image)
        with self._deck:
            self._deck.set_key_image(key, deck_image)

    def close(self):
        with self._deck:
            self._deck.reset()
            self._deck.close()
        for t in threading.enumerate():
            try:
                t.join()
            except (TransportError, RuntimeError):
                pass
