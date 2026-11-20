import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from rehearsal.json_sources import snapshot_json, compare_json, inspect_json_sources


class JsonSourceTests(unittest.TestCase):
    def test_pointer_escaping_array_positions_and_types(self):
        value=snapshot_json(b'{"a/b":{"~key":[true,null,1,"1",{},[]]}}')
        nodes={n['pointer']:n for n in value['nodes']}
        self.assertEqual(nodes['/a~1b/~0key/0']['kind'],'boolean')
        self.assertEqual(nodes['/a~1b/~0key/1']['kind'],'null')
        self.assertEqual(nodes['/a~1b/~0key/2']['kind'],'number')
        self.assertEqual(nodes['/a~1b/~0key/3']['kind'],'string')
        self.assertEqual(nodes['/a~1b/~0key/4']['kind'],'object')
        self.assertEqual(nodes['/a~1b/~0key/5']['kind'],'array')
        self.assertEqual(len({n['anchor'] for n in nodes.values()}),len(nodes))

    def test_object_order_whitespace_and_string_escapes_preserve_structure(self):
        result=compare_json(b'{"a":"A","b":2}',b'{ "b":2, "a":"\\u0041" }')
        self.assertTrue(result['structure_equal']);self.assertFalse(result['raw_bytes_equal'])
        self.assertTrue(all(c['change']=='equal' for c in result['changes']))

    def test_number_precision_and_spelling_are_not_coerced(self):
        for old,new in (('1','1.0'),('0.10000000000000001','0.1'),('true','1'),('1e9999','1e9998')):
            result=compare_json(old.encode(),new.encode())
            self.assertFalse(result['structure_equal'])
            self.assertEqual(result['changes'][0]['change'],'replace')
        self.assertEqual(snapshot_json(b'0.10000000000000001')['nodes'][0]['value'],'0.10000000000000001')

    def test_null_missing_and_array_shift_are_explicit(self):
        result=compare_json(b'{"x":null}',b'{}')
        deleted=next(c for c in result['changes'] if c['pointer']=='/x')
        self.assertEqual(deleted['change'],'delete');self.assertEqual(deleted['before']['kind'],'null');self.assertIsNone(deleted['after'])
        shifted=compare_json(b'[1,2]',b'[0,1,2]')
        self.assertEqual([c['change'] for c in shifted['changes']],['equal','replace','replace','insert'])

    def test_invalid_and_resource_excess_fail_closed(self):
        invalid=[b'{"a":1,"a":2}',b'NaN',b'Infinity',b'\xff',b'"\\ud800"',b'[',b' '*262145,
                 ('['*66+'0'+']'*66).encode(),json.dumps({str(i):i for i in range(4097)}).encode()]
        for raw in invalid:
            with self.subTest(length=len(raw)),self.assertRaises(ValueError):snapshot_json(raw)

    def test_node_hashes_bind_pointer_and_typed_value(self):
        from rehearsal.storage import sha
        value=snapshot_json(b'{"a":1,"b":1}')
        for node in value['nodes']:
            self.assertEqual(node['sha256'],sha({'kind':node['kind'],'value':node['value']}))
            self.assertEqual(node['anchor'],sha({'document':value['structure_sha256'],'pointer':node['pointer'],'node':node['sha256']}))
        self.assertNotEqual(value['nodes'][1]['anchor'],value['nodes'][2]['anchor'])

    def test_local_read_cli_and_drift_do_not_write_or_disclose_paths(self):
        from inspect_json_sources import main
        import rehearsal.json_sources as sources
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);a=root/'a.json';b=root/'b.json';a.write_bytes(b'{"limit":14}');b.write_bytes(b'{"limit":30}')
            before={p:p.read_bytes() for p in (a,b)}
            result=inspect_json_sources(a,b)
            self.assertEqual(result['provenance'],'unverified_local_files');self.assertFalse(result['business_validated'])
            self.assertNotIn(str(root),json.dumps(result))
            self.assertEqual(before,{p:p.read_bytes() for p in before})
            out=io.StringIO()
            with contextlib.redirect_stdout(out):self.assertEqual(main(['--before',str(a),'--after',str(b)]),0)
            self.assertFalse(json.loads(out.getvalue())['structure_equal'])
            original=sources._read_local_markdown
            def changed(path,**kwargs):
                result=original(path,**kwargs)
                if Path(path)==b:a.write_bytes(b'{}')
                return result
            with patch.object(sources,'_read_local_markdown',changed),self.assertRaises(ValueError):inspect_json_sources(a,b)
            err=io.StringIO();b.write_bytes(b'invalid-private-source')
            with contextlib.redirect_stderr(err):self.assertEqual(main(['--before',str(a),'--after',str(b)]),1)
            self.assertNotIn('private-source',err.getvalue());self.assertNotIn(str(root),err.getvalue())
