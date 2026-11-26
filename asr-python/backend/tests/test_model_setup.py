import hashlib
import os
import sys
import tempfile
import unittest
from array import array
from pathlib import Path
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from model_setup import ModelAsset, ModelFiles, ModelSetup


class ModelSetupTest(unittest.IsolatedAsyncioTestCase):
    async def test_download_retry_reuses_completed_file_and_loads_once(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            files = ModelFiles("test/model", "revision", {"config.json": 2, "model.bin": 4}, root)
            downloads = []
            loaded = []

            def download(file, progress):
                self.assertIn(f"/{files.repo}/resolve/{files.revision}/", file.url)
                downloads.append(file.path.name)
                if file.path.name == "model.bin" and downloads.count("model.bin") == 1:
                    raise OSError("interrupted")
                file.path.write_bytes(b"x" * file.size)
                progress(file.size)

            setup = ModelSetup(files, loaded.append)
            self.assertEqual(setup.status()["state"], "idle")
            with patch.object(ModelAsset, "download", autospec=True, side_effect=download):
                setup.start()
                with self.assertLogs("model_setup", "ERROR"):
                    await setup.task
                self.assertEqual(setup.status()["state"], "error")
                self.assertEqual(setup.status()["downloaded_bytes"], 2)
                self.assertFalse(setup.status()["installed"])

                setup.start()
                first_task = setup.task
                setup.start()
                self.assertIs(setup.task, first_task)
                await first_task

            self.assertEqual(downloads, ["config.json", "model.bin", "model.bin"])
            self.assertEqual(loaded, [root])
            self.assertEqual(setup.status()["state"], "ready")
            self.assertEqual(setup.status()["downloaded_bytes"], 6)

    async def test_existing_models_load_without_downloading(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "model.bin").write_bytes(b"1234")
            files = ModelFiles("test/model", "revision", {"model.bin": 4}, root)
            loaded = []
            setup = ModelSetup(files, loaded.append)
            self.assertEqual(setup.status()["state"], "installed")
            with patch.object(ModelAsset, "download") as download:
                setup.start()
                await setup.task
                download.assert_not_called()
            self.assertEqual(loaded, [root])


class ModelAssetTest(unittest.TestCase):
    def test_resumes_partial_download_and_verifies_hash(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            partial = root / ".model.bin.part"
            partial.write_bytes(b"abc")
            url = "https://example.com/model.bin"
            asset = ModelAsset(root / "model.bin", url, 6, hashlib.sha256(b"abcdef").hexdigest())
            response = MagicMock(status_code=206, headers={"Content-Range": "bytes 3-5/6"})
            response.__enter__.return_value = response
            response.iter_content.return_value = iter([b"de", b"f"])
            progress = []
            with patch("model_setup.requests.get", return_value=response) as download:
                asset.download(progress.append)
                self.assertEqual(download.call_args.kwargs["headers"]["Range"], "bytes=3-")
            self.assertEqual(progress, [3, 5, 6])
            self.assertEqual(asset.path.read_bytes(), b"abcdef")
            self.assertFalse(partial.exists())


class LocalApiTest(unittest.TestCase):
    def test_empty_library_and_model_status_start_without_weights(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {"GLM_ASR_DATA_DIR": folder}):
            from main import app, model_setups
            from cosyvoice.cli.frontend import TTSFrontEnd
            from llm.glmtts import GLMTTS
            from utils.file_utils import read_audio
            from utils.hift_util import HiFTInference

            self.assertTrue(callable(TTSFrontEnd))
            self.assertTrue(callable(GLMTTS))
            self.assertTrue(callable(HiFTInference))
            with TestClient(app, base_url="http://127.0.0.1") as client:
                self.assertEqual(client.get("/api/recordings").json(), {"recordings": []})
                if (Path(__file__).resolve().parents[2] / "frontend" / "dist").is_dir():
                    self.assertIn("GLM-ASR", client.get("/").text)
                self.assertEqual(set(client.get("/api/models").json()), {"asr", "tts"})
                self.assertTrue(all(setup.task is None for setup in model_setups.values()))
                self.assertEqual(client.post("/api/models/unknown/prepare").status_code, 404)
                denied = client.post("/api/models/asr/prepare", headers={"Origin": "https://example.com"})
                self.assertEqual(denied.status_code, 403)

                with patch.object(model_setups["asr"], "state", "ready"), patch(
                    "main.transcribe", return_value="最后一段"
                ), patch("main.get_speech_timestamps", return_value=[]):
                    with client.websocket_connect("ws://127.0.0.1/ws/transcribe") as socket:
                        socket.send_json({"type": "start", "sample_rate": 48000})
                        socket.send_bytes(array("f", [0.25] * 4800).tobytes())
                        socket.send_json({"type": "stop"})
                        self.assertEqual(socket.receive_text(), "最后一段")
                        self.assertEqual(socket.receive_json(), {"type": "stopped"})

                recordings = client.get("/api/recordings").json()["recordings"]
                self.assertEqual(len(recordings), 1)
                self.assertEqual(recordings[0]["prompt_text"], "最后一段")
                self.assertAlmostEqual(recordings[0]["duration"], 0.1)
                samples, rate = read_audio(recordings[0]["filepath"])
                self.assertEqual(rate, 16000)
                self.assertEqual(samples.shape, (1, 1600))
