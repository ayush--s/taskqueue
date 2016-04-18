import sys
import uuid
import redis
import queue
from hashlib import md5
import threading
import dill, types
import requests

import thriftpy
rpc_thrift = thriftpy.load('rpc.thrift', module_name='rpc_thrift')
from thriftpy.rpc import make_server, make_client

redis_ip = '192.168.56.101'
redis_port = 6379
master_ip = '172.16.1.137'
master_port = 9091

from task import Task
rconn = redis.Redis(redis_ip, redis_port)


tq = queue.Queue()  # queue of task objs
pending_queue = {}
workers = []
threads = []


def getint(id):
    try:
        return int(rconn.get(id).decode('utf-8'))
    except AttributeError:
        return None

def getstr(id):
    try:
        return rconn.get(id).decode('utf-8')
    except AttributeError:
        return None


def send(task, ip, port):
    client = make_client(rpc_thrift.RPC, ip, port)
    client.task_service(task)



class Producer:

    def __init__(self, ip, port):
        self.r = rconn
        self.available = False

    def set_available(self):
        self.available = True

    def set_not_available(self):
        self.available = False

    def enqueue(self, work):
        source = work.__code__
        task = Task(source)
        data = dill.dumps(task)
        self.r.set(task.id, 'pending')
        send(data, master_ip, master_port)


class Worker:

    def __init__(self, ip, port):
        self.r = rconn
        self.id = md5((ip+str(port)).encode()).hexdigest()[:8]
        self.ip = ip
        self.port = port
        self.set_available()

    def set_available(self):
        self.r.set(self.id+'.available', '1')

    def set_not_available(self, task_id):
        self.r.set(self.id+'.available', '0')
        self.r.set(self.id+'.current', task_id)

    def is_available(self):
        state = self.r.get(self.id+'.available').decode('utf-8')
        if state == '0':
            return False
        else:
            return True

    def task_service(self, task):
        task = dill.loads(task)
        self.set_not_available(task.id)
        self.work(task)

    def work(self, task):
        self.r.set(task.id, 'running')
        try:
            run = types.FunctionType(task.data, globals(), 'run')
            task.result = run()
            self.r.set(task.id, 'finished')
            self.r.incr(self.id+".count_success")
        except Exception as error_msg:
            print(error_msg, file=sys.stderr)
            self.r.set(task.id, 'failed')
            self.r.incr(self.id+".count_failed")
        self.set_available()
        return task.result


def add_worker(ip, port):
    worker = Worker(ip, port)
    worker.available = True
    workers.append(worker)


def round_robin():
    offset = 0
    while True:
        if workers[offset].is_available():
            worker = workers[offset]
            task = tq.get()
            rconn.incr("output")
            send(task, worker.ip, worker.port)
        offset += 1
        offset = offset % len(workers)


class QueueHandler:

    def task_service(self, task):
        rconn.incr("input")
        tq.put(task)


def listen():
    server = make_server(rpc_thrift.RPC, QueueHandler(), master_ip, master_port)
    server.serve()

def main():
    add_worker('172.16.1.137', 9090)
    round_robin()


# Threading
if __name__ == '__main__':
    main_thread = threading.Thread(target=main)
    threads.append(main_thread)
    main_thread.start()

    listener_thread = threading.Thread(target=listen)
    threads.append(listener_thread)
    listener_thread.start()
