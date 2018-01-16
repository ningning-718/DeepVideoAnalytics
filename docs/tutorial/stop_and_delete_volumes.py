#!/usr/bin/env python
import os, requests, subprocess, time, webbrowser

if __name__ == '__main__':
    print "Attempting to stop all containers and deleting volumes."
    try:
        subprocess.check_call(["docker-compose",'down','-v'],
                              cwd=os.path.join(os.path.dirname(__file__),'../../deploy/cpu'))
    except:
        raise SystemError("Could not stop containers")
