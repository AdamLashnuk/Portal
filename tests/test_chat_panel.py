import os
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication, QWidget

from app.chat_panel import ChatPanel
from app import utils as portal_utils


class FakeBrowser:
    def __init__(self):
        self.properties = {}
        self.loaded_urls = []

    def property(self, name):
        return self.properties.get(name)

    def setProperty(self, name, value):
        self.properties[name] = value

    def setUrl(self, url):
        self.loaded_urls.append(url.toString())


class FakeSignal:
    def __init__(self):
        self.callbacks = []

    def connect(self, callback):
        self.callbacks.append(callback)

    def emit(self):
        for callback in list(self.callbacks):
            callback()


class FakeProfile:
    def __init__(self):
        self.destroyed = FakeSignal()
        self.delete_requested = False

    def deleteLater(self):
        self.delete_requested = True


class FakeAnimation:
    def __init__(self):
        self.finished = FakeSignal()
        self.delete_requested = False

    def deleteLater(self):
        self.delete_requested = True


class FakeWinReg:
    HKEY_CURRENT_USER = object()
    KEY_SET_VALUE = 1
    KEY_READ = 2
    REG_SZ = 1

    def __init__(self):
        self.values = {}

    def OpenKey(self, *_args):
        return self

    def SetValueEx(self, _key, name, *_args):
        self.values[name] = _args[-1]

    def DeleteValue(self, _key, name):
        if name not in self.values:
            raise FileNotFoundError
        del self.values[name]

    def QueryValueEx(self, _key, name):
        if name not in self.values:
            raise FileNotFoundError
        return self.values[name], self.REG_SZ

    def CloseKey(self, _key):
        pass


class ChatPanelStateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.settings_dir = tempfile.TemporaryDirectory()
        QSettings.setDefaultFormat(QSettings.IniFormat)
        QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, self.settings_dir.name)
        QSettings("MyLLMWidget", "Portal").clear()

    def tearDown(self):
        self.settings_dir.cleanup()

    def make_setup_only_panel(self):
        panel = ChatPanel.__new__(ChatPanel)
        QWidget.__init__(panel)
        panel.setup_window()
        return panel

    def test_default_provider_ids_survive_restart_and_repair_stale_current_id(self):
        settings = QSettings("MyLLMWidget", "Portal")
        settings.setValue("current_provider_id", "stale-id")

        first_panel = self.make_setup_only_panel()
        first_ids = [llm["id"] for llm in first_panel.active_llms]
        self.assertIn(first_panel.current_provider_id, first_ids)

        second_panel = self.make_setup_only_panel()
        second_ids = [llm["id"] for llm in second_panel.active_llms]
        self.assertEqual(first_ids, second_ids)
        self.assertEqual(first_panel.current_provider_id, second_panel.current_provider_id)

    def test_provider_browser_loads_only_once(self):
        browser = FakeBrowser()
        browser.setProperty("portal_url", "https://example.com")
        browser.setProperty("portal_loaded", False)

        ChatPanel.ensure_browser_loaded(browser)
        ChatPanel.ensure_browser_loaded(browser)

        self.assertEqual(browser.loaded_urls, ["https://example.com"])

    def test_startup_marks_only_the_current_provider_for_loading(self):
        load_requests = []

        def add_fake_browser(panel, llm_id, _url, load_immediately=False):
            browser = QWidget()
            panel.browsers[llm_id] = browser
            panel.browser_stack.addWidget(browser)
            load_requests.append((llm_id, load_immediately))

        with (
            patch.object(ChatPanel, "apply_keybinds"),
            patch.object(ChatPanel, "create_browser_profile", return_value=None),
            patch.object(ChatPanel, "add_browser_to_stack", add_fake_browser),
        ):
            panel = ChatPanel()

        requested_ids = [llm_id for llm_id, should_load in load_requests if should_load]
        self.assertEqual(requested_ids, [panel.current_provider_id])

    def test_isolated_profile_path_cannot_escape_its_root(self):
        with self.assertRaises(ValueError):
            ChatPanel.isolated_profile_storage_path(os.path.join("..", "outside"))

    def test_profile_is_released_only_after_its_last_tab_is_deleted(self):
        profile = FakeProfile()
        removed_paths = []
        panel = type("PanelState", (), {})()
        panel.active_llms = [{"profile_id": "shared-profile"}]
        panel.extra_profiles = {"shared-profile": profile}
        panel.isolated_profile_storage_path = lambda profile_id: f"safe/{profile_id}"
        panel.remove_profile_storage = removed_paths.append

        ChatPanel.release_unused_profile(panel, "shared-profile")
        self.assertIn("shared-profile", panel.extra_profiles)

        panel.active_llms.clear()
        ChatPanel.release_unused_profile(panel, "shared-profile")
        self.assertNotIn("shared-profile", panel.extra_profiles)
        self.assertTrue(profile.delete_requested)

        profile.destroyed.emit()
        self.assertEqual(removed_paths, ["safe/shared-profile"])

    def test_finished_animation_is_released_and_scheduled_for_deletion(self):
        animation = FakeAnimation()
        panel = type("AnimationState", (), {})()
        panel.tab_animations = []
        panel.release_animation = lambda tracked: ChatPanel.release_animation(panel, tracked)

        ChatPanel.track_animation(panel, animation)
        self.assertEqual(panel.tab_animations, [animation])

        animation.finished.emit()
        self.assertEqual(panel.tab_animations, [])
        self.assertTrue(animation.delete_requested)

    def test_existing_installation_keeps_startup_disabled(self):
        settings = QSettings("MyLLMWidget", "Portal")
        settings.setValue("active_llms", "[]")
        fake_registry = FakeWinReg()

        with patch.object(portal_utils, "winreg", fake_registry):
            portal_utils.initialize_startup_default()

        self.assertNotIn(portal_utils.APP_NAME, fake_registry.values)
        self.assertTrue(settings.value(portal_utils.STARTUP_INITIALIZED_KEY, type=bool))

    def test_explicit_startup_off_survives_later_initialization(self):
        fake_registry = FakeWinReg()
        fake_registry.values[portal_utils.APP_NAME] = "Portal"

        with patch.object(portal_utils, "winreg", fake_registry):
            portal_utils.set_startup(False)
            portal_utils.initialize_startup_default()

        self.assertNotIn(portal_utils.APP_NAME, fake_registry.values)

    def test_new_installation_enables_startup_once(self):
        fake_registry = FakeWinReg()

        with patch.object(portal_utils, "winreg", fake_registry):
            portal_utils.initialize_startup_default()

        self.assertIn(portal_utils.APP_NAME, fake_registry.values)


if __name__ == "__main__":
    unittest.main()
