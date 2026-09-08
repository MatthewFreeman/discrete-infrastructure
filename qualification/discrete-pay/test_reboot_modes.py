"""Read-only qualification routing checks; no units, files or host are changed."""
import ast
import os
from pathlib import Path
from unittest.mock import patch

source=Path(__file__).with_name('reboot-test.py').read_text()
module=ast.parse(source)
# Execute declarations only: dispatch begins at action=sys.argv[1].
prefix=[]
for statement in module.body:
    if isinstance(statement,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='action' for t in statement.targets):
        break
    prefix.append(statement)
else:
    raise AssertionError('reboot dispatch boundary missing')
code=compile(ast.Module(body=prefix,type_ignores=[]),'reboot-mode-declarations','exec')
for mode,prefix_name,stem in [(None,'payqual-',''),('current-v0.9.10','payqual-','current-'),('paged-main','payqual-paged-','paged-')]:
    env={} if mode is None else {'DISCRETE_PAY_REBOOT_FIXTURE':mode}
    with patch.dict(os.environ,env,clear=True):
        values={};exec(code,values)
        assert values['PREFIX']==prefix_name
        assert values['TARGET']==prefix_name+'reboot.target'
        assert values['STATE'].name==stem+'reboot-state.json'
        assert values['EVIDENCE'].name==stem+'reboot-evidence.json'
        assert (os.environ.get('DISCRETE_PAY_QUALIFICATION_MODE')=='paged') == (mode=='paged-main')
with patch.dict(os.environ,{'DISCRETE_PAY_REBOOT_FIXTURE':'unexpected'},clear=True):
    try:exec(code,{})
    except AssertionError:pass
    else:raise AssertionError('unknown mode accepted')
print('PASS: legacy/current/paged routing and invalid-mode refusal; no host mutation')
