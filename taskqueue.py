import redis
import queue
import thriftpy


redis_ip = "127.0.0.1"
redis_port = 6767
master_ip = "172.16.1.146"
master_port = 9090

tq = queue.Queue()  # queue of task objs

producers = []
workers = []
threads = []


class Producer:

    def __init__(id, ip, port):
        self.r = redis.Redis(host=redis_ip, port=redis_port)
        self.id = id
        self.available = False

    def set_available(self):
        self.available = True

    def set_not_available(self):
        self.available = False

    def enqueue(self, work):
        source = marshal.dumps(work.__code__)
        task = Task(source)
        self.r.set(task.id, "pending")
        send(task, master_ip, master_port)


class Worker:

    def __init__(self, ip, port):
        self.r = redis.Redis(host=redis_ip, port=redis_port)
        # self.id = None
        self.ip = ip
        self.port = port

    def set_available(self):
        self.r.set(self.id+".available", "1")

    def set_not_available(self):
        self.r.set(self.id+".available", "0")

    def is_available(self):
        if self.r.get(self.id+".available") == 0:
            return False
        else:
            return True

    def task_service(self, task):
        task = marshal.loads(task)
        work(task)

    def work(self, task):
        self.r.set(task.id, "running")
        result = None
        try:
            run = types.FunctionType(task.data, globals(), "run")
            result = run()
            self.r.set(task.id, "finished")
        except Exception:
            self.r.set(task.id, "failed")
        return result


def add_producer(ip, port):
    producer_id = md5(ip+port).hexdigest[:6]
    producer = Producer(producer_id, redis_ip, redis_port)
    producer.available = True
    producers.push(producer)


def add_worker(ip, port):
    worker_id = md5(ip+port).hexdigest[:8]
    worker = Worker(worker_id, ip, port)
    worker.available = True
    workers.push(worker)
