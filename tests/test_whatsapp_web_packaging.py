from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock
from urllib.parse import quote

import whatsapp
import main


class WhatsAppWebPackagingTests(unittest.TestCase):
    def test_frozen_runtime_diagnostic_cli_skips_database_and_ui(self) -> None:
        with (
            mock.patch("whatsapp.selenium_runtime_diagnostics") as diagnostics,
            mock.patch("main.database.initialize_database") as initialize_database,
            mock.patch("main.ft.run") as run_ui,
        ):
            result = main.cli(["--check-whatsapp-web-runtime"])

        self.assertEqual(result, 0)
        diagnostics.assert_called_once_with()
        initialize_database.assert_not_called()
        run_ui.assert_not_called()

    def test_runtime_diagnostics_loads_concrete_chrome_edge_and_manager(self) -> None:
        diagnostics = whatsapp.selenium_runtime_diagnostics()

        self.assertTrue(diagnostics["selenium_version"])
        self.assertEqual(
            diagnostics["chrome_driver_module"],
            "selenium.webdriver.chrome.webdriver",
        )
        self.assertEqual(
            diagnostics["edge_driver_module"],
            "selenium.webdriver.edge.webdriver",
        )
        self.assertTrue(Path(diagnostics["selenium_manager_path"]).is_file())

    def test_browser_options_keep_separate_persistent_profiles(self) -> None:
        config = whatsapp.WhatsAppConfig(
            delivery_mode=whatsapp.DELIVERY_MODE_WHATSAPP_WEB_EXPERIMENTAL,
            dry_run=False,
        )
        with tempfile.TemporaryDirectory() as temporary_directory:
            profile_root = Path(temporary_directory) / "whatsapp-profile"
            with mock.patch.object(whatsapp, "WEB_PROFILE_DIR", profile_root):
                chrome_provider = whatsapp.WhatsAppWebExperimentalProvider(config)
                chrome_options = chrome_provider._build_browser_options(
                    "chrome",
                    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                )
                edge_provider = whatsapp.WhatsAppWebExperimentalProvider(config)
                edge_options = edge_provider._build_browser_options(
                    "edge",
                    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
                )

        chrome_profile = profile_root / "chrome"
        edge_profile = profile_root / "edge"
        self.assertIn(f"--user-data-dir={chrome_profile}", chrome_options.arguments)
        self.assertIn(f"--user-data-dir={edge_profile}", edge_options.arguments)
        self.assertIn("--profile-directory=Default", chrome_options.arguments)
        self.assertIn("--profile-directory=Default", edge_options.arguments)
        self.assertNotEqual(chrome_profile, edge_profile)

    def test_start_driver_uses_concrete_class_without_webdriver_lazy_attribute(self) -> None:
        provider = whatsapp.WhatsAppWebExperimentalProvider(
            whatsapp.WhatsAppConfig(
                delivery_mode=whatsapp.DELIVERY_MODE_WHATSAPP_WEB_EXPERIMENTAL,
                dry_run=False,
            )
        )
        fake_driver = object()
        driver_class = mock.Mock(return_value=fake_driver)
        service_class = mock.Mock(return_value=object())
        options_class = mock.Mock()
        built_options = object()

        with (
            mock.patch.object(
                whatsapp,
                "_selenium_browser_components",
                return_value=(driver_class, service_class, options_class),
            ) as load_components,
            mock.patch.object(
                provider,
                "_resolve_browser_paths",
                return_value=(r"C:\drivers\chromedriver.exe", r"C:\chrome.exe"),
            ),
            mock.patch.object(
                provider,
                "_build_browser_options",
                return_value=built_options,
            ) as build_options,
        ):
            result = provider._start_browser_driver("chrome")

        self.assertIs(result, fake_driver)
        load_components.assert_called_once_with("chrome")
        service_class.assert_called_once_with(executable_path=r"C:\drivers\chromedriver.exe")
        build_options.assert_called_once_with(
            "chrome",
            r"C:\chrome.exe",
            options_class=options_class,
        )
        driver_class.assert_called_once_with(
            service=service_class.return_value,
            options=built_options,
        )

    def test_selenium_manager_resolves_both_supported_browsers(self) -> None:
        from selenium.webdriver.common.selenium_manager import SeleniumManager

        provider = whatsapp.WhatsAppWebExperimentalProvider()
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            driver_path = root / "driver.exe"
            browser_path = root / "browser.exe"
            driver_path.touch()
            browser_path.touch()

            for browser_name in ("chrome", "edge"):
                with self.subTest(browser=browser_name):
                    with mock.patch.object(
                        SeleniumManager,
                        "binary_paths",
                        return_value={
                            "driver_path": str(driver_path),
                            "browser_path": str(browser_path),
                        },
                    ) as binary_paths:
                        resolved = provider._resolve_browser_paths(browser_name)

                    self.assertEqual(resolved, (str(driver_path), str(browser_path)))
                    binary_paths.assert_called_once_with(["--browser", browser_name])

    def test_qr_state_and_mocked_text_send_flow(self) -> None:
        class QrDriver:
            def find_elements(self, _by: object, selector: str) -> list[object]:
                return [object()] if selector == "canvas" else []

            def find_element(self, _by: object, _selector: str) -> object:
                raise AssertionError("QR should be detected before reading body text")

        provider = whatsapp.WhatsAppWebExperimentalProvider(
            whatsapp.WhatsAppConfig(
                delivery_mode=whatsapp.DELIVERY_MODE_WHATSAPP_WEB_EXPERIMENTAL,
                dry_run=False,
            )
        )
        status, message = provider._page_state(QrDriver())
        self.assertEqual(status, whatsapp.WEB_STATUS_WAITING_QR)
        self.assertIn("QR Code", message)

        browser = mock.Mock()
        send_button = mock.Mock()
        contact = {"phone": "+55 (11) 99999-1234"}
        campaign = {"message": "Olá, teste sem envio real!", "media_path": ""}
        with (
            mock.patch.object(provider, "_ensure_connected_driver", return_value=browser),
            mock.patch.object(provider, "_wait_for_send_button", return_value=send_button),
            mock.patch("whatsapp.time.sleep"),
            mock.patch("whatsapp.random.uniform", return_value=0.0),
        ):
            result = provider.send_campaign_message(contact, campaign)

        expected_text = quote(campaign["message"])
        opened_url = browser.get.call_args.args[0]
        self.assertIn("phone=5511999991234", opened_url)
        self.assertIn(f"text={expected_text}", opened_url)
        send_button.click.assert_called_once_with()
        self.assertEqual(result.status, "enviado")
        self.assertEqual(
            result.delivery_mode,
            whatsapp.DELIVERY_MODE_WHATSAPP_WEB_EXPERIMENTAL,
        )

    def test_build_collects_lazy_modules_and_validates_frozen_archive(self) -> None:
        root = Path(__file__).resolve().parents[1]
        build_script = (root / "build.ps1").read_text(encoding="utf-8")

        self.assertIn(
            '"--pyinstaller-build-args=--collect-submodules=selenium"',
            build_script,
        )
        self.assertIn('"--check-whatsapp-web-runtime"', build_script)
        self.assertIn('"selenium.webdriver.chrome.webdriver"', build_script)
        self.assertIn('"selenium.webdriver.edge.webdriver"', build_script)
        self.assertIn('"selenium\\webdriver\\common\\windows\\selenium-manager.exe"', build_script)


if __name__ == "__main__":
    unittest.main()
