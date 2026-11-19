#!/bin/sh
# The flaky draft test, run the way CI runs it: one process, unittest discover, CI placeholder env.
cd "$(dirname "$0")/../backend"
pass=0
for i in $(seq 1 20); do
  if SECRET_KEY=ci-placeholder-secret-key-0123456789-abcdef ENCRYPTION_KEY=ci-placeholder-encryption-key-0123456789 AUTH_PROVIDER=local \
     .venv/Scripts/python.exe -m unittest discover -s tests -k test_prepared_messages > /tmp/flaky-$i.txt 2>&1; then
    pass=$((pass+1)); echo "run $i: pass ($(grep -o 'Ran [0-9]* tests' /tmp/flaky-$i.txt))"
  else
    echo "run $i: FAIL"; tail -30 /tmp/flaky-$i.txt
  fi
done
echo "passed $pass of 20"
