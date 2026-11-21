import tempfile
import unittest
from pathlib import Path
from PIL import Image, ImageDraw
from flow import capture_step, locate, patch_of, load, save


class FlowTest(unittest.TestCase):
    def setUp(self):
        self.screen = Image.new("RGB",(640,360),"white")
        ImageDraw.Draw(self.screen).rectangle((80,70,144,102),fill="navy")
        ImageDraw.Draw(self.screen).text((87,79),"Wallet",fill="white")
        self.step = capture_step(self.screen,110,86,.4)
        self.patch = patch_of(self.step)

    def test_relocated(self):
        scene = Image.new("RGB",(840,500),"white")
        scene.paste(self.screen,(91,110))
        self.assertEqual(locate(scene,self.patch,self.step["offset"]),(201,196))

    def test_missing_or_duplicate(self):
        scene = Image.new("RGB",self.screen.size,"white")
        self.assertIsNone(locate(scene,self.patch,self.step["offset"]))
        scene.paste(self.patch,(50,30))
        scene.paste(self.patch,(250,30))
        self.assertIsNone(locate(scene,self.patch,self.step["offset"]))

    def test_blank(self):
        self.assertIsNone(locate(self.screen,Image.new("RGB",(50,50),"white"),[5,5]))

    def test_disk(self):
        doc = dict(version=1,platform="darwin",app="demo",steps=[self.step])
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/"demo.json"
            save(path, doc)
            self.assertEqual(load(path),doc)
            self.step["delay"] = -1
            with self.assertRaises(ValueError):
                save(path,doc)
            self.assertEqual(load(path)["steps"][0]["delay"],.4)
