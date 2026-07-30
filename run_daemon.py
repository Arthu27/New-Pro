#!/usr/bin/env python3
"""Background server starter - fully detaches from parent process"""
import os
import sys
import time

# Double-fork to fully detach
if os.fork() > 0:
    sys.exit(0)
os.setsid()
if os.fork() > 0:
    sys.exit(0)

# Redirect stdio
sys.stdout.flush()
sys.stderr.flush()
with open('/dev/null', 'rb', 0) as f:
    os.dup2(f.fileno(), sys.stdin.fileno())
log = open('/tmp/flask.log', 'ab', 0)
os.dup2(log.fileno(), sys.stdout.fileno())
os.dup2(log.fileno(), sys.stderr.fileno())

# Change to project directory
os.chdir('/home/user/New-Pro')

# Now run the server
os.execvp('python3', ['python3', 'test_server.py'])
