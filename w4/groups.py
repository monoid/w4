from collections import deque
import time

HISTORY_SIZE = 10

SESSION_TIMEOUT = 300     # Ten minutes
POLL_TIMEOUT = 120-0.2    # Almost two minutes
GC_PERIOD = 10            # Half minute



class History:
    buf = None
    # Store only particular commands in history.
    # So we do not login and logout images for user privacy.
    cmdFilter = []

    def __init__(self, size=HISTORY_SIZE, hist=()):
        self.buf = deque(hist, size)
        self.cmdFilter = ['say', 'me']

    def message(self, msg):
        if msg['cmd'] in self.cmdFilter:
            self.buf.append(msg)

    def __iter__(self):
        return self.buf.__iter__()


# TODO: group should have an ACL.  Even public group has an ACL where
# its owners are listed.
class Group:
    name = None
    public = True
    channels = None
    history = None
    subject = None

    # Class attribute
    groups = {}

    def __init__(self, name):
        self.name = name
        self.channels = {}
        self.history = History()

        Group.groups[name] = self

    def join(self, chan, nickname):
        if self.public:
            hist = list(self.history)
            if self.subject:
                hist += [{'cmd': 'subject',
                          'group': self.name,
                          'message': self.subject
                         }]
            chan.sendMessages(hist)

            if nickname in self.channels:
                if self.channels[nickname] == chan:
                    # returning user with same nickname.
                    return True
                else:
                    chan.error("Nickname exists.", group=self.name)
                    return False

            # Leave group if the channel have been logged before with
            # different names
            if self.name in chan.groups:
                if chan.groups[self.name] != nickname:
                    self.leave(chan)

            self.channels[nickname] = chan
            chan.groups[self.name] = nickname

            self.broadcast({
                'cmd': 'join',
                'user': nickname
            })
            return True
        else:
            # TODO: check ACL
            chan.error('Access denied', self, group=self.name)
            return False

    def leave(self, chan):
        nickname = chan.groups[self.name]
        if nickname in self.channels:
            self.broadcast({
                'cmd': 'leave',
                'user': nickname
            })
            del self.channels[nickname]
            del chan.groups[self.name]
            return True
        else:
            # TODO exception
            return False

    def broadcast(self, message):
        message['ts'] = int(1000*time.time())
        message['group'] = self.name
        self.history.message(message)
        for chan in self.channels.values():
            chan.sendMessages([message])

    def __getinitargs__(self):
        return self.name,

    def __getstate__(self):
        return {
            'name': self.name,
            'public': self.public,
            'history': list(self.history),
            'subject': self.subject
        }

    def __setstate__(self, state):
        self.name = state['name']
        self.public = state['public']
        self.history = History(hist=state['history'])
        self.subject = state['subject']

    @classmethod
    def saveGroups(cls, outf):
        import pickle
        pickle.dump(cls.groups.values(), outf)

    @classmethod
    def loadGroups(cls, inf):
        import pickle
        groups = pickle.load(inf)
        for group in groups:
            cls.groups[group.name] = group

