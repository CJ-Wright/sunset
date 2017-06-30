import functools as ft
from collections import deque

from streams.core import Stream, no_default
from tornado.locks import Condition

from .streamer import Doc


def star(f):
    @ft.wraps(f)
    def wraps(args):
        return f(*args)

    return wraps


def dstar(f):
    @ft.wraps(f)
    def wraps(kwargs):
        return f(**kwargs)

    return wraps


class EventStream(Stream, Doc):
    def __init__(self, child=None, children=None, output_info=None,
                 input_info=None, **kwargs):
        # TODO: this needs something super maybe a Base Class
        Stream.__init__(self, child, children)
        Doc.__init__(self, output_info, input_info)

    def emit(self, x):
        """ Push data into the stream at this point

        This is typically done only at source Streams but can theortically be
        done at any point
        """
        if x is not None:
            result = []
            for parent in self.parents:
                r = parent.update(x, who=self)
                if type(r) is list:
                    result.extend(r)
                else:
                    result.append(r)
            return [element for element in result if element is not None]


class map(EventStream):
    def __init__(self, func, child, raw=False, output_info=None,
                 input_info=None, **kwargs):
        self.func = func
        self.kwargs = kwargs
        self.raw = raw

        EventStream.__init__(self, child, output_info=output_info,
                             input_info=input_info, **kwargs)
        # TODO: update the provenence now that we have the func

    def update(self, x, who=None):
        # massage the pair(s)
        res = self.dispatch(x)
        # if we are giving back a new doc, just emit it
        if isinstance(res, tuple) and res[0] in ['start', 'descriptor',
                                                 'stop']:
            return self.emit(res)
        try:
            # we need to expose the raw event data
            res = self.event_guts(res)
            if not self.raw and hasattr(x, '__stream_map__'):
                result = x.__stream_map__(self.func, **self.kwargs)
            else:
                result = self.func(res, **self.kwargs)
            # Now we must massage the raw return into a new event
            result = self.issue_event(result)
        except Exception as e:
            result = self.issue_event(e)
        return self.emit(result)


class filter(EventStream):
    def __init__(self, predicate, child, full_event=False, **kwargs):
        self.predicate = predicate

        EventStream.__init__(self, child, **kwargs)
        self.full_event = full_event

    def update(self, x, who=None):
        res = self.dispatch(x)
        # We issue these new docs without filtering
        if isinstance(res, tuple) and res[0] in ['start', 'descriptor',
                                                 'stop']:
            return self.emit(res)
        if not self.full_event:
            res = self.event_guts(res)
        if self.predicate(res):
            return self.emit(x)


class scan(EventStream):
    def __init__(self, func, child, start=no_default, state_key=None,
                 output_info=None,
                 input_info=None):
        self.state_key = state_key
        self.func = func
        self.state = start
        EventStream.__init__(self, child, input_info=input_info,
                             output_info=output_info)

    def update(self, x, who=None):
        res = self.dispatch(x)
        # We issue these new docs without doing anything
        if isinstance(res, tuple) and res[0] in ['start', 'descriptor',
                                                 'stop']:
            return self.emit(res)

        x = self.event_guts(res)
        # TODO: this handling of the initial state is a bit clunky
        # I need to decide if state is going to be the array or the dict
        if self.state is no_default:
            self.state = x
        # in case we need a bit more flexibility eg lambda x: np.empty(x.shape)
        elif hasattr(self.state, '__call__'):
            self.state = self.state(x)
        else:
            if hasattr(x, '__stream_reduce__'):
                result = x.__stream_reduce__(self.func, self.state)
            else:
                x[self.state_key] = self.state
                result = self.func(x)
            self.state = result
        return self.emit(self.issue_event(self.state))


