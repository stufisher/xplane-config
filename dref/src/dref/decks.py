from dataclasses import dataclass, field
from ruamel import yaml
import os
import time
from typing import Callable

from .drawing import KEY_TYPES, create_image
from .deck import Deck
from .fcu import FCU
from .udp import UDP


def translate_press(value: int):
    return 0 if value else 1


def translate_press_iterate(max_iterate: str, char_id: str = None, length: int = None):
    def translate_iterate(value: int):
        if char_id:
            if not isinstance(value, int):
                value = int(value)
            str_value = f"{value:0{length}d}"
            value = int(str_value[int(char_id)])

        if value == int(max_iterate) - 1:
            value = 0
        else:
            value += 1

        if char_id:
            str_list = list(str_value)
            str_list[int(char_id)] = str(value)
            value = int("".join(str_list))
        return value

    return translate_iterate


PRESS_TRANSLATORS = {"translate_press_iterate": translate_press_iterate}


def command_press_iterate(max_iterate: str):
    def command_press(
        value, command_up: Callable[[], None], command_down: Callable[[], None]
    ):
        if value == int(max_iterate) - 1:
            for i in range(max_iterate):
                command_down()
        else:
            command_up()

    return command_press


COMMAND_TRANSLATORS = {"command_press_iterate": command_press_iterate}


def translate_dref_character(char_id: str, length: int = 4):
    char_id = int(char_id)

    def translate_dref(value: int):
        if not isinstance(value, int):
            value = int(value)
        char = f"{value:0{length}d}"
        if char_id < len(char):
            return char[char_id]
        else:
            return ""

    return translate_dref


def translate_dref_value_bool(compare_value: str, comparator="equal"):
    compare_value = int(compare_value)

    def translate_dref(value: int):
        if comparator == "equal":
            return value == compare_value
        elif comparator == "greater":
            if isinstance(value, list):
                for v in value:
                    if v is not None:
                        if v > compare_value:
                            return True
            else:
                if value is not None:
                    return value > compare_value

    return translate_dref


def translate_dref_gear_lever():
    def translate_dref_gear_lever(values: int):
        gear, lever = values

        if lever == 1 and gear < 2:
            return True
        if lever == 0 and gear > 0:
            return True

    return translate_dref_gear_lever


DREF_TRANSLATORS = {
    "translate_dref_character": translate_dref_character,
    "translate_dref_value_bool": translate_dref_value_bool,
    "translate_dref_gear_lever": translate_dref_gear_lever,
}


def get_translator(function_string: str, translators=PRESS_TRANSLATORS):
    parts = function_string.split(",")
    translate_fn = translators[parts[0]]
    if len(parts) > 1:
        translator = translate_fn(*parts[1:])
    else:
        translator = translate_fn()
    return translator


@dataclass
class DeckKeyMapping:
    key_id: int
    key_type: str | None = None
    key_options: dict[str, any] = field(default_factory=dict)
    state_dataref: str | list[str] = None
    secondary_dataref: str | list[str] = None
    translate_dataref: Callable[[int | None], any] = None
    secondary_dataref_is_fault: bool = False
    translate_secondary_dataref: Callable[[int | None], any] = None
    translate_press: Callable[[str], int] = None
    command_press_toggle: str = None
    command_press_up: str = None
    command_press_down: str = None
    translate_command_press: Callable[
        [int, Callable[[], None], Callable[[], None]], None
    ] = None
    static: bool = False


@dataclass
class DeckMapping:
    deck_id: int
    name: str
    keys: list[DeckKeyMapping]
    icon: str = None
    has_fault: bool = False


