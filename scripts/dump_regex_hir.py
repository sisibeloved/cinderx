#!/root/.pyenv/versions/3.14.3/bin/python3.14
import os
import sys

# Enable JIT and HIR dump
os.environ['PYTHONJITENABLE'] = '1'
os.environ['PYTHONJITDUMPFINALHIR'] = '1'
os.environ['PYTHONJITLOGFILE'] = '/tmp/regex_compile_hir.log'

import cinderx
cinderx.init()
import cinderx.jit as jit

print("JIT initialized:", cinderx.is_initialized(), flush=True)

import re

# Typical regexes from the benchmark (captured from effbot + v8)
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

# Warm up re.compile path first
for regex, flags in regexes[:3]:
    re.compile(regex, flags)

# Force compile the bench function
print("Force compiling bench_regex_compile...", flush=True)
try:
    jit.force_compile(bench_regex_compile)
    print("Compiled bench_regex_compile!", flush=True)
except Exception as e:
    print(f"Failed to compile bench_regex_compile: {e}", flush=True)

# Also try force compiling key re module functions
import sre_compile
import sre_parse

print("Force compiling sre_compile.compile...", flush=True)
try:
    jit.force_compile(sre_compile.compile)
    print("Compiled sre_compile.compile!", flush=True)
except Exception as e:
    print(f"Failed: {e}", flush=True)

print("Force compiling re.compile wrapper...", flush=True)

def re_compile_wrapper(pattern, flags=0):
    return re.compile(pattern, flags)

try:
    jit.force_compile(re_compile_wrapper)
    print("Compiled re_compile_wrapper!", flush=True)
except Exception as e:
    print(f"Failed: {e}", flush=True)

# Check what functions were actually compiled
compiled = jit.get_compiled_functions()
print(f"\nTotal compiled functions: {len(compiled)}", flush=True)
for func in compiled:
    print(f"  {func}", flush=True)

print(f"\nHIR log written to /tmp/regex_compile_hir.log", flush=True)
