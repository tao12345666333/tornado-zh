#!/bin/sh

set -e

tox

.tox/py27/bin/wstest -m fuzzingserver &
FUZZING_SERVER_PID=$!

sleep 1

.tox/py26/bin/python client.py --name='Tornado/py26'
.tox/py27/bin/python client.py --name='Tornado/py27'
.tox/py32/bin/python client.py --name='Tornado/py32'
.tox/pypy/bin/python client.py --name='Tornado/pypy'

kill $FUZZING_SERVER_PID
wait

echo "Tests complete.  Output is in ./reports/clients/index.html"
