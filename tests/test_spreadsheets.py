"""Local import/search contract checks using disposable source fixtures."""
import io
import json
import struct
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from app.main import app
from app.services import spreadsheets as service


def xlsx_fixture():
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w') as book:
        book.writestr('[Content_Types].xml', '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>')
        book.writestr('xl/workbook.xml', '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Orders" sheetId="1" r:id="rId1"/><sheet name="Other" sheetId="2" r:id="rId2"/></sheets></workbook>')
        book.writestr('xl/_rels/workbook.xml.rels', '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet2.xml"/></Relationships>')
        book.writestr('xl/worksheets/sheet1.xml', '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData><row r="1"><c r="A1" t="inlineStr"><is><t>Order</t></is></c></row><row r="3"><c r="A3" t="inlineStr"><is><t>00123</t></is></c><c r="B3"><f>1+2</f><v>3</v></c><c r="C3"><f>5+5</f></c></row></sheetData></worksheet>')
        book.writestr('xl/worksheets/sheet2.xml', '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData><row r="2"><c r="D2" t="inlineStr"><is><t>Unique second sheet</t></is></c></row></sheetData></worksheet>')
    return output.getvalue()


def xls_fixture():
    # Minimal BIFF5 stream: one sheet with a numeric cell, no executable code.
    def record(code, payload=b''):
        return struct.pack('<HH', code, len(payload)) + payload
    def bof(kind):
        return record(0x809, struct.pack('<HHHH', 0x500, kind, 0x096c, 1993))
    prefix = bof(5) + record(0x42, struct.pack('<H', 1252)) + record(0xe0, bytes(16))
    bounds = record(0x85, struct.pack('<IBBB', 0, 0, 0, 6) + b'Orders')
    offset = len(prefix) + len(bounds) + 4
    bounds = record(0x85, struct.pack('<IBBB', offset, 0, 0, 6) + b'Orders')
    sheet = bof(0x10) + record(0x200, struct.pack('<HHHHH', 0, 1, 0, 1, 0))
    sheet += record(0x203, struct.pack('<HHHd', 0, 0, 0, 12345)) + record(0x0a)
    return prefix + bounds + record(0x0a) + sheet


class SpreadsheetTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = patch.object(service, 'ROOT', Path(self.temp.name))
        self.root.start()
        # No lifespan: do not start the real processing queue or repair workers.
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        self.root.stop()
        self.temp.cleanup()

    def upload(self, name, content):
        response = self.client.post('/api/spreadsheets/upload', files={'files': (name, content)})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['errors'], [])
        return response.json()['files'][0]['id']

    def test_csv_search_paging_and_original(self):
        content = ('ID,Company\r\n00123,"Alpha, Inc"\r\n' + '\r\n'.join(f'{i},Match' for i in range(120))).encode()
        file_id = self.upload('Orders.csv', content)
        rows = self.client.get(f'/api/spreadsheets/{file_id}/rows', params={'query': '00123'}).json()['rows']
        self.assertEqual(rows[0]['row'], 2)
        self.assertEqual(rows[0]['cells'][0]['address'], 'A2')
        self.assertEqual(rows[0]['cells'][0]['value'], '00123')
        result = service.table(file_id, query='Match', offset=100)
        self.assertEqual(result['total'], 120)
        self.assertEqual(len(result['rows']), 20)
        self.assertIn('A2', service.cards('00123')[0]['match_preview'])
        self.assertEqual(len(service.cards('ORDERS.CSV')), 1)
        download = self.client.get(f'/api/spreadsheets/{file_id}/download')
        self.assertEqual(download.content, content)
        self.assertIn('attachment', download.headers['content-disposition'])
        self.assertNotEqual(file_id, self.upload('Orders.csv', content))

    def test_xlsx_sheets_coordinates_and_cached_formulas(self):
        file_id = self.upload('Workbook.xlsx', xlsx_fixture())
        result = service.table(file_id, query='00123')
        self.assertEqual(result['rows'][0]['row'], 3)
        self.assertEqual(result['rows'][0]['cells'][1]['value'], '3')
        self.assertTrue(result['warnings'])
        result = service.table(file_id, query='second sheet')
        self.assertEqual(result['rows'][0]['sheet'], 'Other')
        self.assertEqual(result['rows'][0]['cells'][0]['address'], 'D2')
        self.assertEqual(service.table(file_id, sheet=0, query='second sheet')['total'], 0)

    def test_xls_saved_values(self):
        file_id = self.upload('Legacy.xls', xls_fixture())
        self.assertEqual(service.table(file_id)['rows'][0]['cells'][0]['value'], '12345')

    def test_validation_and_no_partial_index(self):
        response = self.client.post('/api/spreadsheets/upload', files={'files': ('broken.xlsx', b'not a workbook')})
        self.assertTrue(response.json()['errors'])
        self.assertEqual(service.cards(), [])
        self.assertEqual(self.client.get('/api/spreadsheets/missing/rows').status_code, 404)
        self.assertEqual(self.client.get('/api/spreadsheets/missing/rows?limit=999').status_code, 422)
        self.assertEqual(service.display(123, '00000'), '00123')

    def test_permanent_delete_requires_confirmation_and_keeps_other_files(self):
        for name, content in [('a.csv', b'A,B\n1,2'), ('a.xlsx', xlsx_fixture()), ('a.xls', xls_fixture())]:
            file_id = self.upload(name, content)
            other = self.upload(name, content)
            path, _ = service.original(file_id)
            self.assertEqual(self.client.delete(f'/api/spreadsheets/{file_id}').status_code, 400)
            self.assertTrue(path.exists())
            self.assertEqual(self.client.delete(f'/api/spreadsheets/{file_id}?confirm=true').status_code, 200)
            self.assertFalse(path.exists())
            self.assertEqual(self.client.get(f'/api/spreadsheets/{file_id}/rows').status_code, 404)
            self.assertEqual(self.client.get(f'/api/spreadsheets/{file_id}/download').status_code, 404)
            self.assertEqual(self.client.get(f'/api/spreadsheets/{other}/download').content, content)
            with service.connect() as db:
                self.assertEqual(db.execute('SELECT count(*) FROM rows WHERE file_id=?', (file_id,)).fetchone()[0], 0)
                self.assertEqual(db.execute('SELECT count(*) FROM sheets WHERE file_id=?', (file_id,)).fetchone()[0], 0)
            db.close()

    def test_delete_rejects_path_outside_file_folder(self):
        file_id = self.upload('a.csv', b'A,B\n1,2')
        other = self.upload('b.csv', b'C,D\n3,4')
        other_path, _ = service.original(other)
        with service.connect() as db:
            db.execute('UPDATE files SET path=? WHERE id=?', (str(other_path.relative_to(service.ROOT)), file_id))
        db.close()
        self.assertEqual(self.client.delete(f'/api/spreadsheets/{file_id}?confirm=true').status_code, 400)
        self.assertTrue(other_path.exists())
        self.assertEqual(len(service.cards()), 1)

    def test_refresh_removes_record_for_manually_deleted_spreadsheet_folder(self):
        file_id = self.upload('manual-delete.csv', b'ID\n007')
        path, _ = service.original(file_id)
        path.unlink()
        self.assertEqual(service.remove_missing_spreadsheet_records(), 1)
        self.assertEqual(self.client.get(f'/api/spreadsheets/{file_id}/rows').status_code, 404)
        self.assertEqual(service.cards(), [])


if __name__ == '__main__':
    unittest.main()
