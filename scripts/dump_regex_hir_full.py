#!/root/.pyenv/versions/3.14.3/bin/python3.14
import os
import sys

os.environ['PYTHONJITENABLE'] = '1'
os.environ['PYTHONJITDUMPFINALHIR'] = '1'
os.environ['PYTHONJITLOGFILE'] = '/tmp/regex_compile_hir_full.log'

import cinderx
cinderx.init()
import cinderx.jit as jit

print("JIT initialized:", cinderx.is_initialized(), flush=True)

import re

regexes = [
    ('Python|Perl|Java|C#|C\\+\\+|Go|Rust|Swift|Kotlin', 0),
    ('[a-z]+@[a-z]+\\.[a-z]{2,4}', 0),
    ('^(?:[A-Z0-9+/]{4})*(?:[A-Z0-9+/]{2}==|[A-Z0-9+/]{3}=)?$', 0),
    ('(?:<script.*?>)([\\s\\S]*?)(?:<\\/script>)', re.IGNORECASE),
    ('^(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$', 0),
    ('\\b(?:\\d{1,3}\\.){3}\\d{1,3}\\b', 0),
    ('[\\w.+-]+@[\\w-]+\\.[\\w.]+', 0),
    ('^(https?|ftp)://[^\\s/$.?#].[^\\s]*$', re.IGNORECASE),
]

def bench_regex_compile(loops, regex_list):
    range_it = range(loops)
    for _ in range_it:
        for regex, flags in regex_list:
            re.purge()
            re.compile(regex, flags)

# Warmup to trigger adaptive JIT
print("Running warmup iterations...", flush=True)
for i in range(5):
    bench_regex_compile(10, regexes)

# Force compile key functions
fns_to_compile = []

# bench function
fns_to_compile.append(("bench_regex_compile", bench_regex_compile))

# sre_compile.compile
try:
    import sre_compile
    fns_to_compile.append(("sre_compile.compile", sre_compile.compile))
except:
    pass

# re._compiler.compile
try:
    import re._compiler
    fns_to_compile.append(("re._compiler.compile", re._compiler.compile))
except:
    pass

# re._parser.parse
try:
    import re._parser
    fns_to_compile.append(("re._parser.parse", re._parser.parse))
except:
    pass

# re._parser.parse (sub functions)
try:
    import re._parser
    # Try some known sub-functions
    if hasattr(re._parser, '_parse'):
        fns_to_compile.append(("re._parser._parse", re._parser._parse))
except:
    pass

# re._compiler._code
try:
    import re._compiler
    if hasattr(re._compiler, '_code'):
        fns_to_compile.append(("re._compiler._code", re._compiler._code))
except:
    pass

for name, fn in fns_to_compile:
    try:
        jit.force_compile(fn)
        print(f"  {name} OK", flush=True)
    except Exception as e:
        print(f"  {name} FAIL: {e}", flush=True)

# Print all compiled functions
compiled = jit.get_compiled_functions()
print(f"\nTotal compiled functions: {len(compiled)}", flush=True)
for func in compiled:
    print(f"  {func}", flush=True)

print(f"\nHIR log written to /tmp/regex_compile_hir_full.log", flush=True)
