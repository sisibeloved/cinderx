#!/root/.pyenv/versions/3.14.3/bin/python3.14
import re
import time

regexes = [
    (r'Python|Perl|Java|C#|C\+\+|Go|Rust|Swift|Kotlin', 0),
    (r'[a-z]+@[a-z]+\.[a-z]{2,4}', 0),
    (r'^(?:[A-Z0-9+/]{4})*(?:[A-Z0-9+/]{2}==|[A-Z0-9+/]{3}=)?$', 0),
    (r'(?:<script.*?>)([\s\S]*?)(?:<\/script>)', re.IGNORECASE),
    (r'^(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$', 0),
    (r'\b(?:\d{1,3}\.){3}\d{1,3}\b', 0),
    (r'[\w.+-]+@[\w-]+\.[\w.]+', 0),
    (r'^(https?|ftp)://[^\s/$.?#].[^\s]*$', re.IGNORECASE),
]

def bench_regex_compile(loops, regex_list):
    for _ in range(loops):
        for regex, flags in regex_list:
            re.purge()
            re.compile(regex, flags)

# Warmup
for _ in range(10):
    bench_regex_compile(5, regexes)

# Benchmark
loops = 100
t0 = time.perf_counter()
bench_regex_compile(loops, regexes)
elapsed = time.perf_counter() - t0
print(f"CPython: {loops} loops, {elapsed*1000:.1f} ms total, {elapsed*1000/loops:.3f} ms/loop", flush=True)
