"""Isolated browser task runner with a bounded process-tree lifetime."""
import json
import os
import signal
import subprocess
import sys

from .browser_transit import browser_env
from .config import ROOT


def run(module, payload, timeout=35):
    if module != 'marine_agent.browser_ferry_worker':
        raise ValueError('Unsupported browser job')
    process=subprocess.Popen([sys.executable,'-m',module],stdin=subprocess.PIPE,stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,cwd=ROOT,env=browser_env(),text=True,encoding='utf-8',start_new_session=os.name!='nt')
    try:
        stdout,_=process.communicate(json.dumps(payload,ensure_ascii=False),timeout=timeout)
        if process.returncode: raise RuntimeError('Browser job failed')
        return json.loads(stdout)
    except subprocess.TimeoutExpired:
        try:
            if os.name=='nt': subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],capture_output=True,timeout=5)
            else: os.killpg(process.pid,signal.SIGKILL)
        finally:
            process.kill();process.communicate(timeout=5)
        raise
