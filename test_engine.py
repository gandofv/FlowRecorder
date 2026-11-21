import sys
import unittest
from unittest.mock import Mock, patch
import importlib.util
from pathlib import Path
from threading import Event
from PIL import Image, ImageDraw
from flow import capture_step

class PlaybackTest(unittest.TestCase):
    def setUp(self):
        self.device = Mock()
        spec = importlib.util.spec_from_file_location("engine_tested",Path(__file__).with_name("engine.py"))
        self.engine = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, desktop=self.device):
            spec.loader.exec_module(self.engine)
        self.engine.countdown = lambda *_: True
        self.device.front.return_value = "demo"
        self.device.target_at.return_value = True
        im = Image.new("RGB",(320,240),"white")
        ImageDraw.Draw(im).text((72,66),"Balance",fill="black")
        self.device.screenshot.return_value = im
        step = capture_step(im,86,73,0)
        self.doc = dict(app="demo",platform=sys.platform,steps=[step,step])
        self.stop = Event()

    def run_flow(self):
        self.engine.play(self.doc,self.stop,lambda *_:None)

    def test_two_clicks(self):
        self.run_flow()
        self.assertEqual(self.device.click.call_count,2)
        self.device.click.assert_called_with((86,73))

    def test_switched(self):
        self.device.front.side_effect = ["demo","other"]
        with self.assertRaises(ValueError):
            self.run_flow()
        self.device.click.assert_not_called()

    def test_blocked(self):
        self.device.target_at.return_value = False
        with self.assertRaises(ValueError):
            self.run_flow()
        self.device.click.assert_not_called()

    def test_stopped(self):
        self.device.click.side_effect = lambda *_:self.stop.set()
        self.run_flow()
        self.assertEqual(self.device.click.call_count,1)
