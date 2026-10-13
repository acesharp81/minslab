import io
import unittest
import zipfile
from html import escape

from backend.demolition import file_index, parse_demolition
from backend.sources import SOURCES


SOURCE = next(source for source in SOURCES if source['id'] == 'molit_demolition')


def workbook(total=13322):
    cells = [
        ['2024년 멸실 주택수'],
        ['시도', '계', '단독주택', '다가구', '연립주택', '다세대주택', '아파트'],
        ['전국', '38225', '9314', '9755', '2771', '5614', '10771'],
        ['서울', str(total), '4452', '3698', '1079', '1793', '2300'],
        ['경기', '24903', '4862', '6057', '1692', '3821', '8471'],
    ] + [['기타'] for _ in range(11)]
    lines = []
    for number, row in enumerate(cells, 1):
        xml = ''.join(f'<c r="{chr(65 + col)}{number}" t="inlineStr"><is><t>{escape(value)}</t></is></c>'
                      for col, value in enumerate(row))
        lines.append(f'<row r="{number}">{xml}</row>')
    xml = '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>' + ''.join(lines) + '</sheetData></worksheet>'
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w') as archive:
        archive.writestr('xl/worksheets/sheet1.xml', xml)
    return output.getvalue()


class DemolitionTests(unittest.TestCase):
    def test_province_totals_are_preserved_and_not_municipalized(self):
        rows = parse_demolition(workbook(), SOURCE, 2024, 'https://www.index.go.kr/file.xlsx')
        self.assertEqual([(row['region'], row['units']) for _, _, row in rows],
                         [('서울특별시', 13322), ('경기도', 24903)])
        self.assertEqual(rows[0][2]['statistic_metric'], '멸실')
        self.assertNotIn('municipality', rows[0][2])
        with self.assertRaises(ValueError):
            parse_demolition(workbook(13323), SOURCE, 2024, 'https://www.index.go.kr/file.xlsx')

    def test_file_index_requires_all_historical_years(self):
        html = ''.join(f'<a href="javascript:fn_downLoadApndFile(\'{year}\',\'2839\',\'1\')">{year-2000}년_멸실주택수_통계누리.xlsx</a>'
                       for year in range(2018, 2025))
        self.assertEqual(len(file_index(html.encode())), 7)
        with self.assertRaises(ValueError):
            file_index(html.replace('18년_멸실', '18년_다른자료').encode())