# class partition(EventStream):
#     def __init__(self, n, child):
#         self.n = n
#         self.buffer = []
#         EventStream.__init__(self, child)
#
#     def update(self, x, who=None):
#         self.buffer.append(x)
#         if len(self.buffer) == self.n:
#             result, self.buffer = self.buffer, []
#             return self.emit(tuple(result))
#         else:
#             return []


# class sliding_window(EventStream):
#     def __init__(self, n, child):
#         self.n = n
#         self.buffer = deque(maxlen=n)
#         EventStream.__init__(self, child)
#
#     def update(self, x, who=None):
#         self.buffer.append(x)
#         if len(self.buffer) == self.n:
#             return self.emit(tuple(self.buffer))
#         else:
#             return []


# class timed_window(EventStream):
#     def __init__(self, interval, child, loop=None):
#         self.interval = interval
#         self.buffer = []
#         self.last = gen.moment
#
#         EventStream.__init__(self, child, loop=loop)
#
#         self.loop.add_callback(self.cb)
#
#     def update(self, x, who=None):
#         self.buffer.append(x)
#         return self.last
#
#     @gen.coroutine
#     def cb(self):
#         while True:
#             L, self.buffer = self.buffer, []
#             self.last = self.emit(L)
#             yield self.last
#             yield gen.sleep(self.interval)


# class delay(EventStream):
#     def __init__(self, interval, child, loop=None):
#         self.interval = interval
#         self.queue = Queue()
#
#         EventStream.__init__(self, child, loop=loop)
#
#         self.loop.add_callback(self.cb)
#
#     @gen.coroutine
#     def cb(self):
#         while True:
#             last = time()
#             x = yield self.queue.get()
#             yield self.emit(x)
#             duration = self.interval - (time() - last)
#             if duration > 0:
#                 yield gen.sleep(duration)
#
#     def update(self, x, who=None):
#         return self.queue.put(x)


# class rate_limit(EventStream):
#     def __init__(self, interval, child):
#         self.interval = interval
#         self.next = 0
#
#         EventStream.__init__(self, child)
#
#     @gen.coroutine
#     def update(self, x, who=None):
#         now = time()
#         old_next = self.next
#         self.next = max(now, self.next) + self.interval
#         if now < old_next:
#             yield gen.sleep(old_next - now)
#         yield self.emit(x)


# class buffer(EventStream):
#     def __init__(self, n, child, loop=None):
#         self.queue = Queue(maxsize=n)
#
#         EventStream.__init__(self, child, loop=loop)
#
#         self.loop.add_callback(self.cb)
#
#     def update(self, x, who=None):
#         return self.queue.put(x)
#
#     @gen.coroutine
#     def cb(self):
#         while True:
#             x = yield self.queue.get()
#             yield self.emit(x)


class zip(EventStream):
    def __init__(self, *children, **kwargs):
        self.maxsize = kwargs.pop('maxsize', 10)
        self.buffers = [deque() for _ in children]
        self.condition = Condition()
        self.prior = ()
        EventStream.__init__(self, children=children)

    def update(self, x, who=None):
        L = self.buffers[self.children.index(who)]
        L.append(x)
        if len(L) == 1 and all(self.buffers):
            if self.prior:
                for i in range(len(self.buffers)):
                    # If the docs don't match, preempt with prior good result
                    if self.buffers[i][0][0] != self.buffers[0][0][0]:
                        self.buffers[i].appendleft(self.prior[i])
            tup = tuple(buf.popleft() for buf in self.buffers)
            self.condition.notify_all()
            if tup and hasattr(tup[0], '__stream_merge__'):
                tup = tup[0].__stream_merge__(*tup[1:])
            self.prior = tup
            return self.emit(tup)
        elif len(L) > self.maxsize:
            return self.condition.wait()


