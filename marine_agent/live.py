"""Bounded in-process live feed. Events contain only allowlisted run/step summaries."""
from collections import deque
import json
import threading
import time
from uuid import uuid4

class LiveFeed:
 def __init__(self,capacity=1024,max_clients=16):
  self.events=deque(maxlen=capacity);self.condition=threading.Condition();self.sequence=0;self.epoch=uuid4().hex;self.clients=0;self.max_clients=max_clients
 def publish(self,event):
  with self.condition:
   self.sequence+=1;self.events.append((self.sequence,event));self.condition.notify_all()
 def acquire(self):
  with self.condition:
   if self.clients>=self.max_clients:return False
   self.clients+=1;return True
 def release(self):
  with self.condition:self.clients=max(0,self.clients-1)
 def cursor(self):
  with self.condition:return self.sequence
 def read(self,cursor,timeout=10):
  with self.condition:
   if self.sequence==cursor:self.condition.wait(timeout)
   gap=bool(self.events and cursor<self.events[0][0]-1)
   return self.sequence,[(seq,e) for seq,e in self.events if seq>cursor],gap
 def encode(self,kind,value,sequence=None):
  return (('id: '+self.epoch+':'+str(sequence)+'\n') if sequence is not None else '')+'event: '+kind+'\ndata: '+json.dumps(value,ensure_ascii=False)+'\n\n'
feed=LiveFeed()
