import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import portfolio_loader as loader

class CatalogTests(unittest.TestCase):
    def test_menu_promotion_keeps_directory_id_and_original_number(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);poc=root/'PoC';portfolio=root/'projects';portfolio.mkdir()
            for no, group in [(7,'portfolio'),(8,'portfolio'),(10,'portfolio'),(11,'poc')]:
                p=poc/f'{no:02d}-example';p.mkdir(parents=True)
                (p/'project.json').write_text(json.dumps({'id':f'poc{no}','menu_group':group,'order':-no}))
            with patch.object(loader,'POC_DIR',poc),patch.object(loader,'PROJECTS_DIR',portfolio):
                promoted=loader.load_projects();remaining=loader.load_poc_projects()
                self.assertEqual({(p['id'],p['no']) for p in promoted},{('poc7','07'),('poc8','08'),('poc10','10')})
                self.assertEqual([(p['id'],p['no']) for p in remaining],[('poc11','11')])
                self.assertTrue((poc/'07-example/project.json').is_file())
                self.assertEqual(list(portfolio.iterdir()),[])
    def test_definition_only_project_shows_structure_without_executable_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);poc=root/'PoC';p=poc/'04-master-press';p.mkdir(parents=True)
            (p/'project.json').write_text(json.dumps({'id':'master-press','definition_only':True,'entry_file':'STRUCTURE.txt'}))
            (p/'STRUCTURE.txt').write_text('과거 폴더 구조')
            with patch.object(loader,'POC_DIR',poc),patch.object(loader,'PROJECTS_DIR',root/'projects'):
                item=loader.load_poc_projects()[0]
                self.assertEqual(item['no'],'04');self.assertEqual(item['code'],'과거 폴더 구조')