class bundle(EventStream):
    def __init__(self, *children, **kwargs):
        self.maxsize = kwargs.pop('maxsize', 100)
        self.buffers = [deque() for _ in children]
        self.condition = Condition()
        self.prior = ()
        EventStream.__init__(self, children=children)

    def update(self, x, who=None):
        L = self.buffers[self.children.index(who)]
        L.append(x)
        if len(L) == 1 and all(self.buffers):
            # if all the docs are of the same type and not an event, issue
            # new documents which are combined
            rvs = []
            while all(self.buffers):
                if all([b[0][0] == self.buffers[0][0][0] and b[0][0] != 'event'
                        for b in self.buffers]):
                    res = self.dispatch(
                        tuple([b.popleft() for b in self.buffers]))
                    rvs.append(self.emit(res))
                elif any([b[0][0] == 'event' for b in self.buffers]):
                    for b in self.buffers:
                        while b:
                            nd_pair = b[0]
                            # run the buffers down until no events are left
                            if nd_pair[0] != 'event':
                                break
                            else:
                                nd_pair = b.popleft()
                                new_nd_pair = self.refresh_event(nd_pair[1])
                                rvs.append(self.emit(new_nd_pair))

                else:
                    raise RuntimeError("There is a mismatch of docs, but none "
                                       "of them are events so we have reached "
                                       "a potential deadlock, so we raise "
                                       "this error instead")

            return rvs
        elif len(L) > self.maxsize:
            return self.condition.wait()


class combine_latest(EventStream):
    def __init__(self, *children, emit_on=None):
        self.last = [None for _ in children]
        self.special_docs_names = ['start', 'descriptor', 'stop']
        self.special_docs = {k: [None for _ in children] for k in
                             self.special_docs_names}
        self.missing = set(children)
        self.special_missing = {k: set(children) for k in
                                self.special_docs_names}
        if emit_on is not None:
            if not hasattr(emit_on, '__iter__'):
                emit_on = (emit_on,)
            self.emit_on = emit_on
        else:
            self.emit_on = children
        Stream.__init__(self, children=children)

    def update(self, x, who=None):
        name, doc = x
        if name in self.special_docs_names:
            idx = self.children.index(who)
            self.special_docs[name][idx] = x
            if self.special_missing[name] and who in \
                    self.special_missing[name]:
                self.special_missing[name].remove(who)

            self.special_docs[name][self.children.index(who)] = x
            if not self.special_missing[name] and who in self.emit_on:
                tup = tuple(self.special_docs[name])
                if tup and hasattr(tup[0], '__stream_merge__'):
                    tup = tup[0].__stream_merge__(*tup[1:])
                return self.emit(tup)
        else:
            if self.missing and who in self.missing:
                self.missing.remove(who)

            self.last[self.children.index(who)] = x
            if not self.missing and who in self.emit_on:
                tup = tuple(self.last)
                if tup and hasattr(tup[0], '__stream_merge__'):
                    tup = tup[0].__stream_merge__(*tup[1:])
                return self.emit(tup)

# class concat(EventStream):
#     def update(self, x, who=None):
#         L = []
#         for item in x:
#             y = self.emit(item)
#             if type(y) is list:
#                 L.extend(y)
#             else:
#                 L.append(y)
#         return L


# class unique(EventStream):
#     def __init__(self, child, history=None, key=identity):
#         self.seen = dict()
#         self.key = key
#         if history:
#             from zict import LRU
#             self.seen = LRU(history, self.seen)
#
#         EventStream.__init__(self, child)
#
#     def update(self, x, who=None):
#         y = self.key(x)
#         if y not in self.seen:
#             self.seen[y] = 1
#             return self.emit(x)


# class union(EventStream):
#     def update(self, x, who=None):
#         return self.emit(x)


# class collect(EventStream):
#     def __init__(self, child, cache=None):
#         if cache is None:
#             cache = deque()
#         self.cache = cache
#
#         EventStream.__init__(self, child)
#
#     def update(self, x, who=None):
#         self.cache.append(x)
#
#     def flush(self, _=None):
#         out = tuple(self.cache)
#         self.emit(out)
#         self.cache.clear()
