"""Run with python tests/ui_regression.py against a running Vite server.

Requires Playwright with Chromium. Set GLM_UI_URL to override port 5173.
"""

import os
import unittest
from contextlib import contextmanager

from playwright.sync_api import expect, sync_playwright


BASE_URL = os.environ.get("GLM_UI_URL", "http://127.0.0.1:5173")
RECORDINGS = [
    {
        "id": str(index),
        "filename": f"recording-{index}.wav",
        "created_at": "2025-01-01T00:00:00",
        "duration": 10,
        "prompt_text": "录音测试文本",
    }
    for index in range(24)
]


class UIRegression(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        playwright = sync_playwright().start()
        cls.addClassCleanup(playwright.stop)
        cls.browser = playwright.chromium.launch(
            args=["--use-fake-device-for-media-stream", "--use-fake-ui-for-media-stream"]
        )
        cls.addClassCleanup(cls.browser.close)

    @contextmanager
    def page(self, width=1280, height=720, asr_ready=False):
        page = self.browser.new_page(
            viewport={"width": width, "height": height},
            permissions=["microphone"] if asr_ready else [],
        )
        page.set_default_timeout(8_000)
        page.route("**/api/models", lambda route: route.fulfill(json={
            "tts": {"state": "ready", "total_bytes": 8_900_000_000},
            "asr": {"state": "ready" if asr_ready else "missing", "total_bytes": 4_500_000_000},
        }))
        page.route("**/api/recordings", lambda route: route.fulfill(json={"recordings": RECORDINGS}))
        page.route("**/audio/recordings/**", lambda route: route.fulfill(status=204))
        try:
            yield page
        finally:
            page.close()

    def open_clone(self, page):
        page.goto(BASE_URL, wait_until="networkidle")
        page.get_by_role("button", name="录音管理").click()
        trigger = page.get_by_role("button", name="克隆音色", exact=True).last
        trigger.click()
        dialog = page.get_by_role("dialog", name="语音克隆")
        expect(dialog).to_be_visible()
        return trigger, dialog

    def test_model_workspace_explains_offline_state_and_recovers(self):
        for width, height in [(848, 400), (320, 640)]:
            with self.subTest(width=width, height=height), self.page(width, height) as page:
                connected = False
                models = {
                    "asr": {"state": "missing", "total_bytes": 4_500_000_000},
                    "tts": {"state": "ready", "total_bytes": 8_900_000_000},
                }

                def respond(route):
                    if connected:
                        route.fulfill(json=models)
                    else:
                        route.fulfill(status=503)

                def prepare(route):
                    models["asr"].update(
                        state="downloading", downloaded_bytes=2_250_000_000, file="model.bin",
                    )
                    route.fulfill(json=models["asr"])

                page.route("**/api/models", respond)
                page.route("**/api/models/asr/prepare", prepare)
                page.goto(BASE_URL, wait_until="networkidle")
                main = page.get_by_role("main")
                status = page.get_by_role("status")
                expect(status).to_have_text("本地服务离线")
                expect(main.get_by_role("alert")).to_contain_text("python asr-python/backend/main.py")
                expect(main.get_by_text("等待连接")).to_have_count(2)
                expect(main.get_by_role("button")).to_have_count(0)
                asr_card = main.get_by_role("article", name="实时转录")
                tts_card = main.get_by_role("article", name="语音克隆")
                asr = asr_card.bounding_box()
                tts = tts_card.bounding_box()
                navigation = page.get_by_role("navigation", name="工作台")
                nav = navigation.bounding_box()
                self.assertAlmostEqual(asr["x"], nav["x"], delta=1)
                if width == 320:
                    self.assertAlmostEqual(asr["x"], tts["x"], delta=1)
                    self.assertGreater(tts["y"], asr["y"] + asr["height"])
                else:
                    expect(asr_card).to_be_in_viewport(ratio=1)
                    expect(tts_card).to_be_in_viewport(ratio=1)
                    self.assertAlmostEqual(asr["y"], tts["y"], delta=1)
                    self.assertGreater(tts["x"], asr["x"] + asr["width"])
                for tab in navigation.get_by_role("button").all():
                    expect(tab).to_be_in_viewport(ratio=1)
                    self.assertAlmostEqual(tab.bounding_box()["y"], nav["y"], delta=1)

                connected = True
                expect(status).to_have_text("本地服务在线")
                expect(main.get_by_role("alert")).to_have_count(0)
                models_tab = navigation.get_by_role("button", name="模型管理")
                models_tab.click()
                expect(models_tab).to_have_attribute("aria-current", "page")
                expect(main.get_by_text("已就绪", exact=True)).to_be_visible()
                main.get_by_role("button", name="一键下载").click()
                expect(main.get_by_role("progressbar")).to_have_attribute("value", "2250000000")
                expect(main.get_by_text("50.0% · model.bin")).to_be_visible()

    def test_voice_card_fits_narrow_workspace(self):
        with self.page(320, 640) as page:
            page.route("**/api/cloned_voices", lambda route: route.fulfill(json={"cloned_voices": [
                {"id": "voice", "filename": "voice.wav", "created_at": "2025-01-01T00:00:00",
                 "source_recording": {"filename": "recording-with-a-long-name.wav"}, "text": "合成测试文本"},
            ]}))
            page.goto(BASE_URL, wait_until="networkidle")
            page.get_by_role("button", name="我的声音").click()
            main = page.get_by_role("main")
            for name in ["下载", "删除"]:
                expect(main.get_by_role("button", name=name)).to_be_in_viewport(ratio=1)
            self.assertTrue(main.evaluate("el => el.scrollWidth === el.clientWidth"))

    def test_dialog_stays_in_viewport_after_scrolling(self):
        for width, height in [(1280, 720), (320, 640), (736, 280), (320, 300)]:
            with self.subTest(width=width, height=height), self.page(width, height) as page:
                trigger, dialog = self.open_clone(page)
                listing = page.locator(".recordings-view")
                scroll_top = listing.evaluate("el => el.scrollTop")
                self.assertGreater(scroll_top, 0)

                bounds = dialog.bounding_box()
                self.assertAlmostEqual(bounds["x"] + bounds["width"] / 2, width / 2, delta=1)
                self.assertAlmostEqual(bounds["y"] + bounds["height"] / 2, height / 2, delta=1)
                expect(dialog.get_by_role("heading")).to_be_in_viewport(ratio=1)
                expect(dialog.get_by_role("button", name="开始克隆")).to_be_in_viewport(ratio=1)
                prompt = dialog.get_by_role("textbox", name="录音中说的话（用于音色提取）")
                target = dialog.get_by_role("textbox", name="要合成的文本")
                expect(prompt).to_have_value("录音测试文本")
                if width != 320 or height != 300:
                    expect(target).to_be_in_viewport(ratio=1)
                target.fill("合成测试文本")
                page.keyboard.press("Escape")
                expect(dialog).to_have_count(0)
                expect(trigger).to_be_focused()
                self.assertEqual(listing.evaluate("el => el.scrollTop"), scroll_top)

                trigger.click()
                page.mouse.click(2, 2)
                expect(dialog).to_have_count(0)

    def test_clone_failure_allows_retry_and_success_closes_dialog(self):
        with self.page() as page:
            trigger, dialog = self.open_clone(page)
            page.route("**/api/recordings/*/prompt_text", lambda route: route.fulfill(json={}))
            submit = dialog.get_by_role("button", name="开始克隆")
            target = dialog.get_by_role("textbox", name="要合成的文本")
            target.fill("合成测试文本")

            page.route("**/api/clone_voice", lambda route: route.fulfill(json={"task_id": "test"}))
            progress_url = "**/api/clone_voice/test/progress"
            page.route(progress_url, lambda route: route.fulfill(json={
                "status": "error", "progress": 0, "message": "测试错误",
            }))
            submit.click()
            expect(dialog.get_by_role("alert")).to_have_text("测试错误")
            expect(target).to_be_enabled()
            expect(target).to_have_value("合成测试文本")

            page.unroute(progress_url)
            page.route(progress_url, lambda route: route.fulfill(json={
                "status": "completed", "progress": 100, "message": "已完成",
            }))
            submit.click()
            expect(dialog.get_by_role("progressbar")).to_have_attribute("value", "100")
            page.keyboard.press("Escape")
            expect(dialog).to_be_visible()
            expect(dialog).to_have_count(0)
            expect(trigger).to_be_focused()

    def test_visualizer_tracks_audio_and_respects_reduced_motion(self):
        with self.page(asr_ready=True) as page:
            page.route_web_socket("**/ws/transcribe", lambda socket: socket.on_message(
                lambda message: socket.send('{"type":"stopped"}') if message == '{"type":"stop"}' else None
            ))
            page.add_init_script("""
                window.audioSamplesRead = 0;
                const readSamples = AnalyserNode.prototype.getByteTimeDomainData;
                AnalyserNode.prototype.getByteTimeDomainData = function(samples) {
                    readSamples.call(this, samples);
                    window.audioSamplesRead++;
                };
            """)
            page.goto(BASE_URL, wait_until="networkidle")
            canvas = page.locator(".visualizer-canvas")
            expect(canvas).to_be_visible()
            idle = canvas.evaluate("el => el.toDataURL()")
            page.wait_for_function(
                "frame => document.querySelector('.visualizer-canvas').toDataURL() !== frame",
                arg=idle,
            )

            page.get_by_role("button", name="开始录音").click()
            page.wait_for_function("window.audioSamplesRead > 2")
            page.get_by_role("button", name="停止录音").click()
            expect(page.get_by_role("button", name="开始录音")).to_be_enabled()

            page.emulate_media(reduced_motion="reduce")
            frozen, stable = canvas.evaluate("""async el => {
                await new Promise(resolve => requestAnimationFrame(resolve));
                const frame = el.toDataURL();
                for (let i = 0; i < 12; i++) {
                    await new Promise(resolve => requestAnimationFrame(resolve));
                }
                return [frame, frame === el.toDataURL()];
            }""")
            self.assertTrue(stable)
            self.assertNotEqual(frozen, idle)


if __name__ == "__main__":
    unittest.main()