class Decks:
    def __init__(self):
        self._mapping: list[DeckMapping] = []
        self.load_mapping()
        self._deck = Deck()
        self._deck.key_change_callback = self._key_change_callback
        self._fcu = FCU()
        self._udp = UDP(
            self.get_all_drefs() + self._fcu.get_drefs(), self.on_drefs_changed
        )
        self._fcu.udp = self._udp
        self._current_deck = 0
        self._is_home = True
        self.update_deck()

    def load_mapping(self):
        yaml_path = os.path.join(
            os.path.dirname(__file__), "..", "..", "mappings", "default.yaml"
        )
        loader = yaml.YAML(typ="safe", pure=True)
        with open(yaml_path) as file:
            yaml_content = loader.load(file)

        self._mapping = []
        for deck in yaml_content:
            deck["keys"] = [DeckKeyMapping(**key) for key in deck["keys"]]
            self._mapping.append(DeckMapping(**deck))

    def on_drefs_changed(self, drefs: dict[str, any]):
        self._fcu.on_drefs_changed(drefs)
        if self._is_home:
            return
        self.update_faults()
        for dref, value in drefs.items():
            keys = self.key_for_dref_in_current_deck(dref)
            if keys:
                for key in keys:
                    # print(dref, value)
                    self.update_key(key.key_id)

    def get_all_drefs(self):
        drefs = []
        for deck in self._mapping:
            for key in deck.keys:
                if key.state_dataref:
                    if isinstance(key.state_dataref, list):
                        drefs.extend(key.state_dataref)
                    else:
                        drefs.append(key.state_dataref)
                if key.secondary_dataref:
                    if isinstance(key.secondary_dataref, list):
                        drefs.extend(key.secondary_dataref)
                    else:
                        drefs.append(key.secondary_dataref)

        return list(set(drefs))

    def _key_change_callback(self, key, state):
        if not state:
            return
        if self._is_home:
            for deck in self._mapping:
                if key == deck.deck_id:
                    self._current_deck = deck.deck_id
                    self._is_home = False
                    self.update_deck()

        elif key == self._deck.key_count - 1:
            self._is_home = True
            self.update_deck()

        else:
            deck = self.get_current_deck()
            for deck_key in deck.keys:
                if deck_key.key_id == key:
                    if deck_key.static:
                        return
                    if deck_key.state_dataref:
                        dref_value = self._udp.get_dref_value(deck_key.state_dataref)
                        if deck_key.command_press_toggle:
                            self._udp.execute_command(deck_key.command_press_toggle)
                        elif (
                            deck_key.command_press_up
                            and deck_key.command_press_up
                            and deck_key.translate_command_press
                        ):
                            translator = get_translator(
                                deck_key.translate_command_press,
                                translators=COMMAND_TRANSLATORS,
                            )

                            def up():
                                self._udp.execute_command(deck_key.command_press_up)

                            def down():
                                self._udp.execute_command(deck_key.command_press_down)

                            translator(dref_value, up, down)
                        else:
                            translator = (
                                get_translator(deck_key.translate_press)
                                if deck_key.translate_press
                                else translate_press
                            )
                            self._udp.set_dref(
                                deck_key.state_dataref, translator(dref_value)
                            )

    def update_deck(self):
        self.clear()
        if self._is_home:
            for deck in self._mapping:
                icon_props = {}
                if deck.icon:
                    icon_props = {"state": deck.icon, "state_font": "symbols"}
                image = KEY_TYPES["text_button"](
                    label=deck.name, notification=deck.has_fault, **icon_props
                )
                self._deck.update_key(deck.deck_id, image)
        else:
            mapping = self.get_current_deck()
            for key in mapping.keys:
                self.update_key(key.key_id)
        self._update_home()

    def _update_home(self):
        has_fault = False
        for deck in self._mapping:
            if deck.has_fault:
                has_fault = True
                break

        image = KEY_TYPES["text_button"](
            label="",
            state="\ue88a",
            state_font="symbols",
            state_font_size=1.5,
            notification=has_fault,
        )
        self._deck.update_key(self._deck.key_count - 1, image)

    def key_for_dref_in_current_deck(self, dref: str):
        mapping = self.get_current_deck()
        mapping_keys = []
        for mapping_key in mapping.keys:
            if (
                dref == mapping_key.state_dataref
                or dref == mapping_key.secondary_dataref
            ):
                mapping_keys.append(mapping_key)
            if isinstance(mapping_key.secondary_dataref, list):
                if dref in mapping_key.secondary_dataref:
                    mapping_keys.append(mapping_key)
        return mapping_keys

    def get_mapping_key(self, key_id: int):
        mapping = self.get_current_deck()
        for mapping_key in mapping.keys:
            if key_id == mapping_key.key_id:
                return mapping_key

    def get_current_deck(self):
        for deck in self._mapping:
            if deck.deck_id == self._current_deck:
                return deck

    def update_key(self, key_id: int):
        mapping_key = self.get_mapping_key(key_id)
        state = self._udp.get_dref_value(mapping_key.state_dataref)
        if mapping_key.translate_dataref:
            translator = get_translator(
                mapping_key.translate_dataref, translators=DREF_TRANSLATORS
            )
            state = translator(state)
        secondary_dref = self._get_secondary_dref(mapping_key)
        secondary_state = {"secondary_state": secondary_dref} if secondary_dref else {}
        image = KEY_TYPES[mapping_key.key_type](
            state=state, **secondary_state, **mapping_key.key_options
        )
        self._deck.update_key(mapping_key.key_id, image)

    def _get_secondary_dref(self, mapping_key: DeckKeyMapping):
        if mapping_key.secondary_dataref:
            secondary_state = self._udp.get_dref_value(mapping_key.secondary_dataref)

            if mapping_key.translate_secondary_dataref:
                translator = get_translator(
                    mapping_key.translate_secondary_dataref,
                    translators=DREF_TRANSLATORS,
                )
                secondary_state = translator(secondary_state)

            return secondary_state

    def update_faults(self):
        for deck in self._mapping:
            deck.has_fault = False
            for mapping_key in deck.keys:
                if (
                    # Assume default is FAULT
                    "secondary_text" not in mapping_key.key_options
                    or mapping_key.secondary_dataref_is_fault
                ):
                    secondary_dref = self._get_secondary_dref(mapping_key)
                    if secondary_dref:
                        deck.has_fault = True
        self._update_home()

    def clear(self):
        for i in range(self._deck.key_count):
            image = create_image()
            self._deck.update_key(i, image)

    def close(self):
        self._udp.close()
        self._fcu.close()
        self._deck.close()


def run():
    decks = Decks()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        decks.close()


if __name__ == "__main__":
    run()
