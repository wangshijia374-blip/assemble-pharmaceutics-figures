"""Execute the ES3 serialization used by Illustrator with hostile text fixtures."""
import json
import shutil
import subprocess

import pytest

from pharmfig.typography import _JS_COMMON


def test_js_audit_json_roundtrips_quotes_paths_and_unicode(tmp_path):
    node = shutil.which('node')
    if not node:
        pytest.skip('Node is only used to validate generated ExtendScript serialization')
    serializer = _JS_COMMON.split('function write(')[0]
    payload = {'source': 'D:\\folder\\figure.ai', 'text': 'α "quoted"\nnext\tline', 'sizes':[8,12]}
    script=tmp_path/'serialization.js'
    script.write_text(serializer+'\nprocess.stdout.write(json('+json.dumps(payload)+'));',encoding='utf-8')
    result=subprocess.run([node,str(script)],capture_output=True,text=True,encoding='utf-8',check=True)
    assert json.loads(result.stdout)==payload
