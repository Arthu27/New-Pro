#!/usr/bin/env python3
"""Truly detached background server using os.setsid and explicit close"""
import os
import sys
import time

# Create new session
os.setsid()

# Fork again
pid = os.fork()
if pid > 0:
    print(f"Started daemon PID: {pid}")
    sys.exit(0)

# Now we're the daemon
os.chdir('/home/user/New-Pro')

# Redirect to log
sys.stdin = open('/dev/null', 'r')
log_fd = os.open('/tmp/flask.log', os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
os.dup2(log_fd, 1)
os.dup2(log_fd, 2)

# Exec the server (replaces this process with python3 test_server.py)
os.execvp('python3', ['python3', '/home/user/New-Pro/test_server.py'])
