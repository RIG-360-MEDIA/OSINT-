"""Patch /start.sh to fix the LaBSE/torch-in-Celery-prefork deadlock.

Root cause: 4 nlp prefork workers each init torch/sentence-transformers; the
fork + internal thread pools deadlock on first model use (idle-CPU hang).

Fix (belt + suspenders):
  1. Force single-threaded native libs (OMP/OpenBLAS/MKL) + disable tokenizer
     parallelism — removes the threads that deadlock across fork.
  2. Drop the nlp worker --concurrency 4 -> 1 (one process, no fork contention).
"""
PATH = "/start.sh"
s = open(PATH).read()
orig = s

# 1. native-thread env vars right after the shebang
if "OMP_NUM_THREADS" not in s:
    nl = s.index("\n")
    s = (
        s[: nl + 1]
        + "export OMP_NUM_THREADS=1\n"
        + "export OPENBLAS_NUM_THREADS=1\n"
        + "export MKL_NUM_THREADS=1\n"
        + "export TOKENIZERS_PARALLELISM=false\n"
        + s[nl + 1 :]
    )

# 2. nlp worker concurrency 4 -> 1 (target ONLY the nlp block)
s = s.replace("--queues=nlp \\\n  --concurrency=4", "--queues=nlp \\\n  --concurrency=1")

open(PATH, "w").write(s)
print("changed:", s != orig)
print("env_added:", "OMP_NUM_THREADS" in s)
print("nlp_conc1:", "--queues=nlp \\\n  --concurrency=1" in s)
